// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Hash-based assumption table storage using AHashMap.
// ABOUTME: Original implementation extracted for modularity alongside array storage.

use ahash::{AHashMap, AHasher};
use polars::prelude::*;
use rayon::prelude::*;
use std::hash::{Hash, Hasher};

/// Exact numerical identity shared by integer and Float64 lookup keys.
///
/// Positive signed integers use the unsigned branch so equal values have one
/// representation regardless of their source dtype. Finite integral floats
/// use an integer branch only when their mathematical value fits that branch;
/// larger integral floats remain floats instead of saturating at an endpoint.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum NumericKey {
    Negative(i64),
    NonNegative(u64),
    Float(u64),
}

impl NumericKey {
    #[inline]
    fn from_value(av: AnyValue) -> Option<Self> {
        match av {
            AnyValue::Int64(i) => Some(Self::from_i64(i)),
            AnyValue::Int32(i) => Some(Self::from_i64(i64::from(i))),
            AnyValue::Int16(i) => Some(Self::from_i64(i64::from(i))),
            AnyValue::Int8(i) => Some(Self::from_i64(i64::from(i))),
            AnyValue::UInt64(u) => Some(Self::NonNegative(u)),
            AnyValue::UInt32(u) => Some(Self::NonNegative(u64::from(u))),
            AnyValue::UInt16(u) => Some(Self::NonNegative(u64::from(u))),
            AnyValue::UInt8(u) => Some(Self::NonNegative(u64::from(u))),
            AnyValue::Float64(f) => Some(Self::from_f64(f)),
            _ => None,
        }
    }

    #[inline]
    fn from_i64(value: i64) -> Self {
        match u64::try_from(value) {
            Ok(value) => Self::NonNegative(value),
            Err(_) => Self::Negative(value),
        }
    }

    #[inline]
    fn from_f64(value: f64) -> Self {
        if !value.is_finite() {
            return Self::Float(value.to_bits());
        }
        if value == 0.0 {
            return Self::NonNegative(0);
        }
        if value.fract() != 0.0 {
            return Self::Float(value.to_bits());
        }

        // These powers of two are exactly representable. The upper bounds are
        // exclusive because Rust float-to-integer casts saturate there.
        const I64_MIN_AS_F64: f64 = -9_223_372_036_854_775_808.0;
        const U64_END_AS_F64: f64 = 18_446_744_073_709_551_616.0;
        if (I64_MIN_AS_F64..0.0).contains(&value) {
            return Self::Negative(value as i64);
        }
        if (0.0..U64_END_AS_F64).contains(&value) {
            return Self::NonNegative(value as u64);
        }
        Self::Float(value.to_bits())
    }

    #[inline]
    fn encoded(self) -> u64 {
        let mut hasher = AHasher::default();
        self.hash(&mut hasher);
        hasher.finish()
    }
}

/// Codec for encoding column values to u64 keys for hash table lookup.
#[derive(Debug, Clone)]
pub enum ColumnCodec {
    String,
    Float64,
    Integer,
}

impl ColumnCodec {
    #[inline]
    pub fn encode(&self, av: AnyValue) -> Option<u64> {
        // Null and unhandled dtype/codec combinations are a miss (None), not
        // a silent 0u64 that aliases to key 0's hash and returns key 0's rate.
        if matches!(av, AnyValue::Null) {
            return None;
        }
        let hash = match (self, av) {
            // A categorical or Enum key is the label it holds, so it hashes as
            // that label's text. Its physical index names nothing on its own:
            // it numbers the label in one dictionary, and the table's text was
            // hashed by its bytes. Hashing the index made every categorical or
            // Enum key miss a text table -- a silent NaN under on_missing="nan"
            // and the fill value under a fill, where array storage answered
            // the rate -- and let two dictionaries that number labels
            // differently agree on an index for two different labels.
            (ColumnCodec::String, AnyValue::Categorical(idx, mapping))
            | (ColumnCodec::String, AnyValue::Enum(idx, mapping)) => {
                Self::hash_text(mapping.cat_to_str(idx)?)
            }
            (ColumnCodec::String, AnyValue::CategoricalOwned(idx, mapping))
            | (ColumnCodec::String, AnyValue::EnumOwned(idx, mapping)) => {
                Self::hash_text(mapping.cat_to_str(idx)?)
            }
            (ColumnCodec::String, AnyValue::String(s)) => Self::hash_text(s),
            (ColumnCodec::String, AnyValue::StringOwned(s)) => Self::hash_text(s.as_str()),
            (ColumnCodec::Float64 | ColumnCodec::Integer, numeric) => {
                NumericKey::from_value(numeric)?.encoded()
            }
            // Everything else is a miss, as it is in array storage: a number
            // against a text table, text against a numeric one. The text codec
            // used to hash a number's decimal spelling, so 5 found a row keyed
            // "5" here while array storage missed it, and the answer depended
            // on which storage the table happened to get. A number never
            // equals text (spec section 11.1.24 keeps the families apart).
            _ => return None,
        };
        Some(hash)
    }

