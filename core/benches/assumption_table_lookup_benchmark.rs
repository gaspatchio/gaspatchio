use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use gaspatchio_core_lib::assumptions::table::{AssumptionTable, StorageMode};
use polars::prelude::*;
use polars_core::utils::concat_df;
use std::fs::File;
use std::path::Path;

// Helper function to load the 1k model points DataFrame from Parquet
fn load_model_points_1k() -> PolarsResult<DataFrame> {
    let path =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("benches/fixtures/age-last-smoking-1k.parquet");
    let file = File::open(&path).map_err(|e| {
        PolarsError::ComputeError(
            format!("Failed to open 1k key source parquet {:?}: {}", path, e).into(),
        )
    })?;
    ParquetReader::new(file).finish()
}

// Helper function to load the 100k model points DataFrame from Parquet
fn load_model_points_100k() -> PolarsResult<DataFrame> {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("benches/fixtures/age-last-smoking-100k.parquet");
    let file = File::open(&path).map_err(|e| {
        PolarsError::ComputeError(
            format!("Failed to open 100k key source parquet {:?}: {}", path, e).into(),
        )
    })?;
    ParquetReader::new(file).finish()
}

// Custom melt implementation (copied from the main crate)
fn custom_melt(
    df: &DataFrame,
    id_vars: &[&str],
    value_vars: &[&str],
    variable_name: &str,
    value_name: &str,
) -> PolarsResult<DataFrame> {
    // Extract the identifier columns
    let id_df = df.select(id_vars.iter().map(|s| s.to_string()))?;

    // For each column to melt, create a DataFrame with the id_vars, a "variable" column and a "value" column.
    let mut melted_frames = Vec::with_capacity(value_vars.len());
    for &col in value_vars {
        // Create a Series filled with the current column name
        let var_series = Series::new(variable_name.into(), vec![col; df.height()]);
        // Get the value Series (and optionally rename it)
        let value_series = df.column(col)?.clone().with_name(value_name.into());
        // Build a temporary DataFrame with the id columns
        let mut temp_df = id_df.clone();
        temp_df.with_column(var_series)?;
        temp_df.with_column(value_series)?;
        melted_frames.push(temp_df);
    }

    // Concatenate all the melted DataFrames vertically
    concat_df(&melted_frames)
}

