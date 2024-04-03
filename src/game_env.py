import torch
import asyncio
import logging
import datetime
import numpy as np

from typing import List
from collections import deque
from numpy_ringbuffer import RingBuffer
from src.models.lob import LOB
from src.zeromq.zeromq import ZeroMQ


MAX_STEPS = 25
MAX_DEPTH = 10
SEQUENCE_LENGTH = 100


class GameEnv:
    def __init__(self, recv_socket: ZeroMQ, send_socket: ZeroMQ, contracts: List = None, 
                 max_depth = 10, max_drawdown = 0) -> None:
        self.logger = logging.getLogger(__name__)

        self.recv = recv_socket
        self.send = send_socket
        self._msg_loop = None

        self.max_depth = max_depth
        self.max_drawdown = max_drawdown
        self.margin = True
        self.inital_cash = None

        self.state = {}
        self.ready = False

        self.step = 0
        self.cash = 0
        self.inventory = []
        self.inventory_delta = 0
        self.inventory_vol = 0
        self.active_orders = {}
        self.executions = deque(maxlen=100)

        self.contracts = [{'symbol': contract} for contract in (contracts or [])]
        
        self.order_books = {
            contract['symbol']: RingBuffer(capacity=SEQUENCE_LENGTH, dtype=(float, self._order_book_dim))
            for contract in self.contracts
        }
        self.trades = {
            contract['symbol']: RingBuffer(capacity=SEQUENCE_LENGTH, dtype=(float, self._trades_dim))
            for contract in self.contracts
        }
        self.klines = {
            contract['symbol']: RingBuffer(capacity=SEQUENCE_LENGTH, dtype=(float, self._klines_dim))
            for contract in self.contracts
        }

    def initialize(self):
        self._msg_loop = asyncio.create_task(self._start_msg_loop())
        
    async def _start_msg_loop(self):
        while True:
            topic, message = await self.recv.listen()
            if message:
                self._handle_message(topic, message)

    def _handle_message(self, topic: str, data: dict):
        if topic not in ['order_book', 'trades', 'kline', 'account', 'orders', 'fills', 'liquidations']:
            self.logger.error(f"Unknown data type: {topic}")
            return

        # Update the game environment based on the topic
        if topic == 'order_book':
            symbol = data['symbol']
            self.order_books[symbol].append(data)
        elif topic == 'trades':
            for trade in data:
                symbol = trade['symbol']
                formatted_trade = self._process_trade(trade)
                self.trades[symbol].append(formatted_trade)
        elif topic == 'kline':
            symbol = data['symbol']
            self.klines[symbol].append(data)
        elif topic == 'account':
            self._process_account(data)
        elif topic == 'orders':
            self._process_orders(data)
        elif topic == 'fills':
            self._process_fills(data)
        elif topic == 'liquidations':
            self._process_liquidations(data)
        else:
            self.logger.error(f"Unhandled data type: {topic}")

        # Update game state based on new data
        # self.update_game_state()

    def _process_account(self, data):
        self.cash = float(data.get('balance', 0))

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
    
    def _process_fills(self, data):
        # Update executions and inventory from filled orders
        for fill in data.get('fills', []):
            self.executions.append(fill)
            if fill.get('side') == 'buy':
                self.inventory.append((fill.get('qty'), fill.get('price')))
            elif fill.get('side') == 'sell':
                # Remove from inventory or adjust quantity. Implement based on your logic.
                pass
    
    def _process_liquidations(self, data):
        # Handle liquidation events, possibly adjusting game state or ending episode
        # For example, you might reset the environment if your position is liquidated
        if data.get('liquidated', False):
            self.logger.info('Liquidation event occurred')

    @staticmethod
    def _process_trade(trade):
        side = 1 if trade['side'] == 'B' else -1
        return (float(trade['price']), side, float(trade['qty']), float(trade['timestamp']))

    @property
    def _order_book_dim(self) -> int:
        # 2 * bid price, bid qty, ask price, ask qty + 1 spread + 1 imbalance
        return self.max_depth * 2 * 2 + 1 + 1

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


class GameActions:
    @property
    def start(self):
        return 0




# class GameEnv:
#     def __init__(self, oms, socket: ZeroMQ, contracts: List = None, max_depth = 10, 
#                  initial_cash = None, initial_inventory = None, cache = None):
#         super().__init__()
#         self.logger = logging.getLogger(__name__)
#         self.oms = oms
#         self.receiver = socket
#         self.cache = cache
#         self.initial_cash = initial_cash if initial_cash is not None else 10_000
#         self.initial_inventory = initial_inventory if initial_inventory is not None else 0
#         self.max_depth = max_depth

#         # State components
#         self.subscriber = None # updates state
#         self.agent_callback = None # updates agent
#         self.states = {} # RingBuffer of states = SEQUENCE_LENGTH

#         self.contracts = contracts or []
#         self.cash = initial_cash
#         self.margin = False
#         self.inventory = initial_inventory
#         self.inventory_delta = 0
#         self.volatility_value = 0
#         self.order_books = {}
        
