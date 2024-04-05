import uvloop
import asyncio
import cProfile
import argparse

from src.feed import Feed
from src.core import GAIA
from src.logger import setup_logger


async def main(profiling=False):
    logging = setup_logger(level='INFO', stream=True)
    
    contracts= ["BTC", "ETH", "SOL"]

    data_feed = Feed(contracts=contracts)
    strategy = asyncio.create_task(GAIA(feed=data_feed).run())
    await strategy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DDQN Market Maker.")
    parser.add_argument('--profile', action='store_true', help='Run Gaia with profiler.')
    args = parser.parse_args()

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    profiler = cProfile.Profile() if args.profile else None

    try:
        if profiler:
            profiler.enable()
            print("WARNING - Running Gaia with profiler!")

        asyncio.run(main(profiling=args.profile))

    except KeyboardInterrupt:
        print("\nShutting down...")

    finally:
        # Ensure profiler stats are printed if profiling was enabled
        if profiler:
            profiler.disable()
            profiler.print_stats()