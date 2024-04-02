import asyncio
import json
import logging
import time
import random
import copy

from datetime import datetime
from src.adapters.base_adapter import Adapter
from src.adapters.ws_client import _CEXSocket

class Kraken(_CEXSocket, Adapter):
    def __init__(self, label=None, adapter_id=None, config=None, ws_name="KrakenV2", api_key=None, api_secret=None, **kwargs):
        custom_callback = (
            kwargs.pop("callback_function")
            if kwargs.get("callback_function")
            else self._handle_incoming_message
        )
        ws_public_url = "wss://ws.kraken.com/v2"
        ws_private_url = "wss://ws-auth.kraken.com/v2"
        url = ws_private_url if api_key and api_secret else ws_public_url
        super().__init__(url=url, ws_name=ws_name, custom_callback=custom_callback, **kwargs)
        Adapter.__init__(self, label=label, adapter_id=adapter_id, config=config)

        self.status = "Disconnected"
        self._msg_loop = None
        self.subscriptions = {}
        self.future_directory = {}
        self.private_channels = [
            "add_order",
            "cancel_order",
            # ...
        ]

        # self.exchange_specific_data = {}
        # self._initialize_exchange_specific_data()
        # self.custom_ping_message = json.dumps({"method": "ping"})

    def on_api_start(self):
        self.status = "Connected"

    def on_api_end(self):
        self.status = "Disconnected"

    def on_api_error(self, errorMsg):
        self.status = "Error"
        self.logger.error(f"API Error: {errorMsg}")

    def start_msg_loop(self):
        self._msg_loop = asyncio.create_task(self._read_msg_task())

    async def _read_msg_task(self):
        try:
            while True:
                await self.recv()
        except asyncio.CancelledError:
            pass

    async def connect(self):
        if self._adapter_id in self._connection_pool and self._connection_pool[self._adapter_id].isConnected():
            self.connection = self._connection_pool[self._adapter_id]
        await super()._connect()
        self.start_msg_loop()
        self.on_api_start()

    async def disconnect(self):
        if self._msg_loop:
            self._msg_loop.cancel()
            await self._msg_loop
        await super()._disconnect()
        self.on_api_end()

    # async def get_auth_token(self):
    #     if self.auth_token and time.time() < self.auth_token_expiry:
    #         return self.auth_token  # Return existing token if not expired
    #     url = "https://api.kraken.com/0/private/GetWebSocketsToken"
    #     headers = {'API-Key': self.config['api_key']}
    #     # Additional authentication details need to be added here
    #     response = requests.post(url, headers=headers)
    #     data = response.json()
    #     self.auth_token = data['result']['token']
    #     self.auth_token_expiry = time.time() + 900  # 15 minutes validity
    #     return self.auth_token
    
    # def is_private_channel(self, channel_name):
    #     private_channels = ["ownTrades", "openOrders"]  # Example private channels
    #     return channel_name in private_channels

    async def send_ping(self):
        ping_request = {"method": "ping"}
        await self.websocket.send(json.dumps(ping_request))
    
    def register_callback(self, adapter_callbacks):
        self.callbacks = {data_type: callback for callback, data_type in adapter_callbacks}

    async def trigger_callback(self, data_type, data):
        if data is not None:
            if data_type in self.callbacks:
                self.callbacks[data_type](data_type, data)

    def transform_symbol_for_rest_api(self, contract):
        contract_copy = copy.deepcopy(contract)
        if 'BTC' in contract_copy.symbol:
            contract_copy.symbol = contract_copy.symbol.replace('BTC', 'XBT')
            symbol = f'X{contract_copy.symbol}Z{contract_copy.currency}'
        else:
            symbol = f'{contract_copy.symbol}{contract_copy.currency}'
        return symbol

    def _process_subscription_message(self, message):
        method = message.get("method")
        success = message.get("success")
        req_id = message.get("req_id")
        stream_msg = f"{success, req_id}"
        if req_id and req_id in self.future_directory:
            self.future_directory[req_id].set_result(stream_msg)
            del self.future_directory[req_id]

        if method == "subscribe":
            if success is True:
                if req_id and req_id in self.subscriptions:
                    result = message.get("result", {})
                    symbol = result.get("symbol")
                    channel = result.get("channel")
                    self.logger.info(f"Subscription successful for {symbol}, {channel}.")
                    # Update subscription details if necessary
                    # self.subscriptions[req_id]["details"] = {"symbol": symbol, "channel": channel}
                else:
                    self.logger.warning(f"Received unknown subscription confirmation: {message}")
            else:
                error_info = message.get("error", {})
                self.logger.error(f"Subscription failed: {error_info}")

        elif method == "unsubscribe":
            if success:
                result = message.get("result", {})
                symbol = result.get("symbol")
                channel = result.get("channel")
                self.logger.info(f"Unsubscription successful for {symbol}, {channel}.")
                # Handle unsubscription logic, like removing from self.subscriptions
                # if req_id in self.subscriptions:
                #     del self.subscriptions[req_id]
            else:
                error_info = message.get("error", {})
                self.logger.error(f"Unsubscription failed: {error_info}")

    def _process_normal_message(self, message):
        channel = message.get("channel")
        if channel is None:
            self.logger.debug(f"Kraken System Msg: {message}")
        elif "book" in channel:
            self._process_orderbook(message)
        elif "trade" in channel:
            self._process_trade(message)
        elif "status" in channel:
            self.logger.info(f"Kraken Status: {message}")
        else:
            self.logger.debug(f"Unrecognized channel: {message}")
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
            if (message.get("method") == "subscribe" 
                or message.get("method") == "unsubscribe"
                ):
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
            "params": params
        }
        if req_id is not None:
            message["req_id"] = req_id
        return json.dumps(message)

    async def _subscribe_to_topic(self, method, params, req_id=None):
        if req_id is None:
            req_id = random.randint(1, 1e17)

        self.future_directory[req_id] = asyncio.Future() # Future containing API response

        subscription_message = self._create_subscription_message(method=method, params=params, req_id=req_id)

        self.subscriptions[req_id] = subscription_message
        
        if self.ws:
            try:
                await self.ws.send(subscription_message)
                return self.future_directory[req_id]
            except Exception as e:
                self.logger.error(f"Error subscribing to {method} channel: {e}")
                self.future_directory[req_id].set_exception(e)
                return self.future_directory[req_id]

    async def _unsubscribe_from_topic(self, channel, symbol, req_id=None):
        params = {
            "channel": channel,
            "symbol": [symbol]
        }
        unsubscribe_message = self._create_subscription_message("unsubscribe", params, req_id)
        if self.ws:
            try:
                await self.ws.send(unsubscribe_message)
            except Exception as e:
                self.logger.error(f"Error unsubscribing from {channel} channel: {e}")

    async def subscribe_order_book(self, contract, depth=10, req_id=None):
        symbol = contract.get("symbol")
        currency = contract.get("currency")
        params = {
            "channel": "book",
            "depth": depth,
            "snapshot": True,
            "symbol": [f"{symbol}/{currency}"]
        }
        return await self._subscribe_to_topic(method="subscribe", params=params, req_id=req_id)

    async def unsubscribe_order_book(self, symbol, req_id=None):
        await self._unsubscribe_from_topic("book", symbol, req_id)

    async def subscribe_trades(self, contract, req_id=None):
        symbol = contract.get("symbol")
        currency = contract.get("currency")
        params = {
            "channel": "trade",
            "symbol": [f"{symbol}/{currency}"]
        }
        return await self._subscribe_to_topic(method="subscribe", params=params, req_id=req_id)

    async def unsubscribe_trades(self, symbol, req_id=None):
        await self._unsubscribe_from_topic("trade", symbol, req_id)

    async def req_historical_data(self, ticker, period):
        pass

    # @staticmethod
    def _process_orderbook(self, message):
        channel_data = message.get("data", [])
        if not channel_data:
            return

        for entry in channel_data:
            symbol = entry.get("symbol", "")
            checksum = entry.get("checksum", "")

            bids = [{'price': float(bid['price']), 'qty': float(bid['qty'])} for bid in entry.get("bids", [])]
            asks = [{'price': float(ask['price']), 'qty': float(ask['qty'])} for ask in entry.get("asks", [])]

            timestamp_str = entry.get("timestamp", "")
            if timestamp_str:
                timestamp_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                timestamp_ms = int(timestamp_dt.timestamp() * 1000)
            else:
                timestamp_ms = int(time.time() * 1000)

            order_book_data = {
                "symbol": symbol,
                "timestamp": timestamp_ms,
                "checksum": checksum,
                "asks": asks,
                "bids": bids,
                # "timestamp": timestamp_ms
            }

        channel = message.get("channel")
        symbol = order_book_data.get("symbol")
        asyncio.create_task(self.trigger_callback("order_book", order_book_data))
            # return order_book_data

    # @staticmethod
    def _process_trade(self, message):
        channel_data = message.get("data", [])
        if not channel_data:
            return

        formatted_trades = []
        for trade in channel_data:
            symbol = trade.get("symbol", "")
            side = trade.get("side", "")
            price = float(trade.get("price", 0))
            qty = float(trade.get("qty", 0))
            ord_type = trade.get("ord_type", "")
            trade_id = trade.get("trade_id", 0)
            trade_timestamp_str = trade.get("timestamp", "")

            if trade_timestamp_str:
                trade_timestamp_dt = datetime.fromisoformat(trade_timestamp_str.replace("Z", "+00:00"))
                trade_timestamp_ms = int(trade_timestamp_dt.timestamp() * 1000)
            else:
                trade_timestamp_ms = int(time.time() * 1000)

            formatted_trades.append({
                "symbol": symbol,
                "side": side,
                "price": price,
                "qty": qty,
                "ord_type": ord_type,
                "trade_id": trade_id,
                "timestamp": trade_timestamp_ms
            })

        asyncio.create_task(self.trigger_callback("trades", formatted_trades))
        # return formatted_trades