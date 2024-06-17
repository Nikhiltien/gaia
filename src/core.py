import os
import yaml
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
from src.models.tet.tet import DDQN, Agent
from src.database.db_manager import PGDatabase
from typing import Dict

from src.adapters.HyperLiquid.HyperLiquid_api import HyperLiquid


class GAIA:
    def __init__(self, feed: Feed) -> None:
        self.logger = logging.getLogger(__name__)

        # self.api_manager = APIManager()
        self.database = PGDatabase()
        self.feed = feed

        self.start_time = datetime.datetime.now(datetime.timezone.utc)

        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

    async def run(self) -> None:
        config = load_config()

        private_key = config["HyperLiquid"]["key"]
        public = '0x7195d5fBC22Afa1FF6A0A25591285Db7a81838D4'
        vault = '0xb22177120b2f33d39770a25993bcb14f2753bae6'

        await self.database.start(config)
        self.feed.db = self.database

        zmq = ZeroMQ()
        router_socket = zmq.create_subscriber(port=50020, name="")
        send_socket = zmq.create_publisher(port=50020)
        recv_socket = zmq.create_subscriber(port=50000, name="")
        pub_socket = zmq.create_publisher(port=50000)

        adapter = HyperLiquid(msg_callback=pub_socket.publish_data)
        await adapter.connect(key=private_key, public=public) # , vault=vault)
        await adapter.subscribe_all_symbol(contracts=self.feed.contracts, num_levels=self.feed.max_depth)

        model = DDQN()
        try:
            model.load_state_dict(torch.load('src/models/tet/Tet.pth'))
            self.logger.info("Loaded model succesfully.")
        except FileNotFoundError:
            self.logger.info("No previous model found, starting new model.")
        agent = Agent(model)

        self.logger.info(f"Waiting for ready signal...")
        await self._wait_for_confirmation()
        self.logger.info(f"Signal received, starting Gaia...")

        tasks = [
            asyncio.create_task(Streams(self.feed, recv_socket).start()),
            # asyncio.create_task(GameEnv(self.feed, send_socket, agent, 
                                        # default_leverage=5, max_depth=10).start()),
            # asyncio.create_task(OMS(self.feed, adapter, router_socket).run()),
            # asyncio.create_task(APIManager().start()),
            ]

        await asyncio.gather(*tasks)

        self.exit()

    def exit(self) -> None:
        pass

    async def _wait_for_confirmation(self) -> None:
        while True:
            await asyncio.sleep(1)

            # if not self.feed.ready:
            #     continue

            break

    def train_agent(num_episodes, env, agent):
        for episode in range(num_episodes):
            state = env.reset()  # Reset the environment for a new episode
            total_reward = 0
            done = False

            while not done:
                action = agent.select_action(state)
                next_state, reward, done, _ = env.step(action)  # Execute action in the environment
                agent.remember(state, action, reward, next_state, done)  # Store experience in memory
                agent.replay()  # Perform a training step using a batch from the memory

                state = next_state  # Move to the next state
                total_reward += reward  # Accumulate rewards

            logging.info(f"Episode {episode + 1}: Total Reward = {total_reward}")
            agent.epsilon = max(agent.epsilon * agent.epsilon_decay, agent.epsilon_min)  # Decay exploration rate

            if episode % 10 == 0:  # Save model checkpoint periodically
                torch.save(agent.model.state_dict(), 'models/tet/Tet.pth')
                logging.info("Model checkpoint saved.")

        logging.info("Training completed.")
        torch.save(agent.model.state_dict(), 'models/tet/Tet.pth')

def load_config(path: str = 'etc/config.yml') -> Dict:
    with open(path, "r") as f:
        config = yaml.safe_load(f)
        for key in config:
            if 'type' in config[key]:
                key_name = config[key]['type']
                config[key]['key'] = load_keys(key=key_name)
        return config
    
def load_keys(path: str = '~/gaia/keys/private_key.env', key: str = None) -> Dict:
    env_path = os.path.expanduser(path)
    load_dotenv(dotenv_path=env_path)
    return os.getenv(key)