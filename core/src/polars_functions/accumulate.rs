// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Linear recurrence accumulation for list columns (state[t] = state[t-1] * M[t] + A[t])
// ABOUTME: Core primitive for account value rollforwards and state-dependent actuarial projections

use polars::prelude::*;
use polars_arrow::array::PrimitiveArray;
use polars_arrow::offset::OffsetsBuffer;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_accumulation() {
        // initial=100, multiply=[1.01, 1.01, 1.01], add=[10, 10, 10]
        // out[0] = 100 * 1.01 + 10 = 111.0
        // out[1] = 111.0 * 1.01 + 10 = 122.11
        // out[2] = 122.11 * 1.01 + 10 = 133.3311
        let initial = Series::new("initial".into(), vec![100.0_f64]);
        let multiply =
            ListChunked::from_iter([Some(Series::new("".into(), vec![1.01, 1.01, 1.01]))]);
        let add = ListChunked::from_iter([Some(Series::new("".into(), vec![10.0, 10.0, 10.0]))]);

        let result = accumulate(&[initial, multiply.into_series(), add.into_series()]).unwrap();
        let result_list = result.list().unwrap();

        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert!((first_f64.get(0).unwrap() - 111.0).abs() < 1e-10);
        assert!((first_f64.get(1).unwrap() - 122.11).abs() < 1e-10);
        assert!((first_f64.get(2).unwrap() - 133.3311).abs() < 1e-10);
    }

    #[test]
    fn test_multiply_only() {
        // add=0 is equivalent to cumulative product with initial
        // initial=100, multiply=[2.0, 3.0, 4.0], add=[0, 0, 0]
        // out[0] = 100 * 2 + 0 = 200
        // out[1] = 200 * 3 + 0 = 600
        // out[2] = 600 * 4 + 0 = 2400
        let initial = Series::new("initial".into(), vec![100.0_f64]);
        let multiply = ListChunked::from_iter([Some(Series::new("".into(), vec![2.0, 3.0, 4.0]))]);
        let add = ListChunked::from_iter([Some(Series::new("".into(), vec![0.0, 0.0, 0.0]))]);

        let result = accumulate(&[initial, multiply.into_series(), add.into_series()]).unwrap();
        let result_list = result.list().unwrap();

        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert_eq!(first_f64.get(0), Some(200.0));
        assert_eq!(first_f64.get(1), Some(600.0));
        assert_eq!(first_f64.get(2), Some(2400.0));
    }

    #[test]
    fn test_add_only() {
        // multiply=1 is equivalent to cumulative sum with initial
        // initial=100, multiply=[1, 1, 1], add=[10, 20, 30]
        // out[0] = 100 * 1 + 10 = 110
        // out[1] = 110 * 1 + 20 = 130
        // out[2] = 130 * 1 + 30 = 160
        let initial = Series::new("initial".into(), vec![100.0_f64]);
        let multiply = ListChunked::from_iter([Some(Series::new("".into(), vec![1.0, 1.0, 1.0]))]);
        let add = ListChunked::from_iter([Some(Series::new("".into(), vec![10.0, 20.0, 30.0]))]);

        let result = accumulate(&[initial, multiply.into_series(), add.into_series()]).unwrap();
        let result_list = result.list().unwrap();

        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert_eq!(first_f64.get(0), Some(110.0));
        assert_eq!(first_f64.get(1), Some(130.0));
        assert_eq!(first_f64.get(2), Some(160.0));
    }

    #[test]
    fn test_null_initial() {
        // Null initial should produce null output row
        let initial = Series::new("initial".into(), &[None::<f64>]);
        let multiply = ListChunked::from_iter([Some(Series::new("".into(), vec![1.01, 1.01]))]);
        let add = ListChunked::from_iter([Some(Series::new("".into(), vec![10.0, 10.0]))]);

        let result = accumulate(&[initial, multiply.into_series(), add.into_series()]).unwrap();
        let result_list = result.list().unwrap();

        // Null initial => null output row
        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        // All values should be null since initial is null
        assert_eq!(first_f64.get(0), None);
        assert_eq!(first_f64.get(1), None);
    }

    #[test]
    fn test_null_inner_list() {
        // Null multiply list should produce null output row
        let initial = Series::new("initial".into(), vec![100.0_f64]);
        let multiply = ListChunked::from_iter([None::<Series>]);
        let add = ListChunked::from_iter([Some(Series::new("".into(), vec![10.0, 10.0]))]);

        let result = accumulate(&[initial, multiply.into_series(), add.into_series()]).unwrap();
        let result_list = result.list().unwrap();

        // Null multiply list => empty series output
        let first = result_list.get_as_series(0).unwrap();
        assert_eq!(first.len(), 0);
    }

    #[test]
    fn test_length_mismatch_error() {
        // multiply and add lists have different lengths => error
        let initial = Series::new("initial".into(), vec![100.0_f64]);
        let multiply =
            ListChunked::from_iter([Some(Series::new("".into(), vec![1.01, 1.01, 1.01]))]);
        let add = ListChunked::from_iter([Some(Series::new("".into(), vec![10.0, 10.0]))]);

        let result = accumulate(&[initial, multiply.into_series(), add.into_series()]);
        assert!(result.is_err());
        let err_msg = result.unwrap_err().to_string();
        assert!(err_msg.contains("mismatched"));
    }

    #[test]
    fn test_multiple_rows() {
        // Two policies with different initial values and projections
        let initial = Series::new("initial".into(), vec![100.0_f64, 200.0]);
        let multiply = ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.01, 1.02])),
            Some(Series::new("".into(), vec![1.05, 1.05])),
        ]);
        let add = ListChunked::from_iter([
            Some(Series::new("".into(), vec![10.0, 20.0])),
            Some(Series::new("".into(), vec![50.0, 50.0])),
        ]);

        let result = accumulate(&[initial, multiply.into_series(), add.into_series()]).unwrap();
        let result_list = result.list().unwrap();

        // Row 0: initial=100, multiply=[1.01, 1.02], add=[10, 20]
        // out[0] = 100 * 1.01 + 10 = 111.0
        // out[1] = 111.0 * 1.02 + 20 = 133.22
        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert!((first_f64.get(0).unwrap() - 111.0).abs() < 1e-10);
        assert!((first_f64.get(1).unwrap() - 133.22).abs() < 1e-10);

        // Row 1: initial=200, multiply=[1.05, 1.05], add=[50, 50]
        // out[0] = 200 * 1.05 + 50 = 260.0
        // out[1] = 260.0 * 1.05 + 50 = 323.0
        let second = result_list.get_as_series(1).unwrap();
        let second_f64 = second.f64().unwrap();
        assert!((second_f64.get(0).unwrap() - 260.0).abs() < 1e-10);
        assert!((second_f64.get(1).unwrap() - 323.0).abs() < 1e-10);
    }

    #[test]
    fn test_broadcast_initial() {
        // Single initial value broadcast to two rows
        let initial = Series::new("initial".into(), vec![100.0_f64]);
        let multiply = ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.01, 1.01])),
            Some(Series::new("".into(), vec![2.0, 2.0])),
        ]);
        let add = ListChunked::from_iter([
            Some(Series::new("".into(), vec![0.0, 0.0])),
            Some(Series::new("".into(), vec![0.0, 0.0])),
        ]);

        let result = accumulate(&[initial, multiply.into_series(), add.into_series()]).unwrap();
        let result_list = result.list().unwrap();

        // Row 0: initial=100, multiply=[1.01, 1.01], add=[0, 0]
        // out[0] = 100 * 1.01 = 101.0
        // out[1] = 101.0 * 1.01 = 102.01
        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert!((first_f64.get(0).unwrap() - 101.0).abs() < 1e-10);
        assert!((first_f64.get(1).unwrap() - 102.01).abs() < 1e-10);

        // Row 1: initial=100 (broadcast), multiply=[2, 2], add=[0, 0]
        // out[0] = 100 * 2 = 200
        // out[1] = 200 * 2 = 400
        let second = result_list.get_as_series(1).unwrap();
        let second_f64 = second.f64().unwrap();
        assert!((second_f64.get(0).unwrap() - 200.0).abs() < 1e-10);
        assert!((second_f64.get(1).unwrap() - 400.0).abs() < 1e-10);
    }
}

