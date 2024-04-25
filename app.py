import uvloop
import asyncio
import argparse
import cProfile

from src.feed import Feed
from src.core import GAIA
from src.logger import setup_logger


async def main(profiling=False):
    logging = setup_logger(level='INFO', stream=True)
    logging.info("Starting Gaia...")
    
    contracts = ["ETH"] # , "BTC"]

    data_feed = Feed(contracts=contracts, max_depth=10)
    strategy = asyncio.create_task(GAIA(data_feed).run())
    await strategy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DDQN Market Maker.")
    parser.add_argument('--profile', action='store_true', help='Run Gaia with profiler.')
    args = parser.parse_args()

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    profiler = cProfile.Profile() if args.profile else None

    try:
        if profiler:
            profiler.enable()
            print("WARNING - Running Gaia with profiler!")

        loop.run_until_complete(main(profiling=args.profile))

    except KeyboardInterrupt:
        print("\nShutting down...")
        for task in asyncio.all_tasks(loop):
            task.cancel()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.stop()

    finally:
        if profiler:
            profiler.disable()
            profiler.print_stats()
        loop.close()