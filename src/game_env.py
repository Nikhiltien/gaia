import torch
import asyncio
import logging
import numpy as np
import gymnasium as gym

from datetime import datetime, timedelta
from typing import List, Tuple
from numpy.typing import NDArray
from src.feed import Feed
from src.zeromq.zeromq import DealerSocket, PublisherSocket


MAX_STEPS = 25
SEQUENCE_LENGTH = 15


class GameEnv(gym.Env):
    def __init__(self, feed: Feed, send_socket: PublisherSocket,
                 default_leverage=5, max_depth=100, max_drawdown=0, margin=True) -> None:
        self.logger = logging.getLogger(__name__)

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

        while True:
            self.get_status()
            await asyncio.sleep(5)
        
    def get_status(self):
        balances = self.feed.balances._unwrap()
        pnl_1h = self.calculate_pnl_1h()
        active_orders_count = len(self.feed.active_orders)
        executions_1h = self.calculate_executions_1h()
        max_drawdown_1h = self.calculate_max_drawdown_1h()

        status_message = (
            f"\n----- Status -----\n"
            f"Cash: {balances[-1][1] if balances.size > 0 else 0:.2f}\n"
            f"Inventory Value: {self.get_inventory_value()[0]:.2f}\n"
            f"Active Orders: {active_orders_count}\n"
            f"1H PnL: {pnl_1h:.2f}\n"
            f"1H # of Trades: {executions_1h}\n"
            # TODO f"1H Drawdown: {max_drawdown_1h:.2f}\n"
            # TODO "Unrealized PNL"
            # TODO "Account Leverage"
        )

        print(status_message)
        # for contract in self.feed.contracts:
        #      print(f"{contract['symbol']}: {self.get_orders_for_symbol(contract['symbol'])}")
        # print(self.get_orders_for_symbol(symbol for contract['symbol'] in self.feed.contracts))

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

    def calculate_max_drawdown_1h(self):
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

    def get_rnn_data(self):
        balances_array = self.feed.balances._unwrap().flatten()
        
        # Extract inventory values
        inventory_values = np.array([value for _, value in self.get_inventory_value()[1].items()])
        
        # Adjusted iteration over contracts to extract symbol strings
        order_books_array = np.concatenate([self.feed.order_books[contract['symbol']]._unwrap().flatten() for contract in self.feed.contracts])
        klines_array = np.concatenate([self.feed.klines[contract['symbol']]._unwrap().flatten() for contract in self.feed.contracts])
        trades_array = np.concatenate([self.feed.trades[contract['symbol']]._unwrap().flatten() for contract in self.feed.contracts])

        # Concatenate all data into a single array for RNN input
        rnn_input_array = np.concatenate((balances_array, inventory_values, order_books_array, klines_array, trades_array))
        
        return rnn_input_array

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