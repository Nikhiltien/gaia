import atexit
import signal
import asyncio

from typing import List, Dict, Tuple
from src.feed import Feed
from src.zeromq.zeromq import RouterSocket
from src.adapters.base_adapter import Adapter


class OMS():
    def __init__(self, feed: Feed, adapter: Adapter, router: RouterSocket) -> None:
        self.exchange = adapter
        self.feed = feed
        self.router = router

        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

    def run(self):
        pass

    def exit(self):
        pass

    async def place_orders(self, new_orders: List[Tuple[str, float, float]]):
        print(new_orders)
        pass

    async def cancel_all_orders(self):
        pass

    async def set_leverage(self, leverage: Tuple[str, float, bool]) -> None:
        """
        args: symbol, leverage, cross margin.
        """
        update = {
            'symbol': leverage[0],
            'leverage': leverage[1],
            'is_cross': leverage[2],
        }
        await self.exchange.update_leverage(update)
