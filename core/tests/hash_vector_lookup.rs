// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

use gaspatchio_core_lib::assumptions::table::{AssumptionTable, StorageMode};
use polars::df;
use polars::prelude::*;

fn assert_hash_list_output(actual: &Series, expected: &[Vec<f64>]) -> PolarsResult<()> {
    let lists = actual.list()?;
    assert_eq!(lists.len(), expected.len());
    for (row, expected_inner) in expected.iter().enumerate() {
        let actual_inner = lists
            .get_as_series(row)
            .unwrap_or_else(|| panic!("output row {row} must be a present list"));
        let actual_inner = actual_inner.f64()?;
        assert_eq!(actual_inner.len(), expected_inner.len(), "row {row}");
        for (period, expected_value) in expected_inner.iter().enumerate() {
            let actual_value = actual_inner
                .get(period)
                .unwrap_or_else(|| panic!("row {row}, period {period} must be non-null"));
            if expected_value.is_nan() {
                assert!(actual_value.is_nan(), "row {row}, period {period}");
            } else {
                assert_eq!(actual_value, *expected_value, "row {row}, period {period}");
            }
        }
    }
    Ok(())
}

fn two_key_hash_table() -> PolarsResult<AssumptionTable> {
    AssumptionTable::build_with_mode(
        df! {
            "age" => [30_i64, 30, 31, 31, 32, 32],
            "gender" => ["M", "F", "M", "F", "M", "F"],
            "rate" => [3001.0, 3002.0, 3101.0, 3102.0, 3201.0, 3202.0],
        }?,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Hash,
    )
}

fn three_key_hash_table() -> PolarsResult<AssumptionTable> {
    AssumptionTable::build_with_mode(
        df! {
            "age" => [30_i64, 31, 31, 30],
            "duration" => [0_i64, 1, 0, 1],
            "band" => ["A", "A", "B", "B"],
            "rate" => [3000.0, 3110.0, 3101.0, 3011.0],
        }?,
        vec![
            "age".to_string(),
            "duration".to_string(),
            "band".to_string(),
        ],
        "rate".to_string(),
        StorageMode::Hash,
    )
}

// Preservation: a single vector key may be jagged across policies. Empty and
// null outer rows both produce present empty lists; an outer null is not
// propagated as an outer null in the result.
#[test]
fn hash_vector_preserves_jagged_empty_and_outer_null_rows() -> PolarsResult<()> {
    let table = AssumptionTable::build_with_mode(
        df! {
            "age" => [30_i64, 31, 32],
            "rate" => [30.0, 31.0, 32.0],
        }?,
        vec!["age".to_string()],
        "rate".to_string(),
        StorageMode::Hash,
    )?;
    let ages = ListChunked::from_iter([
        Some(Series::new("".into(), [30_i64, 31])),
        Some(Series::new("".into(), Vec::<i64>::new())),
        None,
        Some(Series::new("".into(), [32_i64])),
    ])
    .into_series();

    let result = table.lookup_series(&[&ages])?;
    assert_hash_list_output(&result, &[vec![30.0, 31.0], vec![], vec![], vec![32.0]])
}

// Preservation: an inner null is a lookup miss represented by NaN, and it
// neither truncates the row nor shifts the following period.
#[test]
fn hash_vector_inner_null_is_nan_without_shifting() -> PolarsResult<()> {
    let table = AssumptionTable::build_with_mode(
        df! {
            "age" => [30_i64, 31],
            "rate" => [30.0, 31.0],
        }?,
        vec!["age".to_string()],
        "rate".to_string(),
        StorageMode::Hash,
    )?;
    let ages =
        ListChunked::from_iter([Some(Series::new("".into(), [Some(30_i64), None, Some(31)]))])
            .into_series();

    let result = table.lookup_series(&[&ages])?;
    assert_hash_list_output(&result, &[vec![30.0, f64::NAN, 31.0]])
}

