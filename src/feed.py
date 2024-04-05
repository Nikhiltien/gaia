import asyncio
import logging
import datetime
import numpy as np
from numpy.typing import NDArray

from typing import List, Dict
from collections import deque
from src.utils.ring_buffer import RingBufferF64 as RingBuffer


SEQUENCE_LENGTH = 100


class Feed:
    def __init__(self, contracts: List = None, max_depth=100, margin=True) -> None:
        self.logger = logging.getLogger(__name__)

        self.ready = False
        self.max_depth = max_depth
        self.margin = margin

        self.contracts = [{'symbol': contract} for contract in (contracts or [])]

        self.balances = RingBuffer(capacity=SEQUENCE_LENGTH) # , data_type=(float, 2))
        self.inventory = {contract['symbol']: {'qty': 0, 'avg_price': 0, 'leverage': 0, 'delta': 0} 
                          for contract in self.contracts}

        self.active_orders = {}
        self.executions = deque(maxlen=100)

        self.order_books = {
            contract['symbol']: RingBuffer(capacity=SEQUENCE_LENGTH) # , dtype=(float, (2 * max_depth, 2)))
            for contract in self.contracts
        }
        self.trades = {
            contract['symbol']: RingBuffer(capacity=SEQUENCE_LENGTH) # , dtype=(float, self._trades_dim))
            for contract in self.contracts
        }
        self.klines = {
            contract['symbol']: RingBuffer(capacity=SEQUENCE_LENGTH) # , dtype=(float, self._klines_dim))
            for contract in self.contracts
        }