/// Computes linear recurrence: out[t] = out[t-1] * multiply[t] + add[t]
///
/// This is the core primitive for account value rollforwards and other
/// state-dependent actuarial projections. Produces all intermediate states
/// of the accumulation, returning a list column with one value per time
/// step per policy.
///
/// # Arguments
/// * `inputs[0]` - initial: Float64 scalar series, one per row/policy
/// * `inputs[1]` - multiply: List<Float64> series, one list per row
/// * `inputs[2]` - add: List<Float64> series, one list per row
///
/// # Returns
/// List<Float64> series with accumulated values
///
/// # Errors
/// Returns error if:
/// - multiply is not a List type
/// - add is not a List type
/// - Inner list lengths of multiply and add don't match
pub fn accumulate(inputs: &[Series]) -> PolarsResult<Series> {
    let initial = &inputs[0];
    let multiply = &inputs[1];
    let add = &inputs[2];

    // Cast initial to Float64
    let initial_f64 = initial.cast(&DataType::Float64)?;
    let initial_ca = initial_f64.f64()?;
    let initial_is_broadcast = initial_ca.len() == 1;

    // Ensure multiply is a List
    let multiply_list = multiply.list().map_err(|_| {
        PolarsError::ComputeError("multiply must be List dtype for accumulate".into())
    })?;

    // Ensure add is a List
    let add_list = add
        .list()
        .map_err(|_| PolarsError::ComputeError("add must be List dtype for accumulate".into()))?;

    // Check for any null lists or nulls in inner values - if so, fall back to the slower path
    // The fast path requires:
    // 1. No null list entries (outer nulls)
    // 2. No nulls in initial values
    // 3. No nulls in inner values (which would cause non-contiguous slices)
    let has_outer_nulls =
        multiply_list.null_count() > 0 || add_list.null_count() > 0 || initial_ca.null_count() > 0;

    // Check for inner nulls by looking at the inner dtype's null count
    let has_inner_nulls = {
        let mul_inner_nulls = multiply_list
            .rechunk()
            .downcast_iter()
            .next()
            .map(|arr| arr.values().null_count())
            .unwrap_or(0);
        let add_inner_nulls = add_list
            .rechunk()
            .downcast_iter()
            .next()
            .map(|arr| arr.values().null_count())
            .unwrap_or(0);
        mul_inner_nulls > 0 || add_inner_nulls > 0
    };

    if has_outer_nulls || has_inner_nulls {
        return accumulate_with_nulls(initial_ca, initial_is_broadcast, multiply_list, add_list);
    }

    // Fast path: no nulls anywhere, use direct array access
    accumulate_fast(initial_ca, initial_is_broadcast, multiply_list, add_list)
}

