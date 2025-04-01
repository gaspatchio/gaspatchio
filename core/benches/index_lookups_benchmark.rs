use criterion::{black_box, criterion_group, criterion_main, Criterion};
use gaspatchio_core_lib::index::{get_registry, register_table, TransformSpec, TransformType};
use polars::prelude::*;
use std::fs::File;
use std::path::Path;

// Helper function to load the model points DataFrame from Parquet
fn load_model_points() -> PolarsResult<DataFrame> {
    let path =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("benches/fixtures/age-last-smoking.parquet"); // Updated filename and type
    let file = File::open(&path).map_err(|e| {
        PolarsError::ComputeError(
            format!("Failed to open key source parquet {:?}: {}", path, e).into(),
        )
    })?;
    ParquetReader::new(file).finish() // Use ParquetReader
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

// Helper function to load a DataFrame from a fixture CSV
fn load_fixture_csv(filename: &str) -> PolarsResult<DataFrame> {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("benches/fixtures")
        .join(filename);
    let file = File::open(&path).map_err(|e| {
        PolarsError::ComputeError(format!("Failed to open fixture CSV {:?}: {}", path, e).into())
    })?;
    CsvReader::new(file) // Use CsvReader::new(file)
        .finish()
}

// Helper function to set up the registry with test data
fn setup_registry() -> PolarsResult<()> {
    // --- Mortality Table --- (Define wide, register with transform)
    let df_mortality_wide = df!(
        "age-last" => &[31i64, 33, 34],
        "MNS" => &[0.0012, 0.0013, 0.0014],
        "FNS" => &[0.0011, 0.0012, 0.0013],
        "MS" => &[0.0022, 0.0023, 0.0024],
        "FS" => &[0.0020, 0.0021, 0.0022]
    )?;

    let mortality_transform_spec = TransformSpec {
        transform_type: TransformType::WideToLong,
        id_vars: vec!["age-last".to_string()],
        value_vars: vec![
            "MNS".to_string(),
            "FNS".to_string(),
            "MS".to_string(),
            "FS".to_string(),
        ],
        var_name: "gender_smoking".to_string(),
        value_name: "mortality_rate".to_string(),
    };

    register_table(
        "mortality", // Keep original name for benchmark consistency
        df_mortality_wide,
        vec!["age-last".to_string(), "gender_smoking".to_string()], // Keys *after* transform
        "mortality_rate", // Value column *after* transform
        Some(mortality_transform_spec),
    )
    .map_err(|e| {
        PolarsError::ComputeError(format!("Failed to register transformed mortality: {}", e).into())
    })?;

    // --- Lapse Table --- (Load from CSV - remains the same)
    let df_lapse = load_fixture_csv("lapse.csv")?;
    register_table(
        "lapse",
        df_lapse,
        vec!["policy_duration".to_string()], // Corrected key name based on previous benchmark code
        "lapse_rate", // Corrected value name based on previous benchmark code
        None,         // No transform spec needed for lapse
    )
    .map_err(|e| PolarsError::ComputeError(format!("Failed to register lapse: {}", e).into()))?;

    Ok(())
}

// Benchmark function using the standard ~100 row parquet file
fn benchmark_vector_lookups_100(c: &mut Criterion) {
    // Setup: Load data and register tables (outside the benchmark loop)
    if let Err(e) = setup_registry() {
        eprintln!("Failed to set up benchmark registry: {}", e);
        return;
    }
    let df_model_points = match load_model_points() {
        Ok(df) => df,
        Err(e) => {
            eprintln!("Failed to load key source parquet for benchmark: {}", e);
            return;
        }
    };

    // Extract key Columns needed for lookups (Assuming names exist in parquet)
    let age_key_col = match df_model_points.column("age-last") {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to get 'age-last' column from parquet: {}", e);
            return;
        }
    };
    let gender_smoking_key_col = match df_model_points.column("gender_smoking") {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to get 'gender_smoking' column from parquet: {}", e);
            return;
        }
    };
    let duration_key_col = match df_model_points.column("policy_duration") {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to get 'policy_duration' column from parquet: {}", e);
            return;
        }
    };

    // Use the columns directly (assuming List<f64> and String from parquet)
    let mortality_keys: Vec<&Series> = vec![
        age_key_col
            .as_series()
            .expect("Failed to convert age_key_col (&Column) to &Series"),
        gender_smoking_key_col
            .as_series()
            .expect("Failed to convert gender_smoking_key_col (&Column) to &Series"),
    ];
    let lapse_keys: Vec<&Series> = vec![duration_key_col
        .as_series()
        .expect("Failed to convert duration_key_col (&Column) to &Series")];

    // Get a snapshot of the registry
    let registry = get_registry();

    let mut group = c.benchmark_group("vector_lookups_parquet_keys_100"); // New group name

    // Benchmark mortality lookup
    group.bench_function("mortality_lookup_parquet_keys_100", |b| {
        b.iter(|| {
            let result = registry.lookup_vector("mortality", black_box(&mortality_keys));
            if let Err(e) = &result {
                eprintln!("100 Mortality lookup failed during benchmark: {:?}", e);
            }
            black_box(result)
        })
    });

    // Benchmark lapse lookup
    group.bench_function("lapse_lookup_parquet_keys_100", |b| {
        b.iter(|| {
            let result = registry.lookup_vector("lapse", black_box(&lapse_keys));
            if let Err(e) = &result {
                eprintln!("100 Lapse lookup failed during benchmark: {:?}", e);
            }
            black_box(result)
        })
    });

    group.finish();
}

