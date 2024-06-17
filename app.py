import uvloop
import asyncio
import argparse
import cProfile
import src.console as console

from multiprocessing import Process
from src.logger import setup_logger
from src.feed import Feed
from src.core import GAIA

logging = setup_logger(level='INFO', stream=True)

async def main(profiling=False, console=False):

    contracts = ["ETH", "BTC", "SOL", "WIF"]
    data_feed = Feed(contracts=contracts, max_depth=10)
    strategy = asyncio.create_task(GAIA(data_feed).run())
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
    if args.console:
        # Start the console in a separate process
        console_process = Process(target=console.main())
        console_process.start()

    try:
        if profiler:
            profiler.enable()
            logging.warning("Running Gaia with profiler!")

        loop.run_until_complete(main(profiling=args.profile))

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

        if args.console:
            console_process.join()