// Preservation of the two-codec fast path: a unit scalar literal broadcasts
// over outer rows exactly like an explicit same-valued per-policy scalar. A
// differing per-policy scalar remains row-specific.
#[test]
fn hash_vector_scalar_literal_matches_repeated_policy_scalar() -> PolarsResult<()> {
    let table = two_key_hash_table()?;
    let ages = ListChunked::from_iter([
        Some(Series::new("".into(), [30_i64, 31])),
        Some(Series::new("".into(), [31_i64, 30])),
    ])
    .into_series();
    let literal = Series::new("gender".into(), ["M"]);
    let repeated = Series::new("gender".into(), ["M", "M"]);
    let per_policy = Series::new("gender".into(), ["M", "F"]);

    let literal_result = table.lookup_series(&[&ages, &literal])?;
    let repeated_result = table.lookup_series(&[&ages, &repeated])?;
    let policy_result = table.lookup_series(&[&ages, &per_policy])?;

    assert_hash_list_output(
        &literal_result,
        &[vec![3001.0, 3101.0], vec![3101.0, 3001.0]],
    )?;
    assert_hash_list_output(
        &repeated_result,
        &[vec![3001.0, 3101.0], vec![3101.0, 3001.0]],
    )?;
    assert_hash_list_output(
        &policy_result,
        &[vec![3001.0, 3101.0], vec![3102.0, 3002.0]],
    )
}

// Preservation of the general (three-or-more codec) path with two vector
// containers and one per-policy scalar codec result.
#[test]
fn hash_vector_multiple_lists_and_policy_scalar_keep_key_order() -> PolarsResult<()> {
    let table = three_key_hash_table()?;
    let ages = ListChunked::from_iter([
        Some(Series::new("".into(), [30_i64, 31])),
        Some(Series::new("".into(), [31_i64, 30])),
    ])
    .into_series();
    let durations = ListChunked::from_iter([
        Some(Series::new("".into(), [0_i64, 1])),
        Some(Series::new("".into(), [0_i64, 1])),
    ])
    .into_series();
    let bands = Series::new("band".into(), ["A", "B"]);

    let result = table.lookup_series(&[&ages, &durations, &bands])?;
    assert_hash_list_output(&result, &[vec![3000.0, 3110.0], vec![3101.0, 3011.0]])
}

// Preservation: outer validity and zero offsets are distinct in the input but
// equivalent for output sizing. A null first vector paired with an empty later
// vector, and an empty first vector paired with a null later vector, both yield
// present empty result rows. A non-empty aligned row still looks up normally.
#[test]
fn hash_vector_first_and_nonfirst_outer_nulls_with_zero_length_peer() -> PolarsResult<()> {
    let table = three_key_hash_table()?;
    let ages = ListChunked::from_iter([
        None,
        Some(Series::new("".into(), [30_i64])),
        Some(Series::new("".into(), Vec::<i64>::new())),
    ])
    .into_series();
    let durations = ListChunked::from_iter([
        Some(Series::new("".into(), Vec::<i64>::new())),
        Some(Series::new("".into(), [0_i64])),
        None,
    ])
    .into_series();
    let bands = Series::new("band".into(), ["A", "A", "A"]);

    let result = table.lookup_series(&[&ages, &durations, &bands])?;
    assert_hash_list_output(&result, &[vec![], vec![3000.0], vec![]])
}

