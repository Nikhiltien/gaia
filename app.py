import re
import uvloop
import asyncio
import cProfile

from src.feed import Feed
from src.core import GAIA
from src.logger import setup_logger


async def main():

    logging = setup_logger(level='INFO', stream=True)
    
    contracts = ['BTC', 'ETH', 'SOL']

    try:
        data_feed = Feed(contracts=contracts)
        strategy = asyncio.create_task(GAIA(feed=data_feed).run())
        await strategy

    except Exception as e:
        logging.error(f"Critical exception occured: {e}")
        # TODO: Add shutdown sequence here
        raise e
    
    except KeyboardInterrupt:
        logging.info("Shutting down...")


if __name__ == "__main__":
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    asyncio.run(main())