#         self.klines = RingBuffer(capacity=500, dtype=(float, 7))
#         self.trades = RingBuffer(capacity=1000, dtype=(float, 4))
#         self.active_orders = []
#         self.executions = deque(maxlen=100)
#         self.current_step = 0

#     @property
#     def state_dim(self):
#         # 1 (time) + 1 (cash) + 1 (inventory) + 1 (weighted midprice) + (2 * max_depth * 2) (order book)
#         return 1 + 1 + 1 + 1 + 2 * self.max_depth * 2

#     @property
#     def action_dim(self):
#         return 6  # Define more if there are additional actions

#     def is_symbol_done(self, symbol):
#         # Example logic: a symbol is considered done if its state sequence reaches a certain length
#         # or you might have more specific logic based on your game's rules
#         return len(self.states[symbol]) >= MAX_STEPS

#     def get_state_sequence(self, symbol):
#         state_sequence = np.array(self.states[symbol])
#         return torch.tensor(state_sequence[np.newaxis, :, :], dtype=torch.float)

#     async def _initialize_states(self):
#         for contract in self.contracts:
#             symbol = contract['symbol']
#             self.states[symbol] = RingBuffer(capacity=SEQUENCE_LENGTH, dtype=(float, self.state_dim))

#             order_book_data = await self.cache.fetch_latest_order_book(contract)
#             self.order_books[symbol] = LOB(order_book_data)

#             self.states[symbol].append(self._get_state(symbol))
        
#         # initialize state updates
#         if self.subscriber is None:
#             self.subscriber = self.cache.start_subscriber(self.update_order_book_callback)

#     def _get_state(self, symbol):
#         # Extract state components from the order book and other attributes
#         lob = self.order_books.get(symbol, LOB(np.zeros((0, 2))))
#         weighted_midprice = lob.weighted_midprice
#         bids_flattened = lob.bids.flatten() if hasattr(lob, 'bids') else np.zeros(self.max_depth * 2)
#         asks_flattened = lob.asks.flatten() if hasattr(lob, 'asks') else np.zeros(self.max_depth * 2)
#         normalized_time = self._get_normalized_time()

#         return np.concatenate([np.array([normalized_time, self.cash, self.inventory, weighted_midprice]), bids_flattened, asks_flattened])

#     @staticmethod
#     def _get_normalized_time():
#         # Normalize current time into a daily slot for state representation
#         current_utc_time = datetime.datetime.now(datetime.timezone.utc)
#         minutes_since_midnight = current_utc_time.hour * 60 + current_utc_time.minute
#         slot_of_the_day = minutes_since_midnight // 30
#         return slot_of_the_day / 47.0

#     async def reset(self):
#         # Reset the environment to its initial state
#         self.states = {}
#         self.subscriber = None
#         self.agent_callback = None
#         self.order_books = {}
#         self.active_orders = []
#         self.cash = self.initial_cash
#         self.inventory = self.initial_inventory
#         self.current_step = 0
#         await self._initialize_states()

#     async def update_order_book(self, contract_symbol, order_book_data):
#         if contract_symbol in self.order_books:
#             updated_lob = LOB(order_book_data)
#             self.order_books[contract_symbol] = updated_lob
#             self.states[contract_symbol].append(self._get_state(contract_symbol))

#             if self.agent_callback and len(self.states[contract_symbol]) >= SEQUENCE_LENGTH:
#                 await self.agent_callback(contract_symbol)
#             else:
#                 self.logger.debug(f"Waiting for buffer for {contract_symbol} to fill...")

#     async def update_order_book_callback(self, message):
#         channel_parts = message['channel'].split(':')
#         if len(channel_parts) == 5:
#             _, _, _, exchange, symbol_currency = channel_parts
#             symbol, currency = symbol_currency.split('/')
#             contract = {'exchange': exchange, 'symbol': symbol, 'secType': 'CRYPTO', 'currency': currency}

#             try:
#                 order_book_data = await self.cache.fetch_latest_order_book(contract)
#                 await self.update_order_book(symbol, order_book_data)
#             except Exception as e:
#                 self.logger.error(f"Error updating order book for {symbol}: {e}")

#     async def apply_action(self, symbol, action):
#         match action:
#             case 0:
#                 await self.place_order(symbol, 'buy', 'limit')
#             case 1:
#                 await self.place_order(symbol, 'sell', 'limit')
#             case 2:
#                 await self.place_order(symbol, 'buy', 'market')
#             case 3:
#                 await self.place_order(symbol, 'sell', 'market')
#             case 4:
#                 await self.cancel_order(symbol, 'buy')
#             case 5:
#                 await self.cancel_order(symbol, 'sell')

#     async def place_order(self, symbol, order_type, order_kind):
#         # Detailed implementation to place a market or limit order.
#         # For limit orders, you'd need to define how the limit price is determined.
#         # For market orders, you execute at the best available price.
#         print(f"Placing a {order_kind} {order_type} order for {symbol}")

#     async def cancel_order(self, symbol, order_type):
#         # Detailed implementation to cancel an existing order.
#         # This might involve identifying the specific order to cancel.
#         print(f"Cancelling a {order_type} order for {symbol}")