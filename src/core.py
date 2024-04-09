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
from src.console import Console
from typing import Dict

from src.adapters.HyperLiquid.HyperLiquid_api import HyperLiquid



order = {
    "symbol": "ETH",
    "side": "BUY",
    "price": 4000.0,
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
    "price": 3200.0,
    "qty": 0.01,
    "reduceOnly": False,
    "orderType": {
        "limit": {
            "tif": "Gtc"
        }
    }
}

order3 = {
    "symbol": "ETH",
    "side": "BUY",
    "price": 3000.0,
    "qty": 0.005,
    "reduceOnly": False,
    "orderType": {
        "limit": {
            "tif": "Gtc"
        }
    }
}

leverage = {
    "leverage": 50,
    "symbol": "ETH",
    "is_cross": True
}

async def place_orders(adapter: HyperLiquid):

    await asyncio.sleep(5)
    order_result = await adapter.place_order(order_details=order3)
    logging.info(order_result)
    await asyncio.sleep(5)
    # await adapter.update_leverage(leverage_details=leverage)
    resp = await adapter.place_order(order_details=order)
    logging.info(resp)
    await asyncio.sleep(65)
    resp2 = await adapter.place_order(order_details=order2)
    logging.info(resp2)

    await asyncio.sleep(5)
    cancel = None
    order_status = None
    if order_result["status"] == "ok":
        status = order_result["response"]["data"]["statuses"][0]
        if "resting" in status:
            order_status = status["resting"]["oid"]

            cancel = {
                "symbol": "ETH",
                "order_id": order_status
            }

    if cancel:
        cancel_resp = await adapter.cancel_order(order_details=cancel)
        logging.info(cancel_resp)

    resp3 = await adapter.place_order(order_details=order)
    logging.info(resp3)
    await asyncio.sleep(55)
    resp4 = await adapter.place_order(order_details=order2)
    logging.info(resp4)


class GAIA:
    def __init__(self, feed: Feed) -> None:
        self.logger = logging.getLogger(__name__)

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

        router_socket = self.zmq.create_subscriber(port=50020, name="OMS")
        send_socket = self.zmq.create_publisher(port=50020)
        recv_socket = self.zmq.create_subscriber(port=50000, name="Streams")
        pub_socket = self.zmq.create_publisher(port=50000)

        # api_manager = APIManager()
        # adapter = await api_manager.load('HYPERLIQUID')

        adapter = HyperLiquid(msg_callback=pub_socket.publish_data)
        await adapter.connect(key=PRIVATE_KEY, public=public) # , vault=vault)

        await adapter.subscribe_klines({'symbol': 'ETH'}, "1m")
        await adapter.subscribe_order_book({'symbol': 'ETH'})
        await adapter.subscribe_trades({'symbol': 'ETH'})

        order_task = asyncio.create_task(place_orders(adapter))

        self.logger.info(f"Waiting for ready signal...")
        await self._wait_for_confirmation()
        self.logger.info(f"Signal received, starting strategy...")

        tasks = [
            asyncio.create_task(Streams(self.feed, recv_socket).start()),
            asyncio.create_task(GameEnv(self.feed, send_socket, max_depth=10).start()),
            asyncio.create_task(OMS(self.feed, adapter, router_socket).run()),
            # asyncio.create_task(APIManager().start()),
            # asyncio.create_task(Console().start()),
            ]
        
        await asyncio.gather(*tasks)

    def exit(self) -> None:
        pass

    async def load_config(self, path: str = '/etc/config.yml') -> Dict:
        pass

    async def _wait_for_confirmation(self) -> None:
        while True:
            await asyncio.sleep(1)

            # if not self.feed.ready:
            #     continue
            
            break
