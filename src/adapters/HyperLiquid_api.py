from ws_client import WebsocketClient
from base_adapter import Adapter

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
        self.future_directory = {}
        self.private_channels = [
            "add_order",
            "cancel_order",
            # ...
        ]
