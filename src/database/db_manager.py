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
from typing import Optional, List, Any, Tuple

class PGDatabase:
    def __init__(self, min_size: int = 5, max_size: int = 25, config=None, **kwargs):
        self.logger = logging.getLogger(__name__)
        self.min_size = min_size
        self.max_size = max_size
        self.pool: Optional[Pool] = None
        self.config = config # sshtunnel

    async def start(self, first_run=False):

        db_params = self.config.get('TimescaleDB')
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
        password = kwargs.get('password', '')  # Assuming password might be optional
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
            self.logger.info("Postgres connection started.")
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

    async def insert_contract(self, contract: dict):
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

    async def store_trade_data(self, trades: pd.DataFrame, contract: dict):
        contract_id = await self.insert_contract(contract)

        if contract_id:
            trades_records = []
            for index, row in trades.iterrows():
                # Create a hash trade_id if it's not present
                hash_input_str = f"{row.get('order_type', '')}{row.get('side', '')}{row.qty}{row.price}{row.timestamp.timestamp()}"
                trade_id = int(hashlib.sha256(hash_input_str.encode()).hexdigest(), 16) & ((1 << 31) - 1)
                
                trades_records.append(
                    (trade_id, contract_id, row.get('order_type'), row.get('side'), row.qty, row.price, int(row.timestamp.timestamp() * 1_000_000))
                )

            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO MarketTrades (trade_id, contract_id, order_type, side, qty, price, timestamp)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT DO NOTHING
                    """,
                    trades_records
                )
            self.logger.info("Successfully stored trade data.")
        else:
            self.logger.error("Failed to store trade data due to missing contract ID.")

    async def store_order_book_data(self, order_books: pd.DataFrame, contract: dict):
        contract_id = await self.insert_contract(contract)

        if contract_id:
            order_book_records = []
            for index, row in order_books.iterrows():
                # Filter out NaN values from bids and asks and serialize
                timestamp = int(row.name.timestamp() * 1_000)
                bids = {col.split(':')[1]: row[col] for col in order_books.columns if col.startswith('bid') and not np.isnan(row[col])}
                asks = {col.split(':')[1]: row[col] for col in order_books.columns if col.startswith('ask') and not np.isnan(row[col])}
                bids_json = json.dumps(bids)
                asks_json = json.dumps(asks)

                order_book_records.append((contract_id, bids_json, asks_json, timestamp))

            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO LimitOrderBook (contract_id, bids, asks, timestamp)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT DO NOTHING
                    """,
                    order_book_records
                )
            self.logger.info("Successfully stored order book data.")
        else:
            self.logger.error("Failed to store order book data due to missing contract ID.")