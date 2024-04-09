import asyncio
import logging
import numpy as np
import datetime as dt

from enum import Enum
from typing import List, Dict, Set
from numpy.typing import NDArray
from collections import deque
from numpy_ringbuffer import RingBuffer


BUFFER_SIZE = 200
BALANCE_CHANGE_THRESHOLD = 0.05


class InventoryField(Enum):
    QUANTITY = 'qty'
    AVERAGE_PRICE = 'avg_price'
    LEVERAGE = 'leverage'
    DELTA = 'delta'


class Feed:
    def __init__(self, contracts: List = None, max_depth=100, margin=True) -> None:

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

        self._order_books = {contract['symbol']: RingBuffer(capacity=BUFFER_SIZE, dtype=(float, (2 * max_depth, 2)))
                             for contract in self.contracts}
        self._trades = {contract['symbol']: RingBuffer(capacity=BUFFER_SIZE, dtype=(float, 4))
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
        if abs(balance) > BALANCE_CHANGE_THRESHOLD:
            await self.enqueue_symbol_update('Balance')

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

    async def add_trade(self, symbol: str, trade: NDArray) -> None:
        self._trades[symbol].append(trade)
        # Enqueuing symbol is unnecessary for Trades as Klines update per trade
        # await self.enqueue_symbol_update(symbol)

    async def add_kline(self, symbol: str, kline: NDArray) -> None:
        unwrapped_data = self._klines[symbol]._unwrap()
        if unwrapped_data.size > 0 and unwrapped_data[-1][0] == kline[0]:
            self._klines[symbol].pop()
        self._klines[symbol].append(kline)
        await self.enqueue_symbol_update(symbol)

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