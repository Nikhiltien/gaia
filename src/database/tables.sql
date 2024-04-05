CREATE TYPE order_type_enum AS ENUM ('market', 'limit', 'cancel', 'take_profit', 'stop_loss', 'iceberg');
CREATE TYPE event_type_enum AS ENUM ('filled', 'partial_fill', 'canceled');
CREATE TYPE side_enum AS ENUM ('buy', 'sell');
CREATE TYPE sec_type_enum AS ENUM ('STK', 'OPT', 'FUT', 'CRYPTO', 'BOND', 'FX', 'PERP');
CREATE TYPE option_right_enum AS ENUM ('call', 'put');
CREATE TYPE corp_action_type_enum AS ENUM ('earnings', 'dividend', 'split', 'merger', 'spin_off', 'rights_issue');

-- Account Table
CREATE TABLE Account (
    account_id TEXT PRIMARY KEY,
    brokerage VARCHAR(50) NOT NULL,
    balance NUMERIC NOT NULL,
    margin NUMERIC NOT NULL,
    pl_24h NUMERIC,
    drawdown_24h NUMERIC,
    timestamp BIGINT NOT NULL
);

-- Contracts Table
CREATE TABLE Contracts (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    sec_type sec_type_enum NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    currency VARCHAR(50) NOT NULL,
    multiplier NUMERIC,
    expiration DATE,
    option_right option_right_enum,
    strike NUMERIC,
    UNIQUE(symbol, exchange)
);
CREATE INDEX idx_contracts_symbol ON Contracts(symbol);

-- Orders Table
CREATE TABLE Orders (
    order_id INT PRIMARY KEY,
    account_id TEXT REFERENCES Account(account_id),
    contract_id INT REFERENCES Contracts(id),
    order_type order_type_enum NOT NULL,
    side side_enum NOT NULL,
    qty NUMERIC NOT NULL,
    price NUMERIC NOT NULL,
    timestamp BIGINT NOT NULL
);

CREATE INDEX idx_orders_account_id ON Orders(account_id);
CREATE INDEX idx_orders_contract_id ON Orders(contract_id);

-- OrdersMetadata Table
CREATE TABLE OrdersMetadata (
    execution_id SERIAL NOT NULL,
    order_id INT REFERENCES Orders(order_id),
    event_type event_type_enum NOT NULL,
    fill_qty NUMERIC NOT NULL,
    fill_price NUMERIC NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    UNIQUE(execution_id, timestamp)
);

SELECT create_hypertable('OrdersMetadata', 'timestamp');
CREATE INDEX idx_ordersmetadata_order_id ON OrdersMetadata(order_id);

-- Positions Table
CREATE TABLE Positions (
    account_id TEXT REFERENCES Account(account_id),
    contract_id INT REFERENCES Contracts(id),
    qty NUMERIC NOT NULL,
    mkt_price NUMERIC NOT NULL,
    timestamp BIGINT NOT NULL,
    UNIQUE(account_id, timestamp)
);

SELECT create_hypertable('Positions', 'timestamp');
CREATE INDEX idx_positions_account_id ON Positions(account_id);
CREATE INDEX idx_positions_contract_id ON Positions(contract_id);

-- HistoricalData Table
CREATE TABLE HistoricalData (
    contract_id INT REFERENCES Contracts(id),
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC NOT NULL,
    spread NUMERIC,
    volume NUMERIC NOT NULL,
    open_interest INT,
    greeks JSON,
    timestamp BIGINT NOT NULL,
    UNIQUE (contract_id, timestamp)
);

SELECT create_hypertable('HistoricalData', 'timestamp');
CREATE INDEX idx_historicaldata_contract_id ON HistoricalData(contract_id);

-- MarketTrades Table
CREATE TABLE MarketTrades (
    trade_id INT NOT NULL,
    contract_id INT REFERENCES Contracts(id),
    order_type order_type_enum,
    side side_enum,
    qty NUMERIC NOT NULL,
    price NUMERIC NOT NULL,
    timestamp BIGINT NOT NULL,
    UNIQUE (trade_id, timestamp)
);
SELECT create_hypertable('MarketTrades', 'timestamp');
CREATE INDEX idx_markettrades_contract_id ON MarketTrades(contract_id);

-- LimitOrderBook Table
CREATE TABLE LimitOrderBook (
    contract_id INT REFERENCES Contracts(id),
    bids JSON NOT NULL,
    asks JSON NOT NULL,
    timestamp BIGINT NOT NULL
);
SELECT create_hypertable('LimitOrderBook', 'timestamp');

-- CorporateActions Table
CREATE TABLE CorporateActions (
    contract_id INT REFERENCES Contracts(id),
    action_type corp_action_type_enum NOT NULL,
    description TEXT,
    effective_date TIMESTAMP NOT NULL,
    datetime TIMESTAMP NOT NULL,
    payment_date TIMESTAMP,
    ratio NUMERIC,
    UNIQUE (contract_id, datetime, action_type)
);

CREATE INDEX idx_corporateactions_contract_id ON CorporateActions(contract_id);
SELECT create_hypertable('CorporateActions', 'datetime');

-- EconomicData Table
CREATE TYPE economic_data_indicator_enum AS ENUM ('GDP', 'inflation_rate', 'unemployment_rate', 'interest_rate', 'consumer_spending');

CREATE TABLE EconomicData (
    id UUID,
    country VARCHAR(50) NOT NULL,
    indicator economic_data_indicator_enum NOT NULL,
    value NUMERIC NOT NULL,
    datetime TIMESTAMP NOT NULL
);

CREATE INDEX idx_economicdata_datetime ON EconomicData(datetime);
CREATE INDEX idx_economicdata_indicator ON EconomicData(indicator);
SELECT create_hypertable('EconomicData', 'datetime');

-- Audit Table
CREATE TABLE Audit (
    id SERIAL PRIMARY KEY,
    TableChanged VARCHAR(50) NOT NULL,
    ChangedBy INT NOT NULL,
    ChangeTimestamp TIMESTAMP NOT NULL,
    OldValue TEXT,
    NewValue TEXT
);
