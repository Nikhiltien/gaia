import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(base_dir))

import asyncio
import numpy as np
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
    start = datetime_to_unix("20240428 12:00:00")
    end = datetime_to_unix("20240428 16:00:00")
    symbol, exchange = "ETH", "HYPERLIQUID"
    book, trades, candles = await dojo.get_training_data(symbol=symbol, 
                                                         exchange=exchange, 
                                                         startTime=start, 
                                                         endTime=end)
    print(trades)
    # Visualizer().plot_candles(symbol, np.array(candles))


if __name__ == "__main__":
    asyncio.run(main())