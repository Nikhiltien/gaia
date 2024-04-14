use criterion::{black_box, criterion_group, criterion_main, Criterion};
use streams::ring_buffer::RingBuffer; // Ensure this path is correct based on your project structure

fn ring_buffer_push_benchmark(c: &mut Criterion) {
    const SIZE: usize = 1000;
    let mut buffer = RingBuffer::<i32, SIZE>::new();

    c.bench_function("ring_buffer_push", |b| {
        b.iter(|| {
            for i in 0..SIZE {
                buffer.push(black_box(i as i32));
            }
        });
    });
}

fn ring_buffer_pop_benchmark(c: &mut Criterion) {
    const SIZE: usize = 1000; // Define the size of the RingBuffer

    let mut buffer = RingBuffer::<i32, SIZE>::new(); // Create a new buffer with the specified size
    for i in 0..SIZE {
        buffer.push(black_box(i as i32));
    }

    c.bench_function("ring_buffer_pop", |b| {
        b.iter(|| {
            for _ in 0..SIZE {
                black_box(buffer.pop());
            }
        });
    });
}

criterion_group!(
    benches,
    ring_buffer_push_benchmark,
    ring_buffer_pop_benchmark
);
criterion_main!(benches);
