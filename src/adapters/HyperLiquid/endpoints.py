from dataclasses import dataclass

@dataclass
class BaseEndpoints:
    MAINNET = f"https://api.hyperliquid.xyz"

@dataclass
class WsLinks:
    domain = f"api.hyperliquid.xyz"
    STREAM = f"wss://{domain}/ws"

@dataclass
class RestLinks:
    EXCHANGE = "/exchange"
    INFO = "/info"
