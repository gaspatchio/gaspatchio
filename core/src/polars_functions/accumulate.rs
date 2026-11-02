// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Linear recurrence accumulation for list columns (state[t] = state[t-1] * M[t] + A[t])
// ABOUTME: Core primitive for account value rollforwards and state-dependent actuarial projections

use polars::prelude::*;
use polars_arrow::array::PrimitiveArray;
use polars_arrow::offset::OffsetsBuffer;

use super::slices::{rows_per_policy, same_periods};

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

    /// Run the recurrence over a column of policies and hand back the states
    /// row by row, each period either a value or a null.
    ///
    /// Every null case below opens with one initial value per policy and two
    /// per-period lists, so the scaffold that wraps those three operands,
    /// calls the kernel and reads a row's values back is written once here
    /// and each case states its run and the states it expects.
    fn states(
        initial: Vec<f64>,
        multiply: Vec<Vec<Option<f64>>>,
        add: Vec<Vec<Option<f64>>>,
    ) -> Vec<Vec<Option<f64>>> {
        let periods = |rows: Vec<Vec<Option<f64>>>| {
            ListChunked::from_iter(
                rows.into_iter()
                    .map(|row| Some(Series::new("".into(), row))),
            )
            .into_series()
        };
        let result = accumulate(&[
            Series::new("initial".into(), initial),
            periods(multiply),
            periods(add),
        ])
        .unwrap();

        let rows = result.list().unwrap();
        (0..rows.len())
            .map(|row| {
                let values = rows.get_as_series(row).unwrap();
                values.f64().unwrap().into_iter().collect()
            })
            .collect()
    }

    #[test]
    fn test_null_multiplier_ends_the_fold() {
        // initial=100, multiply=[1.1, null, 1.1, 1.1], add=[0, 0, 0, 0].
        // out[0] = 100 * 1.1 + 0 = 110.0 is reached before the hole; period 1
        // has no growth factor, so the state is unknown there and at every
        // later period. Folding past it would report 121.0 and 133.1, two
        // account values that had each quietly lost a period's growth.
        let answer = states(
            vec![100.0],
            vec![vec![Some(1.1), None, Some(1.1), Some(1.1)]],
            vec![vec![Some(0.0), Some(0.0), Some(0.0), Some(0.0)]],
        );

        assert!((answer[0][0].unwrap() - 110.0).abs() < 1e-10);
        assert_eq!(answer[0][1], None);
        assert_eq!(answer[0][2], None);
        assert_eq!(answer[0][3], None);
    }

    #[test]
    fn test_null_addend_ends_the_fold() {
        // initial=100, multiply=[1.1, 1.1, 1.1, 1.1], add=[0, 0, null, 0].
        // 100 * 1.1 = 110.0 and 110.0 * 1.1 = 121.0 are both reached before
        // the hole at period 2, which has no flow to add.
        let answer = states(
            vec![100.0],
            vec![vec![Some(1.1), Some(1.1), Some(1.1), Some(1.1)]],
            vec![vec![Some(0.0), Some(0.0), None, Some(0.0)]],
        );

        assert!((answer[0][0].unwrap() - 110.0).abs() < 1e-10);
        assert!((answer[0][1].unwrap() - 121.0).abs() < 1e-10);
        assert_eq!(answer[0][2], None);
        assert_eq!(answer[0][3], None);
    }

    #[test]
    fn test_null_at_the_first_period_nulls_the_whole_run() {
        // The fold reaches no period before the hole, so it never reports a
        // state at all -- but the row keeps its length rather than collapsing.
        let answer = states(
            vec![100.0],
            vec![vec![None, Some(1.1), Some(1.1)]],
            vec![vec![Some(0.0), Some(0.0), Some(0.0)]],
        );

        assert_eq!(answer[0], vec![None, None, None]);
    }

    #[test]
    fn test_null_at_the_last_period_leaves_the_earlier_states() {
        // The hole is the last thing the fold meets, so every period before
        // it keeps the state it reported: 110.0 and then 121.0.
        let answer = states(
            vec![100.0],
            vec![vec![Some(1.1), Some(1.1), None]],
            vec![vec![Some(0.0), Some(0.0), Some(0.0)]],
        );

        assert!((answer[0][0].unwrap() - 110.0).abs() < 1e-10);
        assert!((answer[0][1].unwrap() - 121.0).abs() < 1e-10);
        assert_eq!(answer[0][2], None);
    }

    #[test]
    fn test_a_nan_operand_is_not_a_null_and_keeps_folding() {
        // A NaN is a value the arithmetic carries, not a period that went
        // missing: 100 * NaN + 0 is NaN, and so is every state after it. The
        // second policy is the same shape with a null in place of the NaN,
        // kept beside it so the two answers are read together.
        let answer = states(
            vec![100.0, 100.0],
            vec![
                vec![Some(1.1), Some(f64::NAN), Some(1.1)],
                vec![Some(1.1), None, Some(1.1)],
            ],
            vec![
                vec![Some(0.0), Some(0.0), Some(0.0)],
                vec![Some(0.0), Some(0.0), Some(0.0)],
            ],
        );

        assert!((answer[0][0].unwrap() - 110.0).abs() < 1e-10);
        assert!(answer[0][1].unwrap().is_nan());
        assert!(answer[0][2].unwrap().is_nan());

        assert!((answer[1][0].unwrap() - 110.0).abs() < 1e-10);
        assert_eq!(answer[1][1], None);
        assert_eq!(answer[1][2], None);
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
/// # Nulls
///
/// A running state that has lost a period is unknown from there on, which is
/// the rule the framework's other forward folds already follow:
///
/// * A null multiplier or a null addend at period `t` makes position `t` and
///   every later position null. It does not make them NaN, and it does not
///   skip the period and carry on: a state folded past a missing charge is a
///   number with nothing wrong on the face of it and a period missing from
///   underneath it. `initial = 100`, `multiply = [1.1, null, 1.1, 1.1]` and a
///   zero addend give `[110.0, null, null, null]`; a null addend at `t=2`
///   gives `[110.0, 121.0, null, null]`.
/// * A null initial gives a null at every position, because the recurrence
///   never had a state to open with.
/// * A null multiply or add list — the whole list for that policy, not one of
///   its periods — gives an empty series for that row, as it always has.
/// * A NaN is not a null. It is a value the arithmetic keeps: `state * NaN`
///   is NaN and so is every state after it, and a caller who wants a missing
///   period read as a number fills it before the recurrence rather than
///   leaving the recurrence to guess.
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
    // The streaming engine hands this kernel a slice of each list column whose
    // inner values are still the whole column's. The fast path below casts,
    // null-checks and indexes those flat values, so it is handed the slice's
    // own elements -- or every morsel would cast the whole portfolio. A
    // one-row list (a literal the in-memory engine hands over unbroadcast) is
    // repeated for every policy, as the streaming engine reads it.
    let operands = rows_per_policy(inputs, false)?;
    let [initial, multiply, add] = operands.as_slice() else {
        return Err(PolarsError::ComputeError(
            format!("accumulate takes three operands, got {}", operands.len()).into(),
        ));
    };

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
        same_periods("multiplier", mul_len, "addend", add_len)?;

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
///
/// This is where the null rule stated on [`accumulate`] is applied: a period
/// whose multiplier or addend is null ends the fold, so that position and
/// every later one are null. The fast path never reaches a null and therefore
/// never reaches this rule.
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
                    same_periods("multiplier", m_ca.len(), "addend", a_ca.len())?;

                    let len = m_ca.len();
                    let mut state = initial_val;
                    let mut results = Vec::with_capacity(len);
                    // A period that arrives with no multiplier or no addend
                    // costs the running state a term, so the state is unknown
                    // from there on. `lost` ends the fold at that period
                    // instead of carrying a substitute value past it.
                    let mut lost = false;

                    for t in 0..len {
                        if lost {
                            results.push(None);
                            continue;
                        }

                        match (m_ca.get(t), a_ca.get(t)) {
                            (Some(mv), Some(av)) => {
                                state = state * mv + av;
                                results.push(Some(state));
                            }
                            _ => {
                                lost = true;
                                results.push(None);
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

#[cfg(test)]
mod refusal_tests {
    use super::*;

    #[test]
    fn a_short_addend_is_refused_by_both_lengths_and_no_row_on_either_path() {
        let initial = Series::new("".into(), vec![100.0_f64, 100.0]);
        let multiply = ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.0, 1.0])),
            Some(Series::new("".into(), vec![1.0, 1.0, 1.0])),
        ])
        .into_series();
        // The fast path reads no nulls; a null period sends the call to the
        // slow path, which must refuse in the same words.
        for add in [vec![Some(1.0), Some(1.0)], vec![Some(1.0), None]] {
            let add = ListChunked::from_iter([
                Some(Series::new("".into(), vec![1.0, 1.0])),
                Some(Series::new("".into(), add)),
            ])
            .into_series();
            let err = accumulate(&[initial.clone(), multiply.clone(), add])
                .unwrap_err()
                .to_string();
            assert!(
                err.contains(
                    "mismatched inner list lengths in one policy: addend against multiplier"
                ),
                "{err}"
            );
            assert!(
                err.contains("multiplier=3, addend=2 in that policy."),
                "{err}"
            );
            assert!(!err.contains("at row"), "{err}");
        }
    }
}

