import atexit
import signal
import asyncio
import time
import logging

from enum import Enum
from typing import List, Dict, Tuple, Any
from src.feed import Feed
from src.zeromq.zeromq import RouterSocket
from src.adapters.base_adapter import Adapter


class OMS():
    def __init__(self, feed: Feed, adapter: Adapter, router: RouterSocket) -> None:
        self.exchange = adapter
        self.feed = feed
        self.router = router

        self.is_running = True
        self.last_order_time = 0
        self.order_cooldown = 5 

        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

    async def run(self):
        await self.router.listen(self._handle_message)

    async def _handle_message(self, topic: str, data: dict) -> None:
        if topic == 'orders':
            await self.place_orders(data)
        elif topic == 'cancel_all':
            await self.cancel_all_orders()
        elif topic == 'cancel':
            await self.cancel_order(data)
        elif topic == 'adjust_leverage':
            await self.set_leverage(data)

    def exit(self):
        pass

    async def place_orders(self, new_orders: List[Tuple[str, float, float]]):
        current_time = time.time()
        if current_time - self.last_order_time < self.order_cooldown:
            logging.info("Order blocked due to rate limiting.")
            return  # Skip placing the order if within cooldown period

        await self.cancel_all_orders() # TODO temporary
        for order in new_orders:
            exchange_order = {
                "symbol": "ETH", # TODO temporary
                "side": order['side'],
                "price": order['price'],
                "qty": order['qty'],
                "reduceOnly": False,
                "orderType": {
                    "limit": {
                        "tif": "Gtc"
                    }
                }
            }
            order = await self.exchange.place_order(exchange_order)
            print(new_orders)
            # print(order)

        self.last_order_time = current_time

    async def cancel_order(self, order: Dict[str, int]):
        await self.exchange.cancel_order(order)

    async def cancel_all_orders(self):
        await self.exchange.cancel_all_orders()

    async def set_leverage(self, leverage: Dict[str, Any]) -> None:
        """
        Expects 'leverage' argument to be a dictionary with:
        - 'symbol' as a string,
        - 'leverage' as a float, and
        - 'is_cross' as a boolean.
        """
        await self.exchange.update_leverage(leverage)
