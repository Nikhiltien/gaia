import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(base_dir))

import asyncio
import numpy as np
from src.utils.math import trades_imbalance
from src.utils.time import time_ms, datetime_to_unix
from src.utils.visualizer import Visualizer
from src.dojo import Dojo
from src.core import load_config
from src.database.db_manager import PGDatabase
    
async def main():
    config = load_config()

    database = PGDatabase()
    await database.start(config)

    dojo = Dojo(database)
    start = datetime_to_unix("20240428 13:59:30")
    end = datetime_to_unix("20240428 14:00:00")
    symbol, exchange = "ETH", "HYPERLIQUID"
    book, trades, candles = await dojo.get_training_data(symbol=symbol, 
                                                         exchange=exchange, 
                                                         startTime=start, 
                                                         endTime=end)
    # Visualizer().plot_candles(symbol, np.array(candles))
    book_timestamps = np.array([b[0] for b in book])
    print(book_timestamps)
    trade_timestamps = trades[:, 0]
    print(np.array(trade_timestamps, dtype=np.int64))

if __name__ == "__main__":
    asyncio.run(main())