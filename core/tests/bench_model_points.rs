// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

//! Contract tests for the generated benchmark model points.
//!
//! The generator replaced `benches/fixtures/age-last-smoking-{1k,100k}.parquet`,
//! 22.8 MB of git-LFS. Nothing else reads it, so without these tests a silent
//! change in shape would surface only as an unexplained benchmark shift. Every
//! expectation below was measured off the retired parquets before deletion.

use polars::prelude::*;

#[path = "../benches/common/mod.rs"]
#[allow(dead_code)] // the memoised 1k/100k helpers are for the benches
mod common;

/// Column names and dtypes exactly as the retired fixtures had them — the
/// benchmarks address these columns by name.
#[test]
fn schema_matches_the_retired_fixture() {
    let df = common::model_points(8).unwrap();
    let actual: Vec<(String, DataType)> = df
        .schema()
        .iter()
        .map(|(name, dtype)| (name.to_string(), dtype.clone()))
        .collect();

    let expected: Vec<(&str, DataType)> = vec![
        ("policyholder_nr", DataType::Int64),
        ("age", DataType::List(Box::new(DataType::Float64))),
        ("gender", DataType::String),
        ("smoking_status", DataType::String),
        ("sum_assured", DataType::Int64),
        (
            "policy_duration",
            DataType::List(Box::new(DataType::Float64)),
        ),
        ("num_proj_months", DataType::Int64),
        ("proj_months", DataType::List(Box::new(DataType::Int64))),
        ("proj_years", DataType::List(Box::new(DataType::Float64))),
        ("age-last", DataType::List(Box::new(DataType::Float64))),
        ("gender_smoking", DataType::String),
    ];

    assert_eq!(actual.len(), expected.len(), "column count");
    for (got, want) in actual.iter().zip(expected.iter()) {
        assert_eq!(got.0, want.0, "column name");
        assert_eq!(got.1, want.1, "dtype of {}", want.0);
    }
}

/// The per-row derivations. Checking every row of a 1,000-policy frame also
/// covers the full 22..=71 issue-age range.
#[test]
fn every_list_column_follows_its_derivation() {
    let df = common::model_points(1_000).unwrap();

    for row in 0..df.height() {
        let age = list_f64(&df, "age", row);
        let age_last = list_f64(&df, "age-last", row);
        let duration = list_f64(&df, "policy_duration", row);
        let years = list_f64(&df, "proj_years", row);
        let months = list_i64(&df, "proj_months", row);

        let issue_age = age[0];
        let n = age.len();

        // Monthly projection from the issue age to exactly 100.
        assert_eq!(
            n,
            ((100.0 - issue_age) * 12.0 + 1.0) as usize,
            "row {row} length"
        );
        assert_eq!(age[n - 1], 100.0, "row {row} terminal age");
        assert!(
            (22.0..=71.0).contains(&issue_age),
            "row {row} issue age {issue_age}"
        );

        let duration_at_issue = duration[0];
        assert!(
            (1.0..=19.0).contains(&duration_at_issue),
            "row {row} duration at issue {duration_at_issue}"
        );

        for i in 0..n {
            let frac = i as f64 / 12.0;
            assert_eq!(age[i], issue_age + frac, "row {row} age[{i}]");
            assert_eq!(
                age_last[i],
                (issue_age + frac).floor(),
                "row {row} age-last[{i}]"
            );
            assert_eq!(
                duration[i],
                duration_at_issue + frac,
                "row {row} duration[{i}]"
            );
            assert_eq!(months[i], i as i64, "row {row} proj_months[{i}]");
            // Ordinal policy year: month 0 is year 0, months 1..=12 are year 1.
            assert_eq!(years[i], i.div_ceil(12) as f64, "row {row} proj_years[{i}]");
        }
    }
}

