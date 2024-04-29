import torch

from src.database.db_manager import PGDatabase

class Dojo():
    def __init__(self, database: PGDatabase) -> None:
        self.db = database

    async def get_training_data(self, symbol: str, exchange: str, startTime: int = None, endTime: int = None, 
                              interval: float = None, sequence_length: int = None, batches: float = None):
        
        conId, _ = await self.db.fetch_contract_by_symbol_exchange(symbol, exchange)
        book = await self.db.fetch_order_book(conId, start_time=startTime, end_time=endTime)
        trades = await self.db.fetch_trades(conId, start_time=startTime, end_time=endTime)
        candles = await self.db.fetch_candles(conId, start_time=startTime, end_time=endTime)

        return book, trades, candles
