// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Integration tests for assumption table storage backends.
// ABOUTME: Verifies hash and array storage produce identical results.

use gaspatchio_core_lib::assumptions::table::{AssumptionTable, StorageMode};
use polars::prelude::*;

fn create_test_df() -> PolarsResult<DataFrame> {
    df! {
        "age" => [30i64, 30, 31, 31, 32, 32, 33, 33],
        "gender" => ["M", "F", "M", "F", "M", "F", "M", "F"],
        "rate" => [0.001, 0.0008, 0.0012, 0.001, 0.0014, 0.0012, 0.0016, 0.0014]
    }
}

#[test]
fn test_hash_and_array_produce_same_results() -> PolarsResult<()> {
    let df = create_test_df()?;

    let hash_table = AssumptionTable::build_with_mode(
        df.clone(),
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Hash,
    )?;

    let array_table = AssumptionTable::build_with_mode(
        df,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Array,
    )?;

    // Verify storage modes
    assert!(!hash_table.is_array_storage());
    assert!(array_table.is_array_storage());

    // Test with various inputs including invalid keys
    let ages = Series::new("age".into(), &[30i64, 31, 32, 33, 99]);
    let genders = Series::new("gender".into(), &["M", "F", "M", "F", "X"]);

    let hash_result = hash_table.lookup_series(&[&ages, &genders])?;
    let array_result = array_table.lookup_series(&[&ages, &genders])?;

    // Results should be identical (including NaN positions)
    let hash_vals: Vec<f64> = hash_result
        .f64()?
        .into_iter()
        .map(|v| v.unwrap_or(f64::NAN))
        .collect();
    let array_vals: Vec<f64> = array_result
        .f64()?
        .into_iter()
        .map(|v| v.unwrap_or(f64::NAN))
        .collect();

    for (h, a) in hash_vals.iter().zip(array_vals.iter()) {
        if h.is_nan() {
            assert!(a.is_nan(), "Both should be NaN");
        } else {
            assert!((h - a).abs() < 1e-15, "Values should match: {} vs {}", h, a);
        }
    }

    Ok(())
}

#[test]
fn test_auto_mode_chooses_array_for_dense_tables() -> PolarsResult<()> {
    // Dense table: 8 rows for 4*2=8 combinations = 100% density
    let df = create_test_df()?;

    let table = AssumptionTable::build_with_mode(
        df,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Auto,
    )?;

    assert!(
        table.is_array_storage(),
        "Auto should choose array for dense table"
    );

    Ok(())
}

#[test]
fn test_auto_mode_uses_array_for_multi_string_keys() -> PolarsResult<()> {
    // Tables with 2+ string key columns should use array storage (dense)
    // and return CORRECT values (not NaN). This was previously broken because
    // the categorical encoder used non-contiguous global physical indices.
    let df = df! {
        "product" => ["TERM", "WL", "UL", "TERM", "WL", "UL"],
        "region" => ["US", "EU", "US", "EU", "US", "EU"],
        "rate" => [0.01, 0.02, 0.015, 0.022, 0.011, 0.021]
    }?;

    let table = AssumptionTable::build_with_mode(
        df,
        vec!["product".to_string(), "region".to_string()],
        "rate".to_string(),
        StorageMode::Auto,
    )?;

    // Dense table (6 rows / 6 combos = 100%) should use array for performance
    assert!(
        table.is_array_storage(),
        "Auto should choose array for dense multi-string-key table"
    );

    // Verify lookups return correct values (not NaN)
    let products = Series::new("product".into(), &["TERM", "WL", "UL", "TERM"]);
    let regions = Series::new("region".into(), &["US", "EU", "US", "EU"]);

    let result = table.lookup_series(&[&products, &regions])?;
    let vals: Vec<Option<f64>> = result.f64()?.into_iter().collect();

    assert_eq!(vals[0], Some(0.01)); // TERM, US
    assert_eq!(vals[1], Some(0.02)); // WL, EU
    assert_eq!(vals[2], Some(0.015)); // UL, US
    assert_eq!(vals[3], Some(0.022)); // TERM, EU

    Ok(())
}

#[test]
fn test_auto_mode_uses_array_for_single_string_key() -> PolarsResult<()> {
    // Tables with only 1 string key column should use array when dense
    let df = create_test_df()?; // age (int) + gender (string) = 1 string key

    let table = AssumptionTable::build_with_mode(
        df,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Auto,
    )?;

    assert!(
        table.is_array_storage(),
        "Auto should choose array for dense table with 1 string key"
    );

    Ok(())
}

