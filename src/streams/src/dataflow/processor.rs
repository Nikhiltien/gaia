use crate::structs::{BatchTrades, OrderBookData, TradeData};
use abomonation_derive::Abomonation;
use crossbeam_channel::{unbounded, Sender};
use serde::{Deserialize, Serialize};
use std::thread;
use timely::communication::Allocate;
use timely::dataflow::channels::pact::Pipeline;
use timely::dataflow::operators::{Input, Inspect, Operator, Probe};
use timely::dataflow::{InputHandle, ProbeHandle, Scope, Stream};
use timely::worker::Worker;
use timely::ExchangeData;

#[derive(Abomonation, Clone, Debug, Serialize, Deserialize)]
struct MergedData {
    pub trade_price: f64,
    pub book_size: f64,
}

pub struct DataChannels {
    trade_sender: Sender<TradeData>,
    orderbook_sender: Sender<OrderBookData>,
}

// impl DataChannels {
//     pub fn new() -> Self {
//         let (trade_sender, trade_receiver) = unbounded();
//         let (orderbook_sender, orderbook_receiver) = unbounded();

//         thread::spawn(move || {
//             timely::execute_from_args(std::env::args().into_iter(), move |worker| {
//                 Self::setup_dataflow(worker, trade_receiver, orderbook_receiver);
//             })
//             .expect("Failed to execute timely dataflow");
//         });

//         DataChannels {
//             trade_sender,
//             orderbook_sender,
//         }
//     }

// fn setup_dataflow(
//     worker: &mut Worker<timely::communication::Allocator>,
//     trade_receiver: crossbeam_channel::Receiver<TradeData>,
//     orderbook_receiver: crossbeam_channel::Receiver<OrderBookData>,
// ) -> (InputHandle<u64, TradeData>, InputHandle<u64, OrderBookData>) {
//     let probe = ProbeHandle::new();

//     let (input_handle_trade, trade_stream) = worker.dataflow::<u64, _, _>(|scope| {
//         let (trade_input, trades) = scope.new_input::<TradeData>();
//         let (order_input, orders) = scope.new_input::<OrderBookData>();

//         let mut order_vec: Vec<OrderBookData> = Vec::new(); // Specify the type explicitly

//         // Process and join data streams
//         let joined = trades.binary_frontier(
//             &orders,
//             Pipeline,
//             Pipeline,
//             "JoinAndProcess",
//             |_capability, _info| {
//                 move |trade_input, order_input, output| {
//                     let mut trade_vec = Vec::new();

//                     trade_input.for_each(|time, data| {
//                         data.swap(&mut trade_vec);
//                         for trade in trade_vec.drain(..) {
//                             for order in &order_vec {
//                                 if trade.timestamp == order.timestamp {
//                                     // Now `order` is correctly typed
//                                     let merged_data = MergedData {
//                                         trade_price: trade.price,
//                                         book_size: order
//                                             .bids
//                                             .get(0)
//                                             .map_or(0.0, |bid| bid.price),
//                                     };
//                                     output.session(&time).give(merged_data);
//                                 }
//                             }
//                         }
//                     });

//                     order_input.for_each(|time, data| {
//                         data.swap(&mut order_vec);
//                     });
//                 }
//             },
//         );

//         joined
//             .inspect(|x| println!("Merged Data: {:?}", x))
//             .probe_with(&mut probe);

//         (trade_input, order_input) // Return these handles from the closure
//     });

//     // Main processing loop with correct frontier checking
//     while worker.step() {
//         let mut all_data_processed = false;
//         probe.with_frontier(|frontier| {
//             all_data_processed = frontier.is_empty();
//         });

//         if all_data_processed {
//             break;
//         }

//         // Handling of incoming data from the channels should be done outside this block
//     }

//     (input_handle_trade, input_handle_order) // Return handles to be used externally
// }
// }
