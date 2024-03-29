from src.logger import setup_logger

if __name__ == "__main__":
    logging = setup_logger(level='INFO', stream=False)
    logging.info("Hello, world!")
