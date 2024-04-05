import asyncio
import atexit
import signal
import logging
import datetime

from src.oms import OMS
from src.feed import Feed
from src.py_streams import Streams
from src.game_env import GameEnv
from src.zeromq.zeromq import ZeroMQ
from typing import Dict


class GAIA:
    def __init__(self, feed: Feed) -> None:
        self.feed = feed
        self.zmq = ZeroMQ()

        self.start_time = datetime.datetime.now(datetime.timezone.utc)

        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

    async def run(self) -> None:

        logging.info(f"{datetime.datetime.now(datetime.timezone.utc)}: Waiting for ready signal...")
        await self._wait_for_confirmation()
        logging.info(f"{datetime.datetime.now(datetime.timezone.utc)}: Starting strategy...")

        recv_socket = self.zmq.create_subscriber(50000)
        send_socket = self.zmq.create_dealer_socket(identity="GameEnv")

        # api_manager = APIManager()
        # adapter = api_manager.load('HYPERLIQUID')

        tasks = [
            asyncio.create_task(Streams(self.feed, recv_socket).start()),
            asyncio.create_task(GameEnv(self.feed, send_socket, margin=True).start()),
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
