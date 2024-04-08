import os
import zmq
import zmq.asyncio
import json
import logging
import subprocess
import src.zeromq.data_pb2

from typing import Any, Dict


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

    def create_publisher(self, port: int):
        socket = self.context.socket(zmq.PUB)
        socket.bind(f"tcp://*:{port}")
        # for port in self.publisher_ports:
        #     try:
        #         socket.bind(f"tcp://*:{port}")
        #         break
        #     except zmq.error.ZMQError as e:
        #         if e.errno != zmq.EADDRINUSE:
        #             raise
        # else:
        #     raise ValueError("No available publisher ports in the range.")
        return PublisherSocket(socket)

    def create_subscriber(self, port, name):
        socket = self.context.socket(zmq.SUB)
        address = f"tcp://localhost:{port}"
        socket.connect(address)
        socket.setsockopt_string(zmq.SUBSCRIBE, '')
        return SubscriberSocket(socket)

    def create_dealer_socket(self, port: int, identity: str = None):
        socket = self.context.socket(zmq.DEALER)
        if identity:
            socket.setsockopt_string(zmq.IDENTITY, identity)
        address = f"tcp://localhost:{port}"
        socket.connect(address)
        return DealerSocket(socket)

    def create_router_socket(self, port: int):
        socket = self.context.socket(zmq.ROUTER)
        address = f"tcp://*:{port}"
        socket.bind(address)
        return RouterSocket(socket)

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
    def __init__(self, socket: zmq.Socket):
        self.socket = socket
        self.poller = zmq.asyncio.Poller()
        self.poller.register(socket, zmq.POLLIN)
        self.socket.setsockopt_string(zmq.SUBSCRIBE, '')

    async def listen(self, callback: Any) -> Dict:
        """
        Callback must be async AND takes 2 arguments, topic and data.
        """
        while True:
            events = await self.poller.poll()  # Await events without blocking
            if events:
                try:
                    parts = self.socket.recv_multipart()
                    if len(parts) == 2:
                        topic, message = parts[0].decode(), parts[1].decode()
                        data = json.loads(message)
                        await callback(topic, data)
                except zmq.Again:
                    continue
                except json.JSONDecodeError:
                    logging.error("Invalid JSON received.")
                except Exception as e:
                    logging.error(f"Error listening: {e}")

    def close(self):
        self.socket.close()

class DealerSocket:
    def __init__(self, socket: zmq.Context):
        self.socket = socket

    async def send_message(self, message: Any) -> Any:
        serialized_message = json.dumps(message).encode('utf-8')
        self.socket.send(serialized_message, timeout=2)
        print(message if message else "ERROR")

    async def receive_message(self: Any) -> Any:
        message = self.socket.recv()
        # Assume the incoming message is JSON serialized.
        deserialized_message = json.loads(message.decode('utf-8'))
        return deserialized_message

    def close(self):
        self.socket.close()

class RouterSocket:
    def __init__(self, socket):
        self.socket = socket

    async def send_message(self, identity, message):
        # Assume 'message' is a Python tuple.
        serialized_message = json.dumps(message).encode('utf-8')
        self.socket.send_multipart([identity, b'', serialized_message])

    async def receive_message(self):
        identity, _, message = self.socket.recv_multipart()
        # Assume the incoming message is JSON serialized.
        deserialized_message = json.loads(message.decode('utf-8'))
        print(identity, deserialized_message)
        return deserialized_message

    def close(self):
        self.socket.close()