import logging
import numpy as np
from numpy.typing import NDArray

from typing import List, Dict
from collections import deque
from numpy_ringbuffer import RingBuffer


SEQUENCE_LENGTH = 100


class Feed:
    def __init__(self, contracts: List = None, max_depth=100, margin=True) -> None:
        self.logger = logging.getLogger(__name__)

        self.ready = False
        self.max_depth = max_depth
        self.margin = margin

        self.contracts = [{'symbol': contract} for contract in (contracts or [])]

        self.balances = RingBuffer(capacity=SEQUENCE_LENGTH, dtype=(float, 2))
        self.inventory = {contract['symbol']: {'qty': 0, 'avg_price': 0, 'leverage': 1, 'delta': 0} 
                          for contract in self.contracts}

        self.active_orders = {}
        self.executions = deque(maxlen=100)

        self.order_books = {
            contract['symbol']: RingBuffer(capacity=SEQUENCE_LENGTH, dtype=(float, (2 * max_depth, 2)))
            for contract in self.contracts
        }
        self.trades = {
            contract['symbol']: RingBuffer(capacity=SEQUENCE_LENGTH, dtype=(float, 4))
            for contract in self.contracts
        }
        self.klines = {
            contract['symbol']: RingBuffer(capacity=SEQUENCE_LENGTH, dtype=(float, 6))
            for contract in self.contracts
        }

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