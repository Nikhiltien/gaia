import json
import random
import time
import asyncio
import numpy as np

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.utils import constants
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

from typing import List, Dict
from src.adapters.base_adapter import Adapter
from src.adapters.ws_client import WebsocketClient


class HyperLiquid(WebsocketClient, Adapter):
    def __init__(self, msg_callback=None, ws_name="HyperLiquid"):
        custom_callback = (self._handle_incoming_message)
        url = "wss://api.hyperliquid.xyz/ws"
        super().__init__(url=url, ws_name=ws_name, custom_callback=custom_callback)

        self._msg_loop = None
        self.headers = {"Content-Type": "application/json"}
        self.base_url = 'https://api.hyperliquid.xyz'

        self.address = None
        self.info = None
        self.exchange = None

        self.msg_callback = msg_callback
        self.subscriptions = {}
        self.active_orders = {}

    def start_msg_loop(self):
        self._msg_loop = asyncio.create_task(self._read_msg_task())

    async def _read_msg_task(self):
        try:
            while True:
                await self.recv()
        except asyncio.CancelledError:
            pass
    
    @staticmethod
    def _setup(base_url=None, skip_ws=False, key=None, address=None):
        account: LocalAccount = eth_account.Account.from_key(key)
        if address == "":
            address = account.address
        print("Running with account address:", address)
        if address != account.address:
            print("Running with agent address:", account.address)
        info = Info(base_url, skip_ws)
        user_state = info.user_state(address)
        margin_summary = user_state["marginSummary"]
        if float(margin_summary["accountValue"]) == 0:
            print("Not running because the provided account has no equity.")
            url = info.base_url.split(".", 1)[1]
            error_string = f"No accountValue:\nIf you think this is a mistake, make sure that {address} has a balance on {url}.\nIf address shown is your API wallet address, update the config to specify the address of your account, not the address of the API wallet."
            raise Exception(error_string)
        exchange = Exchange(account, base_url, account_address=address)
        return address, info, exchange

    async def connect(self, key, public, vault=None):
        await super()._connect()
        self.start_msg_loop()
        address, info, exchange = self._setup(constants.MAINNET_API_URL, skip_ws=True, key=key, address=public)

        if exchange.account_address != exchange.wallet.address:
            raise Exception("You should not create an agent using an agent")
        
        approve_result, agent_key = exchange.approve_agent()
        if approve_result["status"] != "ok":
            print("approving agent failed", approve_result)
            return
        
        agent_account: LocalAccount = eth_account.Account.from_key(agent_key)
        print("Running with agent address:", agent_account.address)

        if vault:
            agent_exchange = Exchange(wallet=agent_account, base_url=constants.MAINNET_API_URL, 
                                      vault_address=vault)
            self.address = vault
        else:
            agent_exchange = Exchange(wallet=agent_account, base_url=constants.MAINNET_API_URL, 
                                      account_address=address)
            self.address = address
            
        self.info = info
        self.exchange = agent_exchange
        self.logger.info(f"Connected to HyperLiquid.")

        asyncio.create_task(self.subscribe_all_user(interval=60))

    def _handle_incoming_message(self, message):
        channel = message.get('channel')
        if channel == 'subscriptionResponse':
            self._process_subscription_message(message)
        elif channel == 'notification':
            self._process_notification(message.get('data'))
        elif channel == 'error':
            self._process_error(message.get('data'))
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
            print(f"HyperLiquid System Msg: {message}")
        elif "orderUpdates" in channel:
            self._process_orders(message)
        elif "l2Book" in channel:
            self._process_order_book(message)
        elif "trade" in channel:
            self._process_trade(message)
        elif "candle" in channel:
            self._process_candle(message)
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

    async def get_user_state(self, user_details: Dict=None):
        if user_details is None:
            address = self.address
        else: 
            address = user_details.get("address")
        response = self.info.user_state(address)
        parsed_response = self._parse_user_state(response)
        return parsed_response

    @staticmethod
    def _parse_user_state(response: dict) -> dict:
        parsed_data = {
            "positions": [],
            "cash_balance": response["crossMarginSummary"]["accountValue"]
        }

        for position in response["assetPositions"]:
            if 'position' in position:
                parsed_data["positions"].append({
                    "symbol": position["position"]["coin"],
                    "qty": position["position"]["szi"],
                    "leverage": position["position"]["leverage"]["value"],
                    "avg_price": position["position"]["entryPx"],
                })

        return parsed_data

    async def get_spot_user_state(self, user_details: Dict=None):
        if user_details is None:
            address = self.address
        else: 
            address = user_details.get("address")
        response = self.info.spot_user_state(address)
        return response

    async def get_open_orders(self, user_details: Dict=None):
        if user_details is None:
            address = self.address
        else: 
            address = user_details.get("address")
        response = self.info.open_orders(address)
        open_orders = []
        for order in response:
            open_orders.append({
                "symbol": order["coin"],
                "side": "BUY" if order["side"] == "B" else "SELL",
                "price": order["limitPx"],
                "qty": order["sz"],
                "order_id": order["oid"],
                "timestamp": order["timestamp"]
            })

        return open_orders

    async def cancel_all_orders(self, user_details: Dict=None):
        open_orders = await self.get_open_orders(user_details)

        # Iterating through the open orders and canceling each one
        cancellation_results = []
        for order in open_orders:
            result = await self.cancel_order({
                "symbol": order["symbol"],
                "order_id": order["order_id"]
            })
            cancellation_results.append(result)

        return cancellation_results

    async def get_all_mids(self):
        response = self.info.all_mids()
        return response

    async def get_user_fills(self, user_details: Dict=None):
        if user_details is None:
            address = self.address
        else: 
            address = user_details.get("address")
        response = self.info.user_fills(address)
        return response

    async def query_order_status_by_oid(self, order_details: Dict):
        response = self.info.query_order_by_oid(
            user=order_details.get("user"),
            oid=order_details.get("oid")
        )
        return response

    async def get_meta(self):
        response = self.info.meta()
        return response

    async def get_spot_meta(self):
        response = self.info.spot_meta()
        return response

    async def place_order(self, order_details: Dict):
        symbol = order_details.get("symbol")
        side = order_details.get("side").upper() == "BUY"
        price = float(order_details.get("price"))
        qty = float(order_details.get("qty"))
        
        order_type = None
        if 'orderType' in order_details and 'limit' in order_details['orderType']:
            order_type = {
                'limit': {
                    'tif': order_details['orderType']['limit'].get('tif', 'Gtc')
                }
            }

        reduce_only = order_details.get("reduceOnly", False)
        
        result = self.exchange.order(coin=symbol, is_buy=side, sz=qty, limit_px=price, 
                                 order_type=order_type, reduce_only=reduce_only)
        
        return result

    async def cancel_order(self, order_details):
        symbol = order_details.get("symbol")
        order_id = int(order_details.get("order_id"))
        result = self.exchange.cancel(coin=symbol, oid=order_id)
        
        return result

    async def modify_order(self, modify_details: Dict):
        response = self.exchange.modify_order(
            oid=modify_details.get("order_id"),
            coin=modify_details.get("coin"),
            is_buy=modify_details.get("is_buy"),
            sz=modify_details.get("qty"),
            limit_px=modify_details.get("limit_price"),
            order_type=modify_details.get("order_type"),
            reduce_only=modify_details.get("reduce_only", False)
        )
        return response

    async def update_leverage(self, leverage_details: Dict):
        response = self.exchange.update_leverage(
            leverage=leverage_details.get("leverage"),
            coin=leverage_details.get("symbol"),
            is_cross=leverage_details.get("is_cross", True)
        )
        return response

    async def update_isolated_margin(self, margin_details: Dict):
        response = self.exchange.update_isolated_margin(
            amount=margin_details.get("amount"),
            coin=margin_details.get("coin")
        )
        return response

    async def subscribe_all_user(self, interval=60):
        await self.subscribe_notifications()
        await self.subscribe_user_events()
        await self.subscribe_orders()

        while True:
            data = []
            user_state = await self.get_user_state()
            open_orders = await self.get_open_orders()
            data.append(user_state)
            data.append(open_orders)
            if self.msg_callback:
                self.msg_callback("sync", data)
            await asyncio.sleep(interval)

    async def subscribe_notifications(self, user_address=None, req_id=None):
        if user_address is None: user_address = self.address
        params = {
            "type": "notification", 
            "user": user_address
            }
        await self._subscribe_to_topic(method="subscribe", params=params, req_id=req_id)

    async def subscribe_user_events(self, user_address=None, req_id=None):
        if user_address is None: user_address = self.address
        params = {
            "type": "userEvents", 
            "user": user_address
            }
        await self._subscribe_to_topic(method="subscribe", params=params, req_id=req_id)

    async def subscribe_orders(self, user_address=None, req_id=None):
        if user_address is None: user_address = self.address
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

    async def get_klines(self, candle_details: Dict):
        response = self.info.candles_snapshot(
            coin=candle_details.get("coin"),
            interval=candle_details.get("interval"),
            startTime=candle_details.get("startTime"),
            endTime=candle_details.get("endTime")
        )
        return response

    async def subscribe_klines(self, contract, interval, req_id=None):
        symbol = contract.get("symbol")
        params = {
            "type": "candle",
            "coin": symbol,
            "interval": str(interval)
        }
        return await self._subscribe_to_topic(method="subscribe", params=params, req_id=req_id)

    def _process_notification(self, data):
        notification = data.get("notification")
        print(f"Notification: {notification}")

    def _process_error(self, data):
        error = data.get("error")
        print(f"Error: {error}")

    def _process_user_event(self, data):
        # print(data)
        topic = None
        parsed_events = []
        if 'fills' in data:
            for fill in data['fills']:
                parsed_event = {
                    "type": "fills",
                    "symbol": fill.get('coin'),
                    "price": fill.get('px'),
                    "qty": fill.get('sz'),
                    "side": fill.get('side'),
                    "timestamp": fill.get('time'),
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
                topic = 'inventory'
                parsed_events.append(parsed_event)

        elif 'liquidation' in data:
            liquidation = data.get('liquidation')
            parsed_event = {
                "type": "liquidation",
                "liquidationID": liquidation.get('lid'),
                "liquidator": liquidation.get('liquidator'),
                "liquidatedUser": liquidation.get('liquidated_user'),
                "netLossPosition": liquidation.get('liquidated_ntl_pos'),
                "accountValue": liquidation.get('liquidated_account_value')
            }
            topic = 'inventory'
            parsed_events.append(parsed_event)

        elif 'nonUserCancel' in data:
            for cancel in data['nonUserCancel']:
                parsed_event = {
                    "coin": cancel.get('coin'),
                    "orderID": cancel.get('oid')
                }
                topic = 'orders'
                parsed_events.append(parsed_event)

        elif 'funding' in data:
            funding = data.get('funding')
            parsed_event = {
                "type": "funding",
                "timestamp": funding.get('time'),
                "symbol": funding.get('coin'),
                "usdc": funding.get('usdc'),
                "qty": funding.get('szi'),
                "fundingRate": funding.get('fundingRate'),
                "nSamples": funding.get('nSamples')
            }
            topic = 'inventory'
            parsed_events.append(parsed_event)

        if self.msg_callback:
            self.msg_callback(topic, parsed_event)
        # print(f"User Events: {parsed_events}")

    def _process_orders(self, data):
        order_updates = data.get('data', [])
        parsed_orders = []
        for order_data in order_updates:  # Iterating through the list of order updates
            order = order_data.get('order', {})
            parsed_order = {
                "symbol": order.get('coin'),
                "side": order.get('side') == 'B' and "BUY" or "SELL",
                "price": order.get('limitPx'),
                "qty": order.get('sz'),
                "order_id": order.get('oid'),
                "timestamp": order.get('timestamp'),
                "originalQty": order.get('origSz'),
                "reduceOnly": order.get('reduceOnly', False),
                "status": order_data.get('status'),
                "statusTimestamp": order_data.get('statusTimestamp')
            }
            parsed_orders.append(parsed_order)

        if self.msg_callback:
            self.msg_callback("orders", parsed_orders)
        # print(f"Order Events: {parsed_orders}")

    def _process_order_book(self, data, num_levels=None):
        book = data.get("data", {}).get("levels", [])
        if len(book) == 2:
            bids, asks = book
            
            # Limit the number of levels if num_levels is specified; otherwise, use all levels
            bids = bids[:num_levels] if num_levels is not None else bids
            asks = asks[:num_levels] if num_levels is not None else asks

            parsed_book = {
                "symbol": data.get("data", {}).get("coin"),
                "timestamp": data.get("data", {}).get("time"),
                "bids": [{"price": level.get("px"), "qty": level.get("sz")} for level in bids],
                "asks": [{"price": level.get("px"), "qty": level.get("sz")} for level in asks]
            }
        else:
            parsed_book = {
                "error": "Invalid book structure",
            }

        if self.msg_callback:
            self.msg_callback("order_book", parsed_book)
        # print(f"Order Book: {parsed_book}")

    def _process_trade(self, data: List[Dict]) -> List[Dict]:
        trades = []
        for trade in data.get("data"):
            trades.append({
                "symbol": trade["coin"],
                "side": trade["side"],
                "price": float(trade["px"]),
                "qty": float(trade["sz"]),
                "timestamp": trade["time"],
                "hash": trade["hash"],
                "trade_id": trade["tid"]
            })

        if self.msg_callback:
            self.msg_callback("trades", trades)
        # print(f"Trades: {trades}")

    def _process_candle(self, message):
        # Directly access 'data' as it already represents a single candle.
        candle_data = message.get('data', {})

        parsed_candle = {
            'open_timestamp': candle_data.get('t'),
            'close_timestamp': candle_data.get('T'),
            'symbol': candle_data.get('s'),
            'interval': candle_data.get('i'),
            'open': float(candle_data.get('o')),
            'close': float(candle_data.get('c')),
            'high': float(candle_data.get('h')),
            'low': float(candle_data.get('l')),
            'volume': float(candle_data.get('v')),
            'num_trades': candle_data.get('n')
        }

        if self.msg_callback:
            self.msg_callback("klines", parsed_candle)
        # print(f"Candle: {parsed_candle}")