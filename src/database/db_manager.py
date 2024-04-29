import json
import asyncio
import asyncpg
import sshtunnel
import hashlib
import logging

import numpy as np
import pandas as pd
from asyncpg.pool import Pool
from contextlib import asynccontextmanager
from typing import Optional, List, Any, Tuple, Dict

class PGDatabase:
    def __init__(self, min_size: int = 5, max_size: int = 25, **kwargs):
        self.logger = logging.getLogger(__name__)
        self.min_size = min_size
        self.max_size = max_size
        self.pool: Optional[Pool] = None
        # sshtunnel

    async def start(self, config, first_run=False):
        db_params = config.get('TimescaleDB')
        await self.connect(**db_params)

        if first_run:
            await self.first_run()

        database_schema = {
            'Orders': [
                'order_id', 'account_id', 'contract_id', 'order_type', 'side', 
                'qty', 'price', 'timestamp'
            ],
            'OrdersMetadata': [
                'execution_id', 'order_id', 'event_type', 'fill_qty', 
                'fill_price', 'timestamp'
            ],
            'Account': [
                'account_id', 'brokerage', 'balance', 'margin', 'pl_24h', 
                'drawdown_24h', 'timestamp'
            ],
            'Contracts': [
                'id', 'symbol', 'sec_type', 'exchange', 'currency', 
                'multiplier', 'expiration', 'option_right', 'strike'
            ],
            'Positions': [
                'account_id', 'contract_id', 'qty', 'mkt_price', 'timestamp'
            ],
            'HistoricalData': [
                'contract_id', 'open', 'high', 'low', 'close', 
                'spread', 'volume', 'open_interest', 'greeks', 'timestamp'
            ],
            'MarketTrades': [
                'trade_id', 'contract_id', 'order_type', 'side', 
                'qty', 'price', 'timestamp'
            ],
            'LimitOrderBook': [
                'contract_id', 'bids', 'asks', 'timestamp'
            ],
            'CorporateActions': [
                'contract_id', 'action_type', 'description', 'effective_date', 
                'datetime', 'payment_date', 'ratio'
            ],
            'EconomicData': [
                'id', 'country', 'indicator', 'value', 'datetime'
            ],
            'Audit': [
                'id', 'tablechanged', 'changedby', 'changetimestamp', 
                'oldvalue', 'newvalue'
            ]
        }

        failed_tests = []

        async with self.connection() as conn:
            for table_name, columns in database_schema.items():

                exists = await conn.fetchval(f"SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = '{table_name.lower()}')")
                if not exists:
                    self.logger.warning(f"Table missing: {table_name}")
                    continue

                # Check for column integrity
                actual_columns = await conn.fetch(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name.lower()}'")
                actual_column_names = {row['column_name'] for row in actual_columns}

                for column in columns:
                    if column not in actual_column_names:
                        self.logger.warning(f"Column missing or corrupted in {table_name}: {column}")
                # try:
                #     # Insert a test row (use appropriate dummy data for each table)
                #     insert_query = f"INSERT INTO {table_name} (column1, column2, ...) VALUES (%s, %s, ...)"
                #     await conn.execute(insert_query, value1, value2, ...)
                    
                #     # Delete the test row
                #     delete_query = f"DELETE FROM {table_name} WHERE condition"
                #     await conn.execute(delete_query)
                # except Exception as e:
                #     failed_tests.append((table_name, str(e)))
                #     self.logger.error(f"Failed to insert and delete test row in {table_name}: {e}")

        if failed_tests:
            error_message = f"Critical issue in tables: {failed_tests}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

    async def first_run(self):
        with open('src/database/tables.sql', 'r') as file:
            sql_script = file.read()
        
        try:
            async with self.connection() as conn:
                sql_commands = sql_script.split(';')
                for command in sql_commands:
                    if command.strip():  # Check if the command is not empty
                        try:
                            await conn.execute(command)
                        except asyncpg.exceptions.DuplicateObjectError as e:
                            self.logger.debug(f"PostgreSQL: {e}")
                            continue
                        except asyncpg.exceptions.DuplicateTableError as e:
                            self.logger.debug(f"PostgreSQL: {e}")
                            continue
                        except asyncpg.exceptions.UnknownPostgresError as e:
                            if "already a hypertable" in str(e):
                                self.logger.debug(f"Table already a hypertable: {e}")
                                continue
                            else:
                                raise
                self.logger.info("First run sequence was successful.")
        except Exception as e:
            self.logger.error(f"Error initiating tables: {e}")
            raise e
        
    async def connect(self, **kwargs):
        user = kwargs.get('user')
        password = kwargs.get('password', '')  # Password optional
        database = kwargs.get('database')
        host = kwargs.get('host')
        port = kwargs.get('port')

        dsn = f'postgresql://{user}:{password}@{host}:{port}/{database}'

        try:
            self.pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=self.min_size,
                max_size=self.max_size,
                max_queries=50000,
                max_inactive_connection_lifetime=300
                # **self.config
                # Other parameters as needed
            )
            self.logger.info("Connected to PostgresDB.")
        except Exception as e:
            self.logger.error(f"Error initiating Postgres connection pool: {e}")
            raise e

    @asynccontextmanager
    async def connection(self):
        conn = await self.pool.acquire()
        try:
            yield conn
        finally:
            await self.pool.release(conn)

    async def close(self):
        if self.pool:
            self.logger.debug("Closing database connection pool...")
            await self.pool.close()
            self.logger.info("Database connection pool closed.")

    async def get_pool_status(self):
        if not self.pool:
            return "Pool is not initialized"
        
        return {
            "min_size": self.pool._minsize,
            "max_size": self.pool._maxsize,
            "current_size": len(self.pool._holders),
            "free_connections": len([h for h in self.pool._holders if not h._in_use]),
            "used_connections": len([h for h in self.pool._holders if h._in_use]),
        }

    async def execute(self, query: str, *args, timeout: float = None) -> str:
        try:
            async with self.pool.acquire() as conn:
                return await conn.execute(query, *args, timeout=timeout)
        except asyncpg.PostgresError as e:
            self.logger.error(f"Error executing query: {e}")
            raise

    async def execute_many(self, query: str, args_list: List[Tuple], timeout: float = None):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for args in args_list:
                    await conn.execute(query, *args, timeout=timeout)

    async def transaction(self, queries: List[str], timeout: float = None):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for query in queries:
                    await conn.execute(query, timeout=timeout)

    async def fetch(self, query: str, *args, timeout: float = None) -> List[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args, timeout=timeout)

    async def fetchrow(self, query: str, *args, timeout: float = None) -> asyncpg.Record:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args, timeout=timeout)

    async def fetchval(self, query: str, *args, timeout: float = None) -> Any:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args, timeout=timeout)

    async def insert_contract(self, contract: Dict):
        symbol_parts = contract['symbol'].split('/')
        if len(symbol_parts) == 2:
            # If the symbol contains '/', split into symbol and currency.
            symbol, currency = symbol_parts
            contract['symbol'] = symbol
            contract['currency'] = currency
        else:
            symbol = contract['symbol']
            currency = contract.get('currency', 'USD')

        async with self.pool.acquire() as conn:
            contract_id = await conn.fetchval(
                """
                INSERT INTO Contracts (symbol, sec_type, exchange, currency)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (symbol, exchange) DO NOTHING
                RETURNING id
                """,
                symbol, contract['secType'], contract['exchange'], currency
            )
            return contract_id or await conn.fetchval(
                "SELECT id FROM Contracts WHERE symbol = $1 AND exchange = $2",
                symbol, contract['exchange']
            )

    async def fetch_contract_by_symbol_exchange(self, symbol: str, exchange: str) -> Optional[Tuple[int, Dict]]:
        """
        Fetch a single contract by symbol and exchange.
        
        :param symbol: The trading symbol of the contract
        :param exchange: The exchange on which the contract is traded
        :return: A tuple containing the contract ID and a dictionary of contract details if found, else None
        """
        query = """
            SELECT id, symbol, sec_type, exchange, currency, multiplier, expiration, option_right, strike
            FROM Contracts
            WHERE symbol = $1 AND exchange = $2;
        """
        async with self.connection() as conn:
            record = await conn.fetchrow(query, symbol, exchange)
            if record:
                # Extract the ID separately and return the rest as a dictionary
                contract_id = record['id']
                contract_details = {key: record[key] for key in record.keys() if key != 'id'}
                return (contract_id, contract_details)
            return None

    async def fetch_all_contracts(self) -> List[Dict]:
        """
        Fetch all contracts from the database and return them in a list of dictionaries.
        
        :return: List of dictionaries, each containing details of one contract
        """
        query = "SELECT id, symbol, sec_type, exchange, currency, multiplier, expiration, option_right, strike FROM Contracts;"
        async with self.connection() as conn:
            records = await conn.fetch(query)
            return [{key: record[key] for key in record.keys()} for record in records]

    async def store_trade_data(self, trades: List[Dict], contract: Dict):
        contract_id = await self.insert_contract(contract)

        if contract_id:
            trades_records = []
            for trade in trades:
                trade_id = trade.get('trade_id', 0)
                side = trade.get('side')
                qty = trade.get('qty')
                price = trade.get('price')
                timestamp = int(trade.get('timestamp'))
                
                trades_records.append(
                    (trade_id, contract_id, side, qty, price, timestamp)
                )

            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO MarketTrades (trade_id, contract_id, side, qty, price, timestamp)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT DO NOTHING
                    """,
                    trades_records
                )
            self.logger.debug(f"Successfully stored trade data for {contract}.")
        else:
            self.logger.error("Failed to store trade data due to missing contract ID.")

    async def fetch_trades(self, contract_id: int, start_time: Optional[int] = None, end_time: Optional[int] = None) -> np.ndarray:
        """
        Fetch trade data for a given contract and time range, returning it as a flat NumPy array of floats.

        :param contract_id: Contract identifier
        :param start_time: Start of the time range as a Unix timestamp (optional)
        :param end_time: End of the time range as a Unix timestamp (optional)
        :return: NumPy array of shape [sequence length, 5 (trade_id, side as float, qty, price, timestamp)]
        """
        query = """
            SELECT trade_id, side, qty, price, timestamp
            FROM MarketTrades
            WHERE contract_id = $1
        """
        conditions = [contract_id]

        if start_time:
            query += " AND timestamp >= $2"
            conditions.append(start_time)

        if end_time:
            query += " AND timestamp <= $3"
            conditions.append(end_time)

        query += " ORDER BY timestamp"

        async with self.connection() as conn:
            records = await conn.fetch(query, *conditions)
            records = [(rec[4], rec[1], rec[3], rec[2]) for rec in records]
            return np.array(records, dtype=float)

    async def store_order_book_data(self, book: np.ndarray, contract: Dict):
        contract_id = await self.insert_contract(contract)

        if contract_id:
            timestamp, snapshot = book['timestamp'], book['data']  # Access by field name

            midpoint = len(snapshot) // 2
            bids = snapshot[:midpoint]
            asks = snapshot[midpoint:]
            
            bids_list = [(float(price), float(qty)) for price, qty in bids]
            asks_list = [(float(price), float(qty)) for price, qty in asks]
            bids_json = json.dumps(bids_list)
            asks_json = json.dumps(asks_list)

            order_book_records = [(contract_id, bids_json, asks_json, int(timestamp))]
            
            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO LimitOrderBook (contract_id, bids, asks, timestamp)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT DO NOTHING
                    """,
                    order_book_records
                )
            self.logger.debug(f"Successfully stored order book data for {contract}.")
        else:
            self.logger.error("Failed to store order book data due to missing contract ID.")

    async def fetch_order_book(self, contract_id: int, start_time: Optional[int] = None, end_time: Optional[int] = None, num_levels: int = 10) -> List[np.ndarray]:
        """
        Fetch order book data for a given contract and time range, returning a list of arrays where each array contains the combined top N levels of bids and asks.
        
        :param contract_id: Contract identifier
        :param start_time: Start of the time range as a Unix timestamp (optional)
        :param end_time: End of the time range as a Unix timestamp (optional)
        :param num_levels: Number of price levels to return for bids and asks
        :return: List of NumPy arrays, each of shape [num_levels * 2, 2]
        """
        query = """
            SELECT bids, asks
            FROM LimitOrderBook
            WHERE contract_id = $1
        """
        conditions = [contract_id]

        if start_time:
            query += " AND timestamp >= $2"
            conditions.append(start_time)

        if end_time:
            query += " AND timestamp <= $3"
            conditions.append(end_time)

        query += " ORDER BY timestamp"

        async with self.connection() as conn:
            records = await conn.fetch(query, *conditions)
            order_book_snapshots = []

            for record in records:
                bids, asks = self.json_to_numpy(record['bids'], record['asks'])
                combined = np.vstack((bids[:num_levels, :], asks[:num_levels, :]))
                order_book_snapshots.append(combined)

            return np.array(order_book_snapshots)

    async def store_klines_data(self, ohlc_data: np.ndarray, contract: dict):
        contract_id = await self.insert_contract(contract)

        if contract_id:
            timestamp, open_price, high, low, close, volume = ohlc_data[:6]

            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO HistoricalData (contract_id, open, high, low, close, volume, timestamp)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (contract_id, timestamp) DO NOTHING
                    """,
                    contract_id, open_price, high, low, close, volume, timestamp
                )
            self.logger.debug(f"Successfully stored OHLC data for contract {contract}.")
        else:
            self.logger.error("Failed to obtain contract ID for storing OHLC data.")

    async def fetch_candles(self, contract_id: int, start_time: Optional[int] = None, end_time: Optional[int] = None) -> np.ndarray:
        """
        Fetch OHLC data for a given contract and time range, returning it as a flat NumPy array of floats.
        
        :param contract_id: Contract identifier
        :param start_time: Start of the time range as a Unix timestamp (optional)
        :param end_time: End of the time range as a Unix timestamp (optional)
        :return: NumPy array of shape [sequence length, 6 (open, high, low, close, volume, timestamp)]
        """
        query = """
            SELECT open, high, low, close, volume, timestamp
            FROM HistoricalData
            WHERE contract_id = $1
        """
        conditions = [contract_id]

        if start_time:
            query += " AND timestamp >= $2"
            conditions.append(start_time)

        if end_time:
            query += " AND timestamp <= $3"
            conditions.append(end_time)

        query += " ORDER BY timestamp"

        async with self.connection() as conn:
            records = await conn.fetch(query, *conditions)
            return np.array(records, dtype=float)

    @staticmethod
    def json_to_numpy(bids_json: str, asks_json: str) -> Tuple[np.ndarray, np.ndarray]:
        bids_list = json.loads(bids_json)
        asks_list = json.loads(asks_json)
        
        bids_array = np.array(bids_list, dtype=float)
        asks_array = np.array(asks_list, dtype=float)

        return bids_array, asks_array