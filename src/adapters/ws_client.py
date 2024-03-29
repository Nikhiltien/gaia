import gzip
import json
import asyncio
import logging
import websockets

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
    TIMEOUT = 10
    NO_MESSAGE_RECONNECT_TIMEOUT = 60
    MAX_QUEUE_SIZE = 100

    def __init__(self, url, ws_name, custom_callback=None, api_key=None, api_secret=None, ping_interval=20, ping_timeout=10, retries=10):
        self.loop = asyncio.get_event_loop()
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

        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.retries = retries

        self._is_binary = False
        self._queue = asyncio.Queue()
        self.subscriptions = []

        self._handle_read_loop = None
        self.ws_state = SocketState.INITIALIZING

    async def _connect(self):
        self.ws_state = SocketState.INITIALIZING
        retries = self.retries
        if self.ws_state != SocketState.EXITING and (retries > 0 or retries == 0):
            try:
                # async with websockets.connect(self.url) as ws:
                    self.ws = await websockets.connect(self.url)
                    self.ws_state = SocketState.CONNECTED
                    self.retries = 0
                    # if self.api_key and self.api_secret:
                    #     await self._authenticate()

                    # await self._after_connect()
                    if not self._handle_read_loop:
                        self._handle_read_loop = asyncio.create_task(self._read_loop())
            except Exception as e:  # More specific exception handling recommended
                self.logger.error(f"WebSocket connection error: {e}")
                retries -= 1
                if retries > 0:
                    await asyncio.sleep(5)  # wait before retrying
                else:
                    raise

    async def _disconnect(self):
        if self.ws and self.ws.open:
            self.ws_state = SocketState.EXITING
            await self.ws.close()
            self.logger.info(f"Disconnected from {self.ws_name}")
            if self._handle_read_loop:
                self._handle_read_loop.cancel()
                self._handle_read_loop = None

    async def _reconnect(self):
        self.ws_state = SocketState.RECONNECTING
        retry_delay = self.MIN_RECONNECT_WAIT

        for attempt in range(self.MAX_RECONNECTS):
            try:
                await asyncio.sleep(retry_delay)
                await self._connect()
                self.logger.info(f"Reconnected on attempt {attempt+1}")
                return
            except Exception as e:
                self.logger.error(f"Reconnect attempt {attempt+1} failed: {e}")
                retry_delay = min(retry_delay * 2, self.MAX_RECONNECT_SECONDS)

        self.logger.error("Max reconnection attempts reached. Exiting.")
        self.ws_state = SocketState.EXITING

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
            return message
        except ValueError:
            self.logger.debug(f'Error parsing evt json: {evt}')
            return None

    async def _read_loop(self):
        while self.ws_state != SocketState.EXITING:
            # if self.ws and not self.ws.closed and self.ws_state == SocketState.CONNECTED:
                try:
                    message = await asyncio.wait_for(self.ws.recv(), timeout=self.TIMEOUT)
                    message = self._handle_message(message)
                    if message:
                        await self._queue.put(message)
                except websockets.exceptions.ConnectionClosed:
                    self.logger.info("WebSocket connection closed, attempting to reconnect.")
                    await self._reconnect()
                except asyncio.TimeoutError:
                    self.logger.warning("No message received in the last {} seconds.".format(self.TIMEOUT))

    async def recv(self):
        res = None
        while not res:
            try:
                res = await asyncio.wait_for(self._queue.get(), timeout=self.TIMEOUT)
                if res:
                    self.callback(res)
            except asyncio.TimeoutError:
                self.logger.debug(f"no message in {self.TIMEOUT} seconds")
        return res