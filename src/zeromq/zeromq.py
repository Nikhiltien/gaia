import os
import zmq
import zmq.asyncio
import json
import logging
import subprocess
from data_pb2 import PriceData, VolumeData, OrderBookData

class ZeroMQ:
    def __init__(self, first_run=False):
        self.logger = logging.getLogger(__name__)
        self.context = zmq.Context()
        self.publisher_ports = iter(range(50000, 50020))
        self.dealer_router_ports = iter(range(50020, 50025))
        if first_run: self.generate_protobuf_file()

    @staticmethod
    def generate_protobuf_file():
        proto_file = 'src/zeromq/data.proto'
        pb2_file = 'src/zeromq/data_pb2.py'

        if not os.path.exists(pb2_file):
            try:
                # Running the protoc command
                subprocess.run(f'protoc --python_out=. {proto_file}', check=True, shell=True)
                print(f"Generated Python file from {proto_file}")
            except subprocess.CalledProcessError as e:
                print(f"Error generating Python file from {proto_file}: {e}")
                # Optionally, you can raise the error to halt the program
                raise e
        else:
            print(f"{pb2_file} already exists.")

    def create_publisher(self, name):
        socket = self.context.socket(zmq.PUB)
        for port in self.publisher_ports:
            try:
                socket.bind(f"tcp://*:{port}")
                break
            except zmq.error.ZMQError as e:
                if e.errno != zmq.EADDRINUSE:
                    raise
        else:
            raise ValueError("No available publisher ports in the range.")
        return PublisherSocket(socket), port

    def create_subscriber(self, port, name):
        socket = self.context.socket(zmq.SUB)
        address = f"tcp://localhost:{port}"
        socket.connect(address)
        socket.setsockopt_string(zmq.SUBSCRIBE, '')
        return SubscriberSocket(socket)

    def create_dealer_socket(self, identity: str = None):
        socket = self.context.socket(zmq.DEALER)
        if identity:
            socket.setsockopt_string(zmq.IDENTITY, identity)
        port = next(self.dealer_router_ports, None)
        if port is None:
            raise ValueError("No available dealer-router ports in the range.")
        socket.bind(f"tcp://*:{port}")
        return DealerSocket(socket), port

    def create_router_socket(self, name):
        socket = self.context.socket(zmq.ROUTER)
        port = next(self.dealer_router_ports, None)
        if port is None:
            raise ValueError("No available dealer-router ports in the range.")
        socket.bind(f"tcp://*:{port}")
        return RouterSocket(socket), port

    def close_all(self):
        self.context.term()

class PublisherSocket:
    def __init__(self, socket):
        self.socket = socket

    def publish_data(self, topic, data):
        if isinstance(data, dict) or isinstance(data, list):
            self.socket.send_string(topic, zmq.SNDMORE)
            self.socket.send_string(json.dumps(data))
        else:
            logging.error("Unsupported data type for publishing")

    def close(self):
        self.socket.close()

class SubscriberSocket:
    def __init__(self, socket):
        self.socket = socket
        self.poller = zmq.asyncio.Poller()
        self.poller.register(socket, zmq.POLLIN)
        self.socket.setsockopt_string(zmq.SUBSCRIBE, '')

    async def listen(self):
        while True:
            try:
                message = await self.receive_message()
                if message:
                    print(f"message123123: {message}")
                else:
                    print("No message received, continuing...")
            except Exception as e:
                logging.error(f"Error listening: {e}")

    async def receive_message(self):
        events = await self.poller.poll(1000)  # Wait for a message with a timeout (e.g., 1000 milliseconds)
        if events:
            # Since we have an event, it's safe to receive without awaiting
            message = self.socket.recv_string(zmq.NOBLOCK)
            return message
        else:
            # No message received within the timeout period
            return None

    def close(self):
        self.socket.close()

class DealerSocket:
    def __init__(self, socket):
        self.socket = socket

    async def send_message(self, message):
        await self.socket.send(message)

    async def receive_message(self):
        message = await self.socket.recv()
        return message

    def close(self):
        self.socket.close()

class RouterSocket:
    def __init__(self, socket):
        self.socket = socket

    async def send_message(self, identity, message):
        await self.socket.send_multipart([identity, b'', message])

    async def receive_message(self):
        identity, _, message = await self.socket.recv_multipart()
        return identity, message

    def close(self):
        self.socket.close()
