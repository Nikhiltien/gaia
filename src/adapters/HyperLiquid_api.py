import json
import random
import asyncio
import logging

from base_adapter import Adapter
from ws_client import WebsocketClient

class HyperLiquid(WebsocketClient, Adapter):
    def __init__(self, ws_name="HyperLiquid", api_key=None, api_secret=None, **kwargs):
        custom_callback = (
            kwargs.pop("callback_function")
            if kwargs.get("callback_function")
            else self._handle_incoming_message
        )
        ws_public_url = "wss://api.hyperliquid.xyz/ws"
        ws_private_url = "https://api.hyperliquid.xyz/exchange"
        url = ws_private_url if api_key and api_secret else ws_public_url
        super().__init__(url=url, ws_name=ws_name, custom_callback=custom_callback, **kwargs)

        self.status = "Disconnected"
        self._msg_loop = None
        self.subscriptions = {}
        self.private_channels = [
            "add_order",
            "cancel_order",
            # ...
        ]

    def start_msg_loop(self):
        self._msg_loop = asyncio.create_task(self._read_msg_task())

    async def _read_msg_task(self):
        try:
            while True:
                await self.recv()
        except asyncio.CancelledError:
            pass

    async def connect(self):
        await super()._connect()
        self.start_msg_loop()

    def _process_subscription_message(self, message):
        data = message.get("data")
        method = data.get("method")

        if method == "subscribe":
            result = data.get("subscription", {})
            symbol = result.get("coin")
            channel = result.get("type")
            self.logger.info(f"Subscription successful for {symbol}, {channel}.")

        elif method == "unsubscribe":
            result = message.get("subscription", {})
            symbol = result.get("coin")
            channel = result.get("type")
            self.logger.info(f"Unsubscription successful for {symbol}, {channel}.")
            # Handle unsubscription logic, like removing from self.subscriptions
            # if req_id in self.subscriptions:
            #     del self.subscriptions[req_id]

    def _process_normal_message(self, message):
        channel = message.get("channel")
        if channel is None:
            self.logger.debug(f"HyperLiquid System Msg: {message}")
        elif "l2Book" in channel:
            self._process_order_book(message)
        elif "trade" in channel:
            self._process_trade(message)
        elif "status" in channel:
            self.logger.info(f"HyperLiquid Status: {message}")
        else:
            self.logger.info(f"Unrecognized channel: {message}")
            pass
            # callback_data = message
        # callback_function = self._get_callback(topic)
        # callback_function(callback_data)

    def _handle_incoming_message(self, message):
        def is_auth_message():
            if (
                message.get("method") == "auth"
                or message.get("type") == "AUTH_RESP"
            ):
                return True
            else:
                return False

        def is_subscription_message():
            if (message.get("channel") == "subscriptionResponse"):
                return True
            else:
                return False

        if is_auth_message():
            self._process_auth_message(message)
        elif is_subscription_message():
            self._process_subscription_message(message)
        else:
            self._process_normal_message(message)


    def _create_subscription_message(self, method, params, req_id=None):
        message = {
            "method": method,
            "subscription": params
        }
        if req_id is not None:
            message["req_id"] = req_id
        return json.dumps(message)

    async def _subscribe_to_topic(self, method, params, req_id=None):
        if req_id is None:
            req_id = random.randint(1, 1e17)

        subscription_message = self._create_subscription_message(method=method, params=params, req_id=req_id)

        self.subscriptions[req_id] = subscription_message
        
        if self.ws:
            try:
                await self.ws.send(subscription_message)
            except Exception as e:
                self.logger.error(f"Error subscribing to {method} channel: {e}")

    async def _unsubscribe_from_topic(self, channel, symbol, req_id=None):
        params = {
            "type": channel,
            "symbol": symbol
        }
        unsubscribe_message = self._create_subscription_message("unsubscribe", params, req_id)
        if self.ws:
            try:
                await self.ws.send(unsubscribe_message)
            except Exception as e:
                self.logger.error(f"Error unsubscribing from {channel} channel: {e}")

    async def subscribe_trades(self, contract, req_id=None):
        symbol = contract.get("symbol")
        params = {
            "type": "trades",
            "coin": symbol
        }
        return await self._subscribe_to_topic(method="subscribe", params=params, req_id=req_id)

    async def subscribe_order_book(self, contract, req_id=None):
        symbol = contract.get("symbol")
        params = {
            "type": "l2Book",
            "coin": symbol
        }
        return await self._subscribe_to_topic(method="subscribe", params=params, req_id=req_id)

    def _process_order_book(self, data):
        book = data.get("data")
        print(f"Book: {book}")

    def _process_trade(self, data):
        trades = data.get("trade")
        print(f"Trades: {trades}")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

eth = {
    "symbol": "ETH",
}

async def main():
    adapter = HyperLiquid()
    await adapter.connect()
    # await adapter.subscribe_trades(contract=eth)
    await adapter.subscribe_order_book(contract=eth)
    await asyncio.sleep(75)

if __name__ == "__main__":
    asyncio.run(main())