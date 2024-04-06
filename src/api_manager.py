from src.adapters import base_adapter
from src.zeromq.zeromq import ZeroMQ

class APIManager:
    def __init__(self) -> None:
        self.zmq = ZeroMQ()

        self.adapters = {}
        self.metrics = {}

