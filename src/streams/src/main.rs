mod dataflow;
mod redis_manager;
mod structs;
mod zeromq;

use crossbeam_channel::{unbounded, Sender};
use dataflow::example::run_timely_dataflow;
use log::{error, info};
use redis_manager::{
    cache::TimeSeriesClient,
    event_bus::EventBus,
    redis_clients::{RedisConfig, RedisConnectionManager},
};
use serde_json::{from_slice, Value};
use structs::{InventoryItem, Klines, Order, OrderBookData, TradeData};
use zeromq::ZmqSocketManager;

#[cfg_attr(feature = "tokio-runtime", tokio::main)]
#[cfg_attr(feature = "async-std-runtime", async_std::main)]
#[tokio::main]
async fn main() {
    env_logger::init();
    info!("Initializing streams...");

    let redis_config = RedisConfig {
        host: "localhost".to_string(),
        port: 6379,
        password: None,
        db: Some(0),
        use_ssl: false,
    };

    let redis_manager = RedisConnectionManager::new(redis_config)
        .await
        .expect("Failed to create Redis manager");
    let _time_series_client = TimeSeriesClient::new(redis_manager.get_regular_client()).await;
    let _event_bus = EventBus::new(redis_manager.get_pub_sub_client());

    let mut zmq_manager = ZmqSocketManager::new();
    zmq_manager.start_subscribers();

    let (t_sender, t_receiver) = unbounded::<TradeData>();
    // let (ob_sender, ob_receiver) = unbounded::<OrderBookData>();
    // let (k_sender, k_receiver) = unbounded::<Klines>();
    // let (ord_sender, ord_receiver) = unbounded::<Order>();
    // let (i_sender, i_receiver) = unbounded::<InventoryItem>();

    let trade_sender = t_sender.clone();

    std::thread::spawn(move || {
        run_timely_dataflow(t_receiver);
    });

    loop {
        let messages = zmq_manager.poll_messages();
        for (exchange, topic, message_bytes) in messages {
            process_message_from_subscriber(&exchange, &topic, &message_bytes, &trade_sender).await;
        }

        // You might want to yield to the scheduler to prevent the loop from consuming too much CPU
        tokio::task::yield_now().await;
    }
}

async fn process_message_from_subscriber(
    exchange: &str,
    topic: &str,
    message_bytes: &[u8],
    sender: &Sender<TradeData>,
) {
    match topic {
        "trades" => {
            let trade_data_result = from_slice::<Vec<TradeData>>(message_bytes)
                .or_else(|_| from_slice::<TradeData>(message_bytes).map(|td| vec![td])); // Handle both single and Vec<TradeData>

            if let Ok(trades) = trade_data_result {
                for mut trade_data in trades {
                    trade_data.exchange = Some(exchange.to_string());
                    // println!("Trade: {:?}", trade_data);
                    if let Err(e) = sender.send(trade_data) {
                        error!("Failed to send trade data: {}", e);
                    }
                }
            } else {
                error!("Invalid trade data format for trades topic.");
            }
        }
        "order_book" => {
            if let Ok(order_book_data) = from_slice::<OrderBookData>(message_bytes) {
                // Additional processing for order book data
            }
        }
        "klines" => {
            if let Ok(klines_data) = from_slice::<Klines>(message_bytes) {
                // Additional processing for order book data
            }
        }
        _ => error!("Unknown topic: {}", topic),
    }
}