// Preservation of validation order and diagnostics. Key arity is checked
// first; then outer vector lengths; then per-row inner lengths. A non-first
// outer null has zero inner length and therefore conflicts with a non-empty
// first vector at that row.
#[test]
fn hash_vector_validation_order_and_length_errors_remain_exact() -> PolarsResult<()> {
    let two_key = two_key_hash_table()?;
    let only_one_key = ListChunked::from_iter([
        Some(Series::new("".into(), [30_i64])),
        Some(Series::new("".into(), [31_i64])),
    ])
    .into_series();
    let wrong_arity = two_key.lookup_series(&[&only_one_key]).unwrap_err();
    assert!(matches!(&wrong_arity, PolarsError::ShapeMismatch(_)));
    assert!(wrong_arity.to_string().contains("wrong # key columns"));

    let three_key = three_key_hash_table()?;
    let ages = ListChunked::from_iter([
        Some(Series::new("".into(), [30_i64, 31])),
        Some(Series::new("".into(), [31_i64])),
    ])
    .into_series();
    let durations = ListChunked::from_iter([
        Some(Series::new("".into(), [0_i64])),
        Some(Series::new("".into(), [1_i64])),
        Some(Series::new("".into(), [0_i64])),
    ])
    .into_series();
    let bands = Series::new("band".into(), ["A", "A", "B"]);
    let outer_mismatch = three_key
        .lookup_series(&[&ages, &durations, &bands])
        .unwrap_err();
    assert!(matches!(&outer_mismatch, PolarsError::ShapeMismatch(_)));
    assert!(outer_mismatch
        .to_string()
        .contains("Vector length mismatch: expected 2, got 3 for column 1"));

    let durations = ListChunked::from_iter([
        Some(Series::new("".into(), [0_i64])),
        Some(Series::new("".into(), [0_i64])),
    ])
    .into_series();
    let bands = Series::new("band".into(), ["A", "A"]);
    let inner_mismatch = three_key
        .lookup_series(&[&ages, &durations, &bands])
        .unwrap_err();
    assert!(matches!(&inner_mismatch, PolarsError::ShapeMismatch(_)));
    // Ragged keys are named by their columns and the policy's two lengths,
    // never by the batch row they were met at.
    let inner_message = inner_mismatch.to_string();
    assert!(
        inner_message.contains("mismatched inner list lengths in one policy"),
        "{inner_message}"
    );
    assert!(
        inner_message.contains("=2") && inner_message.contains("=1"),
        "{inner_message}"
    );
    assert!(!inner_message.contains("at row"), "{inner_message}");

    let first_nonempty = ListChunked::from_iter([
        Some(Series::new("".into(), [30_i64])),
        Some(Series::new("".into(), [31_i64])),
    ])
    .into_series();
    let later_outer_null =
        ListChunked::from_iter([None, Some(Series::new("".into(), [1_i64]))]).into_series();
    let later_null_mismatch = three_key
        .lookup_series(&[&first_nonempty, &later_outer_null, &bands])
        .unwrap_err();
    assert!(matches!(
        &later_null_mismatch,
        PolarsError::ShapeMismatch(_)
    ));
    let later_null_message = later_null_mismatch.to_string();
    assert!(
        later_null_message.contains("mismatched inner list lengths in one policy"),
        "{later_null_message}"
    );
    assert!(
        later_null_message.contains("=1") && later_null_message.contains("=0"),
        "{later_null_message}"
    );
    assert!(
        !later_null_message.contains("at row"),
        "{later_null_message}"
    );
    Ok(())
}

// Preservation across Arrow offsets and chunks. The assertion on chunk count
// ensures the fixture reaches the intended input shape before it is sliced.
#[test]
fn hash_vector_sliced_chunked_lists_and_scalars_keep_outer_alignment() -> PolarsResult<()> {
    let table = two_key_hash_table()?;
    let mut ages = ListChunked::from_iter([
        Some(Series::new("".into(), [99_i64])),
        Some(Series::new("".into(), [30_i64, 31])),
    ])
    .into_series();
    let ages_tail = ListChunked::from_iter([
        Some(Series::new("".into(), [31_i64])),
        Some(Series::new("".into(), Vec::<i64>::new())),
    ])
    .into_series();
    ages.append(&ages_tail)?;
    assert!(ages.n_chunks() > 1);
    let ages = ages.slice(1, 3);

    let mut genders = Series::new("gender".into(), ["X", "M"]);
    let genders_tail = Series::new("gender".into(), ["F", "M"]);
    genders.append(&genders_tail)?;
    assert!(genders.n_chunks() > 1);
    let genders = genders.slice(1, 3);

    let result = table.lookup_series(&[&ages, &genders])?;
    assert_hash_list_output(&result, &[vec![3001.0, 3101.0], vec![3102.0], vec![]])
}

// Preservation after immutable append/rebuild: the vector path must see both
// the old map entry and the appended entry, with a missing key still NaN.
#[test]
fn hash_vector_lookup_after_append_sees_old_and_new_entries() -> PolarsResult<()> {
    let base = AssumptionTable::build_with_mode(
        df! {
            "age" => [30_i64],
            "gender" => ["M"],
            "rate" => [3001.0],
        }?,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Hash,
    )?;
    let combined = AssumptionTable::build_combined(
        &base,
        df! {
            "age" => [31_i64],
            "gender" => ["M"],
            "rate" => [3101.0],
        }?,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
    )?;
    let ages =
        ListChunked::from_iter([Some(Series::new("".into(), [30_i64, 31, 32]))]).into_series();
    let gender = Series::new("gender".into(), ["M"]);

    let result = combined.lookup_series(&[&ages, &gender])?;
    assert_hash_list_output(&result, &[vec![3001.0, 3101.0, f64::NAN]])
}
