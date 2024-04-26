import uvloop
import asyncio
import argparse
import cProfile

from src.logger import setup_logger
from src.feed import Feed
from src.database.db_manager import PGDatabase
from src.core import GAIA, load_config

logging = setup_logger(level='INFO', stream=True)

async def main(profiling=False, console=False):
    config = load_config()

    database = PGDatabase(config=config)
    await database.start()

    contracts = ["ETH", "BTC", "SOL", "WIF"]
    data_feed = Feed(database=database, contracts=contracts, max_depth=10)
    strategy = asyncio.create_task(GAIA(feed=data_feed, console=console).run())
    await strategy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DDQN Market Maker.")
    parser.add_argument('--profile', action='store_true', help='Run with profiler.')
    parser.add_argument('--console', action='store_true', help='Run with console.')
    args = parser.parse_args()

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    profiler = cProfile.Profile() if args.profile else None
    console = args.console

    try:
        if profiler:
            profiler.enable()
            logging.warn("Running Gaia with profiler!")

        loop.run_until_complete(main(profiling=args.profile, console=console))

    except KeyboardInterrupt:
        logging.info("\nShutting down...")
        for task in asyncio.all_tasks(loop):
            task.cancel()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.stop()

    finally:
        if profiler:
            profiler.disable()
            profiler.print_stats()
        loop.close()