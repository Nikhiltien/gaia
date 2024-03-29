from abc import ABC, abstractmethod

class Adapter(ABC):
    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def subscribe_orderbook(self):
        pass