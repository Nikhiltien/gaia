import os
import asyncio
import atexit
import signal
import logging
import datetime
import torch

from dotenv import load_dotenv
from src.oms import OMS
from src.feed import Feed
from src.py_streams import Streams
from src.game_env import GameEnv
from src.zeromq.zeromq import ZeroMQ
from src.console import Console
from src.models.tet.tet import DDQN, Agent
from typing import Dict

from src.adapters.HyperLiquid.HyperLiquid_api import HyperLiquid



order = {
    "symbol": "ETH",
    "side": "BUY",
    "price": 3200.0,
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
    "price": 2800.0,
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
    "price": 2500.0,
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
    # logging.info(order_result)
    await asyncio.sleep(5)
    # await adapter.update_leverage(leverage_details=leverage)
    await adapter.place_order(order_details=order)
    # logging.info(resp)
    await asyncio.sleep(65)
    await adapter.place_order(order_details=order2)
    # logging.info(resp2)

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
        await adapter.cancel_order(order_details=cancel)
        # logging.info(cancel_resp)

    await adapter.place_order(order_details=order)
    # logging.info(resp3)
    await asyncio.sleep(55)
    await adapter.place_order(order_details=order2)
    # logging.info(resp4)


class GAIA:
    def __init__(self, feed: Feed) -> None:
        self.logger = logging.getLogger(__name__)

        self.feed = feed
        self.zmq = ZeroMQ()

        self.start_time = datetime.datetime.now(datetime.timezone.utc)

        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

    async def run(self, console=False) -> None:

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
        await adapter.subscribe_all_symbol(self.feed.contracts)
        # order_task = asyncio.create_task(place_orders(adapter))

        model = DDQN()
        try:
            model.load_state_dict(torch.load('models/tet/Tet.pth'))
        except FileNotFoundError:
            print("No previous model found, starting new model.")
        agent = Agent(model)

        self.logger.info(f"Waiting for ready signal...")
        await self._wait_for_confirmation()
        self.logger.info(f"Signal received, starting strategy...")

        tasks = [
            asyncio.create_task(Streams(self.feed, recv_socket).start()),
            asyncio.create_task(GameEnv(self.feed, send_socket, agent, 
                                        default_leverage=5, max_depth=10).start()),
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

    def train_agent(num_episodes, env, agent):
        for episode in range(num_episodes):
            state = env.reset()
            total_reward = 0
            done = False

            while not done:
                action = agent.select_action(state, agent.epsilon)
                next_state, reward, done, _ = env.step(action)
                agent.remember(state, action, reward, next_state, done)
                agent.replay()  # Update the agent's knowledge base
                state = next_state
                total_reward += reward

            print(f"Episode {episode + 1}: Total Reward = {total_reward}")

            # Decay epsilon to reduce exploration over time
            agent.epsilon = max(agent.epsilon * 0.99, 0.01)  # Adjust the decay rate as necessary

            if episode % 10 == 0:
                torch.save(agent.model.state_dict(), 'models/tet/Tet.pth')
                print("Model checkpoint saved.")

            if done:
                break

        print("Training completed.")
        torch.save(agent.model.state_dict(), 'models/tet/Tet.pth')