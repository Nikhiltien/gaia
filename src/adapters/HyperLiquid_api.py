import json
import random
import asyncio
import logging

from typing import List, Dict
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
        self.logger.info(f"Connected to HyperLiquid.")

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
        elif "orderUpdates" in channel:
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
        notification = data.get("notification")
        print(f"Notification: {notification}")

    def _process_user_event(self, data):
        parsed_events = []
        if 'fills' in data:
            for fill in data['fills']:
                parsed_event = {
                    "eventType": "Fill",
                    "coin": fill.get('coin'),
                    "price": fill.get('px'),
                    "size": fill.get('sz'),
                    "side": fill.get('side'),
                    "time": fill.get('time'),
                    "startPosition": fill.get('startPosition'),
                    "direction": fill.get('dir'),
                    "closedPnL": fill.get('closedPnl'),
                    "hash": fill.get('hash'),
                    "orderID": fill.get('oid'),
                    "crossed": fill.get('crossed'),
                    "fee": fill.get('fee'),
                    "tradeID": fill.get('tid'),
                    "feeToken": fill.get('feeToken')
                }
                parsed_events.append(parsed_event)

        if 'liquidation' in data:
            liquidation = data['liquidation']
            parsed_event = {
                "eventType": "Liquidation",
                "liquidationID": liquidation.get('lid'),
                "liquidator": liquidation.get('liquidator'),
                "liquidatedUser": liquidation.get('liquidated_user'),
                "netLossPosition": liquidation.get('liquidated_ntl_pos'),
                "accountValue": liquidation.get('liquidated_account_value')
            }
            parsed_events.append(parsed_event)

        if 'nonUserCancel' in data:
            for cancel in data['nonUserCancel']:
                parsed_event = {
                    "eventType": "NonUserCancel",
                    "coin": cancel.get('coin'),
                    "orderID": cancel.get('oid')
                }
                parsed_events.append(parsed_event)

        print(f"User Events: {parsed_events}")

    def _process_orders(self, data):
        order_updates = data.get('data', [])
        parsed_orders = []
        for order_data in order_updates:  # Iterating through the list of order updates
            order = order_data.get('order', {})
            parsed_order = {
                "coin": order.get('coin'),
                "side": order.get('side') == 'B' and "buy" or "sell",
                "limitPrice": order.get('limitPx'),
                "size": order.get('sz'),
                "orderID": order.get('oid'),
                "timestamp": order.get('timestamp'),
                "originalSize": order.get('origSz'),
                "reduceOnly": order.get('reduceOnly', False),
                "status": order_data.get('status'),
                "statusTimestamp": order_data.get('statusTimestamp')
            }
            parsed_orders.append(parsed_order)
        print(f"Order Events: {parsed_orders}")

    def _process_order_book(self, data):
        book = data.get("data", {}).get("levels", [])
        if len(book) == 2:
            bids = book[0]
            asks = book[1]

            parsed_book = {
                "timestamp": data.get("data", {}).get("time"),
                "bids": [{"price": level.get("px"), "qty": level.get("sz")} for level in bids], # "n": level.get("n")
                "asks": [{"price": level.get("px"), "qty": level.get("sz")} for level in asks] # "n": level.get("n")
            }
        else:
            parsed_book = {
                "error": "Invalid book structure",
            }

        print(f"Order Book: {parsed_book}")

    def _process_trade(self, data: List[Dict]) -> List[Dict]:
        trades = []
        for trade in data.get("data"):
            trades.append({
                "coin": trade["coin"],
                "side": trade["side"],
                "price": float(trade["px"]),
                "size": float(trade["sz"]),
                "time": trade["time"],
                "hash": trade["hash"],
                "trade_id": trade["tid"]
            })
        print(f"Trades: {trades}")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

eth = {
    "symbol": "ETH",
}

wallet = '0x7195d5fBC22Afa1FF6A0A25591285Db7a81838D4'

async def main():
    adapter = HyperLiquid()
    await adapter.connect()

    await adapter.subscribe_notifications(user_address=wallet)
    await adapter.subscribe_user_events(user_address=wallet)
    await adapter.subscribe_orders(user_address=wallet)
    # await adapter.subscribe_trades(contract=eth)
    # await adapter.subscribe_order_book(contract=eth)
    await asyncio.sleep(9999)

if __name__ == "__main__":
    asyncio.run(main())