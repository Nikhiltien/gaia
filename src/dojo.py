import torch
import numpy as np

from datetime import datetime
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
        book, trades = self.align_book_to_trades(book, trades)

        time_series = self.merge_data(book, trades)
        z_time_series = self.normalize_prices(time_series)
        z_candles = self.normalize_candles(candles)

        final_timeseries = self.convert_timestamps_to_deltas(z_time_series)
        final_candles = self.convert_timestamps_to_deltas(z_candles)

        return final_timeseries, final_candles

    @staticmethod
    def convert_timestamps_to_deltas(data: np.ndarray) -> np.ndarray:
        # Calculate deltas
        deltas = np.diff(data[:, 0], prepend=data[0, 0])
        # Compute cumulative sum to retain positional context
        data[:, 0] = np.cumsum(deltas)
        return data

    @staticmethod
    def normalize_prices(time_series: np.ndarray) -> np.ndarray:
        # Indices for trade average buy and sell prices
        trade_price_indices = [2, 5]
        book_price_indices = np.arange(7, time_series.shape[1], 2)  # Assuming book prices are every second column from index 7
        
        # Extract prices from these indices
        trade_prices = time_series[:, trade_price_indices]
        book_prices = time_series[:, book_price_indices].flatten()

        # Exclude zero prices from trades for the normalization process
        nonzero_trade_prices = trade_prices[trade_prices != 0]
        all_prices_to_normalize = np.concatenate((nonzero_trade_prices, book_prices)) # Combining non-zero trade prices and book prices

        mean_price = np.mean(all_prices_to_normalize)
        std_price = np.std(all_prices_to_normalize)

        if std_price == 0:  # Avoid division by zero if no variation
            return time_series

        # Normalize non-zero trade prices separately
        for idx in trade_price_indices:
            nonzero_indices = time_series[:, idx] != 0  # Find where prices are not zero
            if np.any(nonzero_indices):  # Check if there are any non-zero prices to normalize
                time_series[nonzero_indices, idx] = (time_series[nonzero_indices, idx] - mean_price) / std_price

        # Normalize book prices
        time_series[:, book_price_indices] = (time_series[:, book_price_indices] - mean_price) / std_price
        
        return time_series

    @staticmethod
    def normalize_candles(candles: np.ndarray) -> np.ndarray:
        # Columns are ordered as [timestamp, open, high, low, close, volume, bb_upper, bb_lower]
        # Indices for OHLC and Bollinger Bands
        price_indices = [1, 2, 3, 4, 6, 7]  # open, high, low, close, bb_upper, bb_lower

        # Extract prices from candles
        prices_to_normalize = candles[:, price_indices].flatten()

        # Compute the mean and standard deviation
        mean_price = np.mean(prices_to_normalize)
        std_price = np.std(prices_to_normalize)

        # Avoid division by zero if no variation
        if std_price == 0:
            return candles

        # Normalize the prices
        candles[:, price_indices] = (candles[:, price_indices] - mean_price) / std_price

        return candles

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
    def align_book_to_trades(book: NDArray, trades: NDArray) -> Tuple[NDArray, NDArray]:
        trade_timestamps = trades[:, 0]
        aligned_books = []
        aligned_trades = []

        # Pointer for the book array
        j = 0
        
        # Iterate over each trade to find the preceding book snapshot
        for i in range(len(trade_timestamps)):
            trade_time = trade_timestamps[i]
            
            # Move the pointer to the last book entry before the trade
            while j < len(book) - 1 and book[j + 1][0] <= trade_time:
                j += 1
            
            # Maintain all book data but replace the timestamp with the trade's timestamp
            adjusted_book = np.copy(book[j])
            adjusted_book[0] = trade_time  # Set book timestamp to match trade's
            
            # Append the book state and trade record
            aligned_books.append(adjusted_book)
            aligned_trades.append(trades[i])
        
        return np.array(aligned_books), np.array(aligned_trades)

    @staticmethod
    def merge_data(book_aligned: np.ndarray, trades_aligned: np.ndarray) -> np.ndarray:
        # Flatten each book snapshot entry, exclude timestamp from book
        flat_book_data = np.array([b[1].flatten() for b in book_aligned])

        # Concatenate the trades (including its timestamp) with the flattened book data
        merged_data = np.concatenate((trades_aligned, flat_book_data), axis=1)

        return merged_data

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