import asyncio
import logging
import numpy as np
import datetime as dt

from src.feed import Feed, InventoryField
from src.zeromq.zeromq import SubscriberSocket
from typing import Dict, List, Any


class Streams:
    def __init__(self, feed: Feed, recv_socket: SubscriberSocket) -> None:
        self._logger = logging.getLogger(__name__)
        self.feed = feed
        self.recv = recv_socket

        self.queue = asyncio.Queue()
        self.lock = asyncio.Lock()

        self.topics = {
            'order_book': Order_Book(self.feed).update_book,
            'trades': Trades(self.feed).update_trades,
            'klines': Klines(self.feed).update_klines,
            'inventory': Inventory(self.feed).update_inventory,
            'orders': Orders(self.feed).update_orders,
            'sync': Inventory(self.feed).update_inventory
        }

    async def start(self) -> None:
        await self.recv.listen(self._handle_message)

    async def _handle_message(self, topic: str, data: dict) -> None:
        try:
            handler = self.topics[topic]
            await handler(data)
        except Exception as e:
            self._logger.error(f"Error processing update: {e}, {data}")
            return

class Inventory:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed
        self.topics = {
            'fills': self._process_fills,
            'funding': self._process_funding,
            'leverage': self._process_leverage,
            'liquidation': self._process_liquidations,
            'sync': self._process_sync
        }

    async def update_inventory(self, update: Any) -> None:
        update_type = update['type']
        if update_type in self.topics:
            handler = self.topics[update_type]
            await handler(update)
        else:
            logging.error('Data type not supported')

    async def _process_sync(self, sync: Dict) -> None:
        if not self.feed.ready: # TODO
            cash_balance = sync.get('cash_balance')
            if cash_balance:
                await self.feed.populate_balance_buffer(float(cash_balance))
            
            positions = sync.get('positions')
            if positions:
                for position in positions:
                    try:
                        symbol = position.get('symbol')
                        qty = float(position.get('qty', 0))
                        leverage = float(position.get('leverage', 1))
                        avg_price = float(position.get('avg_price', 0))
                        
                        await self.feed.update_inventory(symbol, {
                            'qty': qty,
                            'avg_price': avg_price,
                            'leverage': leverage
                        })

                    except ValueError:
                        logging.error(f"Invalid format in position data: {position}")

            self.feed.ready = True # TODO
            logging.info('Inventory is synced.')

    async def _process_fills(self, fill: Dict):
        self.feed.executions.append(fill)

        fee = float(fill['fee'])
        pnl = float(fill['closedPnL'])
        await self.feed.update_balance((fee * -1) + pnl)

        symbol = fill['symbol']
        qty = float(fill['qty'])
        price = float(fill['price'])
        side = fill['side']

        if symbol not in self.feed.inventory:
            logging.error(f"Symbol not in contract list: {symbol}")
            return
            # self.feed.inventory[symbol] = {'qty': 0, 'avg_price': 0, 'leverage': 0}

        current_qty = self.feed.inventory[symbol]['qty']
        current_avg_price = self.feed.inventory[symbol]['avg_price']

        if side == 'B':  # Adjust for buy
            updated_qty = current_qty + qty
            if updated_qty != 0:
                updated_avg_price = (current_avg_price * current_qty + price * qty) / updated_qty
            else:
                updated_avg_price = 0  # In case updated_qty results in zero
        else:  # Adjust for sell
            updated_qty = current_qty - qty
            updated_avg_price = current_avg_price  # Average price remains unchanged for sell

        await self.feed.update_inventory(symbol, {
            'qty': updated_qty,
            'avg_price': updated_avg_price
        })

    async def _process_leverage(self, leverage: Dict) -> None:
        symbol = leverage['symbol']
        if leverage['status'] == 'ok':
            if symbol in self.feed.inventory:
                await self.feed.update_inventory(symbol, {
                    InventoryField.LEVERAGE.value: leverage['leverage']
                })
            logging.info(f"Leverage updated for {symbol}: x{leverage['leverage']}")
        else:
            logging.error(f"Unexpected response from API: {leverage}")

    async def _process_liquidations(self, liquidations: List) -> None:
        pass

    async def _process_funding(self, funding: List) -> None:
        pass

class Orders:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    async def update_orders(self, update: List) -> None:
        for order in update:
            order_id = order.get('order_id')

            if order.get('status') in ['filled', 'canceled']:
                await self.feed.remove_order(order_id)
            elif order.get('status') == 'rejected':
                logging.warning(f"Order rejected: {update}")
                return
            else:
                await self.feed.add_order(order_id, order)

class Order_Book:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    async def update_book(self, update: Dict[str, List[Any]]) -> None:
        symbol = update['symbol']
        _timestamp = update['timestamp']
        bids = update.get('bids', [])
        asks = update.get('asks', [])

        bids_array = np.array([[float(bid['price']), 
                                float(bid['qty'])] for bid in sorted(bids, key=lambda x: -float(x['price']), 
                                                  reverse=True)[:self.feed.max_depth]], dtype=float)
        asks_array = np.array([[float(ask['price']), 
                                float(ask['qty'])] for ask in sorted(asks, key=lambda x: float(x['price'])
                                                                     )[:self.feed.max_depth]], dtype=float)

        snapshot = np.vstack((bids_array, asks_array))
        await self.feed.add_orderbook_snapshot(symbol, snapshot)


class Trades:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    async def update_trades(self, update: List):
        for trade in update:
            symbol = trade['symbol']
            side = 1 if trade['side'] == 'B' else 0
            update = (float(trade['timestamp']), side, float(trade['price']), float(trade['qty']))
            await self.feed.add_trade(symbol, update)


class Klines:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    async def update_klines(self, update: Dict):
        symbol = update['symbol']
        
        kline_array = np.array([
            float(update['open_timestamp']),
            float(update['open']),
            float(update['high']),
            float(update['low']),
            float(update['close']),
            float(update['volume']),
        ], dtype=float)

        await self.feed.add_kline(symbol, kline_array)

