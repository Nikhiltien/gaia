import torch
import asyncio
import logging
import numpy as np
import gymnasium as gym

# from src.models.tet.tet import Tet
from datetime import datetime, timedelta
from typing import List, Tuple
from numpy.typing import NDArray
from numpy_ringbuffer import RingBuffer
from src.feed import Feed
from src.zeromq.zeromq import DealerSocket, PublisherSocket


MAX_STEPS = 25
SEQUENCE_LENGTH = 3


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

        while True:
            self.get_status()
            await asyncio.sleep(5)

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
                    all_lengths[f'{symbol}_klines'] = klines_length

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
                    await asyncio.sleep(15)  # Wait and then check again.
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
        # drawdown_1h = self.calculate_drawdown_1h()

        status_message = (
            f"\n----- Status -----\n"
            f"Cash: {balances[-1][1] if balances.size > 0 else 0:.2f}\n"
            f"Inventory Value: {self.get_inventory_value()[0]:.2f}\n"
            f"Active Orders: {active_orders_count}\n"
            f"1H PnL: {pnl_1h:.2f}\n"
            f"1H # of Trades: {executions_1h}\n"
            # TODO f"1H Drawdown: {drawdown_1h:.2f}\n"
            # TODO "Unrealized PNL"
            # TODO "Account Leverage"
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
            [order['side'] == 'BUY' and 1 or -1, order['price'], order['qty']]
            for order in self.feed.active_orders.values()
        ]
        return np.array(orders_data, dtype=float) if orders_data else np.empty((0, 3))

    def get_balance_array(self) -> np.ndarray:
        """Represents balance as a numpy array."""
        balance = self.get_balance()
        return np.array([balance], dtype=float)

    def process_symbol_data(self, update_symbol: str):
        """Processes the data for a given symbol."""
        
        order_book_data = self._get_data_sequence(self.feed.order_books[update_symbol])
        trade_data = self._get_data_sequence(self.feed.trades[update_symbol])
        kline_data = self._get_data_sequence(self.feed.klines[update_symbol])

        return self.process_data_with_model(order_book_data, trade_data, kline_data)

    def process_data_with_model(self, order_book_data: np.ndarray, trade_data: np.ndarray, kline_data: np.ndarray) -> np.ndarray:
        """Placeholder function to simulate data processing with ML model."""
        # This function should be replaced with your actual model inference logic.
        # Currently, it just concatenates the data for demonstration purposes.
        return np.concatenate((order_book_data.flatten(), trade_data.flatten(), kline_data.flatten()))


    def calculate_pnl_1h(self):
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        pnl_1h = sum(
            float(fill['closedPnL'])
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

    def get_balance(self):
        balances = self.feed.balances._unwrap()
        return balances[-1][1] if balances.size > 0 else 0
    
    def get_orders_for_symbol(self, symbol: str) -> NDArray:
        # Filter active orders by symbol
        filtered_orders = [
            [order["side"] == "BUY" and 1 or -1,
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