import os
import asyncio

from dotenv import load_dotenv
from src.logger import setup_logger
from src.zeromq.zeromq import ZeroMQ
from src.game_env import GameEnv
from src.adapters.HyperLiquid.HyperLiquid_api import HyperLiquid

eth = {
    "symbol": "ETH",
    "currency": "USD",
    "secType": "PERP",
    "exchange": "HYPERLIQUID",
}

logging = setup_logger(level='INFO', stream=True)

async def main():
    zmq = ZeroMQ()
    pub_socket = zmq.create_publisher(port=50000)

    env_path = os.path.expanduser('~/gaia/keys/private_key.env')
    load_dotenv(dotenv_path=env_path)
    PRIVATE_KEY = os.getenv('PRIVATE_KEY_MAIN')
    public = '0x7195d5fBC22Afa1FF6A0A25591285Db7a81838D4'
    # vault = '0xb22177120b2f33d39770a25993bcb14f2753bae6'

    adapter = HyperLiquid(msg_callback=pub_socket.publish_data)
    await adapter.connect(key=PRIVATE_KEY, public=public) # , vault=vault)

    # await adapter.subscribe_all_symbol([{"symbol": "ETH"}])
    await adapter.subscribe_trades({"symbol": "ETH"})
    await adapter.subscribe_order_book(contract={"symbol": "ETH"}, num_levels=10)

    await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())

# ssh -i /Users/nikhiltien/Gaea/keys/oceanid_rsa root@157.245.123.122