    /// Hash a text key by its bytes: the one identity a label has.
    #[inline]
    fn hash_text(s: &str) -> u64 {
        let mut hasher = AHasher::default();
        hasher.write(s.as_bytes());
        hasher.finish()
    }
}

/// Hash-based storage backend for assumption tables.
#[derive(Debug)]
pub struct HashStorage {
    pub(crate) codecs: Vec<ColumnCodec>,
    pub(crate) map: AHashMap<u64, f64>,
}

impl HashStorage {
    /// Build hash storage from DataFrame.
    pub fn build(df: &DataFrame, keys: &[String], value: &str) -> PolarsResult<Self> {
        let n_rows = df.height();

        // Prepare codecs
        let mut codecs = Vec::with_capacity(keys.len());
        for col_name in keys {
            let s = df.column(col_name)?;
            codecs.push(match s.dtype() {
                DataType::String => ColumnCodec::String,
                // Categorical values only have encode arms on the String
                // codec (physical index / string hash); the Integer codec
                // would treat every row as unencodable.
                DataType::Categorical(_, _) => ColumnCodec::String,
                DataType::Float64 => ColumnCodec::Float64,
                _ => ColumnCodec::Integer,
            });
        }

        // Build the hash map
        let mut map: AHashMap<u64, f64> = AHashMap::with_capacity(n_rows.next_power_of_two());
        // Transient build-time index: first source row per hash, so a hash
        // conflict can be verified against the actual key values rather than
        // misreported (a 64-bit collision between distinct keys is
        // astronomically rare but must not be called a duplicate).
        let mut first_row_for_hash: AHashMap<u64, usize> =
            AHashMap::with_capacity(n_rows.next_power_of_two());
        let value_series = df.column(value)?.f64()?;

        for row_idx in 0..n_rows {
            let hash = Self::compute_hash_for_row(df, keys, &codecs, row_idx)?;
            let v = value_series.get(row_idx).unwrap_or(f64::NAN);
            if let Some(&prev_row) = first_row_for_hash.get(&hash) {
                let is_true_duplicate = keys.iter().all(|key_name| {
                    let col = df.column(key_name);
                    match col {
                        Ok(c) => match (c.get(prev_row), c.get(row_idx)) {
                            (Ok(a), Ok(b)) => a == b,
                            _ => false,
                        },
                        Err(_) => false,
                    }
                });
                if is_true_duplicate {
                    return Err(polars_err!(ComputeError:
                        "Duplicate key combination at source row {} while building table (same keys as row {}). Deduplicate the source or fix the dimension mapping.",
                        row_idx, prev_row));
                }
                return Err(polars_err!(ComputeError:
                    "64-bit key-hash collision between distinct source rows {} and {} while building table; use storage_mode=\"array\" for this table.",
                    prev_row, row_idx));
            }
            first_row_for_hash.insert(hash, row_idx);
            map.insert(hash, v);
        }

        Ok(Self { codecs, map })
    }

