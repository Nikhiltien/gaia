import asyncio
import numpy as np
import datetime as dt

from enum import Enum
from typing import List, Dict, Set
from numpy.typing import NDArray
from collections import deque
from numpy_ringbuffer import RingBuffer
from src.database.db_manager import PGDatabase


BUFFER_SIZE = 200
BALANCE_CHANGE_THRESHOLD = 0.05

contract = {
    "symbol": "ETH",
    "secType": "PERP",
    "exchange": "HYPERLIQUID",
    "currency": "USD"
    }

class InventoryField(Enum):
    QUANTITY = 'qty'
    AVERAGE_PRICE = 'avg_price'
    LEVERAGE = 'leverage'
    DELTA = 'delta'


class Feed:
    def __init__(self, database: PGDatabase = None, contracts: List = None, 
                 max_depth=100, margin=True) -> None:

        self.db = database
        self.queue = asyncio.Queue()
        self._queued_symbols: Set[str] = set()

        self.ready = False
        self.max_depth = max_depth
        self.margin = margin

        self.contracts = [{'symbol': contract} for contract in (contracts or [])]

        self._balances = RingBuffer(capacity=BUFFER_SIZE, dtype=(float, 2))
        self._inventory = {contract['symbol']: {InventoryField.QUANTITY.value: 0, 
                                                InventoryField.AVERAGE_PRICE.value: 0, 
                                                InventoryField.LEVERAGE.value: 1,
                                                InventoryField.DELTA.value: 0} 
                           for contract in self.contracts}
        
        self._active_orders = {}
        self._executions = deque(maxlen=100)

        order_book_dtype = [('timestamp', np.int64), ('data', (float, (2 * max_depth, 2)))]
        self._order_books = {contract['symbol']: RingBuffer(capacity=BUFFER_SIZE, dtype=order_book_dtype)
                                    for contract in self.contracts}
        self._trades = {contract['symbol']: RingBuffer(capacity=BUFFER_SIZE, dtype=(float, 7))
                        for contract in self.contracts}
        self._klines = {contract['symbol']: RingBuffer(capacity=BUFFER_SIZE, dtype=(float, 6))
                        for contract in self.contracts}
    
    @property
    def balances(self):
        return self._balances

    @property
    def last_balance(self):
        if len(self._balances) > 0:
            unwrapped_balances = self._balances._unwrap()
            return unwrapped_balances[-1][1] # [timestamp, balance]
        return 0.0

    @property
    def inventory(self):
        return self._inventory

    @property
    def active_orders(self):
        return self._active_orders
    
    @property
    def executions(self):
        return self._executions
    
    @property
    def order_books(self):
        return self._order_books
    
    @property
    def trades(self):
        return self._trades
    
    @property
    def klines(self):
        return self._klines

    def reset(self):
        self._executions = deque(maxlen=100)
        self.ready = False

    async def enqueue_symbol_update(self, symbol: str) -> None:
        if symbol not in self._queued_symbols:
            await self.queue.put(symbol)
            self._queued_symbols.add(symbol)

    async def peek_symbol_update(self) -> str:
        symbol = await self.queue.get()
        return symbol

    def dequeue_symbol_update(self, symbol: str) -> None:
        if symbol in self._queued_symbols:
            self._queued_symbols.remove(symbol)

    def add_contract(self, contract: str) -> None:
        if contract not in self.inventory:
            self.inventory[contract] = {InventoryField.QUANTITY.value: 0, 
                                                InventoryField.AVERAGE_PRICE.value: 0, 
                                                InventoryField.LEVERAGE.value: 1}
            self.order_books[contract] = RingBuffer(capacity=BUFFER_SIZE, dtype=(float, (2 * self._max_depth, 2)))
            self.trades[contract] = RingBuffer(capacity=BUFFER_SIZE, dtype=(float, 4))
            self.klines[contract] = RingBuffer(capacity=BUFFER_SIZE, dtype=(float, 6))
            self.contracts.append({'symbol': contract})

    async def update_balance(self, cash_diff: float) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        balance = self.last_balance + cash_diff
        self._balances.append(np.array([now.timestamp(), balance]))
        # if abs(balance) > BALANCE_CHANGE_THRESHOLD:
        #     await self.enqueue_symbol_update('Balance')

    async def populate_balance_buffer(self, starting_balance: float) -> None:
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        for _ in range(BUFFER_SIZE):
            self._balances.append(np.array([now, starting_balance]))

    async def update_inventory(self, symbol: str, inventory: Dict):
        self._inventory[symbol].update((k.value if isinstance(k, InventoryField) else k, v) for k, v in inventory.items())
        await self.enqueue_symbol_update('Inventory')

    async def add_order(self, order_id: int, order: Dict):
        self._active_orders[order_id] = order
        await self.enqueue_symbol_update('Orders')

    async def remove_order(self, order_id: int):
        if order_id in self._active_orders:
            del self._active_orders[order_id]
        await self.enqueue_symbol_update('Orders')

    def add_execution(self, execution: List) -> None:
        self.executions.append(execution)

    async def add_orderbook_snapshot(self, symbol: str, book: NDArray) -> None:            
        self._order_books[symbol].append(book)
        await self.enqueue_symbol_update(symbol)

        if self.db:
            await self.db.store_order_book_data(book, contract)

    async def add_trades(self, trades: List[Dict]) -> None:
        for trade in trades:
            symbol = trade['symbol']
            side = trade['side']
            trade_array = (float(trade['timestamp']), side, float(trade['price']), float(trade['qty']))
            self._trades[symbol].append(trade_array)

        if self.db:
            await self.db.store_trade_data(trades, contract)
       
        # await self.enqueue_symbol_update(symbol)

    async def add_trades_custom(self, trades: List[Dict]) -> None:
        symbol = trades[0]['symbol']
        timestamp = float(trades[0]['timestamp'])

        # Initialize aggregation variables
        buy_count, buy_qty_sum, buy_price_qty_sum = 0, 0, 0
        sell_count, sell_qty_sum, sell_price_qty_sum = 0, 0, 0

        # Aggregate trades
        for trade in trades:
            side = trade['side']
            qty = float(trade['qty'])
            price = float(trade['price'])

            if side == 1:
                buy_count += 1
                buy_qty_sum += qty
                buy_price_qty_sum += price * qty
            else:
                sell_count += 1
                sell_qty_sum += qty
                sell_price_qty_sum += price * qty

        # Calculate average prices
        avg_buy_price = buy_price_qty_sum / buy_qty_sum if buy_count > 0 else 0
        avg_sell_price = sell_price_qty_sum / sell_qty_sum if sell_count > 0 else 0

        # Create the aggregated trade summary
        aggregated_trade_data = (timestamp, buy_count, avg_buy_price, buy_qty_sum, sell_count, avg_sell_price, sell_qty_sum)

        # Append to the ring buffer
        self._trades[symbol].append(aggregated_trade_data)
        # await self.enqueue_symbol_update(symbol)

        if self.db:
            await self.db.store_trade_data(trades, contract)

    async def add_kline(self, symbol: str, kline: NDArray) -> None:
        unwrapped = self._klines[symbol]._unwrap()
        last_kline_exists = unwrapped.size > 0  # Check if there are any klines

        # Check if the last kline should be replaced
        if last_kline_exists and unwrapped[-1][0] == kline[0]:
            self._klines[symbol].pop()  # Remove the last kline if it has the same timestamp
            store = False
        else:
            store = True

        self._klines[symbol].append(kline)

        if store and self.db:
            await self.db.store_klines_data(kline, contract)

        # Enqueuing symbol is unnecessary for Trades as Klines update per trade
        # await self.enqueue_symbol_update(symbol)

    @property
    def _order_book_dim(self) -> int:
        # 2 * bid price, bid qty, ask price, ask qty # TODO + 1 spread + 1 imbalance + timestamp?
        return self.max_depth * 2 * 2 # + 1 + 1 + 1

    @property
    def _trades_dim(self) -> int:
        # price, side, qty, timestamp
        return 1 + 1 + 1 + 1

    @property
    def _klines_dim(self) -> int:
        # OHLC, volume, additional features, timestamp
        return 4 + 1 + 0 + 1