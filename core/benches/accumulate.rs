use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use gaspatchio_core_lib::polars_functions::accumulate;
use polars::prelude::*;

fn bench_accumulate(c: &mut Criterion) {
    let mut group = c.benchmark_group("accumulate");

    for num_rows in [100, 1_000, 10_000, 100_000] {
        group.bench_with_input(
            BenchmarkId::from_parameter(num_rows),
            &num_rows,
            |b, &num_rows| {
                // Setup: Create initial values and list columns
                // Each row has 240 elements (typical actuarial projection - 20 years monthly)
                let initial_data: Vec<f64> = (0..num_rows).map(|i| 100.0 + (i as f64)).collect();
                let initial = Series::new("initial".into(), initial_data);

                let multiply_data: Vec<_> = (0..num_rows)
                    .map(|_| {
                        let values: Vec<f64> = (0..240).map(|_| 1.01).collect();
                        Some(Series::new("".into(), values))
                    })
                    .collect();

                let add_data: Vec<_> = (0..num_rows)
                    .map(|_| {
                        let values: Vec<f64> = (0..240).map(|i| 10.0 + (i as f64 * 0.1)).collect();
                        Some(Series::new("".into(), values))
                    })
                    .collect();

                let multiply_list = ListChunked::from_iter(multiply_data);
                let add_list = ListChunked::from_iter(add_data);

                let multiply_series = multiply_list.into_series();
                let add_series = add_list.into_series();

                b.iter(|| {
                    accumulate(&[initial.clone(), multiply_series.clone(), add_series.clone()])
                        .unwrap();
                });
            },
        );
    }

    group.finish();
}

fn bench_accumulate_varying_projection_length(c: &mut Criterion) {
    let mut group = c.benchmark_group("accumulate_projection_length");
    let num_rows = 10_000;

    for projection_length in [60, 120, 240, 360, 600] {
        group.bench_with_input(
            BenchmarkId::from_parameter(projection_length),
            &projection_length,
            |b, &projection_length| {
                let initial_data: Vec<f64> = (0..num_rows).map(|i| 100.0 + (i as f64)).collect();
                let initial = Series::new("initial".into(), initial_data);

                let multiply_data: Vec<_> = (0..num_rows)
                    .map(|_| {
                        let values: Vec<f64> = (0..projection_length).map(|_| 1.01).collect();
                        Some(Series::new("".into(), values))
                    })
                    .collect();

                let add_data: Vec<_> = (0..num_rows)
                    .map(|_| {
                        let values: Vec<f64> =
                            (0..projection_length).map(|i| 10.0 + (i as f64 * 0.1)).collect();
                        Some(Series::new("".into(), values))
                    })
                    .collect();

                let multiply_list = ListChunked::from_iter(multiply_data);
                let add_list = ListChunked::from_iter(add_data);

                let multiply_series = multiply_list.into_series();
                let add_series = add_list.into_series();

                b.iter(|| {
                    accumulate(&[initial.clone(), multiply_series.clone(), add_series.clone()])
                        .unwrap();
                });
            },
        );
    }

    group.finish();
}

criterion_group!(
    benches,
    bench_accumulate,
    bench_accumulate_varying_projection_length
);
criterion_main!(benches);