    /// Compute hash for a single row during build.
    fn compute_hash_for_row(
        df: &DataFrame,
        keys: &[String],
        codecs: &[ColumnCodec],
        row_idx: usize,
    ) -> PolarsResult<u64> {
        if codecs.len() == 2 {
            // Fast path for 2-key case
            let av1 = df.column(&keys[0])?.get(row_idx)?;
            let av2 = df.column(&keys[1])?.get(row_idx)?;
            let hash1 = codecs[0].encode(av1).ok_or_else(|| polars_err!(ComputeError:
                "null or unencodable key value in column '{}' at source row {} while building table",
                keys[0], row_idx))?;
            let hash2 = codecs[1].encode(av2).ok_or_else(|| polars_err!(ComputeError:
                "null or unencodable key value in column '{}' at source row {} while building table",
                keys[1], row_idx))?;
            Ok(hash1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ hash2)
        } else {
            let mut h = AHasher::default();
            for (codec, key_name) in codecs.iter().zip(keys) {
                let av = df.column(key_name)?.get(row_idx)?;
                let part = codec.encode(av).ok_or_else(|| polars_err!(ComputeError:
                    "null or unencodable key value in column '{}' at source row {} while building table",
                    key_name, row_idx))?;
                h.write_u64(part);
            }
            Ok(h.finish())
        }
    }

    /// Lookup values for scalar key columns.
    pub fn lookup_scalar(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
        let len = key_cols[0].len();

        // Validate all series have same length
        for s in key_cols.iter().skip(1) {
            if s.len() != len {
                return Err(polars_err!(ShapeMismatch: "key columns not equal length"));
            }
        }

        // Fast path for common case: 2 keys with >1000 rows
        if self.codecs.len() == 2 && len > 1000 {
            return self.lookup_scalar_fast_path_2keys(key_cols);
        }

        let mut out = vec![f64::NAN; len];

        out.par_iter_mut().enumerate().for_each(|(idx, slot)| {
            let key = if self.codecs.len() == 2 {
                // SAFETY: idx is bounded by out.len() == key_cols[0].len() == key_cols[1].len()
                // (length parity verified above). Series::get_unchecked is measurably faster
                // (~15%) than Series::get on this hot lookup path.
                let av1 = unsafe { key_cols[0].get_unchecked(idx) };
                let av2 = unsafe { key_cols[1].get_unchecked(idx) };
                match (self.codecs[0].encode(av1), self.codecs[1].encode(av2)) {
                    (Some(h1), Some(h2)) => Some(h1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ h2),
                    _ => None,
                }
            } else {
                let mut h = AHasher::default();
                let mut valid = true;
                for (codec, series) in self.codecs.iter().zip(key_cols) {
                    // SAFETY: idx is bounded by out.len() == series.len() (length parity above).
                    let av = unsafe { series.get_unchecked(idx) };
                    match codec.encode(av) {
                        Some(part) => h.write_u64(part),
                        None => {
                            valid = false;
                            break;
                        }
                    }
                }
                valid.then(|| h.finish())
            };
            if let Some(v) = key.and_then(|k| self.map.get(&k)) {
                *slot = *v;
            }
        });

        Ok(Series::from_vec("lookup".into(), out))
    }

    /// Fast path for 2-key lookups.
    fn lookup_scalar_fast_path_2keys(&self, key_cols: &[&Series]) -> PolarsResult<Series> {
        let len = key_cols[0].len();
        let mut out = vec![f64::NAN; len];

        let series1 = key_cols[0];
        let series2 = key_cols[1];

        const CHUNK_SIZE: usize = 1024;

        out.par_chunks_mut(CHUNK_SIZE)
            .enumerate()
            .for_each(|(chunk_idx, chunk)| {
                let start_idx = chunk_idx * CHUNK_SIZE;
                let end_idx = (start_idx + chunk.len()).min(len);

                for (local_idx, slot) in chunk.iter_mut().enumerate() {
                    let global_idx = start_idx + local_idx;
                    if global_idx >= end_idx {
                        break;
                    }

                    // SAFETY: global_idx < end_idx <= len == series1.len() == series2.len()
                    // (verified by the early-break above). Series::get_unchecked is measurably
                    // faster than Series::get on this 1024-row chunked hot path.
                    let av1 = unsafe { series1.get_unchecked(global_idx) };
                    let av2 = unsafe { series2.get_unchecked(global_idx) };

                    if let (Some(hash1), Some(hash2)) =
                        (self.codecs[0].encode(av1), self.codecs[1].encode(av2))
                    {
                        let key = hash1.wrapping_mul(0x9e37_79b9_7f4a_7c15_u64) ^ hash2;
                        if let Some(v) = self.map.get(&key) {
                            *slot = *v;
                        }
                    }
                }
            });

        Ok(Series::from_vec("lookup".into(), out))
    }