// Helper function to create the mortality assumption table (mimics setup_registry)
fn create_mortality_table() -> PolarsResult<AssumptionTable> {
    // Create a realistic mortality table with 100+ ages and multiple factors
    let ages: Vec<i64> = (18..=100).collect(); // 83 ages
    let df_mortality_wide = df!(
        "age-last" => ages.clone(),
        "MNS" => ages.iter().map(|&age| 0.001 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "FNS" => ages.iter().map(|&age| 0.0008 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "MS" => ages.iter().map(|&age| 0.0015 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "FS" => ages.iter().map(|&age| 0.0012 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
    )?;

    // Transform from wide to long format using custom_melt
    let df_mortality_long = custom_melt(
        &df_mortality_wide,
        &["age-last"],
        &["MNS", "FNS", "MS", "FS"],
        "gender_smoking",
        "mortality_rate",
    )?;

    // Build the AssumptionTable
    AssumptionTable::build(
        df_mortality_long,
        vec!["age-last".to_string(), "gender_smoking".to_string()],
        "mortality_rate".to_string(),
    )
}

// Helper function to create the mortality table with a specific storage mode
fn create_mortality_table_with_mode(mode: StorageMode) -> PolarsResult<AssumptionTable> {
    let ages: Vec<i64> = (18..=100).collect(); // 83 ages
    let df_mortality_wide = df!(
        "age-last" => ages.clone(),
        "MNS" => ages.iter().map(|&age| 0.001 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "FNS" => ages.iter().map(|&age| 0.0008 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "MS" => ages.iter().map(|&age| 0.0015 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "FS" => ages.iter().map(|&age| 0.0012 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
    )?;

    let df_mortality_long = custom_melt(
        &df_mortality_wide,
        &["age-last"],
        &["MNS", "FNS", "MS", "FS"],
        "gender_smoking",
        "mortality_rate",
    )?;

    AssumptionTable::build_with_mode(
        df_mortality_long,
        vec!["age-last".to_string(), "gender_smoking".to_string()],
        "mortality_rate".to_string(),
        mode,
    )
}

// Benchmark function using AssumptionTable with 1k model points
fn benchmark_assumption_table_lookup_1k(c: &mut Criterion) {
    // Setup: Create the mortality assumption table
    let mortality_table = match create_mortality_table() {
        Ok(table) => table,
        Err(e) => {
            eprintln!("Failed to create mortality assumption table: {}", e);
            return;
        }
    };

    // Load the 1k model points (outside benchmark)
    let df_model_points = match load_model_points_1k() {
        Ok(df) => df,
        Err(e) => {
            eprintln!("Failed to load 1k key source parquet for benchmark: {}", e);
            return;
        }
    };

    // Extract key columns needed for lookups (outside benchmark)
    let age_key_col = match df_model_points.column("age-last") {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to get 'age-last' column from 1k parquet: {}", e);
            return;
        }
    };
    let gender_smoking_key_col = match df_model_points.column("gender_smoking") {
        Ok(s) => s,
        Err(e) => {
            eprintln!(
                "Failed to get 'gender_smoking' column from 1k parquet: {}",
                e
            );
            return;
        }
    };

    // Prepare key columns for lookup (outside benchmark)
    let mortality_keys: Vec<&Series> = vec![
        age_key_col
            .as_series()
            .expect("Failed to convert age_key_col to Series"),
        gender_smoking_key_col
            .as_series()
            .expect("Failed to convert gender_smoking_key_col to Series"),
    ];

    let mut group = c.benchmark_group("assumption_table_lookup_1k");

    // Benchmark pure lookup performance (excluding data loading)
    group.bench_function("mortality_assumption_table_lookup_1k", |b| {
        b.iter(|| {
            let result = mortality_table.lookup_series(black_box(&mortality_keys));
            if let Err(e) = &result {
                eprintln!(
                    "1k Mortality assumption table lookup failed during benchmark: {:?}",
                    e
                );
            }
            black_box(result)
        })
    });

    group.finish();
}

// Benchmark function using AssumptionTable with 100k model points
fn benchmark_assumption_table_lookup_100k(c: &mut Criterion) {
    // Setup: Create the mortality assumption table
    let mortality_table = match create_mortality_table() {
        Ok(table) => table,
        Err(e) => {
            eprintln!("Failed to create mortality assumption table: {}", e);
            return;
        }
    };

    // Load the 100k model points
    let df_model_points = match load_model_points_100k() {
        Ok(df) => df,
        Err(e) => {
            eprintln!(
                "Failed to load 100k key source parquet for benchmark: {}",
                e
            );
            return;
        }
    };

    // Extract key columns needed for lookups
    let age_key_col = match df_model_points.column("age-last") {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to get 'age-last' column from 100k parquet: {}", e);
            return;
        }
    };
    let gender_smoking_key_col = match df_model_points.column("gender_smoking") {
        Ok(s) => s,
        Err(e) => {
            eprintln!(
                "Failed to get 'gender_smoking' column from 100k parquet: {}",
                e
            );
            return;
        }
    };

    // Prepare key columns for lookup
    let mortality_keys: Vec<&Series> = vec![
        age_key_col
            .as_series()
            .expect("Failed to convert age_key_col to Series"),
        gender_smoking_key_col
            .as_series()
            .expect("Failed to convert gender_smoking_key_col to Series"),
    ];

    let mut group = c.benchmark_group("assumption_table_lookup_100k");

    // Benchmark mortality lookup using AssumptionTable
    group.bench_function("mortality_assumption_table_lookup_100k", |b| {
        b.iter(|| {
            let result = mortality_table.lookup_series(black_box(&mortality_keys));
            if let Err(e) = &result {
                eprintln!(
                    "100k Mortality assumption table lookup failed during benchmark: {:?}",
                    e
                );
            }
            black_box(result)
        })
    });

    group.finish();
}

// Benchmark function for vector lookups using AssumptionTable with 1k model points
fn benchmark_assumption_table_vector_lookup_1k(c: &mut Criterion) {
    // Setup: Create the mortality assumption table
    let mortality_table = match create_mortality_table() {
        Ok(table) => table,
        Err(e) => {
            eprintln!(
                "Failed to create mortality assumption table for vector lookup: {}",
                e
            );
            return;
        }
    };

    // Load the 1k model points (outside benchmark)
    let df_model_points = match load_model_points_1k() {
        Ok(df) => df,
        Err(e) => {
            eprintln!(
                "Failed to load 1k key source parquet for vector benchmark: {}",
                e
            );
            return;
        }
    };

    // Extract key columns needed for vector lookups (outside benchmark)
    // age-last is List(Float64), gender_smoking is String (scalar that broadcasts)
    let age_vector_col = match df_model_points.column("age-last") {
        Ok(s) => s,
        Err(e) => {
            eprintln!(
                "Failed to get 'age-last' vector column from 1k parquet: {}",
                e
            );
            return;
        }
    };
    let gender_smoking_scalar_col = match df_model_points.column("gender_smoking") {
        Ok(s) => s,
        Err(e) => {
            eprintln!(
                "Failed to get 'gender_smoking' scalar column from 1k parquet: {}",
                e
            );
            return;
        }
    };

    // Prepare key columns for vector lookup (outside benchmark)
    let mortality_vector_keys: Vec<&Series> = vec![
        age_vector_col
            .as_series()
            .expect("Failed to convert age_vector_col to Series"),
        gender_smoking_scalar_col
            .as_series()
            .expect("Failed to convert gender_smoking_scalar_col to Series"),
    ];

    let mut group = c.benchmark_group("assumption_table_vector_lookup_1k");

    // Benchmark pure vector lookup performance (excluding data loading)
    group.bench_function("mortality_assumption_table_vector_lookup_1k", |b| {
        b.iter(|| {
            let result = mortality_table.lookup_series(black_box(&mortality_vector_keys));
            if let Err(e) = &result {
                eprintln!(
                    "1k Vector mortality assumption table lookup failed during benchmark: {:?}",
                    e
                );
            }
            black_box(result)
        })
    });

    group.finish();
}

// Benchmark function for vector lookups using AssumptionTable with 100k model points
fn benchmark_assumption_table_vector_lookup_100k(c: &mut Criterion) {
    // Setup: Create the mortality assumption table
    let mortality_table = match create_mortality_table() {
        Ok(table) => table,
        Err(e) => {
            eprintln!(
                "Failed to create mortality assumption table for vector lookup: {}",
                e
            );
            return;
        }
    };

    // Load the 100k model points
    let df_model_points = match load_model_points_100k() {
        Ok(df) => df,
        Err(e) => {
            eprintln!(
                "Failed to load 100k key source parquet for vector benchmark: {}",
                e
            );
            return;
        }
    };

    // Extract key columns needed for vector lookups
    // age-last is List(Float64), gender_smoking is String (scalar that broadcasts)
    let age_vector_col = match df_model_points.column("age-last") {
        Ok(s) => s,
        Err(e) => {
            eprintln!(
                "Failed to get 'age-last' vector column from 100k parquet: {}",
                e
            );
            return;
        }
    };
    let gender_smoking_scalar_col = match df_model_points.column("gender_smoking") {
        Ok(s) => s,
        Err(e) => {
            eprintln!(
                "Failed to get 'gender_smoking' scalar column from 100k parquet: {}",
                e
            );
            return;
        }
    };

    // Prepare key columns for vector lookup
    let mortality_vector_keys: Vec<&Series> = vec![
        age_vector_col
            .as_series()
            .expect("Failed to convert age_vector_col to Series"),
        gender_smoking_scalar_col
            .as_series()
            .expect("Failed to convert gender_smoking_scalar_col to Series"),
    ];

    let mut group = c.benchmark_group("assumption_table_vector_lookup_100k");

    // Benchmark vector mortality lookup using AssumptionTable
    group.bench_function("mortality_assumption_table_vector_lookup_100k", |b| {
        b.iter(|| {
            let result = mortality_table.lookup_series(black_box(&mortality_vector_keys));
            if let Err(e) = &result {
                eprintln!(
                    "100k Vector mortality assumption table lookup failed during benchmark: {:?}",
                    e
                );
            }
            black_box(result)
        })
    });

    group.finish();
}

// Benchmark comparing hash vs array storage with 1k model points
fn benchmark_hash_vs_array_1k(c: &mut Criterion) {
    let df_model_points = match load_model_points_1k() {
        Ok(df) => df,
        Err(e) => {
            eprintln!("Failed to load 1k model points: {}", e);
            return;
        }
    };

    let age_col = df_model_points
        .column("age-last")
        .unwrap()
        .as_series()
        .unwrap();
    let gender_col = df_model_points
        .column("gender_smoking")
        .unwrap()
        .as_series()
        .unwrap();
    let keys: Vec<&Series> = vec![age_col, gender_col];

    let mut group = c.benchmark_group("hash_vs_array_1k");

    // Hash storage
    let hash_table = create_mortality_table_with_mode(StorageMode::Hash)
        .expect("Failed to create hash table");
    group.bench_function("hash_lookup_1k", |b| {
        b.iter(|| {
            let result = hash_table.lookup_series(black_box(&keys));
            black_box(result)
        })
    });

    // Array storage
    let array_table = create_mortality_table_with_mode(StorageMode::Array)
        .expect("Failed to create array table");
    assert!(
        array_table.is_array_storage(),
        "Should use array storage for dense table"
    );
    group.bench_function("array_lookup_1k", |b| {
        b.iter(|| {
            let result = array_table.lookup_series(black_box(&keys));
            black_box(result)
        })
    });

    group.finish();
}

// Benchmark comparing hash vs array storage with 100k model points
fn benchmark_hash_vs_array_100k(c: &mut Criterion) {
    let df_model_points = match load_model_points_100k() {
        Ok(df) => df,
        Err(e) => {
            eprintln!("Failed to load 100k model points: {}", e);
            return;
        }
    };

    let age_col = df_model_points
        .column("age-last")
        .unwrap()
        .as_series()
        .unwrap();
    let gender_col = df_model_points
        .column("gender_smoking")
        .unwrap()
        .as_series()
        .unwrap();
    let keys: Vec<&Series> = vec![age_col, gender_col];

    let mut group = c.benchmark_group("hash_vs_array_100k");
    group.sample_size(20); // Reduce sample size for long benchmarks

    // Hash storage
    let hash_table = create_mortality_table_with_mode(StorageMode::Hash)
        .expect("Failed to create hash table");
    group.bench_function("hash_lookup_100k", |b| {
        b.iter(|| {
            let result = hash_table.lookup_series(black_box(&keys));
            black_box(result)
        })
    });

    // Array storage
    let array_table = create_mortality_table_with_mode(StorageMode::Array)
        .expect("Failed to create array table");
    group.bench_function("array_lookup_100k", |b| {
        b.iter(|| {
            let result = array_table.lookup_series(black_box(&keys));
            black_box(result)
        })
    });

    group.finish();
}

// Parameterized benchmark with scaling across different sizes
fn benchmark_scaling(c: &mut Criterion) {
    let mut group = c.benchmark_group("lookup_scaling");

    for size in [1_000, 10_000, 100_000].iter() {
        // Load or create appropriately sized model points
        let df = if *size <= 1_000 {
            load_model_points_1k().unwrap()
        } else {
            load_model_points_100k().unwrap().head(Some(*size))
        };

        let age_col = df.column("age-last").unwrap().as_series().unwrap();
        let gender_col = df.column("gender_smoking").unwrap().as_series().unwrap();
        let keys: Vec<&Series> = vec![age_col, gender_col];

        let hash_table = create_mortality_table_with_mode(StorageMode::Hash).unwrap();
        let array_table = create_mortality_table_with_mode(StorageMode::Array).unwrap();

        group.bench_with_input(BenchmarkId::new("hash", size), size, |b, _| {
            b.iter(|| hash_table.lookup_series(black_box(&keys)))
        });

        group.bench_with_input(BenchmarkId::new("array", size), size, |b, _| {
            b.iter(|| array_table.lookup_series(black_box(&keys)))
        });
    }

    group.finish();
}

criterion_group!(
    benches,
    benchmark_assumption_table_lookup_1k,
    //benchmark_assumption_table_lookup_100k,
    benchmark_assumption_table_vector_lookup_1k,
    //benchmark_assumption_table_vector_lookup_100k
    benchmark_hash_vs_array_1k,
    benchmark_hash_vs_array_100k,
    benchmark_scaling,
);
criterion_main!(benches);
