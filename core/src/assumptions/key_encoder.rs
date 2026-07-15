// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

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
    /// Categorical storage with string fallback - handles both categorical and string input.
    /// Used when table stores categorical but users may pass strings at lookup time.
    CategoricalWithStringFallback {
        string_to_idx: AHashMap<String, u32>,
        size: usize,
    },
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

    /// Build encoder for categorical column with string fallback.
    /// This enables transparent string-to-categorical conversion at lookup time.
    pub fn categorical_with_string_fallback(string_to_idx: AHashMap<String, u32>) -> Self {
        let size = string_to_idx.len();
        KeyEncoder::CategoricalWithStringFallback {
            string_to_idx,
            size,
        }
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
            DataType::Int64
            | DataType::Int32
            | DataType::Int16
            | DataType::Int8
            | DataType::UInt64
            | DataType::UInt32
            | DataType::UInt16
            | DataType::UInt8 => {
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
                let mut unique: Vec<String> = series
                    .unique()?
                    .str()?
                    .into_iter()
                    .filter_map(|opt| opt.map(|s| s.to_string()))
                    .collect();
                // Sort alphabetically for deterministic index mapping.
                // This ensures consistency with Polars Enum ordering in Python bindings.
                unique.sort();
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
            KeyEncoder::CategoricalWithStringFallback { size, .. } => *size,
        }
    }

    /// Encode an entire Series to indices. Returns u32::MAX for invalid/missing values.
    /// Sequential processing — Polars engine handles parallelism across expressions.
    pub fn encode_column(&self, series: &Series) -> PolarsResult<Vec<u32>> {
        let len = series.len();
        let invalid = u32::MAX;

        match self {
            KeyEncoder::IntRange { offset, size } => {
                let offset = *offset;
                let size = *size;

                match series.dtype() {
                    DataType::Int64 => {
                        let ca = series.i64()?;
                        let ca = ca.rechunk();
                        if let Some(values) = ca.cont_slice().ok() {
                            let out: Vec<u32> = values
                                .iter()
                                .map(|&v| {
                                    let idx = v - offset;
                                    if idx >= 0 && (idx as usize) < size {
                                        idx as u32
                                    } else {
                                        invalid
                                    }
                                })
                                .collect();
                            return Ok(out);
                        }
                        let mut out = vec![invalid; len];
                        for (i, opt) in ca.into_iter().enumerate() {
                            if let Some(v) = opt {
                                let idx = v - offset;
                                if idx >= 0 && (idx as usize) < size {
                                    out[i] = idx as u32;
                                }
                            }
                        }
                        Ok(out)
                    }
                    DataType::Float64 => {
                        let ca = series.f64()?;
                        let ca = ca.rechunk();
                        if let Some(values) = ca.cont_slice().ok() {
                            let out: Vec<u32> = values
                                .iter()
                                .map(|&f| {
                                    if f.fract() == 0.0 && f.is_finite() {
                                        let idx = f as i64 - offset;
                                        if idx >= 0 && (idx as usize) < size {
                                            return idx as u32;
                                        }
                                    }
                                    invalid
                                })
                                .collect();
                            return Ok(out);
                        }
                        let mut out = vec![invalid; len];
                        for (i, opt) in ca.into_iter().enumerate() {
                            if let Some(f) = opt {
                                if f.fract() == 0.0 && f.is_finite() {
                                    let idx = f as i64 - offset;
                                    if idx >= 0 && (idx as usize) < size {
                                        out[i] = idx as u32;
                                    }
                                }
                            }
                        }
                        Ok(out)
                    }
                    _ => {
                        let mut out = vec![invalid; len];
                        for i in 0..len {
                            if let Ok(av) = series.get(i) {
                                if let Some(idx) = self.encode(av) {
                                    out[i] = idx;
                                }
                            }
                        }
                        Ok(out)
                    }
                }
            }

            KeyEncoder::Dictionary { value_to_idx, .. } => {
                let mut out = vec![invalid; len];
                if let Ok(ca) = series.str() {
                    for (i, opt) in ca.into_iter().enumerate() {
                        if let Some(s) = opt {
                            if let Some(&idx) = value_to_idx.get(s) {
                                out[i] = idx;
                            }
                        }
                    }
                } else {
                    for i in 0..len {
                        if let Ok(av) = series.get(i) {
                            if let Some(idx) = self.encode(av) {
                                out[i] = idx;
                            }
                        }
                    }
                }
                Ok(out)
            }

            KeyEncoder::Categorical { size } => {
                let size = *size;
                let mut out = vec![invalid; len];

                if let Ok(ca) = series.cat32() {
                    let physical = ca.physical();
                    let physical = physical.rechunk();
                    if let Some(values) = physical.cont_slice().ok() {
                        let result: Vec<u32> = values
                            .iter()
                            .map(|&idx| if (idx as usize) < size { idx } else { invalid })
                            .collect();
                        return Ok(result);
                    }
                    for (i, opt) in physical.into_iter().enumerate() {
                        if let Some(idx) = opt {
                            if (idx as usize) < size {
                                out[i] = idx;
                            }
                        }
                    }
                } else if matches!(series.dtype(), DataType::UInt32) {
                    let u32_ca = series.u32()?;
                    let u32_ca = u32_ca.rechunk();
                    if let Some(values) = u32_ca.cont_slice().ok() {
                        let result: Vec<u32> = values
                            .iter()
                            .map(|&idx| if (idx as usize) < size { idx } else { invalid })
                            .collect();
                        return Ok(result);
                    }
                    for (i, opt) in u32_ca.into_iter().enumerate() {
                        if let Some(idx) = opt {
                            if (idx as usize) < size {
                                out[i] = idx;
                            }
                        }
                    }
                } else {
                    for i in 0..len {
                        if let Ok(av) = series.get(i) {
                            if let Some(idx) = self.encode(av) {
                                out[i] = idx;
                            }
                        }
                    }
                }
                Ok(out)
            }

            KeyEncoder::CategoricalWithStringFallback { string_to_idx, .. } => {
                let mut out = vec![invalid; len];

                if let Ok(ca) = series.cat32() {
                    // Resolve each categorical value to its string, then look up
                    // in our contiguous mapping. Cannot use physical indices directly
                    // because Categories::global() assigns non-contiguous indices.
                    let cat_mapping = ca.get_mapping();
                    for (i, opt_idx) in ca.physical().into_iter().enumerate() {
                        if let Some(phys_idx) = opt_idx {
                            if let Some(s) = cat_mapping.cat_to_str(phys_idx) {
                                if let Some(&contiguous_idx) = string_to_idx.get(s) {
                                    out[i] = contiguous_idx;
                                }
                            }
                        }
                    }
                    return Ok(out);
                }

                if let Ok(ca) = series.str() {
                    for (i, opt) in ca.into_iter().enumerate() {
                        if let Some(s) = opt {
                            if let Some(&idx) = string_to_idx.get(s) {
                                out[i] = idx;
                            }
                        }
                    }
                    return Ok(out);
                }

                for i in 0..len {
                    if let Ok(av) = series.get(i) {
                        if let Some(idx) = self.encode(av) {
                            out[i] = idx;
                        }
                    }
                }
                Ok(out)
            }
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
            // Narrow integers widen like Int32/UInt32 instead of missing
            (KeyEncoder::IntRange { offset, size }, AnyValue::Int16(i)) => {
                let idx = i as i64 - offset;
                if idx >= 0 && (idx as usize) < *size {
                    Some(idx as u32)
                } else {
                    None
                }
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::Int8(i)) => {
                let idx = i as i64 - offset;
                if idx >= 0 && (idx as usize) < *size {
                    Some(idx as u32)
                } else {
                    None
                }
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::UInt16(u)) => {
                let idx = u as i64 - offset;
                if idx >= 0 && (idx as usize) < *size {
                    Some(idx as u32)
                } else {
                    None
                }
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::UInt8(u)) => {
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
            (KeyEncoder::Categorical { size }, AnyValue::Categorical(idx, _)) => {
                if (idx as usize) < *size {
                    Some(idx)
                } else {
                    None
                }
            }

            // Handle U32 values as pre-computed categorical physical indices
            (KeyEncoder::Categorical { size }, AnyValue::UInt32(idx)) => {
                if (idx as usize) < *size {
                    Some(idx)
                } else {
                    None
                }
            }

            // CategoricalWithStringFallback - handles both categorical and string input.
            // For categorical values, resolve to string first then look up in our
            // contiguous index mapping. We cannot use the physical categorical index
            // directly because Categories::global() assigns non-contiguous indices.
            (
                KeyEncoder::CategoricalWithStringFallback { string_to_idx, .. },
                AnyValue::Categorical(idx, mapping),
            ) => {
                // Resolve categorical physical index to string, then look up
                if let Some(s) = mapping.cat_to_str(idx) {
                    string_to_idx.get(s).copied()
                } else {
                    None
                }
            }
            (
                KeyEncoder::CategoricalWithStringFallback { string_to_idx, .. },
                AnyValue::String(s),
            ) => string_to_idx.get(s).copied(),
            (
                KeyEncoder::CategoricalWithStringFallback { string_to_idx, .. },
                AnyValue::StringOwned(s),
            ) => string_to_idx.get(s.as_str()).copied(),

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

    #[test]
    fn test_from_series_string_sorted_order() -> PolarsResult<()> {
        // Input order: TERM, WL, UL (not alphabetical)
        // Expected sorted order: TERM=0, UL=1, WL=2
        let series = Series::new("product".into(), &["TERM", "WL", "UL", "TERM", "UL"]);
        let encoder = KeyEncoder::from_series(&series)?;

        match encoder {
            KeyEncoder::Dictionary { value_to_idx, size } => {
                assert_eq!(size, 3);
                // Verify alphabetically sorted mapping
                assert_eq!(value_to_idx.get("TERM"), Some(&0), "TERM should map to 0");
                assert_eq!(value_to_idx.get("UL"), Some(&1), "UL should map to 1");
                assert_eq!(value_to_idx.get("WL"), Some(&2), "WL should map to 2");
            }
            _ => panic!("Expected Dictionary encoder"),
        }
        Ok(())
    }
}
