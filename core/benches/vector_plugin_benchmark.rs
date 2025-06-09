use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use gaspatchio_core_lib::polars_functions::vector::{fill_series, FillSeriesKwargs}; // Adjust path if necessary
use polars::prelude::*;
use std::iter;

fn create_length_series(name: &str, size: usize) -> Series {
    let lengths: Vec<Option<i64>> = iter::repeat(Some(10i64)).take(size).collect(); // Fixed inner length for simplicity
    Int64Chunked::from_slice_options(name.into(), &lengths).into_series()
}

fn benchmark_fill_series(c: &mut Criterion) {
    let mut group = c.benchmark_group("fill_series");

    let kwargs = FillSeriesKwargs {
        start: 1,
        increment: 2,
    };

    for size in [100, 1_000, 10_000].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(size), size, |b, &size| {
            let length_series = create_length_series("length", size);
            let inputs = [length_series];
            b.iter(|| {
                fill_series(
                    black_box(&inputs),
                    black_box(&FillSeriesKwargs {
                        start: kwargs.start,
                        increment: kwargs.increment,
                    }),
                )
            });
        });
    }
    group.finish();
}

criterion_group!(benches, benchmark_fill_series);
criterion_main!(benches);