#[cfg(test)]
mod slice_tests {
    use super::*;

    /// Six policies, three periods each; `nulls` puts a missing period in the
    /// last policy's multiplier, outside the slice the tests take.
    fn six_policies(nulls: bool) -> (Series, Series, Series) {
        let initial = Series::new(
            "initial".into(),
            (0..6).map(|r| 100.0 + r as f64).collect::<Vec<_>>(),
        );
        let multiply = ListChunked::from_iter((0..6).map(|r| {
            let factor = 1.0 + r as f64 / 100.0;
            if nulls && r == 5 {
                Some(Series::new(
                    "".into(),
                    vec![Some(factor), None, Some(factor)],
                ))
            } else {
                Some(Series::new("".into(), vec![Some(factor); 3]))
            }
        }))
        .into_series();
        let add = ListChunked::from_iter(
            (0..6).map(|r| Some(Series::new("".into(), vec![r as i64, 1, 2]))),
        )
        .into_series();
        (initial, multiply, add)
    }

    fn rows(series: &Series) -> Vec<Vec<Option<f64>>> {
        series
            .list()
            .unwrap()
            .into_iter()
            .map(|row| row.unwrap().f64().unwrap().into_iter().collect())
            .collect()
    }

    #[test]
    fn a_slice_answers_what_the_whole_column_answers_for_those_rows() -> PolarsResult<()> {
        for nulls in [false, true] {
            let (initial, multiply, add) = six_policies(nulls);
            let whole = accumulate(&[initial.clone(), multiply.clone(), add.clone()])?;
            let part = accumulate(&[initial.slice(1, 3), multiply.slice(1, 3), add.slice(1, 3)])?;
            assert_eq!(rows(&part), rows(&whole.slice(1, 3)), "nulls={nulls}");
        }
        Ok(())
    }
}
