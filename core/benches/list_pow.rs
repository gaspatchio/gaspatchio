use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use gaspatchio_core_lib::polars_functions::list_pow;
use polars::prelude::*;

fn bench_list_pow_list_list(c: &mut Criterion) {
    let mut group = c.benchmark_group("list_pow_list_list");

    for num_rows in [100, 1_000, 10_000, 100_000] {
        group.bench_with_input(
            BenchmarkId::from_parameter(num_rows),
            &num_rows,
            |b, &num_rows| {
                // Setup: Create two list columns
                // Each row has 240 elements (typical actuarial projection)
                let base_data: Vec<_> = (0..num_rows)
                    .map(|_| {
                        let values: Vec<f64> =
                            (0..240).map(|i| 1.0 + (i as f64 * 0.004)).collect();
                        Some(Series::new("".into(), values))
                    })
                    .collect();

                let exp_data: Vec<_> = (0..num_rows)
                    .map(|_| {
                        let values: Vec<f64> = (0..240).map(|i| -(i as f64)).collect();
                        Some(Series::new("".into(), values))
                    })
                    .collect();

                let base_list = ListChunked::from_iter(base_data);
                let exp_list = ListChunked::from_iter(exp_data);

                let base_series = base_list.into_series();
                let exp_series = exp_list.into_series();

                b.iter(|| {
                    list_pow(&[base_series.clone(), exp_series.clone()]).unwrap();
                });
            },
        );
    }

    group.finish();
}

fn bench_list_pow_list_scalar(c: &mut Criterion) {
    let mut group = c.benchmark_group("list_pow_list_scalar");

    for num_rows in [100, 1_000, 10_000, 100_000] {
        group.bench_with_input(
            BenchmarkId::from_parameter(num_rows),
            &num_rows,
            |b, &num_rows| {
                // Setup: List column and scalar exponent
                let base_data: Vec<_> = (0..num_rows)
                    .map(|_| {
                        let values: Vec<f64> =
                            (0..240).map(|i| 1.0 + (i as f64 * 0.004)).collect();
                        Some(Series::new("".into(), values))
                    })
                    .collect();

                let base_list = ListChunked::from_iter(base_data);
                let base_series = base_list.into_series();

                // Scalar exponent column (each row has same value)
                let exp_series = Series::new("exp".into(), vec![-2.0; num_rows]);

                b.iter(|| {
                    list_pow(&[base_series.clone(), exp_series.clone()]).unwrap();
                });
            },
        );
    }

    group.finish();
}

criterion_group!(benches, bench_list_pow_list_list, bench_list_pow_list_scalar);
criterion_main!(benches);