#[test]
fn test_auto_mode_chooses_hash_for_sparse_tables() -> PolarsResult<()> {
    // Sparse table: 2 rows for 100*100=10000 combinations = 0.02% density
    let df = df! {
        "key1" => [0i64, 99],
        "key2" => [0i64, 99],
        "value" => [1.0, 2.0]
    }?;

    let table = AssumptionTable::build_with_mode(
        df,
        vec!["key1".to_string(), "key2".to_string()],
        "value".to_string(),
        StorageMode::Auto,
    )?;

    assert!(
        !table.is_array_storage(),
        "Auto should choose hash for sparse table"
    );

    Ok(())
}

#[test]
fn test_force_hash_mode() -> PolarsResult<()> {
    let df = create_test_df()?;

    let table = AssumptionTable::build_with_mode(
        df,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Hash,
    )?;

    assert!(
        !table.is_array_storage(),
        "Hash mode should force hash storage"
    );

    Ok(())
}

#[test]
fn test_storage_mode_from_str() -> PolarsResult<()> {
    use std::str::FromStr;

    assert!(matches!(
        StorageMode::from_str("hash"),
        Ok(StorageMode::Hash)
    ));
    assert!(matches!(
        StorageMode::from_str("Hash"),
        Ok(StorageMode::Hash)
    ));
    assert!(matches!(
        StorageMode::from_str("HASH"),
        Ok(StorageMode::Hash)
    ));
    assert!(matches!(
        StorageMode::from_str("array"),
        Ok(StorageMode::Array)
    ));
    assert!(matches!(
        StorageMode::from_str("Array"),
        Ok(StorageMode::Array)
    ));
    assert!(matches!(
        StorageMode::from_str("auto"),
        Ok(StorageMode::Auto)
    ));
    assert!(matches!(
        StorageMode::from_str("Auto"),
        Ok(StorageMode::Auto)
    ));

    assert!(StorageMode::from_str("invalid").is_err());

    Ok(())
}

#[test]
fn test_storage_mode_query() -> PolarsResult<()> {
    let df = create_test_df()?;

    let hash_table = AssumptionTable::build_with_mode(
        df.clone(),
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Hash,
    )?;

    let array_table = AssumptionTable::build_with_mode(
        df,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Array,
    )?;

    assert_eq!(hash_table.storage_mode(), StorageMode::Hash);
    assert_eq!(array_table.storage_mode(), StorageMode::Array);

    Ok(())
}

#[test]
fn test_large_batch_consistency() -> PolarsResult<()> {
    // Test with a larger batch to exercise parallel code paths
    let df = create_test_df()?;

    let hash_table = AssumptionTable::build_with_mode(
        df.clone(),
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Hash,
    )?;

    let array_table = AssumptionTable::build_with_mode(
        df,
        vec!["age".to_string(), "gender".to_string()],
        "rate".to_string(),
        StorageMode::Array,
    )?;

    // Create 5000 lookups (more than CHUNK_SIZE of 1024)
    let ages: Vec<i64> = (0..5000).map(|i| 30 + (i % 4) as i64).collect();
    let genders: Vec<&str> = (0..5000)
        .map(|i| if i % 2 == 0 { "M" } else { "F" })
        .collect();

    let age_series = Series::new("age".into(), ages);
    let gender_series = Series::new("gender".into(), genders);

    let hash_result = hash_table.lookup_series(&[&age_series, &gender_series])?;
    let array_result = array_table.lookup_series(&[&age_series, &gender_series])?;

    // Verify all values match
    let hash_vals: Vec<f64> = hash_result
        .f64()?
        .into_iter()
        .map(|v| v.unwrap_or(f64::NAN))
        .collect();
    let array_vals: Vec<f64> = array_result
        .f64()?
        .into_iter()
        .map(|v| v.unwrap_or(f64::NAN))
        .collect();

    assert_eq!(hash_vals.len(), 5000);
    assert_eq!(array_vals.len(), 5000);

    for (i, (h, a)) in hash_vals.iter().zip(array_vals.iter()).enumerate() {
        assert!(
            (h - a).abs() < 1e-15,
            "Mismatch at index {}: {} vs {}",
            i,
            h,
            a
        );
    }

    Ok(())
}