/// Fast path for accumulate when there are no null lists.
/// Works directly with underlying arrays to avoid per-row allocations.
fn accumulate_fast(
    initial_ca: &Float64Chunked,
    initial_is_broadcast: bool,
    multiply_list: &ListChunked,
    add_list: &ListChunked,
) -> PolarsResult<Series> {
    // Rechunk to get contiguous arrays
    let multiply_rechunked = multiply_list.rechunk();
    let add_rechunked = add_list.rechunk();

    // Get the underlying LargeListArrays
    let mul_arr = multiply_rechunked.downcast_iter().next().unwrap();
    let add_arr = add_rechunked.downcast_iter().next().unwrap();

    // Get offsets and values
    let mul_offsets = mul_arr.offsets();
    let add_offsets = add_arr.offsets();

    // Wrap the inner Arrow value arrays as Series, then cast to Float64.
    let mul_values_series = Series::from_arrow(PlSmallStr::EMPTY, mul_arr.values().clone())?
        .cast(&DataType::Float64)?;

    let add_values_series = Series::from_arrow(PlSmallStr::EMPTY, add_arr.values().clone())?
        .cast(&DataType::Float64)?;

    let mul_values = mul_values_series.f64()?;
    let add_values = add_values_series.f64()?;

    // Get contiguous slices for maximum performance
    let mul_values_rechunked = mul_values.rechunk();
    let add_values_rechunked = add_values.rechunk();

    let mul_slice = mul_values_rechunked
        .cont_slice()
        .map_err(|_| PolarsError::ComputeError("multiply values not contiguous".into()))?;
    let add_slice = add_values_rechunked
        .cont_slice()
        .map_err(|_| PolarsError::ComputeError("add values not contiguous".into()))?;

    let initial_rechunked = initial_ca.rechunk();
    let initial_slice = initial_rechunked
        .cont_slice()
        .map_err(|_| PolarsError::ComputeError("initial values not contiguous".into()))?;

    let num_rows = mul_offsets.len() - 1;

    // Pre-calculate total output length and build output offsets
    let total_len: usize = *mul_offsets.last() as usize;
    let mut output_values: Vec<f64> = Vec::with_capacity(total_len);
    let mut output_offsets: Vec<i64> = Vec::with_capacity(num_rows + 1);
    output_offsets.push(0);

    for row_idx in 0..num_rows {
        let mul_start = mul_offsets[row_idx] as usize;
        let mul_end = mul_offsets[row_idx + 1] as usize;
        let add_start = add_offsets[row_idx] as usize;
        let add_end = add_offsets[row_idx + 1] as usize;

        let mul_len = mul_end - mul_start;
        let add_len = add_end - add_start;

        // Verify lengths match
        if mul_len != add_len {
            return Err(PolarsError::ComputeError(
                format!(
                    "mismatched inner list lengths for accumulate at row {}: multiply={}, add={}",
                    row_idx, mul_len, add_len
                )
                .into(),
            ));
        }

        // Get initial value (broadcast or per-row)
        let initial_idx = if initial_is_broadcast { 0 } else { row_idx };
        let mut state = initial_slice[initial_idx];

        // Compute the recurrence for this row
        let mul_row = &mul_slice[mul_start..mul_end];
        let add_row = &add_slice[add_start..add_end];

        for t in 0..mul_len {
            state = state * mul_row[t] + add_row[t];
            output_values.push(state);
        }

        output_offsets.push(output_values.len() as i64);
    }

    // Build the output List<Float64> Series from the flat arrays via safe Polars APIs.
    let offsets = OffsetsBuffer::try_from(output_offsets)
        .map_err(|e| PolarsError::ComputeError(format!("invalid offsets: {e}").into()))?;
    let values_arr = PrimitiveArray::from_vec(output_values);

    let list_arr = LargeListArray::new(
        ArrowDataType::LargeList(Box::new(ArrowField::new(
            PlSmallStr::from_static("item"),
            ArrowDataType::Float64,
            true,
        ))),
        offsets,
        Box::new(values_arr),
        None, // no validity - no nulls in fast path
    );

    Series::from_arrow(PlSmallStr::EMPTY, Box::new(list_arr))
}

