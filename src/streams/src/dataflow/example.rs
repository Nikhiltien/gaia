use crate::structs::{BatchTrades, Klines, Order, OrderBookData, TradeData};
use crossbeam_channel::Receiver;
use std::collections::HashMap;
use timely::dataflow::channels::pact::Pipeline;
use timely::dataflow::operators::generic::operator::Operator;
use timely::dataflow::operators::generic::source;
use timely::dataflow::operators::probe::Handle as ProbeHandle;
use timely::dataflow::operators::Capability;
use timely::dataflow::operators::Probe;
use timely::dataflow::operators::{Inspect, Map, ToStream};
use timely::dataflow::{Scope, Stream};
use timely::scheduling::Scheduler;

pub fn run_timely_dataflow(receiver: Receiver<TradeData>) {
    timely::execute_from_args(std::env::args(), move |worker| {
        let receiver = receiver.clone();
        let mut probe = ProbeHandle::new();

        worker.dataflow::<u64, _, _>(move |scope| {
            let stream = source(scope, "Trades", move |capability, _info| {
                let mut cap = Some(capability);
                move |output| {
                    let mut capabilities = HashMap::new();

                    if let Some(initial_cap) = cap.take() {
                        while let Ok(data) = receiver.recv() {
                            let time = data.timestamp; // Assuming timestamp is in milliseconds

                            // Ensure that we get a mutable reference to a delayed capability
                            let cap = capabilities
                                .entry(time)
                                .or_insert_with(|| initial_cap.delayed(&time));

                            // Clone data to use inside the session
                            output.session(cap).give(data.clone());
                        }

                        // Compute new time for downgrading by finding the maximum key (time) in the hash map
                        if let Some(&max_time) = capabilities.keys().max() {
                            let new_time = max_time + 1; // Advance logical time

                            // Iterate over mutable references to each capability
                            for (&time, cap) in capabilities.iter_mut() {
                                if time < new_time {
                                    cap.downgrade(&new_time);
                                }
                            }

                            // Retain only the capabilities for times >= new_time
                            capabilities.retain(|&k, _| k >= new_time);
                        }
                    }
                }
            });

            stream
                .unary_frontier(Pipeline, "AggregateTrades", move |_capability, _info| {
                    let mut cap = None;
                    let mut trade_buffer = HashMap::new();

                    move |input, output| {
                        input.for_each(|temp_cap, data| {
                            cap = Some(temp_cap.delayed(&temp_cap.time()));
                            data.swap(
                                &mut trade_buffer
                                    .entry(*temp_cap.time())
                                    .or_insert_with(Vec::new),
                            );
                        });

                        if let Some(ref cap) = cap {
                            for (&timestamp, trades) in trade_buffer.iter() {
                                let batch_trades = aggregate_trades(trades, timestamp);
                                output.session(cap).give(batch_trades); // Give the aggregated batch to the output
                            }
                            trade_buffer.clear();
                        }
                    }
                })
                .inspect(|batch_trade| {
                    println!("Aggregated Trade: {:?}", batch_trade); // This is the new line you add for printing
                })
                .probe_with(&mut probe);
        });
    })
    .unwrap();
}

fn aggregate_trades(trades: &Vec<TradeData>, timestamp: u64) -> BatchTrades {
    let mut num_buys: u64 = 0;
    let mut total_buy_qty: f64 = 0.0;
    let mut total_buy_value: f64 = 0.0;

    let mut num_sells: u64 = 0;
    let mut total_sell_qty: f64 = 0.0;
    let mut total_sell_value: f64 = 0.0;

    let extracted_symbol = trades.get(0).map_or(String::new(), |t| t.symbol.clone());
    // Use `.map_or` combined with `.unwrap_or` or use another `.map_or` to provide a default String directly
    let extracted_exchange = trades.get(0).map_or(String::new(), |t| {
        t.exchange
            .clone()
            .unwrap_or_else(|| "Unknown Exchange".into())
    });

    for trade in trades.iter() {
        match trade.side {
            Some(1) => {
                num_buys += 1;
                total_buy_qty += trade.qty;
                total_buy_value += trade.qty * trade.price;
            }
            Some(0) => {
                num_sells += 1;
                total_sell_qty += trade.qty;
                total_sell_value += trade.qty * trade.price;
            }
            _ => {}
        }
    }

    let avg_buy_price = if num_buys > 0 {
        total_buy_value / total_buy_qty
    } else {
        0.0
    };
    let avg_sell_price = if num_sells > 0 {
        total_sell_value / total_sell_qty
    } else {
        0.0
    };

    BatchTrades {
        exchange: extracted_exchange,
        symbol: extracted_symbol,
        timestamp,
        num_buys,
        avg_buy_price,
        total_buy_qty,
        num_sells,
        avg_sells_price: avg_sell_price,
        total_sells_qty: total_sell_qty,
    }
}
