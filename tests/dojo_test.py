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
from src.logger import setup_logger
from src.database.db_manager import PGDatabase
from src.models.tet.moe import MixtureOfExperts
    
async def main():
    logging = setup_logger(level='INFO', stream=True)
    config = load_config()

    database = PGDatabase()
    await database.start(config)

    dojo = Dojo(database)
    start = datetime_to_unix("20240428 14:00:00")
    end = datetime_to_unix("20240428 16:00:00")
    symbol, exchange = "ETH", "HYPERLIQUID"
    batch = await dojo.get_training_data(symbol=symbol, 
                                                         exchange=exchange, 
                                                         startTime=start, 
                                                         endTime=end)
    # Visualizer().plot_candles(symbol, np.array(candles))

    print(batch[-1][0].shape, batch[-1][1].shape)
    # print(batch[1][1])

if __name__ == "__main__":
    asyncio.run(main())