// use futures_channel::mpsc; // For creating channels
// use futures_util::stream::StreamExt;
// use futures_util::SinkExt;
// use serde_json::Value;
// use timely::dataflow::operators::Input;
// use timely::dataflow::operators::{Inspect, Map, Probe};
// use tokio::runtime::Runtime;
// use tokio_tungstenite::{connect_async, tungstenite::Message}; // For using send on channel

fn main() {
    println!("Hello, world!")
}

// fn main() {
//     let runtime = Runtime::new().unwrap();

//     let url = "wss://stream.binance.com:9443/ws/btcusdt@trade";
//     let (tx, mut rx) = mpsc::unbounded();

//     let web_socket_task = runtime.spawn(async move {
//         let (ws_stream, _) = connect_async(url).await.expect("Failed to connect");
//         println!("WebSocket connected");

//         let (_, mut read) = ws_stream.split();
//         while let Some(msg) = read.next().await {
//             if let Ok(Message::Text(text)) = msg {
//                 if let Err(_) = tx.unbounded_send(text) {
//                     break; // Exit if the receiver is dropped
//                 }
//             }
//         }
//     });

//     timely::execute_from_args(std::env::args(), move |worker| {
//         let mut input = worker.dataflow::<u64, _, _>(|scope| {
//             let (input, stream) = scope.new_input::<Value>();
//             stream
//                 .map(|x| {
//                     let price: f64 = x["p"].as_str().unwrap().parse().unwrap();
//                     let new_price = price + 1.0;
//                     (x["s"].clone(), new_price)
//                 })
//                 .inspect(|x| println!("Modified trade: {:?}", x))
//                 .probe();
//             input
//         });

//         // Processing messages from WebSocket
//         while let Some(text) = runtime.block_on(rx.next()) {
//             let v: Value = serde_json::from_str(&text).unwrap();
//             input.send(v);
//             input.advance_to(1);
//         }
//     })
//     .unwrap();
// }
