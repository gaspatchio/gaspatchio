// ABOUTME: Key encoders for converting column values to array indices.
// ABOUTME: Supports integer ranges, string dictionaries, and Polars categoricals.

use ahash::AHashMap;
use polars::prelude::*;

/// Encodes column values to array indices for multi-dimensional array storage.
#[derive(Debug, Clone)]
pub enum KeyEncoder {
    /// Integer keys with known range (age 0-100, duration 0-24).
    IntRange { offset: i64, size: usize },
    /// String keys mapped to indices via dictionary.
    Dictionary {
        value_to_idx: AHashMap<String, u32>,
        size: usize,
    },
    /// Pre-encoded categorical columns - use physical value directly.
    Categorical { size: usize },
}

impl KeyEncoder {
    /// Build encoder for an integer column with known min/max.
    pub fn int_range(min_val: i64, max_val: i64) -> Self {
        KeyEncoder::IntRange {
            offset: min_val,
            size: (max_val - min_val + 1) as usize,
        }
    }

    /// Build encoder for a string column by extracting unique values.
    pub fn dictionary(unique_values: &[String]) -> Self {
        let value_to_idx: AHashMap<String, u32> = unique_values
            .iter()
            .enumerate()
            .map(|(i, v)| (v.clone(), i as u32))
            .collect();
        KeyEncoder::Dictionary {
            size: unique_values.len(),
            value_to_idx,
        }
    }

    /// Build encoder for categorical column.
    pub fn categorical(n_categories: usize) -> Self {
        KeyEncoder::Categorical { size: n_categories }
    }

    /// Build encoder automatically from a Column.
    pub fn from_column(column: &Column) -> PolarsResult<Self> {
        // Convert Column to Series for processing
        let series = column.as_materialized_series().clone();
        Self::from_series(&series)
    }

    /// Build encoder automatically from a Series.
    pub fn from_series(series: &Series) -> PolarsResult<Self> {
        match series.dtype() {
            DataType::Categorical(_, _) => {
                let n_unique = series.n_unique()?;
                Ok(KeyEncoder::categorical(n_unique))
            }
            DataType::Int64 | DataType::Int32 | DataType::UInt64 | DataType::UInt32 => {
                let min = series.min::<i64>()?.unwrap_or(0);
                let max = series.max::<i64>()?.unwrap_or(0);
                Ok(KeyEncoder::int_range(min, max))
            }
            DataType::Float64 => {
                // Treat as integer if all whole numbers
                let f64_ca = series.f64()?;
                let all_whole = f64_ca.into_iter().all(|opt| {
                    opt.map(|f| f.fract() == 0.0 && f.is_finite())
                        .unwrap_or(true)
                });
                if all_whole {
                    let min = series.min::<i64>()?.unwrap_or(0);
                    let max = series.max::<i64>()?.unwrap_or(0);
                    Ok(KeyEncoder::int_range(min, max))
                } else {
                    Err(
                        polars_err!(ComputeError: "Float64 keys with decimals not supported for array storage"),
                    )
                }
            }
            DataType::String => {
                let unique: Vec<String> = series
                    .unique()?
                    .str()?
                    .into_iter()
                    .filter_map(|opt| opt.map(|s| s.to_string()))
                    .collect();
                Ok(KeyEncoder::dictionary(&unique))
            }
            dt => {
                Err(polars_err!(ComputeError: "Unsupported key type for array storage: {:?}", dt))
            }
        }
    }

    /// Get the size (cardinality) of this encoder.
    pub fn size(&self) -> usize {
        match self {
            KeyEncoder::IntRange { size, .. } => *size,
            KeyEncoder::Dictionary { size, .. } => *size,
            KeyEncoder::Categorical { size } => *size,
        }
    }

    /// Encode a single AnyValue to an index. Returns None for out-of-bounds or unknown values.
    #[inline]
    pub fn encode(&self, av: AnyValue) -> Option<u32> {
        match (self, av) {
            // Integer range encoding
            (KeyEncoder::IntRange { offset, size }, AnyValue::Int64(i)) => {
                let idx = i - offset;
                if idx >= 0 && (idx as usize) < *size {
                    Some(idx as u32)
                } else {
                    None
                }
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::Int32(i)) => {
                let idx = i as i64 - offset;
                if idx >= 0 && (idx as usize) < *size {
                    Some(idx as u32)
                } else {
                    None
                }
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::UInt64(u)) => {
                let idx = u as i64 - offset;
                if idx >= 0 && (idx as usize) < *size {
                    Some(idx as u32)
                } else {
                    None
                }
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::UInt32(u)) => {
                let idx = u as i64 - offset;
                if idx >= 0 && (idx as usize) < *size {
                    Some(idx as u32)
                } else {
                    None
                }
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::Float64(f)) => {
                if f.fract() == 0.0 && f.is_finite() {
                    let idx = f as i64 - offset;
                    if idx >= 0 && (idx as usize) < *size {
                        Some(idx as u32)
                    } else {
                        None
                    }
                } else {
                    None
                }
            }

            // Dictionary encoding
            (KeyEncoder::Dictionary { value_to_idx, .. }, AnyValue::String(s)) => {
                value_to_idx.get(s).copied()
            }
            (KeyEncoder::Dictionary { value_to_idx, .. }, AnyValue::StringOwned(s)) => {
                value_to_idx.get(s.as_str()).copied()
            }

            // Categorical - use physical index directly
            (KeyEncoder::Categorical { size }, AnyValue::Categorical(idx, _, _)) => {
                if (idx as usize) < *size {
                    Some(idx)
                } else {
                    None
                }
            }

            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_int_range_encoder() {
        let encoder = KeyEncoder::int_range(18, 100);
        assert_eq!(encoder.size(), 83);

        // Valid values
        assert_eq!(encoder.encode(AnyValue::Int64(18)), Some(0));
        assert_eq!(encoder.encode(AnyValue::Int64(50)), Some(32));
        assert_eq!(encoder.encode(AnyValue::Int64(100)), Some(82));

        // Out of bounds
        assert_eq!(encoder.encode(AnyValue::Int64(17)), None);
        assert_eq!(encoder.encode(AnyValue::Int64(101)), None);

        // Float that's a whole number
        assert_eq!(encoder.encode(AnyValue::Float64(50.0)), Some(32));
    }

    #[test]
    fn test_dictionary_encoder() {
        let values = vec!["M".to_string(), "F".to_string()];
        let encoder = KeyEncoder::dictionary(&values);
        assert_eq!(encoder.size(), 2);

        assert_eq!(encoder.encode(AnyValue::String("M")), Some(0));
        assert_eq!(encoder.encode(AnyValue::String("F")), Some(1));
        assert_eq!(encoder.encode(AnyValue::String("X")), None);
    }

    #[test]
    fn test_from_series_integer() -> PolarsResult<()> {
        let series = Series::new("age".into(), &[18i64, 25, 30, 100]);
        let encoder = KeyEncoder::from_series(&series)?;

        match encoder {
            KeyEncoder::IntRange { offset, size } => {
                assert_eq!(offset, 18);
                assert_eq!(size, 83); // 100 - 18 + 1
            }
            _ => panic!("Expected IntRange encoder"),
        }
        Ok(())
    }

    #[test]
    fn test_from_series_string() -> PolarsResult<()> {
        let series = Series::new("gender".into(), &["M", "F", "M", "F"]);
        let encoder = KeyEncoder::from_series(&series)?;

        match encoder {
            KeyEncoder::Dictionary { size, .. } => {
                assert_eq!(size, 2);
            }
            _ => panic!("Expected Dictionary encoder"),
        }
        Ok(())
    }
}
