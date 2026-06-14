// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use gaspatchio_core_lib::polars_functions::accumulate;
use polars::prelude::*;

/// Benchmark 1: Scale by number of policies (rows), fixed 240-month projection.
/// Tests how the kernel scales with portfolio size.
fn bench_accumulate(c: &mut Criterion) {
    let mut group = c.benchmark_group("accumulate");

    for num_rows in [100, 1_000, 10_000, 100_000] {
        group.bench_with_input(
            BenchmarkId::from_parameter(num_rows),
            &num_rows,
            |b, &num_rows| {
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
                    let _ = black_box(
                        accumulate(&[initial.clone(), multiply_series.clone(), add_series.clone()])
                            .unwrap(),
                    );
                });
            },
        );
    }

    group.finish();
}

/// Benchmark 2: Scale by projection length, fixed 10K policies.
/// Tests how the kernel scales with projection horizon.
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
                    let _ = black_box(
                        accumulate(&[initial.clone(), multiply_series.clone(), add_series.clone()])
                            .unwrap(),
                    );
                });
            },
        );
    }

    group.finish();
}

/// Benchmark 3: Compare uniform vs variable-length projection for the same portfolio.
/// 10K policies with terms distributed 60-600 months.
/// "Uniform" gives every policy 600-element lists.
/// "Variable" gives each policy its actual term-length lists.
fn bench_accumulate_uniform_vs_variable(c: &mut Criterion) {
    let mut group = c.benchmark_group("accumulate_uniform_vs_variable");
    let num_rows: usize = 10_000;
    let max_projection: usize = 600;

    // Per-policy projection lengths: uniformly distributed 60..=600
    let per_policy_lengths: Vec<usize> = (0..num_rows)
        .map(|i| 60 + (i % 541))  // 60 to 600 inclusive
        .collect();

    let total_uniform_elements: usize = num_rows * max_projection;
    let total_variable_elements: usize = per_policy_lengths.iter().sum();

    // --- Uniform: all policies get max_projection elements ---
    let initial_uniform: Vec<f64> = (0..num_rows).map(|i| 100.0 + (i as f64)).collect();
    let initial_uniform = Series::new("initial".into(), initial_uniform);

    let mul_uniform: Vec<_> = (0..num_rows)
        .map(|_| {
            let values: Vec<f64> = (0..max_projection).map(|_| 1.01).collect();
            Some(Series::new("".into(), values))
        })
        .collect();
    let add_uniform: Vec<_> = (0..num_rows)
        .map(|_| {
            let values: Vec<f64> = (0..max_projection).map(|i| 10.0 + (i as f64 * 0.1)).collect();
            Some(Series::new("".into(), values))
        })
        .collect();

    let mul_uniform_series = ListChunked::from_iter(mul_uniform).into_series();
    let add_uniform_series = ListChunked::from_iter(add_uniform).into_series();

    // --- Variable: each policy gets its actual term-length elements ---
    let initial_variable: Vec<f64> = (0..num_rows).map(|i| 100.0 + (i as f64)).collect();
    let initial_variable = Series::new("initial".into(), initial_variable);

    let mul_variable: Vec<_> = per_policy_lengths
        .iter()
        .map(|&len| {
            let values: Vec<f64> = (0..len).map(|_| 1.01).collect();
            Some(Series::new("".into(), values))
        })
        .collect();
    let add_variable: Vec<_> = per_policy_lengths
        .iter()
        .map(|&len| {
            let values: Vec<f64> = (0..len).map(|i| 10.0 + (i as f64 * 0.1)).collect();
            Some(Series::new("".into(), values))
        })
        .collect();

    let mul_variable_series = ListChunked::from_iter(mul_variable).into_series();
    let add_variable_series = ListChunked::from_iter(add_variable).into_series();

    group.bench_function(
        BenchmarkId::new("uniform", format!("{total_uniform_elements}_elements")),
        |b| {
            b.iter(|| {
                let _ = black_box(
                    accumulate(&[
                        initial_uniform.clone(),
                        mul_uniform_series.clone(),
                        add_uniform_series.clone(),
                    ])
                    .unwrap(),
                );
            });
        },
    );

    group.bench_function(
        BenchmarkId::new("variable", format!("{total_variable_elements}_elements")),
        |b| {
            b.iter(|| {
                let _ = black_box(
                    accumulate(&[
                        initial_variable.clone(),
                        mul_variable_series.clone(),
                        add_variable_series.clone(),
                    ])
                    .unwrap(),
                );
            });
        },
    );

    group.finish();
}

criterion_group!(
    benches,
    bench_accumulate,
    bench_accumulate_varying_projection_length,
    bench_accumulate_uniform_vs_variable
);
criterion_main!(benches);
