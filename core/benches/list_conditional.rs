// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Criterion benchmarks for list_conditional plugin
// ABOUTME: Measures performance of element-wise conditional operations across various row counts

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use gaspatchio_core_lib::polars_functions::{list_conditional, ConditionalKwargs};
use polars::prelude::*;

fn bench_list_conditional_eq(c: &mut Criterion) {
    let mut group = c.benchmark_group("list_conditional_eq");

    for num_rows in [100, 1_000, 10_000, 100_000] {
        let list_len = 240; // Typical actuarial projection length

        // Build test data: left=[0..240], right=[1..241], then=100.0, otherwise=200.0
        // For i in 0..240: 0 == 1 -> false (200.0), 1 == 2 -> false (200.0), etc.
        let left = ListChunked::from_iter((0..num_rows).map(|_| {
            Some(Series::new(
                "".into(),
                (0..list_len).map(|i| i as f64).collect::<Vec<f64>>(),
            ))
        }));

        let right = ListChunked::from_iter((0..num_rows).map(|_| {
            Some(Series::new(
                "".into(),
                (1..=list_len).map(|i| i as f64).collect::<Vec<f64>>(),
            ))
        }));

        let then_val = Series::new("".into(), vec![100.0; num_rows]);
        let otherwise_val = Series::new("".into(), vec![200.0; num_rows]);

        let kwargs = ConditionalKwargs {
            operator: "eq".to_string(),
        };

        group.bench_function(format!("{}_rows", num_rows), |b| {
            b.iter(|| {
                list_conditional(
                    black_box(&[
                        left.clone().into_series(),
                        right.clone().into_series(),
                        then_val.clone(),
                        otherwise_val.clone(),
                    ]),
                    black_box(&kwargs),
                )
            })
        });
    }

    group.finish();
}

fn bench_list_conditional_lt_scalar(c: &mut Criterion) {
    let mut group = c.benchmark_group("list_conditional_lt_scalar");

    for num_rows in [100, 1_000, 10_000, 100_000] {
        let list_len = 240; // Typical actuarial projection length

        // Build test data: left=[0..240], right=100.0 (scalar), then=10.0, otherwise=20.0
        // Elements < 100 will be 10.0, >= 100 will be 20.0
        let left = ListChunked::from_iter((0..num_rows).map(|_| {
            Some(Series::new(
                "".into(),
                (0..list_len).map(|i| i as f64).collect::<Vec<f64>>(),
            ))
        }));

        let right = Series::new("".into(), vec![100.0; num_rows]);
        let then_val = Series::new("".into(), vec![10.0; num_rows]);
        let otherwise_val = Series::new("".into(), vec![20.0; num_rows]);

        let kwargs = ConditionalKwargs {
            operator: "lt".to_string(),
        };

        group.bench_function(format!("{}_rows", num_rows), |b| {
            b.iter(|| {
                list_conditional(
                    black_box(&[
                        left.clone().into_series(),
                        right.clone(),
                        then_val.clone(),
                        otherwise_val.clone(),
                    ]),
                    black_box(&kwargs),
                )
            })
        });
    }

    group.finish();
}

fn bench_list_conditional_gte_all_lists(c: &mut Criterion) {
    let mut group = c.benchmark_group("list_conditional_gte_all_lists");

    for num_rows in [100, 1_000, 10_000, 100_000] {
        let list_len = 240; // Typical actuarial projection length

        // Build test data with all list types
        // left=[0..240], right=[120..360], then=[5..245], otherwise=[10..250]
        let left = ListChunked::from_iter((0..num_rows).map(|_| {
            Some(Series::new(
                "".into(),
                (0..list_len).map(|i| i as f64).collect::<Vec<f64>>(),
            ))
        }));

        let right = ListChunked::from_iter((0..num_rows).map(|_| {
            Some(Series::new(
                "".into(),
                (120..120 + list_len)
                    .map(|i| i as f64)
                    .collect::<Vec<f64>>(),
            ))
        }));

        let then_val = ListChunked::from_iter((0..num_rows).map(|_| {
            Some(Series::new(
                "".into(),
                (5..5 + list_len).map(|i| i as f64).collect::<Vec<f64>>(),
            ))
        }));

        let otherwise_val = ListChunked::from_iter((0..num_rows).map(|_| {
            Some(Series::new(
                "".into(),
                (10..10 + list_len).map(|i| i as f64).collect::<Vec<f64>>(),
            ))
        }));

        let kwargs = ConditionalKwargs {
            operator: "gte".to_string(),
        };

        group.bench_function(format!("{}_rows", num_rows), |b| {
            b.iter(|| {
                list_conditional(
                    black_box(&[
                        left.clone().into_series(),
                        right.clone().into_series(),
                        then_val.clone().into_series(),
                        otherwise_val.clone().into_series(),
                    ]),
                    black_box(&kwargs),
                )
            })
        });
    }

    group.finish();
}

criterion_group!(
    benches,
    bench_list_conditional_eq,
    bench_list_conditional_lt_scalar,
    bench_list_conditional_gte_all_lists
);
criterion_main!(benches);
