// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

//! Deterministic model-point generation for the lookup benchmarks.
//!
//! These benchmarks need a large set of policy key vectors. That set used to be
//! committed as `benches/fixtures/age-last-smoking-{1k,100k}.parquet` — 22.8 MB
//! of git-LFS. Almost all of it was redundant: every list column is a pure
//! function of five scalars per policy, so 100,000 policies expand to 64.4M
//! projection months from ~500 KB of actual entropy.
//!
//! Committing that cost real money. LFS bandwidth is billed to the repository
//! owner on *every* fetch, including third-party clones of this public repo, and
//! CI plus the plugin marketplace between them exhausted the account's quota.
//! Generating the data removes the file from checkouts and clones alike.
//!
//! # Shape
//!
//! One row per policy, projected monthly from the issue age to age 100:
//!
//! | column            | type        | rule                                    |
//! |-------------------|-------------|-----------------------------------------|
//! | `policyholder_nr` | `i64`       | `1..=n`                                 |
//! | `age`             | `list[f64]` | `issue_age + i/12`                      |
//! | `gender`          | `str`       | `F` \| `M`                              |
//! | `smoking_status`  | `str`       | `S` \| `NS`                             |
//! | `sum_assured`     | `i64`       | `100_000..=929_571`                     |
//! | `policy_duration` | `list[f64]` | `duration_at_issue + i/12`              |
//! | `num_proj_months` | `i64`       | list length                             |
//! | `proj_months`     | `list[i64]` | `0..len`                                |
//! | `proj_years`      | `list[f64]` | `ceil(i/12)` — the ordinal policy year  |
//! | `age-last`        | `list[f64]` | `floor(age[i])`                         |
//! | `gender_smoking`  | `str`       | `gender ++ smoking_status`              |
//!
//! Ranges match the distributions measured off the retired fixtures: issue age
//! uniform on 22..=71, duration at issue uniform on 1..=19, gender and smoking
//! status each an even split.
//!
//! # Determinism
//!
//! Each policy draws from its own SplitMix64 stream seeded from its index, so a
//! policy's attributes depend only on that index — never on how many policies
//! were asked for. `model_points(1_000)` is therefore exactly the first 1,000
//! rows of `model_points(100_000)`, the same nesting the committed fixtures had.
//! SplitMix64 is all wrapping integer arithmetic, so runs are reproducible
//! across platforms and across Rust versions — Linux and Windows benchmark
//! numbers stay comparable.

use polars::prelude::*;
use std::sync::OnceLock;

/// Projection runs monthly from the issue age to this age, inclusive.
const TERMINAL_AGE: i64 = 100;

