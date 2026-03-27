/// Realistic vector-lookup benchmarks matching the L4 lifelib model pattern.
///
/// The real model has N rows (policies), where each key column is a List(Int64/Float64)
/// of ~120 elements (one per projection month). Some keys are scalar strings that broadcast.
///
/// This benchmark creates that exact shape and measures `lookup_series` on the vector path:
///   explode lists → encode keys → lookup → re-list results.
///
/// Tables used: mortality_select (3 keys), lapse_rates (2 keys), surrender_charges (2 keys),
///              risk_free_rates (3 keys) — loaded from the actual L4 fixture parquets.
use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use gaspatchio_core_lib::assumptions::table::{AssumptionTable, StorageMode};
use polars::prelude::*;
use std::fs::File;
use std::path::Path;

// ---------------------------------------------------------------------------
// Table loaders (actual L4 assumption parquets from fixtures)
// ---------------------------------------------------------------------------

fn load_table(
    filename: &str,
    keys: Vec<String>,
    value: &str,
    mode: StorageMode,
) -> PolarsResult<AssumptionTable> {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("benches/fixtures/{filename}"));
    let file = File::open(&path).map_err(|e| {
        PolarsError::ComputeError(format!("Failed to open {filename}: {e}").into())
    })?;
    let df = ParquetReader::new(file).finish()?;
    AssumptionTable::build_with_mode(df, keys, value.to_string(), mode)
}

fn load_mortality_select(mode: StorageMode) -> PolarsResult<AssumptionTable> {
    load_table(
        "mortality_select.parquet",
        vec![
            "table_id".into(),
            "attained_age".into(),
            "duration".into(),
        ],
        "mort_rate",
        mode,
    )
}

fn load_lapse_rates(mode: StorageMode) -> PolarsResult<AssumptionTable> {
    load_table(
        "lapse_rates.parquet",
        vec!["duration".into(), "lapse_id".into()],
        "lapse_rate",
        mode,
    )
}

fn load_surrender_charges(mode: StorageMode) -> PolarsResult<AssumptionTable> {
    load_table(
        "surrender_charges.parquet",
        vec!["duration".into(), "surr_charge_id".into()],
        "surr_charge_rate",
        mode,
    )
}

fn load_risk_free_rates(mode: StorageMode) -> PolarsResult<AssumptionTable> {
    load_table(
        "risk_free_rates.parquet",
        vec!["scenario".into(), "currency".into(), "year".into()],
        "forward_rate",
        mode,
    )
}

// ---------------------------------------------------------------------------
// Helpers to build List-column key Series matching the real model shape
// ---------------------------------------------------------------------------

/// Creates a List(Int64) column: `n_policies` rows, each containing a vector
/// of `months_per_policy` elements produced by `value_fn(policy_idx, month_idx)`.
fn make_list_i64(
    name: &str,
    n_policies: usize,
    months_per_policy: usize,
    value_fn: impl Fn(usize, usize) -> i64,
) -> Series {
    let lists: ListChunked = (0..n_policies)
        .map(|p| {
            let vals: Vec<i64> = (0..months_per_policy).map(|m| value_fn(p, m)).collect();
            Some(Series::new("".into(), vals))
        })
        .collect();
    lists.into_series().with_name(name.into())
}

/// Creates a String scalar column: `n_policies` rows, each a single string value.
fn make_scalar_str(name: &str, n_policies: usize, value_fn: impl Fn(usize) -> &'static str) -> Series {
    let vals: Vec<&str> = (0..n_policies).map(|p| value_fn(p)).collect();
    Series::new(name.into(), vals)
}

// ---------------------------------------------------------------------------
// Individual table benchmarks — vector path
// ---------------------------------------------------------------------------

/// Mortality select: 3 keys (table_id: scalar String, attained_age: List[i64], duration: List[i64])
/// This is the #1 hotspot in the profile (~8.6% of runtime).
fn bench_mortality_select_vector(c: &mut Criterion) {
    let table_ids = ["T3275", "T3276", "T3363", "T3364"];
    let months: usize = 120;

    let mut group = c.benchmark_group("realistic_vector/mortality_select");
    group.sample_size(20);

    for &n_policies in &[1_000, 10_000] {
        // Build keys matching the real model shape
        let table_id_col = make_scalar_str("table_id", n_policies, |p| {
            table_ids[p % table_ids.len()]
        });
        let age_col = make_list_i64("attained_age", n_policies, months, |p, m| {
            let base_age = 30 + (p % 50) as i64;
            base_age + (m as i64 / 12)
        });
        let duration_col = make_list_i64("duration", n_policies, months, |p, m| {
            let base_dur = (p % 10) as i64;
            (base_dur + m as i64 / 12).min(30)
        });

        let keys: Vec<&Series> = vec![&table_id_col, &age_col, &duration_col];

        for &mode in &[StorageMode::Array, StorageMode::Hash] {
            let mode_name = match mode {
                StorageMode::Array => "array",
                StorageMode::Hash => "hash",
                StorageMode::Auto => "auto",
            };
            let table = load_mortality_select(mode).expect("Failed to load mortality_select");

            group.bench_with_input(
                BenchmarkId::new(format!("{mode_name}_{n_policies}"), n_policies),
                &n_policies,
                |b, _| {
                    b.iter(|| {
                        black_box(table.lookup_series(black_box(&keys)).unwrap());
                    })
                },
            );
        }
    }

    group.finish();
}

