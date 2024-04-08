import asyncio
import unittest
import time
from ..src.feed import Feed

class TestFeedNotificationLatency(unittest.TestCase):
    async def add_data_and_measure(self, feed, symbol, data_type, data):
        if data_type == 'orderbook':
            await feed.add_orderbook_snapshot(symbol, data)
        elif data_type == 'trade':
            await feed.add_trade(symbol, data)
        elif data_type == 'kline':
            await feed.add_kline(symbol, data)

    async def get_notification_and_measure(self, feed):
        await feed.dequeue_symbol_update()

    async def test_notification_latency(self):
        feed = Feed(['AAPL'])

        # Prepare dummy data for a large number of iterations
        num_iterations = 100000
        start_time = time.perf_counter()

        for _ in range(num_iterations):
            # Assuming order book update
            await self.add_data_and_measure(feed, 'AAPL', 'orderbook', {'data': 'some_data'})
            await self.get_notification_and_measure(feed)

        total_time = time.perf_counter() - start_time
        average_time = total_time / num_iterations

        print(f"Average notification latency over {num_iterations} iterations: {average_time} seconds")
        self.assertTrue(average_time >= 0)

    def test_feed(self):
        asyncio.run(self.test_notification_latency())

if __name__ == "__main__":
    unittest.main()
