import numpy as np
from typing import Tuple, List

class LOB:
    def __init__(self, order_book: List, outside_volume=1) -> None:
        # Transform and separate order book data into asks and bids
        self.asks, self.bids = self.transform_order_book_data(order_book)
        self._outside_volume = outside_volume

    def __str__(self):
        """
        Returns a string representation of the LOB object showing bids and asks with dynamic precision.
        """
        bid_str = '\n'.join([f"Bid: Price {price}, Quantity {qty}" for price, qty in self.bids])
        ask_str = '\n'.join([f"Ask: Price {price}, Quantity {qty}" for price, qty in self.asks])
        return f"{bid_str}\n{ask_str}"

    def __repr__(self):
        bid_str = ', '.join([f"({price}, {qty})" for price, qty in self.bids])
        ask_str = ', '.join([f"({price}, {qty})" for price, qty in self.asks])
        return f"LOB(Bids=[{bid_str}], Asks=[{ask_str}])"

    def transform_order_book_data(self, order_book: list) -> Tuple[np.ndarray, np.ndarray]:
        """
        Splits and transforms the list of order book data into two arrays for asks and bids.

        :param order_book: A list of [price, quantity] pairs, with bids followed by asks.
        :return: Two NumPy arrays, one for asks and one for bids.
        """
        num_levels = len(order_book) // 2
        bids_list = order_book[:num_levels]
        asks_list = order_book[num_levels:]

        # Sort bids in descending order and asks in ascending order
        bids_array = np.array(sorted(bids_list, key=lambda x: x[0], reverse=True))
        asks_array = np.array(sorted(asks_list, key=lambda x: x[0]))

        return asks_array, bids_array

    def sort_book(self):
        """
        Sorts the ask and bid arrays by price. Bids are sorted in descending order,
        and asks are sorted in ascending order.
        """
        self.bids = self.bids[np.argsort(-self.bids[:, 0])]
        self.asks = self.asks[np.argsort(self.asks[:, 0])]

    def update_book(self, asks_or_bids: str, data: np.ndarray):
        """
        Updates either the asks or bids attribute with new data and then sorts.

        :param asks_or_bids: A string indicating whether to update 'asks' or 'bids'.
        :param data: A NumPy array containing the new order data to incorporate.
        :return: Updated order book data as a NumPy array.
        """
        if asks_or_bids == 'asks':
            self.asks = np.vstack([self.asks, data])
            self.sort_book()
            return self.asks
        elif asks_or_bids == 'bids':
            self.bids = np.vstack([self.bids, data])
            self.sort_book()
            return self.bids
        else:
            raise ValueError("asks_or_bids must be either 'asks' or 'bids'")

    @property
    def best_ask(self) -> float:
        """
        Returns the best ask price in the order book.

        :return: Best ask price as a float.
        """
        return self.asks[0][0] if self.asks.size > 0 else np.inf

    @property
    def best_bid(self) -> float:
        """
        Returns the best bid price in the order book.

        :return: Best bid price as a float.
        """
        return self.bids[0][0] if self.bids.size > 0 else -np.inf

    @property
    def spread(self) -> float:
        """
        Calculates the current spread between the best ask and bid.

        :return: Spread as a float.
        """
        return self.best_ask - self.best_bid
    
    @property
    def mid_price(self) -> float:
        """
        Calculates the mid-price from the best bid and ask.

        :return: Mid-price as a float.
        """
        return (self.best_ask + self.best_bid) / 2

    @property
    def weighted_midprice(self):
        """
        Calculates the weighted midprice based on the best bid and ask.

        :return: Weighted midprice as a float.
        """
        if not self.asks.size or not self.bids.size:
            return 0

        best_bid = self.bids[0]  # The best bid is the first entry after sorting
        best_ask = self.asks[0]  # The best ask is the first entry after sorting

        p_b, q_b = best_bid
        p_a, q_a = best_ask

        if q_a + q_b > 0:
            return (q_a * p_a + q_b * p_b) / (q_a + q_b)
        else:
            return 0
        
    def get_market_depth(self, levels: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        """
        Retrieves the market depth up to a specified number of levels for both bids and asks.

        :param levels: The number of levels to include in the market depth.
        :return: A tuple containing two arrays with the market depth for bids and asks.
        """
        # Get the minimum of requested levels and actual available levels
        bid_levels = min(levels, len(self.bids))
        ask_levels = min(levels, len(self.asks))

        # Slice the order book to get the top levels for bids and asks
        bid_depth = self.bids[:bid_levels, :]
        ask_depth = self.asks[:ask_levels, :]

        return bid_depth, ask_depth
    
    def calculate_order_imbalance(self, levels: int) -> float:
        """
        Calculates the order imbalance based on the specified number of levels.

        :param levels: The number of levels to consider for the imbalance calculation.
        :return: The order imbalance ratio, ranging from -1 (all asks) to 1 (all bids).
        """
        bid_depth, ask_depth = self.get_market_depth(levels)

        # Calculate the total volumes at the specified depth for bids and asks
        total_bid_volume = np.sum(bid_depth[:, 1])
        total_ask_volume = np.sum(ask_depth[:, 1])

        # Calculate the imbalance
        # If there's no volume on either side, define the imbalance as 0
        if total_bid_volume + total_ask_volume == 0:
            return 0

        imbalance = (total_bid_volume - total_ask_volume) / (total_bid_volume + total_ask_volume)
        return imbalance

    def ask_n(self, n: int) -> float:
        """
        Returns the price at the n-th level ask.

        :param n: The depth level to query (0-based).
        :return: The price at the n-th level ask.
        """
        return self.asks[n][0] if n < len(self.asks) else np.inf

    def bid_n(self, n: int) -> float:
        """
        Returns the price at the n-th level bid.

        :param n: The depth level to query (0-based).
        :return: The price at the n-th level bid.
        """
        return self.bids[n][0] if n < len(self.bids) else -np.inf

    def ask_n_volume(self, n: int) -> float:
        """
        Returns the volume available at the n-th level ask.

        :param n: The depth level to query (0-based).
        :return: The volume at the n-th level ask.
        """
        return self.asks[n][1] if n < len(self.asks) else 0

    def bid_n_volume(self, n: int) -> float:
        """
        Returns the volume available at the n-th level bid.

        :param n: The depth level to query (0-based).
        :return: The volume at the n-th level bid.
        """
        return self.bids[n][1] if n < len(self.bids) else 0
    
    def buy_n(self, n: int) -> float:
        """
        Simulates buying 'n' quantities starting from the best ask and moving deeper into the book.

        :param n: The quantity to buy.
        :return: The total cost of buying 'n' quantities.
        """
        total_cost = 0
        for level in range(len(self.asks)):
            available = self.asks[level][1]
            price = self.asks[level][0]
            volume_to_buy = min(n, available)
            total_cost += volume_to_buy * price
            n -= volume_to_buy
            if n <= 0:
                break
        return total_cost

    def sell_n(self, n: int) -> float:
        """
        Simulates selling 'n' quantities starting from the best bid and moving deeper into the book.

        :param n: The quantity to sell.
        :return: The total revenue from selling 'n' quantities.
        """
        total_revenue = 0
        for level in range(len(self.bids)):
            available = self.bids[level][1]
            price = self.bids[level][0]
            volume_to_sell = min(n, available)
            total_revenue += volume_to_sell * price
            n -= volume_to_sell
            if n <= 0:
                break
        return total_revenue

    def change_volume(self, level: int, volume_change: float, asks_or_bids: str):
        """
        Adjusts the volume at a certain level in the order book.

        :param level: The depth level to adjust (0-based).
        :param volume_change: The amount to adjust the volume by.
        :param asks_or_bids: A string indicating whether to adjust 'asks' or 'bids'.
        """
        book = self.asks if asks_or_bids == 'asks' else self.bids
        if 0 <= level < len(book):
            new_volume = book[level][1] + volume_change
            book[level][1] = max(0, new_volume)
        else:
            raise IndexError("The specified level is out of range.")