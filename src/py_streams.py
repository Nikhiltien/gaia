import asyncio
import logging
import numpy as np

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

            # self.feed.ready = True # TODO
            logging.info('Inventory is synced.')

    async def _process_fills(self, fill: Dict):
        self.feed.executions.append(fill)

        fee = float(fill['fee'])
        pnl = float(fill['closedPnL'])
        await self.feed.update_balance((fee * -1) + pnl)

        symbol = fill['symbol']
        qty = float(fill['qty']) * (-1 if fill['side'] != 'B' else 1)
        price = float(fill['price'])

        logging.info(f"Order filled: {symbol} {'BUY' if qty > 0 else 'SELL'} qty: {abs(qty)} price: {price}")

        if symbol not in self.feed.inventory:
            logging.error(f"Symbol not in contract list: {symbol}")
            return

        current_qty = self.feed.inventory[symbol]['qty']
        current_avg_price = self.feed.inventory[symbol]['avg_price']

        # Initial position or closing a position triggers direct price update.
        if current_qty == 0 or (current_qty + qty) == 0:
            updated_qty = current_qty + qty
            updated_avg_price = price if updated_qty != 0 else 0
        else:
            # Transition from long to short, short to long, or increase in current position
            if (current_qty > 0 and qty > 0) or (current_qty < 0 and qty < 0):  # Increasing position
                updated_qty = current_qty + qty
                updated_avg_price = ((current_avg_price * abs(current_qty)) + (price * abs(qty))) / abs(updated_qty)
            elif abs(qty) > abs(current_qty):  # Flipping position
                updated_qty = current_qty + qty
                updated_avg_price = price  # New position flipped, use new price
            else:  # Decreasing but not flipping
                updated_qty = current_qty + qty
                # Decrease doesn't change avg price, unless flipping which resets above
                updated_avg_price = current_avg_price

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
        timestamp = int(update['timestamp'])
        bids = update.get('bids', [])
        asks = update.get('asks', [])

        bids_array = np.array([[float(bid['price']), 
                                float(bid['qty'])] for bid in sorted(bids, key=lambda x: -float(x['price']), 
                                                  reverse=True)[:self.feed.max_depth]], dtype=float)
        asks_array = np.array([[float(ask['price']), 
                                float(ask['qty'])] for ask in sorted(asks, key=lambda x: float(x['price'])
                                                                     )[:self.feed.max_depth]], dtype=float)

        snapshot = np.vstack((bids_array, asks_array))
        snapshot_with_timestamp = np.array((timestamp, snapshot), dtype=self.feed._order_books[symbol].dtype)
        await self.feed.add_orderbook_snapshot(symbol, snapshot_with_timestamp)


class Trades:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    async def update_trades(self, update: List[Dict]) -> None:
        await self.feed.add_trades_custom(update)


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