/// Lapse rates: 2 keys (duration: List[i64], lapse_id: scalar String)
/// Combined with dynamic lapse, this is ~15% of runtime.
fn bench_lapse_rates_vector(c: &mut Criterion) {
    let lapse_ids = ["L001", "L002"];
    let months: usize = 120;

    let mut group = c.benchmark_group("realistic_vector/lapse_rates");
    group.sample_size(20);

    for &n_policies in &[1_000, 10_000] {
        let duration_col = make_list_i64("duration", n_policies, months, |p, m| {
            let base_dur = (p % 10) as i64;
            (base_dur + m as i64 / 12).min(14)
        });
        let lapse_id_col = make_scalar_str("lapse_id", n_policies, |p| {
            lapse_ids[p % lapse_ids.len()]
        });

        let keys: Vec<&Series> = vec![&duration_col, &lapse_id_col];

        for &mode in &[StorageMode::Array, StorageMode::Hash] {
            let mode_name = match mode {
                StorageMode::Array => "array",
                StorageMode::Hash => "hash",
                StorageMode::Auto => "auto",
            };
            let table = load_lapse_rates(mode).expect("Failed to load lapse_rates");

            group.bench_with_input(
                BenchmarkId::new(format!("{mode_name}_{n_policies}"), n_policies),
                &n_policies,
                |b, _| {
                    b.iter(|| {
                        black_box(table.lookup_series(black_box(&keys)).unwrap());
                    })
                },
            );
        }
    }

    group.finish();
}

/// Surrender charges: 2 keys (duration: List[i64], surr_charge_id: scalar String)
fn bench_surrender_charges_vector(c: &mut Criterion) {
    let surr_ids = ["SC001", "SC002"];
    let months: usize = 120;

    let mut group = c.benchmark_group("realistic_vector/surrender_charges");
    group.sample_size(20);

    for &n_policies in &[1_000, 10_000] {
        let duration_col = make_list_i64("duration", n_policies, months, |p, m| {
            let base_dur = (p % 10) as i64;
            (base_dur + m as i64 / 12).min(9) // capped at 9 for surrender charges
        });
        let surr_id_col = make_scalar_str("surr_charge_id", n_policies, |p| {
            surr_ids[p % surr_ids.len()]
        });

        let keys: Vec<&Series> = vec![&duration_col, &surr_id_col];

        for &mode in &[StorageMode::Array, StorageMode::Hash] {
            let mode_name = match mode {
                StorageMode::Array => "array",
                StorageMode::Hash => "hash",
                StorageMode::Auto => "auto",
            };
            let table = load_surrender_charges(mode).expect("Failed to load surrender_charges");

            group.bench_with_input(
                BenchmarkId::new(format!("{mode_name}_{n_policies}"), n_policies),
                &n_policies,
                |b, _| {
                    b.iter(|| {
                        black_box(table.lookup_series(black_box(&keys)).unwrap());
                    })
                },
            );
        }
    }

    group.finish();
}

/// Risk-free rates: 3 keys (scenario: scalar String, currency: scalar String, year: List[i64])
fn bench_risk_free_rates_vector(c: &mut Criterion) {
    let months: usize = 120;

    let mut group = c.benchmark_group("realistic_vector/risk_free_rates");
    group.sample_size(20);

    for &n_policies in &[1_000, 10_000] {
        let scenario_col = make_scalar_str("scenario", n_policies, |_| "BASE");
        let currency_col = make_scalar_str("currency", n_policies, |_| "USD");
        let year_col = make_list_i64("year", n_policies, months, |_, m| m as i64 / 12);

        let keys: Vec<&Series> = vec![&scenario_col, &currency_col, &year_col];

        for &mode in &[StorageMode::Array, StorageMode::Hash] {
            let mode_name = match mode {
                StorageMode::Array => "array",
                StorageMode::Hash => "hash",
                StorageMode::Auto => "auto",
            };
            let table = load_risk_free_rates(mode).expect("Failed to load risk_free_rates");

            group.bench_with_input(
                BenchmarkId::new(format!("{mode_name}_{n_policies}"), n_policies),
                &n_policies,
                |b, _| {
                    b.iter(|| {
                        black_box(table.lookup_series(black_box(&keys)).unwrap());
                    })
                },
            );
        }
    }

    group.finish();
}

