use crate::structs::{OrderBookData, TradeData};
use rustis::{
    client::Client,
    commands::{
        HashCommands, SortedSetCommands, StringCommands, TimeSeriesCommands, TsAddOptions,
        TsCreateOptions,
    },
    Error, Result as RustisResult,
};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::sync::Mutex;

#[derive(Clone)]
pub struct TimeSeriesClient {
    client: Arc<Mutex<Client>>,
    // Maintain a map to track the last sequence number for each unique timestamp-key combination
    sequence_numbers: Arc<Mutex<std::collections::HashMap<String, u64>>>,
}

impl TimeSeriesClient {
    pub async fn new(client: Arc<Mutex<Client>>) -> Self {
        TimeSeriesClient {
            client,
            sequence_numbers: Arc::new(Mutex::new(std::collections::HashMap::new())),
        }
    }

    pub async fn insert_trade_data(
        &self,
        trade_data: &TradeData,
        exchange: &str,
    ) -> RustisResult<()> {
        let key = format!("trades:{}:{}", exchange, trade_data.symbol);

        // Construct the unique key for the sequence number map
        let sequence_key = format!("{}:{}", key, trade_data.timestamp);

        let unique_timestamp = {
            // Lock the sequence number map to safely increment and retrieve the sequence number
            let mut seq_nums = self.sequence_numbers.lock().await;
            let sequence_number = seq_nums.entry(sequence_key).or_insert(0);
            *sequence_number += 1;

            // Calculate the unique timestamp by appending the sequence number
            trade_data.timestamp as i64 * 1000 + *sequence_number as i64
        };

        let price: f64 = trade_data.price;
        let qty: f64 = trade_data.qty;

        let mut client_guard = self.client.lock().await;

        let price_key = format!("{}:price", key);
        client_guard
            .ts_add(price_key, unique_timestamp, price, TsAddOptions::default())
            .await?;

        let qty_key = format!("{}:qty", key);
        client_guard
            .ts_add(qty_key, unique_timestamp, qty, TsAddOptions::default())
            .await?;

        Ok(())
    }

    pub async fn insert_ema_value(
        &self,
        exchange: &str,
        symbol: &str,
        ema_key_suffix: &str, // e.g., "ema30"
        ema_value: f64,
        timestamp: u64,
    ) -> RustisResult<()> {
        // Generate the key for storing the EMA value
        let key = format!("trades:{}:{}:{}", exchange, symbol, ema_key_suffix);

        // Construct the unique key for the sequence number map
        let sequence_key = format!("{}:{}", key, timestamp);

        let unique_timestamp = {
            // Lock the sequence number map to safely increment and retrieve the sequence number
            let mut seq_nums = self.sequence_numbers.lock().await;
            let sequence_number = seq_nums.entry(sequence_key).or_insert(0);
            *sequence_number += 1;

            // Calculate the unique timestamp by appending the sequence number
            timestamp as i64 * 1000 + *sequence_number as i64
        };

        let mut client_guard = self.client.lock().await;

        // Store the EMA value using a time series add command and ignore the returned id.
        client_guard
            .ts_add(&key, unique_timestamp, ema_value, TsAddOptions::default())
            .await
            .map(|_| ()) // Map the success value from u64 to ()
    }

    pub async fn insert_order_book_snapshot(
        &self,
        order_book_data: &OrderBookData,
    ) -> RustisResult<()> {
        let exchange = order_book_data.exchange.as_ref().unwrap();
        let timestamp_ms = current_unix_timestamp_ms();

        let order_book_key = format!(
            "order_book:{}:{}:{}",
            exchange, order_book_data.symbol, timestamp_ms
        );

        let mut client_guard = self.client.lock().await;

        let mut asks_bids = Vec::new();
        for ask in &order_book_data.asks {
            let field = format!("ask:{}", ask.price);
            asks_bids.push((field, ask.qty.to_string()));
        }

        for bid in &order_book_data.bids {
            let field = format!("bid:{}", bid.price);
            asks_bids.push((field, bid.qty.to_string()));
        }

        client_guard.hset(&order_book_key, asks_bids).await?;

        let ts_key = format!("ts:order_book:{}:{}", exchange, order_book_data.symbol);
        client_guard
            .ts_add(&ts_key, timestamp_ms, 1.0, TsAddOptions::default())
            .await?;

        Ok(())
    }

