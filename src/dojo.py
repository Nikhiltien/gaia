import torch
import numpy as np

from typing import Tuple
from numpy.typing import NDArray
from src.utils.math import trades_imbalance, calculate_bollinger_bands
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

        candles = self.process_candles(candles)
        trades = self.process_trades(trades)

        book, trades = self.align_snapshots(book, trades)

        return book, trades, candles

    @staticmethod
    def align_snapshots(book: NDArray, trades: NDArray) -> Tuple[NDArray, NDArray]:
        # Get all unique timestamps from both trades and book snapshots
        book_timestamps = np.array([b[0] for b in book])
        trade_timestamps = trades[:, 0]

        # Find missing timestamps in trades that exist in book snapshots
        missing_trade_timestamps = np.setdiff1d(book_timestamps, trade_timestamps)

        # Create zero-filled trade arrays for missing timestamps
        for timestamp in missing_trade_timestamps:
            zero_trade = np.array([timestamp, 0, 0, 0, 0, 0, 0])
            trades = np.vstack([trades, zero_trade])

        # Sort trades to ensure they are in the same order as book snapshots
        trades = trades[np.argsort(trades[:, 0])]

        return book, trades

    @staticmethod
    def process_candles(candles: NDArray, length: float = 20, multiplier: float = 2) -> NDArray:
        bb_upper, bb_lower = calculate_bollinger_bands(candles, length, multiplier)
        pad_size = len(candles) - len(bb_upper)
        upper_band_padded = np.pad(bb_upper, (pad_size, 0), 'constant', constant_values=(np.nan,))
        lower_band_padded = np.pad(bb_lower, (pad_size, 0), 'constant', constant_values=(np.nan,))

        return np.column_stack((candles, upper_band_padded, lower_band_padded))

    @staticmethod
    def process_trades(trades: NDArray) -> NDArray:
        unique_timestamps = np.unique(trades[:, 0])
        processed_trades = np.zeros((len(unique_timestamps), 7))

        for i, timestamp in enumerate(unique_timestamps):
            current_trades = trades[trades[:, 0] == timestamp]
            buy_trades = current_trades[current_trades[:, 1] == 1]
            sell_trades = current_trades[current_trades[:, 1] == 0]
            num_buys = buy_trades.shape[0]
            avg_buy_price = np.average(buy_trades[:, 2], weights=buy_trades[:, 3]) if num_buys > 0 else 0
            total_buy_qty = np.sum(buy_trades[:, 3])
            num_sells = sell_trades.shape[0]
            avg_sell_price = np.average(sell_trades[:, 2], weights=sell_trades[:, 3]) if num_sells > 0 else 0
            total_sell_qty = np.sum(sell_trades[:, 3])

            processed_trades[i] = [timestamp, num_buys, avg_buy_price, total_buy_qty, num_sells, avg_sell_price, total_sell_qty]

        return np.array(processed_trades)