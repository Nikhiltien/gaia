use futures_util::stream::StreamExt;
use timely::dataflow::operators::generic::operator::source;
use timely::dataflow::Scope;
use timely::dataflow::Stream;

/// Converts a futures_util::stream::Stream of data into a timely::dataflow::Stream.
pub trait ToStreamAsync<T, D>
where
    T: Timestamp,
    D: Data,
{
    fn to_stream<S: Scope<Timestamp = T>>(self, scope: &S) -> Stream<S, D>;
}

impl<T, D, I> ToStreamAsync<T, D> for I
where
    D: Data,
    T: Timestamp,
    I: futures_util::stream::Stream<Item = D> + Unpin + 'static,
{
    fn to_stream<S: Scope<Timestamp = T>>(self, scope: &S) -> Stream<S, D> {
        source(scope, "AsyncStreamSource", move |capability, info| {
            let activator = Arc::new(scope.sync_activator_for(&info.address[..]));
            let mut cap_set = CapabilitySet::from_elem(capability);

            move |output| {
                let waker = futures_util::task::waker_ref(&activator);
                let mut context = Context::from_waker(&waker);

                while let Poll::Ready(item) = Pin::new(&mut self).poll_next(&mut context) {
                    match item {
                        Some(data) => {
                            let time = data.timestamp; // Assuming `data` has a `timestamp` field
                            output.session(&cap_set.delayed(&time)).give(data);
                        }
                        None => {
                            cap_set.downgrade(&[]);
                            break;
                        }
                    }
                }
            }
        })
    }
}
