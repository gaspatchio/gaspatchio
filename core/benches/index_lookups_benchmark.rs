use criterion::{black_box, criterion_group, criterion_main, Criterion};
use gaspatchio_core_lib::index::{
    get_registry, perform_lookup, register_table, reset_global_registry, TransformSpec,
    TransformType,
};
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

// Helper function to load the 1k model points DataFrame from Parquet
fn load_model_points_1k() -> PolarsResult<DataFrame> {
    let path =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("benches/fixtures/age-last-smoking-1k.parquet"); // Assume this file exists
    let file = File::open(&path).map_err(|e| {
        PolarsError::ComputeError(
            format!("Failed to open 1k key source parquet {:?}: {}", path, e).into(),
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
    // Create a realistic mortality table with 100+ ages and multiple factors
    let ages: Vec<i64> = (18..=100).collect(); // 83 ages
    let df_mortality_wide = df!(
        "age-last" => ages.clone(),
        "MNS" => ages.iter().map(|&age| 0.001 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "FNS" => ages.iter().map(|&age| 0.0008 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "MS" => ages.iter().map(|&age| 0.0015 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
        "FS" => ages.iter().map(|&age| 0.0012 * (1.0 + age as f64/100.0)).collect::<Vec<f64>>(),
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
        vec!["policy duration".to_string()], // Corrected key name based on previous benchmark code
        "lapse rate", // Corrected value name based on previous benchmark code
        None,         // No transform spec needed for lapse
    )
    .map_err(|e| PolarsError::ComputeError(format!("Failed to register lapse: {}", e).into()))?;

    Ok(())
}

// Benchmark function using the standard ~100 row parquet file
fn benchmark_vector_lookups_100(c: &mut Criterion) {
    reset_global_registry(); // Reset registry before setup
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

    // Use the columns directly (assuming List<f64> and String from parquet)
    let mortality_keys: Vec<&Series> = vec![
        age_key_col
            .as_series()
            .expect("Failed to convert age_key_col (&Column) to &Series"),
        gender_smoking_key_col
            .as_series()
            .expect("Failed to convert gender_smoking_key_col (&Column) to &Series"),
    ];

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

    group.finish();
}

// Benchmark function using the 1k row parquet file
fn benchmark_vector_lookups_1k(c: &mut Criterion) {
    reset_global_registry(); // Reset registry before setup
                             // Setup: Load data and register tables (outside the benchmark loop)
                             // Note: We still register the same small assumption tables
    if let Err(e) = setup_registry() {
        eprintln!("Failed to set up benchmark registry for 1k: {}", e);
        return;
    }
    let df_model_points = match load_model_points_1k() {
        // Load 1k file
        Ok(df) => df,
        Err(e) => {
            eprintln!("Failed to load 1k key source parquet for benchmark: {}", e);
            return;
        }
    };

    // Extract key Columns needed for lookups (Assuming names exist in parquet)
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

    // Use the columns directly (assuming correct types from parquet)
    let mortality_keys: Vec<&Series> = vec![
        age_key_col
            .as_series()
            .expect("Failed to convert 1k age_key_col (&Column) to &Series"),
        gender_smoking_key_col
            .as_series()
            .expect("Failed to convert 1k gender_smoking_key_col (&Column) to &Series"),
    ];

    // Get a snapshot of the registry
    let registry = get_registry();

    let mut group = c.benchmark_group("vector_lookups_parquet_keys_1k"); // New group name

    // Benchmark mortality lookup
    group.bench_function("mortality_lookup_parquet_keys_1k", |b| {
        b.iter(|| {
            let result = registry.lookup_vector("mortality", black_box(&mortality_keys));
            if let Err(e) = &result {
                eprintln!("1k Mortality lookup failed during benchmark: {:?}", e);
            }
            black_box(result)
        })
    });

    group.finish();
}

// Benchmark function using the 100k row parquet file
fn benchmark_vector_lookups_100k(c: &mut Criterion) {
    reset_global_registry(); // Reset registry before setup
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

    // Use the columns directly (assuming List<f64> and String from parquet)
    let mortality_keys: Vec<&Series> = vec![
        age_key_col
            .as_series()
            .expect("Failed to convert 100k age_key_col (&Column) to &Series"),
        gender_smoking_key_col
            .as_series()
            .expect("Failed to convert 100k gender_smoking_key_col (&Column) to &Series"),
    ];

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

    group.finish();
}

// Benchmark function using perform_lookup with the standard ~100 row parquet file
fn benchmark_perform_lookup_100(c: &mut Criterion) {
    reset_global_registry(); // Reset registry before setup
                             // Setup: Load data and register tables (outside the benchmark loop)
    if let Err(e) = setup_registry() {
        eprintln!(
            "Failed to set up benchmark registry for perform_lookup 100: {}",
            e
        );
        return;
    }
    let df_model_points = match load_model_points() {
        Ok(df) => df,
        Err(e) => {
            eprintln!(
                "Failed to load key source parquet for perform_lookup benchmark: {}",
                e
            );
            return;
        }
    };

    // Extract key Columns needed for lookups (Assuming names exist in parquet)
    let age_key_col = match df_model_points.column("age-last") {
        Ok(s) => s,
        Err(e) => {
            eprintln!(
                "Failed to get 'age-last' column from parquet (perform_lookup): {}",
                e
            );
            return;
        }
    };
    let gender_smoking_key_col = match df_model_points.column("gender_smoking") {
        Ok(s) => s,
        Err(e) => {
            eprintln!(
                "Failed to get 'gender_smoking' column from parquet (perform_lookup): {}",
                e
            );
            return;
        }
    };

    // Use the columns directly (assuming correct types from parquet)
    let mortality_keys: Vec<&Series> = vec![
        age_key_col
            .as_series()
            .expect("Failed to convert age_key_col (&Column) to &Series (perform_lookup)"),
        gender_smoking_key_col.as_series().expect(
            "Failed to convert gender_smoking_key_col (&Column) to &Series (perform_lookup)",
        ),
    ];

    // Note: perform_lookup accesses the global registry internally via get_registry()

    let mut group = c.benchmark_group("perform_lookup_100");

    // Benchmark mortality lookup using perform_lookup
    group.bench_function("mortality_perform_lookup_100", |b| {
        b.iter(|| {
            // Call the core perform_lookup function
            let result = perform_lookup("mortality", black_box(&mortality_keys));
            if let Err(e) = &result {
                eprintln!("Mortality perform_lookup failed during benchmark: {:?}", e);
            }
            black_box(result)
        })
    });

    group.finish();
}

// Benchmark function for scalar lookups using index registry with 1k model points
fn benchmark_scalar_lookups_1k(c: &mut Criterion) {
    reset_global_registry(); // Reset registry before setup
    if let Err(e) = setup_registry() {
        eprintln!("Failed to set up benchmark registry for scalar 1k: {}", e);
        return;
    }
    let df_model_points = match load_model_points_1k() {
        Ok(df) => df,
        Err(e) => {
            eprintln!(
                "Failed to load 1k key source parquet for scalar benchmark: {}",
                e
            );
            return;
        }
    };

    // For scalar lookup, we need to extract scalar values from the vector data
    // Let's take the first element from each age-last vector and use gender_smoking as-is
    let age_list_col = match df_model_points.column("age-last") {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to get 'age-last' column from 1k parquet: {}", e);
            return;
        }
    };
    let gender_smoking_col = match df_model_points.column("gender_smoking") {
        Ok(s) => s,
        Err(e) => {
            eprintln!(
                "Failed to get 'gender_smoking' column from 1k parquet: {}",
                e
            );
            return;
        }
    };

    // Extract first age from each list to create scalar age series
    let age_list_ca = match age_list_col.list() {
        Ok(ca) => ca,
        Err(e) => {
            eprintln!("Failed to convert age-last to list chunked array: {}", e);
            return;
        }
    };

    let scalar_ages: Vec<Option<f64>> = (0..age_list_ca.len())
        .map(|i| match age_list_ca.get_any_value(i) {
            Ok(AnyValue::List(inner_series)) => {
                if inner_series.len() > 0 {
                    match inner_series.get(0) {
                        Ok(AnyValue::Float64(f)) => Some(f),
                        _ => None,
                    }
                } else {
                    None
                }
            }
            _ => None,
        })
        .collect();

    let age_scalar_series = Series::new("age-last".into(), scalar_ages);

    let mortality_scalar_keys: Vec<&Series> = vec![
        &age_scalar_series,
        gender_smoking_col
            .as_series()
            .expect("Failed to convert gender_smoking_col to Series"),
    ];

    // Get a snapshot of the registry
    let registry = get_registry();

    let mut group = c.benchmark_group("scalar_lookups_1k");

    // Benchmark scalar mortality lookup using index registry
    group.bench_function("mortality_scalar_lookup_1k", |b| {
        b.iter(|| {
            let result = registry.lookup_vector("mortality", black_box(&mortality_scalar_keys));
            if let Err(e) = &result {
                eprintln!(
                    "1k Scalar mortality lookup failed during benchmark: {:?}",
                    e
                );
            }
            black_box(result)
        })
    });

    group.finish();
}

// Benchmark function for scalar lookups using index registry with 100k model points
fn benchmark_scalar_lookups_100k(c: &mut Criterion) {
    reset_global_registry(); // Reset registry before setup
    if let Err(e) = setup_registry() {
        eprintln!("Failed to set up benchmark registry for scalar 100k: {}", e);
        return;
    }
    let df_model_points = match load_model_points_100k() {
        Ok(df) => df,
        Err(e) => {
            eprintln!(
                "Failed to load 100k key source parquet for scalar benchmark: {}",
                e
            );
            return;
        }
    };

    // For scalar lookup, we need to extract scalar values from the vector data
    // Let's take the first element from each age-last vector and use gender_smoking as-is
    let age_list_col = match df_model_points.column("age-last") {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to get 'age-last' column from 100k parquet: {}", e);
            return;
        }
    };
    let gender_smoking_col = match df_model_points.column("gender_smoking") {
        Ok(s) => s,
        Err(e) => {
            eprintln!(
                "Failed to get 'gender_smoking' column from 100k parquet: {}",
                e
            );
            return;
        }
    };

    // Extract first age from each list to create scalar age series
    let age_list_ca = match age_list_col.list() {
        Ok(ca) => ca,
        Err(e) => {
            eprintln!("Failed to convert age-last to list chunked array: {}", e);
            return;
        }
    };

    let scalar_ages: Vec<Option<f64>> = (0..age_list_ca.len())
        .map(|i| match age_list_ca.get_any_value(i) {
            Ok(AnyValue::List(inner_series)) => {
                if inner_series.len() > 0 {
                    match inner_series.get(0) {
                        Ok(AnyValue::Float64(f)) => Some(f),
                        _ => None,
                    }
                } else {
                    None
                }
            }
            _ => None,
        })
        .collect();

    let age_scalar_series = Series::new("age-last".into(), scalar_ages);

    let mortality_scalar_keys: Vec<&Series> = vec![
        &age_scalar_series,
        gender_smoking_col
            .as_series()
            .expect("Failed to convert gender_smoking_col to Series"),
    ];

    // Get a snapshot of the registry
    let registry = get_registry();

    let mut group = c.benchmark_group("scalar_lookups_100k");

    // Benchmark scalar mortality lookup using index registry
    group.bench_function("mortality_scalar_lookup_100k", |b| {
        b.iter(|| {
            let result = registry.lookup_vector("mortality", black_box(&mortality_scalar_keys));
            if let Err(e) = &result {
                eprintln!(
                    "100k Scalar mortality lookup failed during benchmark: {:?}",
                    e
                );
            }
            black_box(result)
        })
    });

    group.finish();
}

criterion_group!(
    benches,
    //benchmark_vector_lookups_100,
    benchmark_vector_lookups_1k,
    //benchmark_vector_lookups_100k,
    benchmark_scalar_lookups_1k,
    //benchmark_scalar_lookups_100k,
    //benchmark_perform_lookup_100
);
criterion_main!(benches);
