use std::collections::HashMap;
use streams::ring_buffer::RingBuffer;
use streams::structs::{InventoryItem, Klines, Order, OrderBookData, TradeData};

const BUFFER_CAPACITY: usize = 1024;

#[derive(Debug)]
pub struct Feed {
    symbols: Vec<String>,
    order_books: HashMap<String, RingBuffer<OrderBookData, BUFFER_CAPACITY>>,
    trades: HashMap<String, RingBuffer<TradeData, BUFFER_CAPACITY>>,
    klines: HashMap<String, RingBuffer<Klines, BUFFER_CAPACITY>>,
    // option_chain: Option<todo!()>,
    orders: Vec<Order>,
    inventory: Vec<InventoryItem>,
}

impl Feed {
    pub fn new(symbols: Vec<String>) -> Self {
        let mut feed = Feed {
            symbols,
            trades: HashMap::new(),
            order_books: HashMap::new(),
            klines: HashMap::new(),
            // option_chain: todo!(),
            orders: Vec::new(),
            inventory: Vec::new(),
        };

        // Initialize a ring buffer for each symbol
        for symbol in &feed.symbols {
            feed.trades.insert(symbol.clone(), RingBuffer::new());
            feed.order_books.insert(symbol.clone(), RingBuffer::new());
            feed.klines.insert(symbol.clone(), RingBuffer::new());
        }

        feed
    }

    pub fn update_trade(&mut self, symbol: &str, trade: TradeData) {
        if let Some(buffer) = self.trades.get_mut(symbol) {
            buffer.push(trade);
        }
    }

    pub fn update_order_book(&mut self, symbol: &str, order_book: OrderBookData) {
        if let Some(buffer) = self.order_books.get_mut(symbol) {
            buffer.push(order_book);
        }
    }

    pub fn update_klines(&mut self, symbol: &str, kline: Klines) {
        if let Some(buffer) = self.klines.get_mut(symbol) {
            buffer.push(kline);
        }
    }

    pub fn update_order(&mut self, order: Order) {
        todo!() // self.orders.push(order);
    }

    pub fn update_inventory_item(&mut self, item: InventoryItem) {
        // Check if inventory item for symbol already exists and update it
        if let Some(existing_item) = self.inventory.iter_mut().find(|i| i.symbol == item.symbol) {
            *existing_item = item;
        } else {
            self.inventory.push(item);
        }
    }
}