// Benchmark function using the 100k row parquet file
fn benchmark_vector_lookups_100k(c: &mut Criterion) {
    // Setup: Load data and register tables (outside the benchmark loop)
    // Note: We still register the same small assumption tables
    if let Err(e) = setup_registry() {
        eprintln!("Failed to set up benchmark registry for 100k: {}", e);
        return;
    }
    let df_model_points = match load_model_points_100k() {
        // Load 100k file
        Ok(df) => df,
        Err(e) => {
            eprintln!(
                "Failed to load 100k key source parquet for benchmark: {}",
                e
            );
            return;
        }
    };

    // Extract key Columns needed for lookups (Assuming names exist in parquet)
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
    let duration_key_col = match df_model_points.column("policy_duration") {
        Ok(s) => s,
        Err(e) => {
            eprintln!(
                "Failed to get 'policy_duration' column from 100k parquet: {}",
                e
            );
            return;
        }
    };

    // Use the columns directly (assuming List<f64> and String from parquet)
    let mortality_keys: Vec<&Series> = vec![
        age_key_col
            .as_series()
            .expect("Failed to convert 100k age_key_col (&Column) to &Series"),
        gender_smoking_key_col
            .as_series()
            .expect("Failed to convert 100k gender_smoking_key_col (&Column) to &Series"),
    ];
    let lapse_keys: Vec<&Series> = vec![duration_key_col
        .as_series()
        .expect("Failed to convert 100k duration_key_col (&Column) to &Series")];

    // Get a snapshot of the registry
    let registry = get_registry();

    let mut group = c.benchmark_group("vector_lookups_parquet_keys_100k"); // New group name

    // Benchmark mortality lookup
    group.bench_function("mortality_lookup_parquet_keys_100k", |b| {
        b.iter(|| {
            let result = registry.lookup_vector("mortality", black_box(&mortality_keys));
            if let Err(e) = &result {
                eprintln!("100k Mortality lookup failed during benchmark: {:?}", e);
            }
            black_box(result)
        })
    });

    // Benchmark lapse lookup
    group.bench_function("lapse_lookup_parquet_keys_100k", |b| {
        b.iter(|| {
            let result = registry.lookup_vector("lapse", black_box(&lapse_keys));
            if let Err(e) = &result {
                eprintln!("100k Lapse lookup failed during benchmark: {:?}", e);
            }
            black_box(result)
        })
    });

    group.finish();
}

criterion_group!(
    benches,
    benchmark_vector_lookups_100,
    benchmark_vector_lookups_100k
);
criterion_main!(benches);
