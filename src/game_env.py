import torch
import asyncio
import logging
import numpy as np
import gymnasium as gym

# from src.models.tet.tet import Tet
from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from numpy.typing import NDArray
from numpy_ringbuffer import RingBuffer
from src.utils import math
from src.feed import Feed
from src.zeromq.zeromq import DealerSocket, PublisherSocket


MAX_STEPS = 25
SEQUENCE_LENGTH = 10


class GameEnv(gym.Env):
    def __init__(self, feed: Feed, send_socket: PublisherSocket,
                 default_leverage=5, max_depth=100, max_drawdown=0, margin=True) -> None:
        self.logger = logging.getLogger(__name__)

        # self.model = model
        self.feed = feed
        self.actions = GameActions(send_socket)

        self.margin = margin
        self.inital_cash = None
        self.default_leverage = default_leverage
        self.max_depth = max_depth
        self.max_drawdown = max_drawdown

        self.state = {}
        self.ready = False

        self.step = 0

    async def start(self):
        self.logger.info(f"Setting leverage to default ({self.default_leverage}) for all symbols.")
        for contract in self.feed.contracts:
            self.actions.adjust_leverage(contract['symbol'], self.default_leverage, True)

        self.logger.info("Cancelling any active orders.")
        self.actions.cancel_all_orders()

        asyncio.create_task(self.monitor_feed_updates())

        await asyncio.sleep(5)

        while True:
            self.get_status()
            await asyncio.sleep(30)

    async def monitor_feed_updates(self):
        while True:
            if not self.ready:
                all_lengths = {}
                # Iterate over order books, trades, and klines for each contract to check their lengths.
                for contract in self.feed.contracts:
                    symbol = contract['symbol']
                    order_books_length = len(self.feed.order_books[symbol]._unwrap())
                    trades_length = len(self.feed.trades[symbol]._unwrap())
                    klines_length = len(self.feed.klines[symbol]._unwrap())

                    all_lengths[f'{symbol}_order_books'] = order_books_length
                    all_lengths[f'{symbol}_trades'] = trades_length
                    # all_lengths[f'{symbol}_klines'] = klines_length

                # Also check the length of balances.
                balances_length = len(self.feed.balances._unwrap())
                all_lengths['balances'] = balances_length

                # Log the lengths.
                for data_type, length in all_lengths.items():
                    if length < SEQUENCE_LENGTH:
                        self.logger.info(f"{data_type} length {length} is below the required SEQUENCE_LENGTH {SEQUENCE_LENGTH}.")

                # Check if all data types across all symbols have sufficient data.
                if all(length >= SEQUENCE_LENGTH for length in all_lengths.values()):
                    self.ready = True
                    self.logger.info("GameEnv is ready!")
                else:
                    # print(f"~{SEQUENCE_LENGTH - length} minutes until GameEnv is ready.")
                    await asyncio.sleep(30)  # Wait and then check again.
                    continue
            
            # Process updates only when data is ready.
            update_symbol = await self.feed.peek_symbol_update()

            if update_symbol == "Orders":
                orders_data = self.get_active_orders_array()
                # self.logger.info(f"Orders Array: {orders_data.shape}")
            elif update_symbol == "Inventory":
                inventory_data = self.get_inventory_array()
                # self.logger.info(f"Inventory Array: {inventory_data.shape}")
            elif update_symbol == "Balance":
                balance_data = self.get_balance_array()
                # self.logger.info(f"Balances Array: {balance_data.shape}")
            else:
                symbol_data = self.process_symbol_data(update_symbol)
                # self.logger.info(f"Symbol Array: {symbol_data.shape}")

            # self.logger.info(f"Acknowledged update for: {update_symbol}")
            self.feed.dequeue_symbol_update(update_symbol)

    def get_status(self):
        balances = self.feed.balances._unwrap()
        pnl_1h = self.calculate_pnl_1h()
        active_orders_count = len(self.feed.active_orders)
        executions_1h = self.calculate_executions_1h()
        unrealized_pnl = self.calculate_unrealized_pnl()
        # drawdown_1h = self.calculate_drawdown_1h()

        status_message = (
            f"\n----- Status -----\n"
            f"Cash: {balances[-1][1] if balances.size > 0 else 0:.2f}\n"
            f"Inventory Value: {self.get_inventory_value()[0]:.2f}\n"
            f"Active Orders: {active_orders_count}\n"
            f"Unrealized PnL: {unrealized_pnl:.2f}\n"
            f"1H PnL: {pnl_1h:.2f}\n"
            f"1H # of Trades: {executions_1h}\n"
            # TODO f"1H Drawdown: {drawdown_1h:.2f}\n"
            # TODO "Unrealized PNL"
            # TODO "Account Leverage"
            f"------------------\n"
        )

        print(status_message)
        # for contract in self.feed.contracts:
        #      print(f"{contract['symbol']}: {self.get_orders_for_symbol(contract['symbol'])}")
        # print(self.get_orders_for_symbol(symbol for contract['symbol'] in self.feed.contracts))

    def _get_data_sequence(self, data: RingBuffer) -> np.ndarray:
        """Extract the last SEQUENCE_LENGTH records from the data."""
        data_seq = data._unwrap()
        if len(data_seq) < SEQUENCE_LENGTH:
            self.logger.warning(f"Not enough data for sequence length: {len(data_seq) - SEQUENCE_LENGTH}")
            return
        else:
            final_data = data_seq[-SEQUENCE_LENGTH:]
        return final_data
    
    def _get_snapshot(self, data: RingBuffer) -> np.ndarray:
        unwrapped = data._unwrap()
        return unwrapped[-1]

    def get_inventory_array(self) -> np.ndarray:
        """Converts inventory data into a numpy array."""
        inventory_data = [
            [item['qty'], item['avg_price'], item['leverage']]
            for _, item in self.feed.inventory.items()
        ]
        return np.array(inventory_data, dtype=float)

    def get_active_orders_array(self) -> np.ndarray:
        """Consolidates active orders into a numpy array."""
        # Flatten the order details across all symbols into a single array
        orders_data = [
            [order['side'] == 'BUY' and 1 or 0, order['price'], order['qty']]
            for order in self.feed.active_orders.values()
        ]
        return np.array(orders_data, dtype=float) if orders_data else np.empty((0, 3))

    def get_balance_array(self) -> np.ndarray:
        """Represents balance as a numpy array."""
        balance = self.get_balance()
        return np.array([balance], dtype=float)

    def align_trade_data(self, order_book_data: np.ndarray, trade_data: np.ndarray) -> np.ndarray:
        # Extract and convert order book timestamps to datetime64 for comparison
        order_book_timestamps = np.array([np.datetime64(entry['timestamp']) for entry in order_book_data], dtype='datetime64[ms]')
        
        # Prepare for data alignment
        expanded_trade_data = []
        trade_timestamps = trade_data[:, 0].astype('datetime64[ms]')

        print(f"Order book timestamps: {order_book_timestamps}")
        print(f"Trade timestamps: {trade_timestamps}")
        
        # Align trade data with order book timestamps
        for ob_timestamp in order_book_timestamps:
            idx = np.where(trade_timestamps == ob_timestamp)[0]
            
            if idx.size == 0:  # If no matching timestamp found, insert zero data row
                self.logger.info('Found misaligned timestamp.')
                zero_data_row = np.zeros(trade_data.shape[1])
                zero_data_row[0] = ob_timestamp.astype('float64')  # Keep timestamp
                expanded_trade_data.append(zero_data_row)
        
        # Combine and sort the trade data if expanded data exists
        if expanded_trade_data:
            expanded_trade_data_array = np.array(expanded_trade_data)
            final_trades = np.vstack((trade_data, expanded_trade_data_array))
            final_trades = final_trades[np.argsort(final_trades[:, 0])]  # Sort by timestamp
        else:
            final_trades = trade_data
        
        # Print the full array without truncation
        np.set_printoptions(suppress=True, precision=3, threshold=np.inf, linewidth=200)
        print("Final aligned and sorted trade data:")
        print(final_trades)
        
        return final_trades

    def process_symbol_data(self, update_symbol: str):
        """Processes the data for a given symbol."""
        order_book_data = self._get_data_sequence(self.feed.order_books[update_symbol])
        trade_data = self._get_data_sequence(self.feed.trades[update_symbol])

        # Align the trade data with the order book data timestamps.
        aligned_trade_data = self.align_trade_data(order_book_data, trade_data)
        # print(aligned_trade_data)

        # # Convert the last order book timestamp to a readable UTC format.
        # ob_last_timestamp = datetime.fromtimestamp(order_book_data[-1][0].astype('O') / 1e3, tz=timezone.utc)
        # print(f"Last Order Book Timestamp in UTC: {ob_last_timestamp}")

        # # For each entry in aligned trade data, convert the timestamp to a readable UTC format and print.
        # print("Aligned Trade Data Timestamps in UTC:")
        # for row in aligned_trade_data:
        #     trade_timestamp = datetime.fromtimestamp(row[0] / 1e3, tz=timezone.utc)
        #     print(f"Trade Timestamp in UTC: {trade_timestamp}")

        return order_book_data[-SEQUENCE_LENGTH:], aligned_trade_data

    def process_data_with_model(self, order_book_data: np.ndarray, trade_data: np.ndarray, kline_data: np.ndarray) -> np.ndarray:
        """Placeholder function to simulate data processing with ML model."""

        # sync_data = self.synchronize_data(trade_data, order_book_data)
        # print(order_book_data[-1])
        # print(trade_data[-1])
        # print(sync_data)
        # best_bid_price, best_bid_volume = order_book_data[9, 0], order_book_data[9, 1]
        # best_ask_price, best_ask_volume = order_book_data[-10, 0], order_book_data[-10, 1]
        
        # bba = np.array([[best_bid_price, best_bid_volume], [best_ask_price, best_ask_volume]])

        # trades_imbalance = math.trades_imbalance(trades=trade_data , window=SEQUENCE_LENGTH)
        # weighted_mid_price = math.get_wmid(bba)
        # print(trades_imbalance)

        return np.concatenate((order_book_data[-1][1].flatten(), trade_data.flatten(), kline_data.flatten()))

    def calculate_pnl_1h(self):
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        pnl_1h = sum(
            float(fill['closedPnL']) - float(fill.get('fee', 0))
            for fill in self.feed.executions
            if one_hour_ago <= datetime.fromtimestamp(fill['timestamp'] / 1000.0) <= now
        )
        return pnl_1h

    def calculate_executions_1h(self):
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        executions_1h = sum(
            1 for execution in self.feed.executions
            if one_hour_ago <= datetime.fromtimestamp(execution['timestamp'] / 1000.0) <= now
        )
        return executions_1h

    def calculate_drawdown_1h(self):
        # Assuming you have some logic to calculate or retrieve drawdown
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        drawdowns = [
            # You'll need to replace this logic with actual drawdown calculation
            np.random.uniform(-5, 0)  # Placeholder: replace with your logic
            for _ in range(60)  # Assuming one value per minute, replace as necessary
            if one_hour_ago <= now - timedelta(minutes=1) * _ <= now
        ]
        max_drawdown_1h = min(drawdowns) if drawdowns else 0
        return max_drawdown_1h

    def calculate_unrealized_pnl(self):
        unrealized_pnl = 0.0
        for symbol, item in self.feed.inventory.items():
            prices = self.feed.klines[symbol]._unwrap()
            if prices.size > 0:
                last_price = prices[-1][4]
                position_value = item['qty'] * last_price
                average_value = item['qty'] * item['avg_price']
                unrealized_pnl += position_value - average_value

        return unrealized_pnl

    def get_inventory_value(self) -> Tuple[float, dict]:
        total_value, individual_values = 0.0, {}
        for symbol, item in self.feed.inventory.items():
            prices = self.feed.klines[symbol]._unwrap()
            if prices.size > 0:
                last_price = prices[-1][4]  # Assuming the closing price as the last price.
                position_value = item['qty'] * last_price * item['leverage']
                individual_values[symbol] = position_value
                total_value += position_value
        return total_value / item['leverage'], individual_values

    def get_mid_price(self, symbol: str):
        order_book_data = self.feed.order_books[symbol]._unwrap()[-1]

        best_bid_price, best_bid_volume = order_book_data[9, 0], order_book_data[9, 1]
        best_ask_price, best_ask_volume = order_book_data[-10, 0], order_book_data[-10, 1]
        
        bba = np.array([[best_bid_price, best_bid_volume], [best_ask_price, best_ask_volume]])

        return math.get_wmid(bba)

    def get_balance(self):
        balances = self.feed.balances._unwrap()
        return balances[-1][1] if balances.size > 0 else 0
    
    def get_orders_for_symbol(self, symbol: str) -> NDArray:
        # Filter active orders by symbol
        filtered_orders = [
            [order["side"] == "BUY" and 1 or 0,
             order["price"],
             order["qty"],
             # order["timestamp"]
             ] 
            for order in self.feed.active_orders.values() if order["symbol"] == symbol
        ]
        
        # If there are no orders for the symbol, return an empty array with the correct shape
        if not filtered_orders:
            return np.empty((0, 3))
        
        # Convert the list to a numpy array
        order_array = np.array(filtered_orders, dtype=float)
        
        return order_array

    def step(self):
        pass

    def reset(self):
        pass


class GameActions(gym.Env):
    def __init__(self, socket: PublisherSocket) -> None:
        self.send = socket

    def adjust_leverage(self, symbol: str, leverage: float, cross_margin: bool = True) -> None:
        update = {
            'symbol': symbol,
            'leverage': leverage,
            'cross_margin': cross_margin
        }

        self.send.publish_data('adjust_leverage', update)

    def cancel_order(self, symbol: str, order_id: int) -> None:
        update = {
            'symbol': symbol,
            'order_id': order_id
        }

        self.send.publish_data('cancel', update)

    def cancel_all_orders(self) -> None:
        update = {'type': 'cancel_all'}
        self.send.publish_data('cancel_all', update)