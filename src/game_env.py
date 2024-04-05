import torch
import asyncio
import logging
import datetime
import numpy as np
import gymnasium as gym

from typing import List
from src.feed import Feed
from src.zeromq.zeromq import ZeroMQ


MAX_STEPS = 25
MAX_DEPTH = 10
SEQUENCE_LENGTH = 100


class GameEnv(gym.Env):
    def __init__(self, feed: Feed, send_socket: ZeroMQ,
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
            print(f"Status: {self.feed.inventory}")
            await asyncio.sleep(15)
        
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

    def _process_account(self, data):
        cash = float(data.get('cash_balance', None))
        if cash:
            self.cash = cash

        if 'positions' in data and data['positions']:
            new_inventory = {}

            for position in data['positions']:
                symbol = position['symbol']
                qty = float(position['qty'])
                leverage = float(position['leverage'])
                avg_price = float(position['avg_price'])
                if qty != 0:
                    new_inventory[symbol] = {'qty': qty, 'avg_price': avg_price, 'leverage': leverage}
            self.inventory = new_inventory

    def _process_orders(self, data):
        for order in data:
            order_id = order.get('order_id')
            # Check if the order should be removed.
            if order.get('status') in ['filled', 'canceled']:
                self.active_orders.pop(order_id, None)  # Removes order if it exists, does nothing otherwise.
            else:
                current_order = self.active_orders.get(order_id)
                if not current_order or current_order != order:
                    self.active_orders[order_id] = order

    def _process_fills(self, fill):
        # Append fill record to executions.
        self.executions.append(fill)

        # Deduct the fee from cash.
        fee = float(fill['fee'])
        self.cash -= fee

        symbol = fill['symbol']
        qty = float(fill['qty'])
        price = float(fill['price'])
        side = fill['side']

        if symbol not in self.inventory:
            self.inventory[symbol] = {'qty': 0, 'avg_price': 0, 'leverage': 0}

        inventory_item = self.inventory[symbol]
        current_qty = inventory_item['qty']
        current_avg_price = inventory_item['avg_price']
        leverage = inventory_item['leverage'] or 0

        if side == 'B':  # Adjust for buy
            updated_qty = current_qty + qty
            if updated_qty != 0:
                updated_avg_price = (current_avg_price * current_qty + price * qty) / updated_qty
            else:
                updated_avg_price = 0  # In case updated_qty results in zero
        else:  # Adjust for sell
            updated_qty = current_qty - qty
            updated_avg_price = current_avg_price  # Average price remains unchanged for sell

        self.inventory[symbol] = {'qty': updated_qty, 'avg_price': updated_avg_price, 'leverage': leverage}

    def _process_account(self, data):
        self.cash = float(data.get('cash_balance', 0))

        if 'positions' in data and data['positions']:
            new_inventory = {}

            for position in data['positions']:
                symbol = position['symbol']
                qty = float(position['qty'])
                avg_price = float(position['avg_price'])  # Confirm this key exists and is correct.

                # Only add the position to the new inventory if the quantity is non-zero.
                if qty != 0:
                    new_inventory[symbol] = {'qty': qty, 'avg_price': avg_price}

            # Update the inventory only if there are positions.
            self.inventory = new_inventory
    
    def _process_liquidations(self, data):
        # Handle liquidation events, possibly adjusting game state or ending episode
        # For example, you might reset the environment if your position is liquidated
        if data.get('liquidated', False):
            self.logger.info('Liquidation event occurred')

    @staticmethod
    def _process_trade(trade):
        side = 1 if trade['side'] == 'B' else -1
        return (float(trade['price']), side, float(trade['qty']), float(trade['timestamp']))

    def _process_order_book(self, order_book_data: dict):
        symbol = order_book_data['symbol']
        bids = order_book_data.get('bids', [])
        asks = order_book_data.get('asks', [])

        bids_array = np.array([[float(bid['price']), float(bid['qty'])] for bid in sorted(bids, reverse=True, key=lambda x: -float(x['price']))[:self.max_depth]], dtype=float)
        asks_array = np.array([[float(ask['price']), float(ask['qty'])] for ask in sorted(asks, key=lambda x: float(x['price']))[:self.max_depth]], dtype=float)

        order_book_snapshot = np.vstack((bids_array, asks_array))
        self.order_books[symbol].append(order_book_snapshot)

    def _process_kline(self, kline):
        symbol = kline['symbol']
        
        kline_array = np.array([
            float(kline['open_timestamp']),
            float(kline['open']),
            float(kline['high']),
            float(kline['low']),
            float(kline['close']),
            float(kline['volume']),
        ], dtype=float)

        unwrapped_data = self.klines[symbol]._unwrap()

        if len(unwrapped_data) > 0 and unwrapped_data[-1][0] != kline_array[0]:
            self.klines[symbol].append(kline_array)
        else:
            if len(self.klines[symbol]) > 0:
                self.klines[symbol].pop()
            self.klines[symbol].append(kline_array)

    @property
    def _order_book_dim(self) -> int:
        # 2 * bid price, bid qty, ask price, ask qty + 1 spread + 1 imbalance
        return self.max_depth * 2 * 2 # + 1 + 1

    @property
    def _trades_dim(self) -> int:
        # price, side, qty, timestamp
        return 1 + 1 + 1 + 1

    @property
    def _klines_dim(self) -> int:
        # OHLC, volume, additional features, timestamp
        return 4 + 1 + 0 + 1

    def step(self):
        pass

    def reset(self):
        pass


class GameActions():
    @property
    def start(self):
        return 0