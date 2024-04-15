use crate::structs::{BatchTrades, TradeData};
use crossbeam_channel::{Receiver, TryRecvError};
use futures_util::stream::{self, StreamExt};
use std::collections::HashMap;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{Context, Poll};
use timely::dataflow::channels::pact::Pipeline;
use timely::dataflow::channels::Message;
use timely::dataflow::operators::generic::operator::source;
use timely::dataflow::operators::{CapabilitySet, Inspect, Operator, ToStream};
use timely::dataflow::{Scope, Stream};
use timely::progress::Timestamp;
use timely::scheduling::Scheduler;
use timely::Data;

/// Define a custom Event type for asynchronous streams
pub enum Event<T, D> {
    Progress(T),
    Message(T, D),
}

/// Trait to convert an async stream of Events to a Timely Stream
pub trait ToStreamAsync<T, D>
where
    T: Timestamp,
    D: Send + 'static,
{
    fn to_stream<S: Scope<Timestamp = T>>(self, scope: &S) -> Stream<S, D>;
}

impl<T, D, I> ToStreamAsync<T, D> for I
where
    T: Timestamp + Copy,
    D: Data + Send + 'static + Clone,
    I: futures_util::stream::Stream<Item = Event<T, D>> + Unpin + 'static,
{
    fn to_stream<S: Scope<Timestamp = T>>(mut self, scope: &S) -> Stream<S, D> {
        source(scope, "ToStreamAsync", move |capability, info| {
            let activator = Arc::new(scope.sync_activator_for(&info.address[..]));
            let mut cap_set = CapabilitySet::from_elem(capability);

            move |output| {
                let waker = futures_util::task::waker_ref(&activator);
                let mut context = Context::from_waker(&waker);

                while let Poll::Ready(option) = Pin::new(&mut self).poll_next(&mut context) {
                    match option {
                        Some(Event::Progress(time)) => {
                            cap_set.downgrade(&[time]); // Update the capability frontier
                        }
                        Some(Event::Message(time, data)) => {
                            let new_capability = cap_set.delayed(&time);
                            if let cap = new_capability {
                                output.session(&cap).give(data);
                            } else {
                                println!(
                                    "Warning: Attempted to delay to an invalid time: {:?}",
                                    time
                                );
                            }
                        }

                        None => break, // End of stream
                    }
                }
            }
        })
    }
}

pub fn run_timely_dataflow(receiver: Receiver<Vec<TradeData>>) {
    let runtime = tokio::runtime::Runtime::new().unwrap();

    timely::execute_from_args(std::env::args(), move |worker| {
        let receiver = receiver.clone();
        worker.dataflow::<u64, _, _>(|scope| {
            let activator = scope.activator_for(&scope.addr());
            source(scope, "Trades", move |capability, _info| {
                let mut capability = capability;
                move |output| {
                    match receiver.try_recv() {
                        Ok(batch) => {
                            println!("batch: {:?}", batch);
                            // Handle capability delay correctly
                            if let c = capability.delayed(&batch.first().map_or(0, |trade| trade.timestamp)) {
                                output.session(&c).give_iterator(batch.iter().cloned());
                                capability = c; // Update the current capability to the delayed one
                            } else {
                                // Log error when capability cannot be delayed
                                println!("Warning: Failed to delay capability to the timestamp of the first trade.");
                            }
                        }
                        Err(TryRecvError::Empty) => {
                            // Use the previously created activator
                            activator.activate(); // Reactivate the operator later
                        }
                        Err(TryRecvError::Disconnected) => return, // Stop the dataflow if the channel is disconnected
                    }
                }
            })
            .inspect(|data| {
                println!("Processed: {:?}", data);
            });
        })
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
