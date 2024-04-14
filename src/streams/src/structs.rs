use abomonation_derive::Abomonation;
use serde::de::{self, Visitor};
use serde::{Deserialize, Deserializer, Serialize};
use std::fmt;

#[derive(Debug, Serialize, Deserialize, Abomonation, Clone)]
pub struct TradeData {
    pub exchange: Option<String>,
    pub symbol: String,
    pub timestamp: u64,
    pub price: f64,
    pub qty: f64,
    pub side: Option<u8>,
    pub ord_type: Option<String>,
    pub trade_id: Option<u64>,
}

#[derive(Debug, Serialize, Clone, Abomonation)]
pub struct BatchTrades {
    pub exchange: String,
    pub symbol: String,
    pub timestamp: u64,
    pub num_buys: u64,
    pub avg_buy_price: f64,
    pub total_buy_qty: f64,
    pub num_sells: u64,
    pub avg_sells_price: f64,
    pub total_sells_qty: f64,
}

#[derive(Debug, Serialize, Deserialize, Abomonation, Clone)]
pub struct OrderBookData {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub exchange: Option<String>,
    pub symbol: String,
    #[serde(deserialize_with = "deserialize_timestamp")]
    pub timestamp: u64,
    pub asks: Vec<OrderBookEntry>,
    pub bids: Vec<OrderBookEntry>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub checksum: Option<u32>,
}

impl OrderBookData {
    pub fn new(
        symbol: String,
        timestamp: u64,
        asks: Vec<OrderBookEntry>,
        bids: Vec<OrderBookEntry>,
        checksum: Option<u32>,
    ) -> Self {
        OrderBookData {
            exchange: None,
            symbol,
            timestamp,
            asks,
            bids,
            checksum,
        }
    }

    pub fn apply_asks_updates(&mut self, updates: Vec<OrderBookEntry>) {
        Self::apply_side_updates(&mut self.asks, updates);
        self.asks.sort_by(|a, b| {
            a.price
                .partial_cmp(&b.price)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
    }

    pub fn apply_bids_updates(&mut self, updates: Vec<OrderBookEntry>) {
        Self::apply_side_updates(&mut self.bids, updates);
        self.bids.sort_by(|a, b| {
            b.price
                .partial_cmp(&a.price)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
    }

    fn apply_side_updates(current_side: &mut Vec<OrderBookEntry>, updates: Vec<OrderBookEntry>) {
        for update in updates {
            if update.qty == 0.0 {
                current_side.retain(|entry| {
                    let retain = entry.price != update.price;
                    retain
                });
            } else {
                match current_side
                    .iter_mut()
                    .find(|entry| entry.price == update.price)
                {
                    Some(entry) => entry.qty = update.qty,
                    None => {
                        current_side.push(update);
                    }
                }
            }
        }
    }

    pub fn truncate_to_depth(&mut self) {
        const DEPTH: usize = 10;

        self.asks.sort_by(|a, b| {
            a.price
                .partial_cmp(&b.price)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        self.bids.sort_by(|a, b| {
            b.price
                .partial_cmp(&a.price)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        self.asks.truncate(DEPTH);
        self.bids.truncate(DEPTH);
    }
}

#[derive(Debug, Serialize, Deserialize, Abomonation, Clone)]
pub struct OrderBookEntry {
    pub price: f64,
    pub qty: f64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Klines {
    pub exchange: Option<String>,
    pub symbol: String,
    pub candles: Vec<Candle>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Candle {
    pub timestamp: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Order {
    pub symbol: String,
    pub side: u8,
    pub price: f64,
    pub qty: f64,
    pub order_id: u64,
    pub timestamp: u64,
    pub status: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct InventoryItem {
    pub symbol: String,
    pub qty: f64,
    pub avg_price: f64,
    pub leverage: f64,
}

fn deserialize_timestamp<'de, D>(deserializer: D) -> Result<u64, D::Error>
where
    D: Deserializer<'de>,
{
    struct TimestampVisitor;

    impl<'de> Visitor<'de> for TimestampVisitor {
        type Value = u64;

        fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
            formatter.write_str("a floating point or integer timestamp")
        }

        fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            Ok(value.round() as u64)
        }

        fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            Ok(value)
        }
    }

    deserializer.deserialize_any(TimestampVisitor)
}
