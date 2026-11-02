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
        let width = i128::from(max_val) - i128::from(min_val) + 1;
        KeyEncoder::IntRange {
            offset: min_val,
            // A range this wide can never pass ArrayStorage's density and
            // memory checks. Saturating here lets that storage decline it
            // without a debug-only overflow or a wrapped release value.
            size: usize::try_from(width).unwrap_or(usize::MAX),
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
            DataType::Int64 | DataType::Int32 | DataType::Int16 | DataType::Int8 => {
                let as_i64 = series.cast(&DataType::Int64)?;
                let min = as_i64.i64()?.min().unwrap_or(0);
                let max = as_i64.i64()?.max().unwrap_or(0);
                Ok(KeyEncoder::int_range(min, max))
            }
            DataType::UInt64 | DataType::UInt32 | DataType::UInt16 | DataType::UInt8 => {
                let as_u64 = series.cast(&DataType::UInt64)?;
                let min = as_u64.u64()?.min().unwrap_or(0);
                let max = as_u64.u64()?.max().unwrap_or(0);
                let min = i64::try_from(min).map_err(|_| {
                    polars_err!(ComputeError: "unsigned key is outside array storage's supported Int64 range")
                })?;
                let max = i64::try_from(max).map_err(|_| {
                    polars_err!(ComputeError: "unsigned key is outside array storage's supported Int64 range")
                })?;
                Ok(KeyEncoder::int_range(min, max))
            }
            DataType::Float64 => {
                // Treat as integer if all whole numbers
                let f64_ca = series.f64()?;
                let all_whole = f64_ca
                    .into_iter()
                    .all(|opt| opt.is_none_or(|value| Self::exact_i64_from_f64(value).is_some()));
                if all_whole {
                    let as_i64 = series.cast(&DataType::Int64)?;
                    let min = as_i64.i64()?.min().unwrap_or(0);
                    let max = as_i64.i64()?.max().unwrap_or(0);
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
                        if let Ok(values) = ca.cont_slice() {
                            if size == 0 {
                                return Ok(vec![invalid; values.len()]);
                            }
                            // Hoist every fallible bound calculation out of the
                            // contiguous loop. Clip the interval at i64::MAX so
                            // an unsigned modular distance cannot wrap a key
                            // below offset into the accepted interval.
                            let max_index = size.saturating_sub(1).min((u32::MAX - 1) as usize);
                            let upper = offset.saturating_add(max_index as i64);
                            let count = upper.wrapping_sub(offset) as u64 + 1;
                            let out: Vec<u32> = values
                                .iter()
                                .map(|&v| {
                                    let index = v.wrapping_sub(offset) as u64;
                                    if index < count {
                                        index as u32
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
                                if let Some(idx) = Self::range_index_i64(v, offset, size) {
                                    out[i] = idx;
                                }
                            }
                        }
                        Ok(out)
                    }
                    DataType::Float64 => {
                        let ca = series.f64()?;
                        let ca = ca.rechunk();
                        if let Ok(values) = ca.cont_slice() {
                            let out: Vec<u32> = values
                                .iter()
                                .map(|&f| Self::range_index_f64(f, offset, size).unwrap_or(invalid))
                                .collect();
                            return Ok(out);
                        }
                        let mut out = vec![invalid; len];
                        for (i, opt) in ca.into_iter().enumerate() {
                            if let Some(f) = opt {
                                if let Some(idx) = Self::range_index_f64(f, offset, size) {
                                    out[i] = idx;
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
                    if let Ok(values) = physical.cont_slice() {
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
                    if let Ok(values) = u32_ca.cont_slice() {
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

                // An Enum narrower than 32 bits is the same column shape read
                // through a smaller physical: Polars picks the smallest width
                // that holds the declared categories, so a three-name scenario
                // Enum arrives 8-bit and never reaches `cat32` above. It is
                // resolved the same way — through the string the category
                // holds, never through the physical index, which for an Enum
                // is its position in the user's declared order and says
                // nothing about this table's contiguous mapping.
                if let Some(ca) = series.try_cat8() {
                    let cat_mapping = ca.get_mapping();
                    for (i, opt_idx) in ca.physical().into_iter().enumerate() {
                        if let Some(phys_idx) = opt_idx {
                            if let Some(s) = cat_mapping.cat_to_str(u32::from(phys_idx)) {
                                if let Some(&contiguous_idx) = string_to_idx.get(s) {
                                    out[i] = contiguous_idx;
                                }
                            }
                        }
                    }
                    return Ok(out);
                }

                if let Some(ca) = series.try_cat16() {
                    let cat_mapping = ca.get_mapping();
                    for (i, opt_idx) in ca.physical().into_iter().enumerate() {
                        if let Some(phys_idx) = opt_idx {
                            if let Some(s) = cat_mapping.cat_to_str(u32::from(phys_idx)) {
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
                Self::range_index_i64(i, *offset, *size)
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::Int32(i)) => {
                Self::range_index_i64(i64::from(i), *offset, *size)
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::UInt64(u)) => {
                Self::range_index_u64(u, *offset, *size)
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::UInt32(u)) => {
                Self::range_index_u64(u64::from(u), *offset, *size)
            }
            // Narrow integers widen like Int32/UInt32 instead of missing
            (KeyEncoder::IntRange { offset, size }, AnyValue::Int16(i)) => {
                Self::range_index_i64(i64::from(i), *offset, *size)
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::Int8(i)) => {
                Self::range_index_i64(i64::from(i), *offset, *size)
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::UInt16(u)) => {
                Self::range_index_u64(u64::from(u), *offset, *size)
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::UInt8(u)) => {
                Self::range_index_u64(u64::from(u), *offset, *size)
            }
            (KeyEncoder::IntRange { offset, size }, AnyValue::Float64(f)) => {
                Self::range_index_f64(f, *offset, *size)
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

            // The owned form is the same value read out of a one-row column:
            // Polars holds a one-row column as a scalar, and a scalar hands
            // its value back owned.
            (KeyEncoder::Categorical { size }, AnyValue::CategoricalOwned(idx, _)) => {
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
            // The owned form of the same value. Polars holds a one-row column as
            // a scalar and hands its value back owned, so a one-row table's
            // only key arrives this way while it is built; without this arm
            // such a table was refused as holding an unencodable key.
            (
                KeyEncoder::CategoricalWithStringFallback { string_to_idx, .. },
                AnyValue::CategoricalOwned(idx, mapping),
            ) => mapping
                .cat_to_str(idx)
                .and_then(|s| string_to_idx.get(s).copied()),
            // An Enum is a Categorical with a fixed category list, and for a key
            // lookup the two are the same thing: the key is the string the
            // category holds. Resolve it exactly as above. The physical index is
            // deliberately not used — an Enum numbers its categories in the order
            // the user declared them, which is unrelated to this encoder's
            // contiguous mapping, so `pl.Enum(["UP", "BASE", "DOWN"])` must place
            // "UP" by its name and not by its position.
            (
                KeyEncoder::CategoricalWithStringFallback { string_to_idx, .. },
                AnyValue::Enum(idx, mapping),
            ) => mapping
                .cat_to_str(idx)
                .and_then(|s| string_to_idx.get(s).copied()),
            (
                KeyEncoder::CategoricalWithStringFallback { string_to_idx, .. },
                AnyValue::EnumOwned(idx, mapping),
            ) => mapping
                .cat_to_str(idx)
                .and_then(|s| string_to_idx.get(s).copied()),
            (
                KeyEncoder::CategoricalWithStringFallback { string_to_idx, .. },
                AnyValue::String(s),
            ) => string_to_idx.get(s).copied(),
            (
                KeyEncoder::CategoricalWithStringFallback { string_to_idx, .. },
                AnyValue::StringOwned(s),
            ) => string_to_idx.get(s.as_str()).copied(),

            // Everything else is a miss rather than a guess. The `Categorical`
            // encoder in particular holds no strings — it places a key by its
            // physical index alone — so it cannot honestly place a label from
            // any other dictionary, and reporting a miss is the only truthful
            // answer available to it.
            _ => None,
        }
    }

    #[inline]
    fn exact_i64_from_f64(value: f64) -> Option<i64> {
        const I64_MIN_AS_F64: f64 = -9_223_372_036_854_775_808.0;
        const I64_END_AS_F64: f64 = 9_223_372_036_854_775_808.0;
        (value.is_finite()
            && value.fract() == 0.0
            && (I64_MIN_AS_F64..I64_END_AS_F64).contains(&value))
        .then_some(value as i64)
    }

    #[inline]
    fn range_index_i64(value: i64, offset: i64, size: usize) -> Option<u32> {
        // A subtraction overflow implies a mathematical distance larger than
        // i64::MAX or a negative distance smaller than i64::MIN. Neither can
        // be a valid array index, which is bounded below u32::MAX.
        let index = value.checked_sub(offset)?;
        let index = u32::try_from(index).ok()?;
        if index == u32::MAX || usize::try_from(index).ok()? >= size {
            return None;
        }
        Some(index)
    }

    #[inline]
    fn range_index_u64(value: u64, offset: i64, size: usize) -> Option<u32> {
        // ArrayStorage only builds IntRange encoders for source domains that
        // fit Int64. A wider query therefore cannot match this array.
        Self::range_index_i64(i64::try_from(value).ok()?, offset, size)
    }

    #[inline]
    fn range_index_f64(value: f64, offset: i64, size: usize) -> Option<u32> {
        let value = Self::exact_i64_from_f64(value)?;
        Self::range_index_i64(value, offset, size)
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
    fn test_int_range_encoder_checks_numeric_boundaries_without_saturation() {
        let maximum = KeyEncoder::int_range(i64::MAX, i64::MAX);
        assert_eq!(maximum.encode(AnyValue::Int64(i64::MAX)), Some(0));
        assert_eq!(
            maximum.encode(AnyValue::Float64(9_223_372_036_854_775_808.0)),
            None
        );
        assert_eq!(
            maximum.encode(AnyValue::UInt64(9_223_372_036_854_775_808)),
            None
        );

        let minimum = KeyEncoder::int_range(i64::MIN, i64::MIN);
        assert_eq!(minimum.encode(AnyValue::Int64(i64::MIN)), Some(0));
        assert_eq!(
            minimum.encode(AnyValue::Float64(-9_223_372_036_854_775_808.0)),
            Some(0)
        );
        assert_eq!(minimum.encode(AnyValue::Float64(f64::NAN)), None);
        assert_eq!(minimum.encode(AnyValue::Float64(f64::INFINITY)), None);
    }

    #[test]
    fn test_full_int64_span_does_not_overflow_range_construction() {
        let encoder = KeyEncoder::int_range(i64::MIN, i64::MAX);
        assert_eq!(encoder.size(), usize::MAX);
        assert_eq!(encoder.encode(AnyValue::Int64(i64::MIN)), Some(0));
        assert_eq!(encoder.encode(AnyValue::Int64(i64::MAX)), None);
    }

    #[test]
    fn test_contiguous_int64_encoding_preserves_checked_boundaries() -> PolarsResult<()> {
        let maximum = KeyEncoder::int_range(i64::MAX - 1, i64::MAX);
        let values = Series::new(
            "key".into(),
            [i64::MIN, i64::MAX - 2, i64::MAX - 1, i64::MAX],
        );
        assert_eq!(
            maximum.encode_column(&values)?,
            vec![u32::MAX, u32::MAX, 0, 1]
        );

        let full = KeyEncoder::int_range(i64::MIN, i64::MAX);
        let values = Series::new("key".into(), [i64::MIN, i64::MIN + 1, i64::MAX]);
        assert_eq!(full.encode_column(&values)?, vec![0, 1, u32::MAX]);
        Ok(())
    }

    #[test]
    fn test_contiguous_ranges_agree_with_wide_integer_oracle() -> PolarsResult<()> {
        for offset in [i64::MIN, -2, 0, i64::MAX - 2, i64::MAX] {
            for size in [0, 1, 3, u32::MAX as usize, usize::MAX] {
                let keys = [
                    i64::MIN,
                    i64::MAX,
                    -1,
                    0,
                    1,
                    offset,
                    offset.saturating_sub(1),
                    offset.saturating_add(1),
                    offset.saturating_add(i64::from(u32::MAX)),
                ];
                let expected: Vec<u32> = keys
                    .iter()
                    .map(|&key| {
                        let distance = i128::from(key) - i128::from(offset);
                        if distance >= 0
                            && distance < size as i128
                            && distance < i128::from(u32::MAX)
                        {
                            distance as u32
                        } else {
                            u32::MAX
                        }
                    })
                    .collect();
                let encoder = KeyEncoder::IntRange { offset, size };
                assert_eq!(
                    encoder.encode_column(&Series::new("key".into(), keys))?,
                    expected,
                    "offset={offset}, size={size}"
                );
            }
        }
        Ok(())
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

    /// The table numbers its labels alphabetically; an `Enum` numbers them in
    /// the order the model point declared. Where those two orders disagree, an
    /// encoder that read the physical index would hand every label another
    /// label's rate — so the encoder must follow the string the category holds.
    #[test]
    fn test_enum_key_is_placed_by_its_name_not_its_declared_position() -> PolarsResult<()> {
        // What the table holds, built from sorted strings: BASE=0, DOWN=1, UP=2.
        let mut string_to_idx: AHashMap<String, u32> = AHashMap::new();
        string_to_idx.insert("BASE".to_string(), 0);
        string_to_idx.insert("DOWN".to_string(), 1);
        string_to_idx.insert("UP".to_string(), 2);
        let encoder = KeyEncoder::categorical_with_string_fallback(string_to_idx);

        // What the model point declares: UP=0, BASE=1, DOWN=2. Every physical
        // index disagrees with the table's index for the same label.
        let categories = FrozenCategories::new(["UP", "BASE", "DOWN"])?;
        let enum_dtype = DataType::from_frozen_categories(categories);
        let labels = Series::new("scenario".into(), &["UP", "BASE", "DOWN"]);
        let as_enum = labels.cast(&enum_dtype)?;

        assert_eq!(encoder.encode_column(&as_enum)?, vec![2, 0, 1]);
        Ok(())
    }

    /// The single-value path is what the vector lookups fall back to, so it has
    /// to agree with the column path label for label.
    #[test]
    fn test_enum_any_value_encodes_like_the_string_it_holds() -> PolarsResult<()> {
        let mut string_to_idx: AHashMap<String, u32> = AHashMap::new();
        string_to_idx.insert("BASE".to_string(), 0);
        string_to_idx.insert("DOWN".to_string(), 1);
        string_to_idx.insert("UP".to_string(), 2);
        let encoder = KeyEncoder::categorical_with_string_fallback(string_to_idx);

        let categories = FrozenCategories::new(["UP", "BASE", "DOWN"])?;
        let enum_dtype = DataType::from_frozen_categories(categories);
        let as_enum = Series::new("scenario".into(), &["UP", "BASE", "DOWN"]).cast(&enum_dtype)?;

        assert_eq!(encoder.encode(as_enum.get(0)?), Some(2), "UP");
        assert_eq!(encoder.encode(as_enum.get(1)?), Some(0), "BASE");
        assert_eq!(encoder.encode(as_enum.get(2)?), Some(1), "DOWN");
        Ok(())
    }

    /// A label the table genuinely does not hold is still a miss. Serving the
    /// encoding must not turn an absent key into some neighbouring rate.
    #[test]
    fn test_an_enum_label_the_table_does_not_hold_is_still_a_miss() -> PolarsResult<()> {
        let mut string_to_idx: AHashMap<String, u32> = AHashMap::new();
        string_to_idx.insert("BASE".to_string(), 0);
        string_to_idx.insert("UP".to_string(), 1);
        let encoder = KeyEncoder::categorical_with_string_fallback(string_to_idx);

        let categories = FrozenCategories::new(["BASE", "STRESS"])?;
        let enum_dtype = DataType::from_frozen_categories(categories);
        let as_enum = Series::new("scenario".into(), &["BASE", "STRESS"]).cast(&enum_dtype)?;

        assert_eq!(encoder.encode_column(&as_enum)?, vec![0, u32::MAX]);
        assert_eq!(encoder.encode(as_enum.get(1)?), None);
        Ok(())
    }

    /// The string fallback is the whole point of this encoder, and the
    /// single-value path is where it is easiest to lose while adding a
    /// dictionary alongside it.
    #[test]
    fn test_the_string_fallback_still_places_a_plain_label() -> PolarsResult<()> {
        let mut string_to_idx: AHashMap<String, u32> = AHashMap::new();
        string_to_idx.insert("BASE".to_string(), 0);
        string_to_idx.insert("UP".to_string(), 1);
        let encoder = KeyEncoder::categorical_with_string_fallback(string_to_idx);

        let labels = Series::new("scenario".into(), &["UP", "BASE", "STRESS"]);
        assert_eq!(encoder.encode(labels.get(0)?), Some(1), "UP");
        assert_eq!(encoder.encode(labels.get(1)?), Some(0), "BASE");
        assert_eq!(encoder.encode(labels.get(2)?), None, "STRESS");
        assert_eq!(encoder.encode_column(&labels)?, vec![1, 0, u32::MAX]);
        Ok(())
    }

    /// A one-row column is a scalar in Polars, and its value comes back in
    /// the owned form. Both encoders that place a categorical key must place
    /// it the same way they place the borrowed form.
    #[test]
    fn test_owned_categorical_value_encodes_like_the_borrowed_one() -> PolarsResult<()> {
        let one_row = Series::new("k".into(), &["b"])
            .cast(&DataType::from_categories(Categories::global()))?;
        let owned = one_row.get(0)?.into_static();
        assert!(matches!(owned, AnyValue::CategoricalOwned(_, _)));

        let mut mapping = AHashMap::new();
        mapping.insert("a".to_string(), 0u32);
        mapping.insert("b".to_string(), 1u32);
        let fallback = KeyEncoder::categorical_with_string_fallback(mapping);
        assert_eq!(fallback.encode(owned.clone()), Some(1));

        let AnyValue::CategoricalOwned(physical, _) = owned else {
            unreachable!("checked above");
        };
        let categorical = KeyEncoder::categorical(physical as usize + 1);
        assert_eq!(
            categorical.encode(one_row.get(0)?.into_static()),
            Some(physical)
        );
        Ok(())
    }
}