/// SplitMix64. Chosen over a `rand` dev-dependency because the whole generator
/// is five lines of wrapping arithmetic with no platform-dependent behaviour.
fn splitmix64(state: &mut u64) -> u64 {
    *state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

/// The five independent draws that define a policy. Everything else is derived.
struct Policy {
    issue_age: i64,
    gender: &'static str,
    smoking_status: &'static str,
    sum_assured: i64,
    duration_at_issue: i64,
}

impl Policy {
    /// Draws policy `index` from its own stream, independent of every other
    /// policy — this is what makes the prefix property hold.
    fn at(index: usize) -> Self {
        let mut state = (index as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15);
        Self {
            issue_age: 22 + (splitmix64(&mut state) % 50) as i64,
            gender: if splitmix64(&mut state) & 1 == 0 {
                "F"
            } else {
                "M"
            },
            smoking_status: if splitmix64(&mut state) & 1 == 0 {
                "S"
            } else {
                "NS"
            },
            sum_assured: 100_000 + (splitmix64(&mut state) % 829_572) as i64,
            duration_at_issue: 1 + (splitmix64(&mut state) % 19) as i64,
        }
    }

    /// Projection months from issue to `TERMINAL_AGE` inclusive, so the final
    /// `age` entry is exactly 100.0.
    fn n_months(&self) -> usize {
        ((TERMINAL_AGE - self.issue_age) * 12 + 1) as usize
    }
}

/// Builds `n_policies` model points. Deterministic: the same `n_policies`
/// always yields an identical frame, and smaller values yield exact prefixes.
pub fn model_points(n_policies: usize) -> PolarsResult<DataFrame> {
    let policies: Vec<Policy> = (0..n_policies).map(Policy::at).collect();

    // i/12 recurs in three columns; compute it once per month index.
    let month_fraction = |i: usize| i as f64 / 12.0;

    let age: ListChunked = policies
        .iter()
        .map(|p| {
            let vals: Vec<f64> = (0..p.n_months())
                .map(|i| p.issue_age as f64 + month_fraction(i))
                .collect();
            Some(Series::new("".into(), vals))
        })
        .collect();

    let age_last: ListChunked = policies
        .iter()
        .map(|p| {
            let vals: Vec<f64> = (0..p.n_months())
                .map(|i| (p.issue_age as f64 + month_fraction(i)).floor())
                .collect();
            Some(Series::new("".into(), vals))
        })
        .collect();

    let policy_duration: ListChunked = policies
        .iter()
        .map(|p| {
            let vals: Vec<f64> = (0..p.n_months())
                .map(|i| p.duration_at_issue as f64 + month_fraction(i))
                .collect();
            Some(Series::new("".into(), vals))
        })
        .collect();

    let proj_months: ListChunked = policies
        .iter()
        .map(|p| {
            let vals: Vec<i64> = (0..p.n_months() as i64).collect();
            Some(Series::new("".into(), vals))
        })
        .collect();

    // Ordinal policy year, ROUNDUP-style: month 0 is year 0, months 1..=12 are
    // year 1. Matches the retired fixture and the framework's `proj_years`.
    let proj_years: ListChunked = policies
        .iter()
        .map(|p| {
            let vals: Vec<f64> = (0..p.n_months()).map(|i| (i.div_ceil(12)) as f64).collect();
            Some(Series::new("".into(), vals))
        })
        .collect();

    let policyholder_nr: Vec<i64> = (1..=n_policies as i64).collect();
    let gender: Vec<&str> = policies.iter().map(|p| p.gender).collect();
    let smoking_status: Vec<&str> = policies.iter().map(|p| p.smoking_status).collect();
    let gender_smoking: Vec<String> = policies
        .iter()
        .map(|p| format!("{}{}", p.gender, p.smoking_status))
        .collect();
    let sum_assured: Vec<i64> = policies.iter().map(|p| p.sum_assured).collect();
    let num_proj_months: Vec<i64> = policies.iter().map(|p| p.n_months() as i64).collect();

    DataFrame::new(
        n_policies,
        vec![
            Series::new("policyholder_nr".into(), policyholder_nr).into_column(),
            age.into_series().with_name("age".into()).into_column(),
            Series::new("gender".into(), gender).into_column(),
            Series::new("smoking_status".into(), smoking_status).into_column(),
            Series::new("sum_assured".into(), sum_assured).into_column(),
            policy_duration
                .into_series()
                .with_name("policy_duration".into())
                .into_column(),
            Series::new("num_proj_months".into(), num_proj_months).into_column(),
            proj_months
                .into_series()
                .with_name("proj_months".into())
                .into_column(),
            proj_years
                .into_series()
                .with_name("proj_years".into())
                .into_column(),
            age_last
                .into_series()
                .with_name("age-last".into())
                .into_column(),
            Series::new("gender_smoking".into(), gender_smoking).into_column(),
        ],
    )
}

/// Generates once per process and hands out clones thereafter.
///
/// The benchmark groups each ask for the same set at setup; regenerating 64.4M
/// projection months per call would dwarf the work being measured. Cloning a
/// `DataFrame` clones column `Arc`s, so the clones are cheap. The error is
/// cached as a `String` because `PolarsError` is not `Clone`.
fn cached(
    cache: &'static OnceLock<Result<DataFrame, String>>,
    n: usize,
) -> PolarsResult<DataFrame> {
    cache
        .get_or_init(|| model_points(n).map_err(|e| e.to_string()))
        .clone()
        .map_err(|e| PolarsError::ComputeError(e.into()))
}

/// 1,000 model points.
pub fn model_points_1k() -> PolarsResult<DataFrame> {
    static CACHE: OnceLock<Result<DataFrame, String>> = OnceLock::new();
    cached(&CACHE, 1_000)
}

/// 100,000 model points — 64.4M projection months. See [`model_points_1k`].
pub fn model_points_100k() -> PolarsResult<DataFrame> {
    static CACHE: OnceLock<Result<DataFrame, String>> = OnceLock::new();
    cached(&CACHE, 100_000)
}