/// Slow path for accumulate when there are null values.
/// Uses amortized_iter which handles nulls correctly but has per-row allocation overhead.
fn accumulate_with_nulls(
    initial_ca: &Float64Chunked,
    initial_is_broadcast: bool,
    multiply_list: &ListChunked,
    add_list: &ListChunked,
) -> PolarsResult<Series> {
    let result = multiply_list
        .amortized_iter()
        .zip(add_list.amortized_iter())
        .enumerate()
        .map(|(idx, (mul_opt, add_opt))| {
            // Get initial value for this row (broadcast if needed)
            let initial_idx = if initial_is_broadcast { 0 } else { idx };
            let initial_val_opt = initial_ca.get(initial_idx);

            match (mul_opt, add_opt, initial_val_opt) {
                (Some(mul_series), Some(add_series), Some(initial_val)) => {
                    let m = mul_series.as_ref().cast(&DataType::Float64)?;
                    let a = add_series.as_ref().cast(&DataType::Float64)?;

                    let m_ca = m.f64().unwrap();
                    let a_ca = a.f64().unwrap();

                    // Verify same length
                    if m_ca.len() != a_ca.len() {
                        return Err(PolarsError::ComputeError(
                            format!(
                                "mismatched inner list lengths for accumulate: multiply={}, add={}",
                                m_ca.len(),
                                a_ca.len()
                            )
                            .into(),
                        ));
                    }

                    let len = m_ca.len();
                    let mut state = initial_val;
                    let mut results = Vec::with_capacity(len);

                    for t in 0..len {
                        let mul_val = m_ca.get(t);
                        let add_val = a_ca.get(t);

                        match (mul_val, add_val) {
                            (Some(mv), Some(av)) => {
                                state = state * mv + av;
                                results.push(Some(state));
                            }
                            _ => {
                                // If either inner value is null, output null and
                                // propagate NaN state for subsequent steps
                                results.push(None);
                                state = f64::NAN;
                            }
                        }
                    }

                    Ok(Some(Float64Chunked::from_iter(results).into_series()))
                }
                // Null initial: produce null-filled output matching multiply length
                (Some(mul_series), Some(_add_series), None) => {
                    let len = mul_series.as_ref().len();
                    let nulls: Vec<Option<f64>> = vec![None; len];
                    Ok(Some(Float64Chunked::from_iter(nulls).into_series()))
                }
                // Null multiply or add list: produce empty series
                _ => Ok(Some(Series::new_empty("".into(), &DataType::Float64))),
            }
        })
        .collect::<PolarsResult<ListChunked>>()?;

    Ok(result.into_series())
}
