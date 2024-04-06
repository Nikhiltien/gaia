import torch
import asyncio
import logging
import datetime
import numpy as np
import gymnasium as gym

from typing import List, Tuple
from src.feed import Feed
from src.zeromq.zeromq import DealerSocket


MAX_STEPS = 25
MAX_DEPTH = 10
SEQUENCE_LENGTH = 100


class GameEnv(gym.Env):
    def __init__(self, feed: Feed, send_socket: DealerSocket,
                 max_depth=100, max_drawdown=0, margin=True) -> None:
        self.logger = logging.getLogger(__name__)

        self.feed = feed
        self.send = send_socket

        self.max_depth = max_depth
        self.max_drawdown = max_drawdown
        self.margin = margin
        self.inital_cash = None

        self.state = {}
        self.ready = False

        self.step = 0

    async def start(self):
        while True:
            balances = self.feed.balances._unwrap()
            print(f"Status \nCash: {balances[-1][1] if balances.size > 0 else 0} \nInventory: {self.get_inventory_value()}")
            await asyncio.sleep(15)
        
    def get_inventory_value(self) -> Tuple[float, float]:
        total_value = 0.0
        individual_values = {}

        for symbol, inventory_item in self.feed.inventory.items():
            prices = self.feed.klines[symbol]._unwrap()
            if prices.size > 0:
                last_price = prices[-1][4]
                # Calculate the value of the individual position
                position_value = inventory_item['qty'] * last_price * inventory_item['leverage']
                individual_values[symbol] = position_value

                # Add to the total inventory value
                total_value += position_value

        return total_value, individual_values

    async def update_leverage(self, symbol: str, leverage: int, is_cross: bool = True):
        leverage_update_msg = {
            "action": "update_leverage",
            "symbol": symbol,
            "leverage": leverage,
            "is_cross": is_cross
        }

        await self.send.send(leverage_update_msg)

        if symbol in self.inventory:
            self.inventory[symbol]['leverage'] = leverage
        else:
            self.inventory[symbol] = {
                'qty': 0,
                'avg_price': 0,
                'leverage': leverage
            }

        self.logger.info(f"Leverage updated for {symbol}: {leverage}")

    def step(self):
        pass

    def reset(self):
        pass


class GameActions():
    @property
    def start(self):
        return 0