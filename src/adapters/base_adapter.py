from abc import ABC, abstractmethod

class Adapter(ABC):
    def __init__(self) -> None:
        super().__init__()

    # @abstractmethod
    # def subscribe_order_book(self):
    #     pass