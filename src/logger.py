import os
import atexit
import queue
import logging
from datetime import datetime
from logging.handlers import QueueHandler, QueueListener, TimedRotatingFileHandler

class Logger:
    def __init__(self, level='INFO', directory='logs', stream=False, propagate=False):
        self.log_queue = queue.Queue(-1)  # No limit on queue size
        self.queue_handler = QueueHandler(self.log_queue)
        
        os.makedirs(directory, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_filename = f"{today}.log"
        log_path = os.path.join(directory, log_filename)

        self.rot_handler = TimedRotatingFileHandler(
            log_path, when="midnight", interval=1, backupCount=5, encoding='utf-8')
        self.rot_handler.suffix = "%Y-%m-%d"
        self.rot_handler.namer = lambda name: name.replace(".log", "") + ".log"

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.rot_handler.setFormatter(formatter)

        self.queue_listener = QueueListener(self.log_queue, self.rot_handler)
        self.queue_listener.start()

        self.logger = logging.getLogger()
        self.logger.setLevel(level)
        self.logger.addHandler(self.queue_handler)
        self.logger.propagate = propagate

        if stream:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

        atexit.register(self.shutdown)

    def get_logger(self):
        """Returns the configured logger."""
        return self.logger

    def shutdown(self):
        """Stops the queue listener and performs cleanup."""
        self.queue_listener.stop()

def setup_logger(level='INFO', directory='logs', stream=False, propagate=True):
    custom_logger = Logger(level=level, directory=directory, stream=stream, propagate=propagate)
    return custom_logger.get_logger()


if __name__ == "__main__":
    setup_logger(level='INFO', stream=True)
    logging.info("Hello, world!")
