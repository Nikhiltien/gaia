import json
import random
import asyncio
import logging

from base_adapter import Adapter
from ws_client import WebsocketClient

class HyperLiquid(WebsocketClient, Adapter):
    def __init__(self, ws_name="HyperLiquid", api_key=None, api_secret=None, **kwargs):
        custom_callback = (self._handle_incoming_message)
        url = "wss://api.hyperliquid.xyz/ws"
        super().__init__(url=url, ws_name=ws_name, custom_callback=custom_callback, **kwargs)

        self._msg_loop = None
        self.subscriptions = {}

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

    def _handle_incoming_message(self, message):
        channel = message.get('channel')
        if channel == 'subscriptionResponse':
            self._process_subscription_message(message)
        elif channel == 'notification':
            self._process_notification(message.get('data'))
        elif channel == 'user':
            self._process_user_event(message.get('data'))
        elif channel == 'pong':
            return
        else:
            self._process_normal_message(message)

    def _process_subscription_message(self, message):
        data = message.get("data")
        method = data.get("method")

        if method == "subscribe":
            result = data.get("subscription", {})
            symbol = result.get("coin")
            channel = result.get("type")
            self.logger.info(f"Subscription successful for {channel}: {symbol if symbol else ''}")

        elif method == "unsubscribe":
            result = message.get("subscription", {})
            symbol = result.get("coin")
            channel = result.get("type")
            self.logger.info(f"Unsubscription successful for {channel}: {symbol if symbol else ''}")
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
        elif "orderUpdate" in channel:
            self._process_orders(message)
        else:
            self.logger.info(f"Unrecognized channel: {message}")
            pass
            # callback_data = message
        # callback_function = self._get_callback(topic)
        # callback_function(callback_data)

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

        subscription_message = self._create_subscription_message(method=method, params=params)

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

    async def subscribe_notifications(self, user_address, req_id=None):
        params = {
            "type": "notification", 
            "user": user_address
            }
        await self._subscribe_to_topic(method="subscribe", params=params, req_id=req_id)

    async def subscribe_user_events(self, user_address, req_id=None):
        params = {
            "type": "userEvents", 
            "user": user_address
            }
        await self._subscribe_to_topic(method="subscribe", params=params, req_id=req_id)

    async def subscribe_orders(self, user_address, req_id=None):
        params = {
            "type": "orderUpdates",
            "user": user_address
            }
        await self._subscribe_to_topic(method="subscribe", params=params, req_id=req_id)

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

    def _process_notification(self, data):
        # Process and log notification data
        print(f"Notification: {data}")

    def _process_user_event(self, data):
        # Process user event data
        print(f"User Event: {data}")

    def _process_orders(self, data):
        # Process user event data
        print(f"orderEvent: {data}")

    def _process_order_book(self, data):
        book = data.get("data")
        print(f"Book: {book}")

    def _process_trade(self, data):
        trades = data.get("data")
        print(f"Trades: {trades}")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

eth = {
    "symbol": "ETH",
}

async def main():
    adapter = HyperLiquid()
    await adapter.connect()

    wallet = '0x7195d5fBC22Afa1FF6A0A25591285Db7a81838D4'

    await adapter.subscribe_notifications(user_address=wallet)
    await adapter.subscribe_user_events(user_address=wallet)
    await adapter.subscribe_orders(user_address=wallet)
    # await adapter.subscribe_trades(contract=eth)
    # await adapter.subscribe_order_book(contract=eth)
    await asyncio.sleep(9999)

if __name__ == "__main__":
    asyncio.run(main())