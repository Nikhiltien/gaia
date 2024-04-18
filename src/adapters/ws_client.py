import gzip
import json
import logging
import threading
import time
import websocket
import queue

from datetime import datetime, timedelta
from enum import Enum

class SocketState(Enum):
    INITIALIZING = 'Initializing'
    CONNECTED = 'Connected'
    RECONNECTING = 'Reconnecting'
    EXITING = 'Exiting'

class WebsocketClient():

    MAX_RECONNECTS = 5
    MAX_RECONNECT_SECONDS = 60
    MIN_RECONNECT_WAIT = 0.1
    TIMEOUT = 55  # Reduced to 30 seconds for faster reaction to timeouts
    NO_MESSAGE_RECONNECT_TIMEOUT = 60
    MAX_QUEUE_SIZE = 100

    def __init__(self, url, ws_name, custom_callback=None, api_key=None, api_secret=None, ping_interval=30, ping_timeout=5, retries=10):
        self.logger = logging.getLogger(__name__)
        self.url = url
        self.ws = None
        self.ws_name = ws_name
        self.api_key = api_key
        self.api_secret = api_secret
        if api_key:
            self.ws_name += " (Auth)"

        self.callback_directory = {}
        self.callback = custom_callback

        # self.ping_interval = ping_interval
        # self.ping_timeout = ping_timeout
        # self.last_pong = datetime.utcnow()
        self.retries = retries

        self._is_binary = False
        self._queue = queue.Queue()
        self.subscriptions = []

        self.read_thread = None
        self.keep_running = True
        self.ws_state = SocketState.INITIALIZING

    # async def _ping_loop(self):
    #     while self.ws_state == SocketState.CONNECTED:
    #         try:
    #             await self.ws.send(json.dumps({"method": "ping"}))
    #             await asyncio.sleep(self.ping_interval)

    #             # Check immediately if a pong response was not received within the timeout.
    #             if (datetime.utcnow() - self.last_pong) > timedelta(seconds=self.ping_interval + self.ping_timeout):
    #                 self.logger.warning("Pong message was not received in time, attempting to reconnect.")
    #                 await self._reconnect()

    #         except Exception as e:
    #             self.logger.error(f"An error occurred in ping loop: {e}")
    #             if self.ws_state != SocketState.EXITING:
    #                 await self._reconnect()

    def _connect(self):
        self.ws_state = SocketState.INITIALIZING
        retries = self.MAX_RECONNECTS
        while self.keep_running and retries > 0:
            try:
                self.ws = websocket.create_connection(self.url)
                self.ws_state = SocketState.CONNECTED
                self.start_read_thread()
                break
            except Exception as e:
                self.logger.error(f"WebSocket connection error: {e}")
                retries -= 1
                time.sleep(5)
            if retries <= 0:
                self.logger.error("Max retries exceeded, unable to connect.")
                self.ws_state = SocketState.EXITING
                self.stop()

    def disconnect(self):
        self.ws_state = SocketState.EXITING
        if self.ws:
            self.ws.close()
            self.logger.info(f"Disconnected from {self.ws_name}")

    def reconnect(self):
        self.logger.info("Attempting to reconnect...")
        self._connect()

    def _handle_message(self, evt):
        if self._is_binary:
            try:
                evt = gzip.decompress(evt)
            except (ValueError, OSError):
                return None
        try:
            message = json.loads(evt)
            if message.get('channel') == 'heartbeat':
                self.logger.debug('Heartbeat message received')
                return None  # Filter heartbeat messages
            elif message.get('channel') == 'pong':
                return None
                # self.last_pong = datetime.utcnow()
            return message
        except ValueError:
            self.logger.debug(f'Error parsing evt json: {evt}')
            return None

    def read_loop(self):
        while self.ws_state == SocketState.CONNECTED:
            try:
                result = self.ws.recv()
                message = self._handle_message(result)
                if message:
                    self._queue.put(message)
            except Exception as e:
                self.logger.error(f"Error in read loop: {e}")
                self.ws_state = SocketState.RECONNECTING
                break
        if self.ws_state == SocketState.RECONNECTING:
            self.reconnect()

    def start_read_thread(self):
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join()
        self.read_thread = threading.Thread(target=self.read_loop)
        self.read_thread.start()

    def recv(self):
        try:
            message = self._queue.get(timeout=self.TIMEOUT)
            if message:
                if self.callback:
                    self.callback(message)
            return message
        except queue.Empty:
            # Handle the timeout condition
            self.logger.debug(f"No message in {self.TIMEOUT} seconds")
            # Optionally, you could add logic here to attempt reconnection or any other custom action
            return None
    
    def stop(self):
        self.keep_running = False
        self.disconnect()
        if self.read_thread:
            self.read_thread.join()