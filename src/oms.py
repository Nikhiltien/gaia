import atexit
import signal
import asyncio

from typing import List, Dict, Tuple
from src.feed import Feed
from src.zeromq.zeromq import RouterSocket
from src.adapters.base_adapter import Adapter

class OMS():
    def __init__(self, router: RouterSocket, adapter: Adapter, feed: Feed) -> None:
        self.router = router
        self.exchange = adapter
        self.feed = feed

        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

    def run(self):
        pass

    def exit(self):
        pass

    def place_orders(self, new_orders: List[Tuple[str, float, float]]) -> Dict:
        print(new_orders)
        pass

    def cancel_all_orders(self):
        pass