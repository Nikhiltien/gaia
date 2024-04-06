import torch
import asyncio
import logging
import numpy as np
import gymnasium as gym

from typing import List, Tuple
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

        for contract in self.feed.contracts:
            self.actions.adjust_leverage(contract['symbol'], self.default_leverage, True)

        while True:
            balances = self.feed.balances._unwrap()
            print(f"Status \nCash: {balances[-1][1] if balances.size > 0 else 0} \nInventory: {self.get_inventory_value()}")
            # print(f"Active Orders: {self.feed.active_orders}, Executions: {self.feed.executions}")
            # print(f"RNN Dim: {self.get_rnn_data().shape}")
            await asyncio.sleep(15)
        
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