/// Combined benchmark: all 4 lookups in sequence, matching a single model step.
/// This is the most representative benchmark of real model performance.
fn bench_combined_model_lookups(c: &mut Criterion) {
    let months: usize = 120;
    let table_ids = ["T3275", "T3276", "T3363", "T3364"];
    let lapse_ids = ["L001", "L002"];
    let surr_ids = ["SC001", "SC002"];

    let mut group = c.benchmark_group("realistic_vector/combined_model");
    group.sample_size(20);

    for &n_policies in &[1_000, 10_000] {
        // Mortality select keys
        let mort_table_id = make_scalar_str("table_id", n_policies, |p| {
            table_ids[p % table_ids.len()]
        });
        let mort_age = make_list_i64("attained_age", n_policies, months, |p, m| {
            let base_age = 30 + (p % 50) as i64;
            base_age + (m as i64 / 12)
        });
        let mort_duration = make_list_i64("duration", n_policies, months, |p, m| {
            let base_dur = (p % 10) as i64;
            (base_dur + m as i64 / 12).min(30)
        });
        let mort_keys: Vec<&Series> = vec![&mort_table_id, &mort_age, &mort_duration];

        // Lapse keys
        let lapse_duration = make_list_i64("duration", n_policies, months, |p, m| {
            let base_dur = (p % 10) as i64;
            (base_dur + m as i64 / 12).min(14)
        });
        let lapse_id = make_scalar_str("lapse_id", n_policies, |p| {
            lapse_ids[p % lapse_ids.len()]
        });
        let lapse_keys: Vec<&Series> = vec![&lapse_duration, &lapse_id];

        // Surrender charge keys
        let surr_duration = make_list_i64("duration", n_policies, months, |p, m| {
            let base_dur = (p % 10) as i64;
            (base_dur + m as i64 / 12).min(9)
        });
        let surr_id = make_scalar_str("surr_charge_id", n_policies, |p| {
            surr_ids[p % surr_ids.len()]
        });
        let surr_keys: Vec<&Series> = vec![&surr_duration, &surr_id];

        // Risk-free rate keys
        let rfr_scenario = make_scalar_str("scenario", n_policies, |_| "BASE");
        let rfr_currency = make_scalar_str("currency", n_policies, |_| "USD");
        let rfr_year = make_list_i64("year", n_policies, months, |_, m| m as i64 / 12);
        let rfr_keys: Vec<&Series> = vec![&rfr_scenario, &rfr_currency, &rfr_year];

        for &mode in &[StorageMode::Array, StorageMode::Hash] {
            let mode_name = match mode {
                StorageMode::Array => "array",
                StorageMode::Hash => "hash",
                StorageMode::Auto => "auto",
            };

            let mort_table =
                load_mortality_select(mode).expect("Failed to load mortality_select");
            let lapse_table = load_lapse_rates(mode).expect("Failed to load lapse_rates");
            let surr_table =
                load_surrender_charges(mode).expect("Failed to load surrender_charges");
            let rfr_table = load_risk_free_rates(mode).expect("Failed to load risk_free_rates");

            group.bench_with_input(
                BenchmarkId::new(format!("{mode_name}_{n_policies}"), n_policies),
                &n_policies,
                |b, _| {
                    b.iter(|| {
                        let r1 = mort_table.lookup_series(black_box(&mort_keys)).unwrap();
                        let r2 = lapse_table.lookup_series(black_box(&lapse_keys)).unwrap();
                        let r3 = surr_table.lookup_series(black_box(&surr_keys)).unwrap();
                        let r4 = rfr_table.lookup_series(black_box(&rfr_keys)).unwrap();
                        black_box((r1, r2, r3, r4));
                    })
                },
            );
        }
    }

    group.finish();
}

criterion_group!(
    benches,
    bench_mortality_select_vector,
    bench_lapse_rates_vector,
    bench_surrender_charges_vector,
    bench_risk_free_rates_vector,
    bench_combined_model_lookups,
);
criterion_main!(benches);