    /// Get the number of entries in the storage.
    pub fn entry_count(&self) -> usize {
        self.map.len()
    }

    /// Get reference to codecs for append validation.
    pub fn codecs(&self) -> &[ColumnCodec] {
        &self.codecs
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use polars::df;

    #[test]
    fn categorical_keys_do_not_collide() -> PolarsResult<()> {
        // Categorical dtype fell into the Integer codec, whose encode had no
        // Categorical arm: every key hashed to the catch-all value, so all
        // rows collided and lookups silently returned one row's rate for
        // every key. Categorical keys must route through the String codec.
        let funds = Series::new("fund".into(), ["A", "B", "C"])
            .cast(&DataType::from_categories(Categories::global()))?;
        let rates = Series::new("rate".into(), [0.1f64, 0.2, 0.3]);
        let df = DataFrame::new(3, vec![funds.clone().into(), rates.into()])?;

        let storage = HashStorage::build(&df, &["fund".to_string()], "rate")?;
        let out = storage.lookup_scalar(&[&funds])?;
        let ca = out.f64()?;

        assert_eq!(ca.get(0), Some(0.1));
        assert_eq!(ca.get(1), Some(0.2));
        assert_eq!(ca.get(2), Some(0.3));
        Ok(())
    }

    /// A categorical or Enum key reads a text table by its label, whatever
    /// dictionary numbers it: the borrowed and owned forms (a one-row column
    /// is a scalar and hands its value back owned), a global categorical, and
    /// an Enum whose declared order differs from the table's.
    #[test]
    fn categorical_and_enum_keys_read_a_text_table_by_label() -> PolarsResult<()> {
        let sex = Series::new("sex".into(), ["M", "F"]);
        let rates = Series::new("q".into(), [0.1f64, 0.2]);
        let df = DataFrame::new(2, vec![sex.into(), rates.into()])?;
        let storage = HashStorage::build(&df, &["sex".to_string()], "q")?;

        let text = Series::new("s".into(), ["F", "M"]);
        let categorical = text.cast(&DataType::from_categories(Categories::global()))?;
        let categories = FrozenCategories::new(["F", "M"])?;
        let enum_key = text.cast(&DataType::from_frozen_categories(categories))?;

        for key in [&text, &categorical, &enum_key] {
            let out = storage.lookup_scalar(&[key])?;
            let ca = out.f64()?;
            assert_eq!(ca.get(0), Some(0.2), "{:?}", key.dtype());
            assert_eq!(ca.get(1), Some(0.1), "{:?}", key.dtype());

            let codec = ColumnCodec::String;
            let owned = key.get(0)?.into_static();
            assert_eq!(
                codec.encode(owned),
                codec.encode(AnyValue::String("F")),
                "{:?}",
                key.dtype()
            );
        }
        Ok(())
    }

    #[test]
    fn mixed_numeric_hashes_follow_exact_value_equality() {
        let codec = ColumnCodec::Float64;

        assert_eq!(
            codec.encode(AnyValue::Float64(9_007_199_254_740_992.0)),
            codec.encode(AnyValue::Int64(9_007_199_254_740_992))
        );
        assert_ne!(
            codec.encode(AnyValue::Float64(9_007_199_254_740_992.0)),
            codec.encode(AnyValue::Int64(9_007_199_254_740_993))
        );
        assert_eq!(
            codec.encode(AnyValue::Float64(9_223_372_036_854_775_808.0)),
            codec.encode(AnyValue::UInt64(9_223_372_036_854_775_808))
        );
        assert_ne!(
            codec.encode(AnyValue::Float64(9_223_372_036_854_775_808.0)),
            codec.encode(AnyValue::Int64(i64::MAX))
        );
        assert_ne!(
            codec.encode(AnyValue::Int64(-1)),
            codec.encode(AnyValue::UInt64(u64::MAX))
        );
    }

    /// A number against a text table is a miss in hash storage, as it is in
    /// array storage, and text against a numeric table likewise: the two
    /// storages give one answer for one query.
    #[test]
    fn a_key_of_the_other_family_is_a_miss_in_either_direction() -> PolarsResult<()> {
        let text = ColumnCodec::String;
        for number in [
            AnyValue::Int8(5),
            AnyValue::Int16(5),
            AnyValue::Int32(5),
            AnyValue::Int64(5),
            AnyValue::UInt8(5),
            AnyValue::UInt16(5),
            AnyValue::UInt32(5),
            AnyValue::UInt64(5),
            AnyValue::Float64(5.0),
            AnyValue::Float64(9_223_372_036_854_775_808.0),
        ] {
            assert_eq!(text.encode(number.clone()), None, "{number:?}");
        }
        for numeric in [ColumnCodec::Float64, ColumnCodec::Integer] {
            assert_eq!(numeric.encode(AnyValue::String("5")), None);
        }

        let keys = Series::new("k".into(), ["5", "7"]);
        let rates = Series::new("q".into(), [0.1f64, 0.2]);
        let df = DataFrame::new(2, vec![keys.into(), rates.into()])?;
        let storage = HashStorage::build(&df, &["k".to_string()], "q")?;
        let numbers = Series::new("k".into(), [5i64, 7]);
        let out = storage.lookup_scalar(&[&numbers])?;
        assert!(out.f64()?.into_iter().all(|v| v.is_some_and(f64::is_nan)));
        Ok(())
    }

    #[test]
    fn fractional_and_nonfinite_hashes_cannot_alias_integer_keys() {
        let codec = ColumnCodec::Float64;
        let smallest_positive = f64::from_bits(1);

        assert_ne!(
            codec.encode(AnyValue::Float64(smallest_positive)),
            codec.encode(AnyValue::Int64(1))
        );
        assert_ne!(
            codec.encode(AnyValue::Float64(1.5)),
            codec.encode(AnyValue::Int64(1))
        );
        assert_ne!(
            codec.encode(AnyValue::Float64(f64::NAN)),
            codec.encode(AnyValue::Int64(f64::NAN.to_bits() as i64))
        );
        assert_ne!(
            codec.encode(AnyValue::Float64(f64::INFINITY)),
            codec.encode(AnyValue::UInt64(f64::INFINITY.to_bits()))
        );
        assert_ne!(
            codec.encode(AnyValue::Float64(f64::NEG_INFINITY)),
            codec.encode(AnyValue::UInt64(f64::NEG_INFINITY.to_bits()))
        );
    }

    #[test]
    fn hash_storage_matches_large_numeric_values_without_endpoint_aliases() -> PolarsResult<()> {
        let df = df! {
            "key" => [
                -9_223_372_036_854_775_808.0,
                9_007_199_254_740_992.0,
                9_223_372_036_854_775_808.0,
            ],
            "rate" => [0.1, 0.2, 0.3],
        }?;
        let storage = HashStorage::build(&df, &["key".to_string()], "rate")?;
        let signed = Series::new("key".into(), [i64::MIN, 9_007_199_254_740_992, i64::MAX]);
        let unsigned = Series::new("key".into(), [9_223_372_036_854_775_808_u64, u64::MAX]);

        let signed_out = storage.lookup_scalar(&[&signed])?;
        let signed_out = signed_out.f64()?;
        assert_eq!(signed_out.get(0), Some(0.1));
        assert_eq!(signed_out.get(1), Some(0.2));
        assert!(signed_out.get(2).is_some_and(f64::is_nan));

        let unsigned_out = storage.lookup_scalar(&[&unsigned])?;
        let unsigned_out = unsigned_out.f64()?;
        assert_eq!(unsigned_out.get(0), Some(0.3));
        assert!(unsigned_out.get(1).is_some_and(f64::is_nan));
        Ok(())
    }
}
