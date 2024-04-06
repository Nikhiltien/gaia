import asyncio
import logging
import numpy as np

from src.feed import Feed
from src.zeromq.zeromq import ZeroMQ
from typing import Dict, List, Any


class Streams:
    def __init__(self, feed: Feed, recv_socket: ZeroMQ) -> None:
        self._logger = logging.getLogger(__name__)
        self.feed = feed
        self.recv = recv_socket

        self.topics = {
            'order_book': Order_Book(self.feed).update_book,
            'trades': Trades(self.feed).update_trades,
            'klines': Klines(self.feed).update_klines,
            'inventory': Inventory(self.feed).update_inventory,
            'orders': Orders(self.feed).update_orders,
        }

    async def start(self) -> None:
        await self.recv.listen(self._handle_message)

    def _handle_message(self, topic: str, data: dict) -> None:
        try:
            handler = self.topics[topic]
            handler(data)
        except Exception as e:
            self._logger.error(f"Error: {e}")
            return


class Order_Book:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    def update_book(self, update: Dict[str, List[Any]]) -> None:
        symbol = update['symbol']
        _timestamp = update['timestamp']
        bids = update.get('bids', [])
        asks = update.get('asks', [])

        bids_array = np.array([[float(bid['price']), float(bid['qty'])] for bid in sorted(bids, key=lambda x: -float(x['price']), reverse=True)[:self.feed.max_depth]], dtype=float)
        asks_array = np.array([[float(ask['price']), float(ask['qty'])] for ask in sorted(asks, key=lambda x: float(x['price']))[:self.feed.max_depth]], dtype=float)

        snapshot = np.vstack((bids_array, asks_array))
        self.feed.order_books[symbol].append(snapshot)


class Inventory:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed
        self.topics = {
            'fills': self._process_fills,
            'funding': self._process_funding,
            'leverage': self._process_leverage,
            'liquidation': self._process_liquidations
        }

    def update_inventory(self, update: List) -> None:
        update_type = update['type']
        if update_type in self.topics:
            handler = self.topics[update_type]
            handler(update)
        else:
            logging.error('Data type not supported')

    def _process_fills(self, fill: List):
        self.feed.executions.append(fill)

        # now = dt.datetime.now(dt.timezone.utc)
        # latest_balance = self.feed.balances[-1][1] if self.feed.balances.size > 0 else 0 # ._unwrap()
        # fee = float(fill['fee'])
        # self.feed.balances.append(np.array([now.timestamp(), latest_balance - fee]))

        symbol = fill['symbol']
        qty = float(fill['qty'])
        price = float(fill['price'])
        side = fill['side']

        if symbol not in self.feed.inventory:
            logging.error(f"Symbol not in contract list: {symbol}")
            # self.feed.inventory[symbol] = {'qty': 0, 'avg_price': 0, 'leverage': 0}

        inventory_item = self.feed.inventory[symbol]
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

        self.feed.inventory[symbol] = {'qty': updated_qty, 'avg_price': updated_avg_price, 'leverage': leverage}

    def _process_liquidations(self, liquidations: List) -> None:
        pass

    def _process_leverage(self, leverage: List) -> None:
        pass

    def _process_funding(self, funding: List) -> None:
        pass

class Orders:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    def update_orders(self, update: List) -> None:
        for order in update:
            order_id = order.get('order_id')
            if order.get('status') in ['filled', 'canceled']:
                self.feed.active_orders.pop(order_id, None)
            else:
                current_order = self.feed.active_orders.get(order_id)
                if not current_order or current_order != order:
                    self.feed.active_orders[order_id] = order


class Trades:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    def update_trades(self, update: List):
        for trade in update:
            symbol = trade['symbol']
            side = 1 if trade['side'] == 'B' else -1
            update = (float(trade['price']), side, float(trade['qty']), float(trade['timestamp']))
            self.feed.trades[symbol].append(update)


class Klines:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    def update_klines(self, update: Dict):
        symbol = update['symbol']
        
        kline_array = np.array([
            float(update['open_timestamp']),
            float(update['open']),
            float(update['high']),
            float(update['low']),
            float(update['close']),
            float(update['volume']),
        ], dtype=float)

        unwrapped_data = self.feed.klines[symbol]._unwrap()

        if len(unwrapped_data) > 0 and unwrapped_data[-1][0] != kline_array[0]:
            self.feed.klines[symbol].append(kline_array)
        else:
            if len(self.feed.klines[symbol]) > 0:
                self.feed.klines[symbol].pop()
            self.feed.klines[symbol].append(kline_array)
