import time
import msgpack
import eth_account

from eth_utils import keccak, to_hex
from eth_account.messages import encode_structured_data, encode_defunct
from src.adapters.post_client import API
from src.adapters.HyperLiquid.endpoints import BaseEndpoints, RestLinks

class Authenticator(API):
    def __init__(self, private_key):
        if not private_key:
            raise ValueError("Private key cannot be empty")
        self.account = eth_account.Account.from_key(private_key)

    def generate_nonce(self):
        """Generate a nonce based on the current timestamp."""
        return int(time.time() * 1000)

    def construct_order_object(self, asset, quantity, price, order_type, is_buy):
        """Constructs an order object based on given parameters."""
        return {
            "asset": asset,
            "quantity": quantity,
            "price": price,
            "order_type": order_type,
            "is_buy": is_buy,
        }

    def serialize_order(self, order_object):
        """Serializes the order object using msgpack."""
        return msgpack.packb(order_object)

    def create_hash(self, serialized_order, nonce, vault_address=None):
        """Creates a hash of the serialized order, nonce, and optionally the vault address."""
        data = serialized_order + nonce.to_bytes(8, 'big')
        data += b'\x01' + bytes.fromhex(vault_address[2:]) if vault_address else b'\x00'
        return keccak(data)

    def sign_order(self, order_object, nonce, vault_address=None):
        """Signs the order using the private key."""
        serialized_order = self.serialize_order(order_object)
        order_hash = self.create_hash(serialized_order, nonce, vault_address)
        signature = self.account.sign_message(encode_defunct(order_hash))
        return {
            'r': to_hex(signature.r),
            's': to_hex(signature.s),
            'v': signature.v
        }

    def _generate_eip712_signature(self, action, nonce, is_mainnet):
        """Generates an EIP-712 signature for the given action."""
        action_hash = self.create_hash(msgpack.packb(action), nonce)
        phantom_agent = {'source': 'a' if is_mainnet else 'b', 'connectionId': to_hex(action_hash)}

        data = {
            'domain': {
                'chainId': 1 if is_mainnet else 4,
                'name': 'HyperLiquid',
                'verifyingContract': '0x0000000000000000000000000000000000000000',
                'version': '1',
            },
            'message': phantom_agent,
            'primaryType': 'Agent',
            'types': {
                'EIP712Domain': [
                    {'name': 'name', 'type': 'string'},
                    {'name': 'version', 'type': 'string'},
                    {'name': 'chainId', 'type': 'uint256'},
                    {'name': 'verifyingContract', 'type': 'address'},
                ],
                'Agent': [
                    {'name': 'source', 'type': 'string'},
                    {'name': 'connectionId', 'type': 'bytes32'},
                ],
            },
        }

        structured_data = encode_structured_data(data)
        signed = self.account.sign_message(structured_data)
        return {'r': to_hex(signed.r), 's': to_hex(signed.s), 'v': signed.v}

# Usage example
# env_path = os.path.join(os.getcwd(), '../../keys/private_key.env')

# load_dotenv(dotenv_path=env_path)
# PRIVATE_KEY = os.getenv('PRIVATE_KEY_MAIN')

# authenticator = Authenticator(PRIVATE_KEY)
# api = API(base_url=BaseEndpoints.MAINNET)

# # Construct and sign an order
# order = authenticator.construct_order_object('ETH', 1, 1000, 'limit', True)
# nonce = authenticator.generate_nonce()
# signature = authenticator.sign_order(order, nonce)

# # The `sign_order` might need adjustment to return signature in the desired format for the API.
# # Now post the order using the API client
# response = api.post_order(order, signature, nonce)

# # Print or process the response from the order submission
# print(response)