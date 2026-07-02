// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use gaspatchio_core_lib::polars_functions::{curve_eval, CurveEvalKwargs};
use polars::prelude::*;

fn make_t(rows: usize) -> Series {
    let data: Vec<Option<Series>> = (0..rows)
        .map(|_| {
            let v: Vec<f64> = (0..120).map(|i| (i as f64 + 1.0) / 12.0).collect();
            Some(Series::new("".into(), v))
        })
        .collect();
    ListChunked::from_iter(data).into_series()
}

fn kw(method: &str) -> CurveEvalKwargs {
    CurveEvalKwargs {
        method: method.into(),
        xs: Some(vec![1.0, 2.0, 5.0, 10.0, 20.0, 30.0]),
        ys: Some(vec![0.02, 0.022, 0.025, 0.028, 0.03, 0.031]),
        slopes: Some(vec![0.002, 0.0015, 0.001, 0.0006, 0.0002, 0.0001]),
        extrapolation: Some("flat".into()),
        b0: Some(0.04),
        b1: Some(-0.01),
        b2: Some(0.005),
        b3: Some(0.002),
        tau1: Some(1.5),
        tau2: Some(10.0),
        u: Some(vec![1.0, 5.0, 10.0, 20.0, 30.0]),
        zeta: Some(vec![0.01, -0.02, 0.015, -0.005, 0.002]),
        omega: Some((1.033_f64).ln()),
        alpha: Some(0.15),
    }
}

fn bench(c: &mut Criterion) {
    let mut g = c.benchmark_group("curve_eval");
    for method in ["linear", "log_linear", "pchip", "svensson", "smith_wilson"] {
        for rows in [1_000usize, 10_000, 100_000] {
            let t = make_t(rows);
            let k = kw(method);
            g.bench_with_input(BenchmarkId::new(method, rows), &rows, |b, _| {
                b.iter(|| curve_eval(std::slice::from_ref(&t), &k).unwrap());
            });
        }
    }
    g.finish();
}

criterion_group!(benches, bench);
criterion_main!(benches);
