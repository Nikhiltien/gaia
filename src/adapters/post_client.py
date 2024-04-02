import json
import logging
from src.adapters.HyperLiquid.endpoints import RestLinks
from json.decoder import JSONDecodeError

import requests

class API:
    def __init__(self, base_url=None):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._logger = logging.getLogger(__name__)

    def post(self, url_path: str, payload=None):
        payload = payload or {}
        url = self.base_url + url_path
        response = self.session.post(url, json=payload)
        
        try:
            response.raise_for_status()  # Raises HTTPError for bad responses
            return response.json()
        except requests.HTTPError as http_err:
            self._logger.error(f"HTTP error occurred: {http_err}")  # Log HTTP errors
            raise
        except JSONDecodeError:
            self._logger.error(f"Could not parse JSON response: {response.text}")
            raise ValueError(f"Could not parse JSON: {response.text}")

    def _handle_exception(self, response):
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            error_msg = f"HTTP Error: {e.response.status_code}"
            if response.text:
                try:
                    error_details = response.json()
                    error_msg += f" - Details: {error_details}"
                except JSONDecodeError:
                    error_msg += " - Non-JSON response"
            self._logger.error(error_msg)
            raise ValueError(error_msg) from None

    def post_order(self, order, signature, nonce, vault_address=None):
        url_path = RestLinks.EXCHANGE
        headers = {"Content-Type": "application/json"}
        payload = {
            "action": order,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": vault_address or ""
        }

        return self.post(url_path, payload)