    // pub async fn insert_order_data(
    //     &self,
    //     contract: &ReceivedContract,
    //     order: &ReceivedOrder,
    //     status: &OrderStatus,
    //     exchange: &str,
    // ) -> RustisResult<()> {
    //     let timestamp_ms = current_unix_timestamp_ms();

    //     let symbol = contract.details["symbol"].as_str().unwrap_or_default();

    //     let security_type_str = match contract.contract_type {
    //         SecurityType::Future => "FUT",
    //         SecurityType::Crypto => "CRYPTO",
    //         SecurityType::Option => "OPT",
    //         SecurityType::Stock => "STK",
    //         SecurityType::Perpetual => "PERP",
    //     };

    //     let order_data_key = format!(
    //         "orders:{}:{}:{}:{}",
    //         exchange, security_type_str, symbol, timestamp_ms
    //     );

    //     let mut client_guard = self.client.lock().await;

    //     let lmt_price = if order.orderType == "MKT" {
    //         0.0
    //     } else {
    //         order.lmtPrice
    //     };

    //     let order_data = vec![
    //         ("orderId", order.orderId.to_string()),
    //         ("action", order.action.clone()),
    //         ("totalQuantity", order.totalQuantity.to_string()),
    //         ("orderType", order.orderType.clone()),
    //         ("lmtPrice", lmt_price.to_string()),
    //         ("orderStatus", status.status.clone()),
    //         ("remaining", status.remaining.to_string()),
    //         ("avgFillPrice", status.avgFillPrice.to_string()),
    //         ("lastFillPrice", status.lastFillPrice.to_string()),
    //     ];

    //     client_guard.hset(&order_data_key, order_data).await?;

    //     let ts_key = format!("ts:orders:{}:{}", exchange, symbol);
    //     client_guard
    //         .ts_add(&ts_key, timestamp_ms, 1.0, TsAddOptions::default())
    //         .await?;

    //     Ok(())
    // }

    // pub async fn insert_account_data(&self, account_data: &AccountValue) -> RustisResult<()> {
    //     let key = format!("account:{}:{}", account_data.account, account_data.tag);
    //     let timestamp_ms = current_unix_timestamp_ms();

    //     let mut client_guard = self.client.lock().await;

    //     // Store the account value
    //     client_guard
    //         .ts_add(
    //             &key,
    //             timestamp_ms,
    //             account_data.value.parse::<f64>().unwrap_or(0.0),
    //             TsAddOptions::default(),
    //         )
    //         .await?;

    //     Ok(())
    // }

    // pub async fn insert_position_data(&self, position: &Position) -> RustisResult<()> {
    //     let key = format!("position:{}", position.symbol);
    //     let timestamp_ms = current_unix_timestamp_ms();

    //     let position_value = position.position;
    //     let _market_value = position.market_value.unwrap_or(0.0); // Assuming market_value is essential; otherwise, adapt logic

    //     let mut client_guard = self.client.lock().await;

    //     // Store the position quantity
    //     client_guard
    //         .ts_add(
    //             &format!("{}:qty", key),
    //             timestamp_ms,
    //             position_value,
    //             TsAddOptions::default(),
    //         )
    //         .await?;

    //     // Store the market value if available
    //     if let Some(mv) = position.market_value {
    //         client_guard
    //             .ts_add(
    //                 &format!("{}:market_value", key),
    //                 timestamp_ms,
    //                 mv,
    //                 TsAddOptions::default(),
    //             )
    //             .await?;
    //     }

    //     Ok(())
    // }
}

fn current_unix_timestamp_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("Time went backwards")
        .as_millis() as i64
}
