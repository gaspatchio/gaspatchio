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

    // Build the AssumptionTable with Hash mode for vector lookup compatibility
    AssumptionTable::build_with_mode(
        df_mortality_long,
        vec!["age-last".to_string(), "gender_smoking".to_string()],
        "mortality_rate".to_string(),
        StorageMode::Hash,
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
    let hash_table =
        create_mortality_table_with_mode(StorageMode::Hash).expect("Failed to create hash table");
    group.bench_function("hash_lookup_1k", |b| {
        b.iter(|| {
            let result = hash_table.lookup_series(black_box(&keys));
            black_box(result)
        })
    });

    // Array storage
    let array_table =
        create_mortality_table_with_mode(StorageMode::Array).expect("Failed to create array table");
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
    let hash_table =
        create_mortality_table_with_mode(StorageMode::Hash).expect("Failed to create hash table");
    group.bench_function("hash_lookup_100k", |b| {
        b.iter(|| {
            let result = hash_table.lookup_series(black_box(&keys));
            black_box(result)
        })
    });

    // Array storage
    let array_table =
        create_mortality_table_with_mode(StorageMode::Array).expect("Failed to create array table");
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

// =============================================================================
// Realistic Benchmarks using actual actuarial assumption tables
// =============================================================================

/// Load the actual mortality_select assumption table from appliedlife model.
/// 9600 rows with keys: [table_id (str), attained_age (i64), duration (i64)]
fn load_mortality_select_table(mode: StorageMode) -> PolarsResult<AssumptionTable> {
    let path =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("benches/fixtures/mortality_select.parquet");
    let file = File::open(&path).map_err(|e| {
        PolarsError::ComputeError(format!("Failed to open mortality_select parquet: {}", e).into())
    })?;
    let df = ParquetReader::new(file).finish()?;

    AssumptionTable::build_with_mode(
        df,
        vec![
            "table_id".to_string(),
            "attained_age".to_string(),
            "duration".to_string(),
        ],
        "mort_rate".to_string(),
        mode,
    )
}

/// Load the actual lapse_rates assumption table.
/// 60 rows with keys: [duration (i64), lapse_id (str)]
fn load_lapse_rates_table(mode: StorageMode) -> PolarsResult<AssumptionTable> {
    let path =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("benches/fixtures/lapse_rates.parquet");
    let file = File::open(&path).map_err(|e| {
        PolarsError::ComputeError(format!("Failed to open lapse_rates parquet: {}", e).into())
    })?;
    let df = ParquetReader::new(file).finish()?;

    AssumptionTable::build_with_mode(
        df,
        vec!["duration".to_string(), "lapse_id".to_string()],
        "lapse_rate".to_string(),
        mode,
    )
}

/// Load the actual risk_free_rates assumption table.
/// 1800 rows with keys: [scenario (str), currency (str), year (i64)]
fn load_risk_free_rates_table(mode: StorageMode) -> PolarsResult<AssumptionTable> {
    let path =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("benches/fixtures/risk_free_rates.parquet");
    let file = File::open(&path).map_err(|e| {
        PolarsError::ComputeError(format!("Failed to open risk_free_rates parquet: {}", e).into())
    })?;
    let df = ParquetReader::new(file).finish()?;

    AssumptionTable::build_with_mode(
        df,
        vec![
            "scenario".to_string(),
            "currency".to_string(),
            "year".to_string(),
        ],
        "forward_rate".to_string(),
        mode,
    )
}

/// Benchmark mortality_select table with realistic lookup patterns.
/// Simulates 1000 model points × 120 projection months = 120k individual lookups
fn benchmark_realistic_mortality_select(c: &mut Criterion) {
    // Create lookup keys simulating realistic actuarial model usage:
    // - 1000 model points (policies)
    // - Each policy has 120 projection months (10 years)
    // - Keys: table_id (categorical), attained_age (0-120), duration (0-30)

    let n_policies = 1000;
    let n_months = 120;
    let total_lookups = n_policies * n_months;

    // Generate realistic key data
    let table_ids: Vec<&str> = (0..total_lookups)
        .map(|_| "T3363") // Single table ID for this benchmark
        .collect();

    // Ages increment over projection: base_age + month/12
    let ages: Vec<i64> = (0..n_policies)
        .flat_map(|policy| {
            let base_age = 30 + (policy % 50) as i64; // Ages 30-79
            (0..n_months).map(move |month| base_age + (month as i64 / 12))
        })
        .collect();

    // Duration caps at 30, typically starts at policy duration + month
    let durations: Vec<i64> = (0..n_policies)
        .flat_map(|policy| {
            let base_dur = (policy % 10) as i64;
            (0..n_months).map(move |month| (base_dur + month as i64 / 12).min(30))
        })
        .collect();

    let table_id_series = Series::new("table_id".into(), table_ids);
    let age_series = Series::new("attained_age".into(), ages);
    let duration_series = Series::new("duration".into(), durations);

    let mut group = c.benchmark_group("realistic_mortality_select");
    group.sample_size(50);

    // Hash storage benchmark
    let hash_table = load_mortality_select_table(StorageMode::Hash)
        .expect("Failed to load mortality_select with hash storage");
    let keys: Vec<&Series> = vec![&table_id_series, &age_series, &duration_series];

    group.bench_function(
        format!("hash_{}k_lookups", total_lookups / 1000),
        |b| {
            b.iter(|| {
                let result = hash_table.lookup_series(black_box(&keys));
                black_box(result)
            })
        },
    );

    // Array storage benchmark
    let array_table = load_mortality_select_table(StorageMode::Array)
        .expect("Failed to load mortality_select with array storage");
    let is_array = array_table.is_array_storage();

    group.bench_function(
        format!("array_{}k_lookups{}", total_lookups / 1000, if is_array { "" } else { "_fallback_hash" }),
        |b| {
            b.iter(|| {
                let result = array_table.lookup_series(black_box(&keys));
                black_box(result)
            })
        },
    );

    group.finish();
}

/// Benchmark lapse_rates table - smaller table, simpler keys
fn benchmark_realistic_lapse_rates(c: &mut Criterion) {
    let n_policies = 1000;
    let n_months = 120;
    let total_lookups = n_policies * n_months;

    // Generate realistic key data
    let durations: Vec<i64> = (0..n_policies)
        .flat_map(|policy| {
            let base_dur = (policy % 10) as i64;
            (0..n_months).map(move |month| (base_dur + month as i64 / 12).min(30))
        })
        .collect();

    let lapse_ids: Vec<&str> = (0..total_lookups)
        .map(|i| if i % 2 == 0 { "L001" } else { "L002" })
        .collect();

    let duration_series = Series::new("duration".into(), durations);
    let lapse_id_series = Series::new("lapse_id".into(), lapse_ids);

    let mut group = c.benchmark_group("realistic_lapse_rates");
    group.sample_size(50);

    // Hash storage
    let hash_table = load_lapse_rates_table(StorageMode::Hash)
        .expect("Failed to load lapse_rates with hash storage");
    let keys: Vec<&Series> = vec![&duration_series, &lapse_id_series];

    group.bench_function(
        format!("hash_{}k_lookups", total_lookups / 1000),
        |b| {
            b.iter(|| {
                let result = hash_table.lookup_series(black_box(&keys));
                black_box(result)
            })
        },
    );

    // Array storage
    let array_table = load_lapse_rates_table(StorageMode::Array)
        .expect("Failed to load lapse_rates with array storage");
    let is_array = array_table.is_array_storage();

    group.bench_function(
        format!("array_{}k_lookups{}", total_lookups / 1000, if is_array { "" } else { "_fallback_hash" }),
        |b| {
            b.iter(|| {
                let result = array_table.lookup_series(black_box(&keys));
                black_box(result)
            })
        },
    );

    group.finish();
}

/// Benchmark risk_free_rates table - 3 string/int keys, 1800 rows
fn benchmark_realistic_risk_free_rates(c: &mut Criterion) {
    let n_policies = 1000;
    let n_months = 120;
    let total_lookups = n_policies * n_months;

    // Generate realistic key data
    let scenarios: Vec<&str> = (0..total_lookups)
        .map(|i| match (i / n_months) % 10 {
            0 => "BASE",
            1 => "S001",
            2 => "S002",
            3 => "S003",
            4 => "S004",
            5 => "S005",
            6 => "S006",
            7 => "S007",
            8 => "S008",
            _ => "S009",
        })
        .collect();

    let currencies: Vec<&str> = (0..total_lookups).map(|_| "EUR").collect();

    let years: Vec<i64> = (0..n_policies)
        .flat_map(|_| (0..n_months).map(|month| (month / 12) as i64))
        .collect();

    let scenario_series = Series::new("scenario".into(), scenarios);
    let currency_series = Series::new("currency".into(), currencies);
    let year_series = Series::new("year".into(), years);

    let mut group = c.benchmark_group("realistic_risk_free_rates");
    group.sample_size(50);

    // Hash storage
    let hash_table = load_risk_free_rates_table(StorageMode::Hash)
        .expect("Failed to load risk_free_rates with hash storage");
    let keys: Vec<&Series> = vec![&scenario_series, &currency_series, &year_series];

    group.bench_function(
        format!("hash_{}k_lookups", total_lookups / 1000),
        |b| {
            b.iter(|| {
                let result = hash_table.lookup_series(black_box(&keys));
                black_box(result)
            })
        },
    );

    // Array storage
    let array_table = load_risk_free_rates_table(StorageMode::Array)
        .expect("Failed to load risk_free_rates with array storage");
    let is_array = array_table.is_array_storage();

    group.bench_function(
        format!("array_{}k_lookups{}", total_lookups / 1000, if is_array { "" } else { "_fallback_hash" }),
        |b| {
            b.iter(|| {
                let result = array_table.lookup_series(black_box(&keys));
                black_box(result)
            })
        },
    );

    group.finish();
}

/// Combined benchmark simulating a full model run with multiple table lookups
fn benchmark_realistic_model_run(c: &mut Criterion) {
    // Simulate a realistic model run:
    // - 100 policies × 120 months = 12k rows per table lookup
    // - 5 different assumption tables queried per projection step

    let n_policies = 100;
    let n_months = 120;
    let total_lookups = n_policies * n_months;

    // Prepare mortality_select keys
    let mort_table_ids: Vec<&str> = (0..total_lookups).map(|_| "T3363").collect();
    let mort_ages: Vec<i64> = (0..n_policies)
        .flat_map(|policy| {
            let base_age = 30 + (policy % 50) as i64;
            (0..n_months).map(move |month| base_age + (month as i64 / 12))
        })
        .collect();
    let mort_durations: Vec<i64> = (0..n_policies)
        .flat_map(|policy| {
            let base_dur = (policy % 10) as i64;
            (0..n_months).map(move |month| (base_dur + month as i64 / 12).min(30))
        })
        .collect();

    // Prepare lapse_rates keys
    let lapse_durations: Vec<i64> = mort_durations.clone();
    let lapse_ids: Vec<&str> = (0..total_lookups)
        .map(|i| if i % 2 == 0 { "L001" } else { "L002" })
        .collect();

    // Create series
    let mort_table_id_series = Series::new("table_id".into(), mort_table_ids);
    let mort_age_series = Series::new("attained_age".into(), mort_ages);
    let mort_duration_series = Series::new("duration".into(), mort_durations);
    let lapse_duration_series = Series::new("duration".into(), lapse_durations);
    let lapse_id_series = Series::new("lapse_id".into(), lapse_ids);

    // Load tables
    let mort_hash = load_mortality_select_table(StorageMode::Hash).unwrap();
    let mort_array = load_mortality_select_table(StorageMode::Array).unwrap();
    let lapse_hash = load_lapse_rates_table(StorageMode::Hash).unwrap();
    let lapse_array = load_lapse_rates_table(StorageMode::Array).unwrap();

    let mort_keys: Vec<&Series> = vec![&mort_table_id_series, &mort_age_series, &mort_duration_series];
    let lapse_keys: Vec<&Series> = vec![&lapse_duration_series, &lapse_id_series];

    let mut group = c.benchmark_group("realistic_model_run");
    group.sample_size(50);

    // Hash storage - combined mortality + lapse lookups
    group.bench_function("hash_combined_lookups", |b| {
        b.iter(|| {
            let mort_result = mort_hash.lookup_series(black_box(&mort_keys));
            let lapse_result = lapse_hash.lookup_series(black_box(&lapse_keys));
            black_box((mort_result, lapse_result))
        })
    });

    // Array storage - combined mortality + lapse lookups
    group.bench_function("array_combined_lookups", |b| {
        b.iter(|| {
            let mort_result = mort_array.lookup_series(black_box(&mort_keys));
            let lapse_result = lapse_array.lookup_series(black_box(&lapse_keys));
            black_box((mort_result, lapse_result))
        })
    });

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

criterion_group!(
    realistic_benches,
    benchmark_realistic_mortality_select,
    benchmark_realistic_lapse_rates,
    benchmark_realistic_risk_free_rates,
    benchmark_realistic_model_run,
);

criterion_main!(benches, realistic_benches);
