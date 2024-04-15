use dasp_ring_buffer::Fixed;
use std::collections::HashMap;
use streams::structs::{InventoryItem, Klines, Order, OrderBookData, TradeData};

const BUFFER_CAPACITY: usize = 200;

#[derive(Debug)]
pub struct Feed {
    symbols: Vec<String>,
    orders: Vec<Order>,
    inventory: Vec<InventoryItem>,
    order_books: HashMap<String, Fixed<OrderBookData>>,
    trades: HashMap<String, Fixed<TradeData>>,
    // klines: HashMap<String, Fixed<Klines>>,
    // option_chain: Option<todo!()>,
}

impl Feed {
    pub fn new(symbols: Vec<String>) -> Self {
        let mut feed = Feed {
            symbols,
            orders: Vec::new(),
            inventory: Vec::new(),
            trades: HashMap::new(),
            order_books: HashMap::new(),
            // klines: HashMap::new(),
            // option_chain: todo!(),
        };

        for symbol in &feed.symbols {
            feed.trades.insert(
                symbol.clone(),
                Fixed::from(vec![TradeData::default(); BUFFER_CAPACITY]),
            );
            feed.order_books.insert(
                symbol.clone(),
                Fixed::from(vec![OrderBookData::default(); BUFFER_CAPACITY]),
            );
            // feed.klines.insert(
            //     symbol.clone(),
            //     Fixed::from(vec![Klines::default(); BUFFER_CAPACITY]),
            // );
        }

        feed
    }

    pub fn update_trade(&mut self, symbol: &str, trade: TradeData) {
        match self.trades.get_mut(symbol) {
            Some(buffer) => buffer.push(trade),
            None => eprintln!("No trade buffer initialized for symbol: {}", symbol),
        }
    }

    pub fn update_order_book(&mut self, symbol: &str, order_book: OrderBookData) {
        match self.order_books.get_mut(symbol) {
            Some(buffer) => buffer.push(order_book),
            None => eprintln!("No order book buffer initialized for symbol: {}", symbol),
        }
    }

    // pub fn update_klines(&mut self, symbol: &str, kline: Klines) {
    //     if let Some(buffer) = self.klines.get_mut(symbol) {
    //         buffer.push(kline);
    //     }
    // }

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
