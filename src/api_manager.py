import os
import time
import asyncio
import json
import logging
import hashlib
import importlib.util
from pathlib import Path
from enum import Enum
from abc import abstractmethod, ABC
from src.adapters import base_adapter
from src.zeromq.zeromq import ZeroMQ
from typing import Dict, Any, List

adapters_dir = Path('src/adapters')

class AdapterStatus(Enum):
    CONNECTED = 'Connected'
    DISCONNECTED = 'Disconnected'
    ERROR = 'Error'

class Adapter(ABC):
    _register = []

    def __init__(self, a_id: int, config: Dict, msg_callback=None):
        self._adapter_id = a_id
        self._config = config
        self._status = AdapterStatus.DISCONNECTED
        self._status_callback = None
        self._last_request_time = None
        self._subscribed_tickers = set()

        self.rate_limit = {call_type: TokenBucket(*values) 
                              for call_type, values in self._config.get('rate_limit').items()}
        self.metrics = AdapterMetrics()
        self.msg_callback = msg_callback
        
        self._register.append(self._adapter_id)

    @property
    def adapter_id(self) -> int:
        return self._adapter_id

    @property
    def config(self) -> Dict:
        return self._config

    @property
    def status(self) -> AdapterStatus:
        return self._status

    @status.setter
    def status(self, status: AdapterStatus) -> None:
        name_id = f"{self.__qualname__}: {self._adapter_id}"
        if status != self._status:
            self._status = status
            if self._status_callback:
                self._status_callback(name_id, self.status)

    def set_status_callback(self, callback: Any):
        self._status_callback = callback

    def _on_api_start(self):
        self.status = AdapterStatus.CONNECTED

    def _on_api_end(self):
        self.status = AdapterStatus.DISCONNECTED

    def _on_api_error(self):
        self.status = AdapterStatus.ERROR

    @property
    def rate_limit(self):
        return self.rate_limit.copy()

    def _request(self, request_type):
        rate_limiter = self.rate_limit.get(request_type)
        if rate_limiter:
            with rate_limiter:
                self._last_request_time = time.time()
        else:
            pass

    @abstractmethod
    def connect(self):
        raise NotImplementedError()

    @abstractmethod
    def disconnect(self):
        raise NotImplementedError()

    @property
    def subscribed_tickers(self):
        return frozenset(self._subscribed_tickers)

    @abstractmethod
    def subscribe_trades(self, ticker):
        self._subscribed_tickers.add(ticker)

    @abstractmethod
    def unsubscribe_trades(self, ticker):
        if ticker in self._subscribed_tickers:
            self._subscribed_tickers.discard(ticker)

    @abstractmethod
    def subscribe_order_book(self, ticker):
        self._subscribed_tickers.add(ticker)

    @abstractmethod
    def unsubscribe_order_book(self, ticker):
        if ticker in self._subscribed_tickers:
            self._subscribed_tickers.discard(ticker)

    @abstractmethod
    def subscribe_klines(self, ticker, startTime, endTime, interval):
        self._subscribed_tickers.add(ticker)
    
    @abstractmethod
    def unsubscribe_klines(self, ticker):
        if ticker in self._subscribed_tickers:
            self._subscribed_tickers.discard(ticker)

class AdapterMetrics:
    def __init__(self):

        self.request_count = 0
        self.error_count = 0
        self.response_time_ms = 0

    def log_request(self):
        self.request_count += 1

    def log_error(self):
        self.error_count += 1

    def update_connection_metrics(self, response_time_ms):
        self.response_time_ms = response_time_ms

class TokenBucket:
    def __init__(self, capacity, fill_rate):

        self.capacity = capacity
        self._tokens = capacity
        self.fill_rate = fill_rate
        self.timestamp = time.time()

    def consume(self, tokens=1):
        now = time.time()
        self._tokens += (now - self.timestamp) * self.fill_rate
        self._tokens = min(self._tokens, self.capacity)
        self.timestamp = now

        if tokens <= self._tokens:
            self._tokens -= tokens
            return True
        return False

class AdapterFactory:
    def __init__(self):
        self.zmq = ZeroMQ()
        self._pool = {}

    def register_adapters(self, adapter_class):
        # Register adapter class without initializing
        self._uninitialized_adapters.append(adapter_class)

    def initialize_adapters(self, config: Dict):
        for adapter_class in self._uninitialized_adapters:
            adapter_id = self._generate_id(adapter_class, config)
            if adapter_id not in self._pool:
                adapter = adapter_class(adapter_id, config)
                self._pool[adapter_id] = adapter

    @staticmethod
    def _generate_id(adapter_class, config: Dict):
        # Generates a unique identifier based on the adapter class and configuration
        combined = {'label': adapter_class.__name__, **config}
        config_str = json.dumps(combined, sort_keys=True)
        adapter_id = hashlib.md5(config_str.encode()).hexdigest()
        return adapter_id[:12]
        
    def close(self):
        self.pool.clear()
        self.zmq.close_all()


class APIManager:
    def __init__(self) -> None:
        self.factory = AdapterFactory()

        self.logger = logging.getLogger(__name__)

    def create_adapter(self, adapter_class):
        return self.factory.create_adapter(adapter_class, self.config)
    
    def load_adapters(self, config):
        adapters_dir = Path('src/adapters')
        for filepath in adapters_dir.rglob('*_api.py'):  # Recursively find all *_api.py files
            module_name = filepath.stem  # Get the module name without the .py extension
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # Assuming each module has a class Adapter inheriting from Adapter base class
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, Adapter) and attr is not Adapter:
                    # Initialize the adapter with configuration and register it
                    self.create_adapter(attr, config)

    def get_adapter_by_id(self, adapter_id):
        return self.factory._pool.get(adapter_id)
    
    def get_adapter_by_source(self, source):
        for _, adapter in self.factory._pool.items():
            if adapter.__name__ == source:
                return adapter
        
        self.logger.error(f"No adapter found for {source}.")
        return None

    def remove_adapter(self, adapter_id):
        if adapter_id in self.adapters:
            del self.adapters[adapter_id]
