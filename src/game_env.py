import torch
import random
import asyncio
import logging
import numpy as np
import gymnasium as gym
from gymnasium.spaces import Box, Dict, Discrete, MultiDiscrete, Tuple as gymTuple

from src.models.tet.tet import DDQN, Agent
from datetime import datetime, timedelta
from typing import List, Tuple
from numpy.typing import NDArray
from numpy_ringbuffer import RingBuffer
from src.utils import math
from src.oms import OMS
from src.feed import Feed
from src.zeromq.zeromq import DealerSocket, PublisherSocket


MAX_ORDERS = 20
SEQUENCE_LENGTH = 50
MIN_BUFFER_SIZE = 1


class GameEnv(gym.Env):
    def __init__(self, feed: Feed, send_socket: PublisherSocket, agent: Agent,
                 default_leverage=5, max_depth=100, max_drawdown=0, margin=True) -> None:
        super(GameEnv, self).__init__()
        self.logger = logging.getLogger(__name__)

        self.margin = margin
        self.inital_cash = None
        self.default_leverage = default_leverage
        self.max_depth = max_depth
        self.max_drawdown = max_drawdown

        self.agent = agent
        self.feed = feed
        self.observation_space = Dict({
            'orders': Box(low=-np.inf, high=np.inf, shape=(MAX_ORDERS, 3), dtype=np.float32),
            'inventory': Box(low=-np.inf, high=np.inf, shape=(len(self.feed.contracts), 3), dtype=np.float32),
            'balances': Box(low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32),
            'order_books': Box(low=-np.inf, high=np.inf, shape=(SEQUENCE_LENGTH, self.max_depth * 4), dtype=np.float32),
            'trades': Box(low=-np.inf, high=np.inf, shape=(SEQUENCE_LENGTH, 7), dtype=np.float32),
            'klines': Box(low=-np.inf, high=np.inf, shape=(SEQUENCE_LENGTH, 6), dtype=np.float32),
        })

        self.actions = GameActions(send_socket)
        self.action_space = gymTuple([
            Discrete(self.max_depth * 50),  # Bid actions: 10 price levels * 50 quantity increments
            Discrete(self.max_depth * 50)   # Ask actions: 10 price levels * 50 quantity increments
        ])

        ## Ring buffer holding the environment's states. Each element in the buffer is a tuple structured as follows:
        ##     - orders (array): Current active orders array.
        ##     - inventory (array): Current positions or inventory array.
        ##     - balance (float): Current balance or account equity.
        ##     - symbol_data (list of tuples): Data related to each symbol being traded, structured for each symbol as:
        ##         - order_book (array): Latest snapshot of the order book data.
        ##        - trades (array): Most recent trade data.
        ##         - klines (array): Latest candlestick (klines) data.

        self.state = RingBuffer(capacity=SEQUENCE_LENGTH, dtype=object)
        self.cumulative_reward = 0
        self.ready = False
        self.steps = 0
        self.reset()

    async def start(self):
        self.logger.info(f"Setting leverage to default ({self.default_leverage}) for all symbols.")
        for contract in self.feed.contracts:
            self.actions.adjust_leverage(contract['symbol'], self.default_leverage, True)

        self.logger.info("Cancelling any active orders.")
        self.actions.cancel_all_orders()

        asyncio.create_task(self._monitor_feed_updates())

        await asyncio.sleep(5)

        while True:
            if self.ready:
                self.get_status()
            await asyncio.sleep(30)

    def step(self):
        self.steps += 1
        current_state = self.get_current_state()
        action = self.agent.select_action(current_state)
        next_state, reward, done, info = self.apply_action(action)
        
        # Accumulate reward
        self.cumulative_reward += reward
        
        # Check if the episode should end
        if done is True:
            reward = self.cumulative_reward  # Use accumulated reward
            self.agent.remember(current_state, action, reward, next_state, done)
            self.agent.replay()
            logging.info(f"Episode complete - Total Reward: {reward}")
            self.agent.epsilon = max(self.agent.epsilon * self.agent.epsilon_decay, self.agent.epsilon_min)
            torch.save(self.agent.model.state_dict(), 'src/models/tet/Tet.pth')
            self.reset()
        else:
            self.agent.remember(current_state, action, reward, next_state, done)
            if random.random() < 0.1:
                self.agent.replay()
        
        return next_state, reward, done, info

    def reset(self):
        self.cumulative_reward = 0
        self.steps = 0
        self.state = RingBuffer(capacity=SEQUENCE_LENGTH, dtype=object)
        self.ready = False
        # return self.get_current_state()

    def render(self):
        pass

    def close(self):
        # TODO
        pass

    def calculate_reward(self):
        profit_loss = self.calculate_unrealized_pnl() / 10
        penalty = 0

        return profit_loss - penalty

    def check_if_done(self):
        if self.steps <= 500:
            return False
        return True

    def apply_action(self, action):
        # Decode the normalized actions to actual market orders
        orders = self.decode_action(action)
        
        # Send orders to OMS
        self.actions.place_orders(orders)
        
        # The OMS executes orders and updates market state asynchronously
        # Need to wait or poll for an update to market state
        next_state = self.get_current_state()
        
        # Calculate reward based on the action's market effect
        reward = self.calculate_reward()
        # print(f'Reward calculated: {reward}')
        
        # Check if the trading conditions or other criteria end the episode
        done = self.check_if_done()
        
        # Additional info can be returned for debugging or logging purposes
        info = {'new_orders': orders}
        
        return next_state, reward, done, info

    async def _monitor_feed_updates(self):
        while True:
            if not self.feed.ready:
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

                for data_type, length in all_lengths.items():
                    if length < MIN_BUFFER_SIZE:
                        self.logger.info(f"{data_type} length {length} is below {MIN_BUFFER_SIZE}.")

                if all(length >= MIN_BUFFER_SIZE for length in all_lengths.values()):
                    self.feed.ready = True
                    print("Feed is ready!")
                else:
                    # print(f"~{SEQUENCE_LENGTH - length} minutes until GameEnv is ready.")
                    await asyncio.sleep(10)  # Wait and then check again.
                    continue
            
            if not self.ready:
                if len(self.state) >= SEQUENCE_LENGTH:
                    self.ready = True
                    print("GameEnv is ready!")

            # Process updates only when data is ready.
            update_symbol = await self.feed.peek_symbol_update()

            if update_symbol:
                await self._process_update()
                if self.ready:
                    _, _, _, info = self.step()
                    self.logger.debug(f"Step: {info}")
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

    def get_current_state(self) -> np.ndarray:
        buffer_data = self.state._unwrap()
        concatenated_datas = []
        # Process each state snapshot in the buffer
        for data in buffer_data:
            # Unpack the tuple
            orders, inventory, balance, timestep_data = data

            # Flatten individual arrays
            orders_flat = orders.flatten()
            inventory_flat = inventory.flatten()

            # Process symbol-specific data - flatten each part (order_book, trades, klines)
            symbol_datasets = []
            for symbol_info in timestep_data:
                for dataset in symbol_info:  # order_book, trades, klines
                    symbol_datasets.append(dataset.flatten())
            
            full_flat_array = np.concatenate([orders_flat, inventory_flat, balance] + symbol_datasets)
            concatenated_datas.append(full_flat_array)

        # Convert the list of all timestep data into a numpy 2D array (sequence x features)
        all_data = np.stack(concatenated_datas)

        return all_data

    async def _process_update(self):
        orders_data = self.get_active_orders_array()
        inventory_data = self.get_inventory_array()
        balance_data = self.get_balance_array()

        timestep_data = []
        for contract in self.feed.contracts:
            symbol_data = self._process_symbol_data(contract['symbol'])
            timestep_data.append(symbol_data)

        self.state.append((orders_data, inventory_data, balance_data, timestep_data))

    def _process_symbol_data(self, symbol: str):
        """Processes the data for a given symbol."""
        # Get the most recent data from order books and trades
        order_book_data = self._get_last(self.feed.order_books[symbol])
        trade_data = self._get_last(self.feed.trades[symbol])
        klines_data = self._get_last(self.feed.klines[symbol])

        # Check if trade data is stale
        if trade_data[0] < order_book_data[0]:
            # Use zeros for trade data if stale (preserve the number of columns in trade data)
            trade_data = np.zeros_like(trade_data)
            # Align timestamps
            trade_data[0] = order_book_data[0]
        
        return (order_book_data[1], trade_data, klines_data)

    def decode_action(self, action):
        bid_action, ask_action = action
        bid_price_idx, bid_qty_idx = divmod(bid_action, 50)
        ask_price_idx, ask_qty_idx = divmod(ask_action, 50)

        inventory_value, _ = self.get_inventory_value()
        portfolio_value = self.get_balance() + inventory_value / self.default_leverage
        
        mid_price = self.get_mid_price(self.feed.contracts[0]['symbol'])
        bid_price = mid_price * (1 - 0.01 * bid_price_idx)  # 1% per level for simplicity
        ask_price = mid_price * (1 + 0.01 * ask_price_idx)
        
        max_bid_qty = (portfolio_value / mid_price) * (bid_qty_idx / 49)  # Normalize qty index
        max_ask_qty = (portfolio_value / mid_price) * (ask_qty_idx / 49)
        
        orders = [('BUY', bid_price, max_bid_qty), ('SELL', ask_price, max_ask_qty)]
        return self.format_orders(orders)

    def format_orders(self, orders):
        return [
            {'side': side,
            'price': float(f"{price:.1f}"),  # Formats price to 1 decimal places
            'qty': float(f"{qty:.4f}")}  # Formats qty to 4 decimal places
            for side, price, qty in orders
        ]

    def _get_last(self, data: RingBuffer) -> np.ndarray:
        return data._unwrap()[-1]

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

    def get_orders_for_symbol(self, symbol: str) -> NDArray:
        # Filter active orders by symbol
        filtered_orders = [
             [1 if order["side"] == "BUY" else 0,
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

    def get_active_orders_array(self) -> np.ndarray:
        """Consolidates and pads active orders into a numpy array with fixed dimensions."""
        if self.feed.active_orders:  # Check if there are any active orders
            orders_data = np.array([
                [1 if order['side'] == "BUY" else 0, order['price'], order['qty']]
                for order in self.feed.active_orders.values()
            ], dtype=float)
        else:
            orders_data = np.empty((0, 3), dtype=float)  # Ensure correct shape even if no orders

        # Pad the orders_data to ensure each array has the same length
        padded_orders = np.zeros((MAX_ORDERS, 3), dtype=float)
        actual_length = min(len(orders_data), MAX_ORDERS)
        padded_orders[:actual_length, :] = orders_data[:actual_length]

        return padded_orders

    def get_balance(self):
        balances = self.feed.balances._unwrap()
        return balances[-1][1] if balances.size > 0 else 0

    def get_balance_array(self) -> np.ndarray:
        """Represents balance as a numpy array."""
        balance = self.get_balance()
        return np.array([balance], dtype=float)

    def get_mid_price(self, symbol: str):
        order_book_data = self.feed.order_books[symbol]._unwrap()[-1]
        book = order_book_data[1]

        best_bid_price, best_bid_volume = book[9, 0], book[9, 1]
        best_ask_price, best_ask_volume = book[-10, 0], book[-10, 1]
        
        bba = np.array([[best_bid_price, best_bid_volume], [best_ask_price, best_ask_volume]])

        return math.get_wmid(bba)

    def calculate_unrealized_pnl(self) -> int:
        unrealized_pnl = 0.0
        for symbol, item in self.feed.inventory.items():
            prices = self.feed.klines[symbol]._unwrap()
            if prices.size > 0:
                last_price = prices[-1][4]
                position_value = item['qty'] * last_price
                average_value = item['qty'] * item['avg_price']
                unrealized_pnl += position_value - average_value

        return unrealized_pnl

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
        # TODO
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


class GameActions(gym.Env):
    def __init__(self, socket: PublisherSocket) -> None:
        self.send = socket
        # self.oms = OMS()

    def place_market_order(self, order: Tuple[str, float]):
        pass

    def place_limit_order(self, order: Tuple[str, float, float]):
        pass

    def place_orders(self, orders: List[Tuple[str, float, float]]) -> None:
        self.send.publish_data('orders', orders)

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