/// Scalar columns, including the two that the retired fixture kept consistent
/// with the list lengths.
#[test]
fn scalar_columns_agree_with_the_lists() {
    let df = common::model_points(1_000).unwrap();
    let nr = df.column("policyholder_nr").unwrap().i64().unwrap();
    let npm = df.column("num_proj_months").unwrap().i64().unwrap();
    let gender = df.column("gender").unwrap().str().unwrap();
    let smoking = df.column("smoking_status").unwrap().str().unwrap();
    let combined = df.column("gender_smoking").unwrap().str().unwrap();
    let sum_assured = df.column("sum_assured").unwrap().i64().unwrap();

    for row in 0..df.height() {
        // policyholder_nr is 1-based and contiguous.
        assert_eq!(
            nr.get(row).unwrap(),
            row as i64 + 1,
            "row {row} policyholder_nr"
        );
        // num_proj_months == list length (not length - 1).
        assert_eq!(
            npm.get(row).unwrap() as usize,
            list_f64(&df, "age", row).len(),
            "row {row} num_proj_months"
        );

        let g = gender.get(row).unwrap();
        let s = smoking.get(row).unwrap();
        assert!(g == "F" || g == "M", "row {row} gender {g}");
        assert!(s == "S" || s == "NS", "row {row} smoking {s}");
        assert_eq!(
            combined.get(row).unwrap(),
            format!("{g}{s}"),
            "row {row} gender_smoking"
        );

        let sa = sum_assured.get(row).unwrap();
        assert!(
            (100_000..=929_571).contains(&sa),
            "row {row} sum_assured {sa}"
        );
    }
}

/// The property the committed fixtures had: the 1k file was byte-identical to
/// the first 1,000 rows of the 100k file. Benchmarks compare across sizes, so a
/// smaller set must stay an exact prefix rather than an independent sample.
#[test]
fn smaller_sets_are_exact_prefixes_of_larger_ones() {
    let small = common::model_points(100).unwrap();
    let large = common::model_points(2_500).unwrap();
    assert!(
        small.equals(&large.head(Some(100))),
        "model_points(100) is not the first 100 rows of model_points(2_500)"
    );
}

/// Same input, same output — across runs and across platforms.
#[test]
fn generation_is_deterministic() {
    assert!(common::model_points(256)
        .unwrap()
        .equals(&common::model_points(256).unwrap()));
}

/// Guards the distribution the benchmarks depend on: lookups must span the whole
/// key space, not cluster on a few ages. Bounds are wide enough that they fail
/// only on a real regression, not on sampling noise.
#[test]
fn draws_cover_the_key_space() {
    let df = common::model_points(5_000).unwrap();

    let issue_ages: std::collections::HashSet<i64> = (0..df.height())
        .map(|r| list_f64(&df, "age", r)[0] as i64)
        .collect();
    assert_eq!(
        issue_ages.len(),
        50,
        "all 50 issue ages 22..=71 should appear"
    );

    let pairs: std::collections::HashSet<&str> = df
        .column("gender_smoking")
        .unwrap()
        .str()
        .unwrap()
        .into_no_null_iter()
        .collect();
    assert_eq!(
        pairs.len(),
        4,
        "all four gender/smoking pairs should appear"
    );

    // An even-ish split; a broken draw would skew far past this.
    let males = df
        .column("gender")
        .unwrap()
        .str()
        .unwrap()
        .into_no_null_iter()
        .filter(|g| *g == "M")
        .count();
    assert!(
        (2_000..3_000).contains(&males),
        "gender split skewed: {males}/5000 male"
    );
}

// --- helpers ---------------------------------------------------------------

fn list_f64(df: &DataFrame, name: &str, row: usize) -> Vec<f64> {
    let s = df
        .column(name)
        .unwrap()
        .list()
        .unwrap()
        .get_as_series(row)
        .unwrap();
    s.f64().unwrap().into_no_null_iter().collect()
}

fn list_i64(df: &DataFrame, name: &str, row: usize) -> Vec<i64> {
    let s = df
        .column(name)
        .unwrap()
        .list()
        .unwrap()
        .get_as_series(row)
        .unwrap();
    s.i64().unwrap().into_no_null_iter().collect()
}
