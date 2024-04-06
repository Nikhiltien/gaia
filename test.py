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

order = {
    "symbol": "ETH",
    "side": "BUY",
    "price": 3350.0,
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

leverage = {
    "leverage": 50,
    "symbol": "ETH",
    "is_cross": True
}

async def monitor(env):
    while True:
        print(f"inventory: {env.inventory}")
        print(f"orders: {env.active_orders}")
        print(f"executions: {env.executions}")
        print(f"cash: {env.cash}")
        print(f"klines: {env.klines['ETH']}")
        await asyncio.sleep(5)

logging = setup_logger(level='INFO', stream=True)

async def main():
    zmq = ZeroMQ()
    pub_socket, _ = zmq.create_publisher(name="HyperLiquid_publisher")
    sub_socket = zmq.create_subscriber(port=50000, name="gameEnv_subscriber")
    dealer_socket = zmq.create_dealer_socket(identity="gameEnv_dealer")

    env_path = os.path.expanduser('~/gaia/keys/private_key.env')
    load_dotenv(dotenv_path=env_path)
    PRIVATE_KEY = os.getenv('PRIVATE_KEY_MAIN')
    public = '0x7195d5fBC22Afa1FF6A0A25591285Db7a81838D4'
    vault = '0xb22177120b2f33d39770a25993bcb14f2753bae6'

    adapter = HyperLiquid(msg_callback=pub_socket.publish_data)
    await adapter.connect(key=PRIVATE_KEY, public=public) # , vault=vault)

    env = GameEnv(recv_socket=sub_socket, send_socket=dealer_socket, 
                  contracts=["BTC", "ETH", "SOL"], max_depth=10)
    env.initialize()

    await asyncio.sleep(5)
    asyncio.create_task(monitor(env=env))

    # await adapter.subscribe_trades(contract=eth)
    # await adapter.subscribe_order_book(contract=eth)
    await adapter.subscribe_klines(eth, "1m")

    # order_result = await adapter.place_order(order_details=order)
    # await adapter.place_order(order_details=order)

    # cancel = None
    # order_status = None

    # await asyncio.sleep(15)
    # if order_result["status"] == "ok":
    #     status = order_result["response"]["data"]["statuses"][0]
    #     if "resting" in status:
    #         order_status = status["resting"]["oid"]

    #         cancel = {
    #             "symbol": "ETH",
    #             "order_id": order_status
    #         }

    # if cancel:
    #     await adapter.cancel_order(order_details=cancel)

    # await adapter.place_order(order_details=order2)

    await asyncio.sleep(35)

    await adapter.cancel_all_orders()

    # leverage_response = await adapter.update_leverage(leverage)
    # print(leverage_response)

    # b = await adapter.get_user_state()
    # print(b)

    await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())