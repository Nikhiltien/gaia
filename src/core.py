import os
import asyncio
import atexit
import signal
import logging
import datetime

from dotenv import load_dotenv
from src.oms import OMS
from src.feed import Feed
from src.py_streams import Streams
from src.game_env import GameEnv
from src.zeromq.zeromq import ZeroMQ
from typing import Dict

from src.adapters.HyperLiquid.HyperLiquid_api import HyperLiquid



order = {
    "symbol": "ETH",
    "side": "BUY",
    "price": 3400.0,
    "qty": 0.01,
    "reduceOnly": False,
    "orderType": {
        "limit": {
            "tif": "Gtc"
        }
    }
}

order2 = {
    "symbol": "ETH",
    "side": "SELL",
    "price": 3100.0,
    "qty": 0.01,
    "reduceOnly": False,
    "orderType": {
        "limit": {
            "tif": "Gtc"
        }
    }
}

class GAIA:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed
        self.zmq = ZeroMQ()

        self.start_time = datetime.datetime.now(datetime.timezone.utc)

        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

    async def run(self) -> None:

        env_path = os.path.expanduser('~/gaia/keys/private_key.env')
        load_dotenv(dotenv_path=env_path)
        PRIVATE_KEY = os.getenv('PRIVATE_KEY_MAIN')
        public = '0x7195d5fBC22Afa1FF6A0A25591285Db7a81838D4'
        # vault = '0xb22177120b2f33d39770a25993bcb14f2753bae6'

        recv_socket = self.zmq.create_subscriber(port=50000, name="Streams")
        send_socket = self.zmq.create_dealer_socket(identity="GameEnv")
        pub_socket, _ = self.zmq.create_publisher(name="HyperLiquid_publisher")

        # api_manager = APIManager()
        # adapter = api_manager.load('HYPERLIQUID')

        adapter = HyperLiquid(msg_callback=pub_socket.publish_data)
        await adapter.connect(key=PRIVATE_KEY, public=public) # , vault=vault)
        await adapter.subscribe_klines({'symbol': 'ETH'}, "1m")

        async def place_orders(adapter):
            # Your order placing logic
            # while True:
            await asyncio.sleep(19)
            # Assuming 'order' is defined elsewhere or passed as a parameter
            resp = await adapter.place_order(order_details=order)
            print(resp)
            await asyncio.sleep(10)
            # Assuming 'order2' is defined elsewhere or passed as a parameter
            resp2 = await adapter.place_order(order_details=order2)
            print(resp2)
                # return

        order_task = asyncio.create_task(place_orders(adapter))

        logging.info(f"Waiting for ready signal...")
        await self._wait_for_confirmation()
        logging.info(f"Signal received, starting strategy...")

        tasks = [
            asyncio.create_task(Streams(self.feed, recv_socket).start()),
            asyncio.create_task(GameEnv(self.feed, send_socket).start()),
            # asyncio.create_task(api_manager.start()),
            # asyncio.create_task(OMS(adapter=adapter).start()),
            ]
        
        await asyncio.gather(*tasks)

    def exit(self) -> None:
        pass

    async def load_config(self, path: str = '/etc/config.yml') -> Dict:
        pass

    async def _wait_for_confirmation(self) -> None:
        while True:
            await asyncio.sleep(1)

            if not self.feed.ready:
                continue
            
            break
