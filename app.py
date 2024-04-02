import os
import asyncio

from dotenv import load_dotenv
from src.logger import setup_logger
from src.adapters.HyperLiquid.HyperLiquid_api import HyperLiquid

# from src.adapters.HyperLiquid.endpoints import BaseEndpoints
# from src.adapters.post_client import API
# from src.adapters.web3_utils import Authenticator

eth = {
    "symbol": "ETH",
    "currency": "USD",
    "secType": "CRYPTO",
    "exchange": "HYPERLIQUID",
}

order = {
    "symbol": "ETH",  # Assuming an asset index, it should be a number.
    "side": "BUY",  # Boolean should not be in quotes.
    "price": 3200.0,  # This should be a string representing the price.
    "qty": 0.01,  # This is a string representing the size of the order.
    "reduceOnly": False,  # Boolean for whether this is a reduce-only order.
    "orderType": {
        "limit": {
            "tif": "Gtc"  # Assuming you are setting 'Good till cancel' time-in-force.
        }
    }
}

logging = setup_logger(level='INFO', stream=True)

async def main():
    env_path = os.path.expanduser('~/gaia/keys/private_key.env')
    load_dotenv(dotenv_path=env_path)
    PRIVATE_KEY = os.getenv('PRIVATE_KEY_MAIN')
    public = '0x7195d5fBC22Afa1FF6A0A25591285Db7a81838D4'

    adapter = HyperLiquid()
    await adapter.connect(key=PRIVATE_KEY, public=public)

    await adapter.subscribe_notifications()
    await adapter.subscribe_user_events()
    await adapter.subscribe_orders()

    # await adapter.subscribe_trades(contract=eth)
    # await adapter.subscribe_order_book(contract=eth)

    order_result = await adapter.place_order(order_details=order)

    if order_result["status"] == "ok":
        status = order_result["response"]["data"]["statuses"][0]
        if "resting" in status:
            order_status = status["resting"]["oid"]

    cancel = {
        "symbol": "ETH",
        "order_id": order_status
    }

    await asyncio.sleep(5)
    await adapter.cancel_order(order_details=cancel)

    await asyncio.sleep(9999)

if __name__ == "__main__":
    asyncio.run(main())