// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Element-wise clip operation for list columns (list.clip(lower, upper) with column bounds)
// ABOUTME: Eliminates EXPLODE/GROUP_BY pattern for clipping list elements with per-row bounds

use polars::prelude::*;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_list_clip_with_scalar_columns() {
        // Create test data: [[0.5, 1.5, 2.5, 3.5], [0.0, 5.0, 10.0]]
        let values = ListChunked::from_iter([
            Some(Series::new("".into(), vec![0.5, 1.5, 2.5, 3.5])),
            Some(Series::new("".into(), vec![0.0, 5.0, 10.0])),
        ]);

        // Lower bounds per row: [1.0, 2.0]
        let lower = Series::new("lower".into(), vec![1.0, 2.0]);

        // Upper bounds per row: [3.0, 8.0]
        let upper = Series::new("upper".into(), vec![3.0, 8.0]);

        // Expected: [[1.0, 1.5, 2.5, 3.0], [2.0, 5.0, 8.0]]
        let result = list_clip(&[values.into_series(), lower, upper]).unwrap();
        let result_list = result.list().unwrap();

        // Verify first list: [1.0, 1.5, 2.5, 3.0]
        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert_eq!(first_f64.get(0), Some(1.0));
        assert_eq!(first_f64.get(1), Some(1.5));
        assert_eq!(first_f64.get(2), Some(2.5));
        assert_eq!(first_f64.get(3), Some(3.0));

        // Verify second list: [2.0, 5.0, 8.0]
        let second = result_list.get_as_series(1).unwrap();
        let second_f64 = second.f64().unwrap();
        assert_eq!(second_f64.get(0), Some(2.0));
        assert_eq!(second_f64.get(1), Some(5.0));
        assert_eq!(second_f64.get(2), Some(8.0));
    }

    #[test]
    fn test_list_clip_with_list_bounds() {
        // Create test data: [[1.0, 2.0, 3.0], [4.0, 5.0]]
        let values = ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.0, 2.0, 3.0])),
            Some(Series::new("".into(), vec![4.0, 5.0])),
        ]);

        // Lower bounds as lists: [[0.5, 1.5, 2.5], [3.5, 4.5]]
        let lower = ListChunked::from_iter([
            Some(Series::new("".into(), vec![0.5, 1.5, 2.5])),
            Some(Series::new("".into(), vec![3.5, 4.5])),
        ]);

        // Upper bounds as lists: [[1.5, 2.5, 3.5], [4.5, 5.5]]
        let upper = ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.5, 2.5, 3.5])),
            Some(Series::new("".into(), vec![4.5, 5.5])),
        ]);

        // Expected: [[1.0, 2.0, 3.0], [4.0, 5.0]] (all values within bounds)
        let result = list_clip(&[
            values.into_series(),
            lower.into_series(),
            upper.into_series(),
        ])
        .unwrap();
        let result_list = result.list().unwrap();

        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert_eq!(first_f64.get(0), Some(1.0));
        assert_eq!(first_f64.get(1), Some(2.0));
        assert_eq!(first_f64.get(2), Some(3.0));
    }

    #[test]
    fn test_list_clip_with_nulls() {
        // Values with null: [[1.0, null, 3.0]]
        let values = ListChunked::from_iter([Some(Series::new(
            "".into(),
            vec![Some(1.0), None, Some(3.0)],
        ))]);

        let lower = Series::new("lower".into(), vec![0.0]);
        let upper = Series::new("upper".into(), vec![2.0]);

        // Expected: [[1.0, null, 2.0]]
        let result = list_clip(&[values.into_series(), lower, upper]).unwrap();
        let result_list = result.list().unwrap();

        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert_eq!(first_f64.get(0), Some(1.0));
        assert_eq!(first_f64.get(1), None);
        assert_eq!(first_f64.get(2), Some(2.0));
    }
}

/// Element-wise clip operation on list columns
///
/// Clips each element in the list column to be within [lower, upper] bounds.
/// Supports per-row scalar bounds or list bounds for element-wise clipping.
///
/// # Arguments
/// * `inputs[0]` - Values to clip (List column)
/// * `inputs[1]` - Lower bound (List column or scalar column)
/// * `inputs[2]` - Upper bound (List column or scalar column)
///
/// # Returns
/// List column with clipped values as List<Float64>
///
/// # Errors
/// Returns error if:
/// - Values is not a List type
/// - Inner list lengths don't match bounds (for list bounds)
pub fn list_clip(inputs: &[Series]) -> PolarsResult<Series> {
    let values = &inputs[0];
    let lower = &inputs[1];
    let upper = &inputs[2];

    // Ensure values is a List
    let values_list = values
        .list()
        .map_err(|_| PolarsError::ComputeError("values must be List dtype for list_clip".into()))?;

    // Determine if bounds are lists or scalars
    let lower_is_list = matches!(lower.dtype(), DataType::List(_));
    let upper_is_list = matches!(upper.dtype(), DataType::List(_));

    // Handle different combinations of bound types
    match (lower_is_list, upper_is_list) {
        (true, true) => clip_list_list_list(values_list, lower, upper),
        (true, false) => clip_list_list_scalar(values_list, lower, upper),
        (false, true) => clip_list_scalar_list(values_list, lower, upper),
        (false, false) => clip_list_scalar_scalar(values_list, lower, upper),
    }
}

/// Clip with both bounds as list columns
fn clip_list_list_list(
    values_list: &ListChunked,
    lower: &Series,
    upper: &Series,
) -> PolarsResult<Series> {
    let lower_list = lower.list()?;
    let upper_list = upper.list()?;

    let result = values_list
        .amortized_iter()
        .zip(lower_list.amortized_iter())
        .zip(upper_list.amortized_iter())
        .map(|((val_opt, lower_opt), upper_opt)| {
            match (val_opt, lower_opt, upper_opt) {
                (Some(val_series), Some(lower_series), Some(upper_series)) => {
                    let v = val_series.as_ref().cast(&DataType::Float64)?;
                    let l = lower_series.as_ref().cast(&DataType::Float64)?;
                    let u = upper_series.as_ref().cast(&DataType::Float64)?;

                    let v_ca = v.f64().unwrap();
                    let l_ca = l.f64().unwrap();
                    let u_ca = u.f64().unwrap();

                    // Verify same lengths
                    if v_ca.len() != l_ca.len() || v_ca.len() != u_ca.len() {
                        return Err(PolarsError::ComputeError(
                            "mismatched inner list lengths for list_clip".into(),
                        ));
                    }

                    let out: Vec<Option<f64>> = v_ca
                        .iter()
                        .zip(l_ca.iter())
                        .zip(u_ca.iter())
                        .map(|((v, l), u)| match (v, l, u) {
                            (Some(val), Some(lo), Some(hi)) => Some(val.max(lo).min(hi)),
                            _ => None,
                        })
                        .collect();

                    Ok(Some(Float64Chunked::from_iter(out).into_series()))
                }
                _ => Ok(Some(Series::new_empty("".into(), &DataType::Float64))),
            }
        })
        .collect::<PolarsResult<ListChunked>>()?;

    Ok(result.into_series())
}

/// Clip with lower as list, upper as scalar
fn clip_list_list_scalar(
    values_list: &ListChunked,
    lower: &Series,
    upper: &Series,
) -> PolarsResult<Series> {
    let lower_list = lower.list()?;
    let upper_f64 = upper.cast(&DataType::Float64)?;
    let upper_ca = upper_f64.f64()?;
    let upper_is_broadcast = upper_ca.len() == 1;

    let result = values_list
        .amortized_iter()
        .zip(lower_list.amortized_iter())
        .enumerate()
        .map(|(idx, (val_opt, lower_opt))| {
            let upper_idx = if upper_is_broadcast { 0 } else { idx };
            let upper_val = upper_ca.get(upper_idx).ok_or_else(|| {
                PolarsError::ComputeError(format!("upper bound at row {} is null", idx).into())
            })?;

            match (val_opt, lower_opt) {
                (Some(val_series), Some(lower_series)) => {
                    let v = val_series.as_ref().cast(&DataType::Float64)?;
                    let l = lower_series.as_ref().cast(&DataType::Float64)?;

                    let v_ca = v.f64().unwrap();
                    let l_ca = l.f64().unwrap();

                    if v_ca.len() != l_ca.len() {
                        return Err(PolarsError::ComputeError(
                            "mismatched inner list lengths for list_clip".into(),
                        ));
                    }

                    let out: Vec<Option<f64>> = v_ca
                        .iter()
                        .zip(l_ca.iter())
                        .map(|(v, l)| match (v, l) {
                            (Some(val), Some(lo)) => Some(val.max(lo).min(upper_val)),
                            _ => None,
                        })
                        .collect();

                    Ok(Some(Float64Chunked::from_iter(out).into_series()))
                }
                _ => Ok(Some(Series::new_empty("".into(), &DataType::Float64))),
            }
        })
        .collect::<PolarsResult<ListChunked>>()?;

    Ok(result.into_series())
}

/// Clip with lower as scalar, upper as list
fn clip_list_scalar_list(
    values_list: &ListChunked,
    lower: &Series,
    upper: &Series,
) -> PolarsResult<Series> {
    let lower_f64 = lower.cast(&DataType::Float64)?;
    let lower_ca = lower_f64.f64()?;
    let lower_is_broadcast = lower_ca.len() == 1;
    let upper_list = upper.list()?;

    let result = values_list
        .amortized_iter()
        .zip(upper_list.amortized_iter())
        .enumerate()
        .map(|(idx, (val_opt, upper_opt))| {
            let lower_idx = if lower_is_broadcast { 0 } else { idx };
            let lower_val = lower_ca.get(lower_idx).ok_or_else(|| {
                PolarsError::ComputeError(format!("lower bound at row {} is null", idx).into())
            })?;

            match (val_opt, upper_opt) {
                (Some(val_series), Some(upper_series)) => {
                    let v = val_series.as_ref().cast(&DataType::Float64)?;
                    let u = upper_series.as_ref().cast(&DataType::Float64)?;

                    let v_ca = v.f64().unwrap();
                    let u_ca = u.f64().unwrap();

                    if v_ca.len() != u_ca.len() {
                        return Err(PolarsError::ComputeError(
                            "mismatched inner list lengths for list_clip".into(),
                        ));
                    }

                    let out: Vec<Option<f64>> = v_ca
                        .iter()
                        .zip(u_ca.iter())
                        .map(|(v, u)| match (v, u) {
                            (Some(val), Some(hi)) => Some(val.max(lower_val).min(hi)),
                            _ => None,
                        })
                        .collect();

                    Ok(Some(Float64Chunked::from_iter(out).into_series()))
                }
                _ => Ok(Some(Series::new_empty("".into(), &DataType::Float64))),
            }
        })
        .collect::<PolarsResult<ListChunked>>()?;

    Ok(result.into_series())
}

/// Clip with both bounds as scalar columns (most common case)
fn clip_list_scalar_scalar(
    values_list: &ListChunked,
    lower: &Series,
    upper: &Series,
) -> PolarsResult<Series> {
    let lower_f64 = lower.cast(&DataType::Float64)?;
    let upper_f64 = upper.cast(&DataType::Float64)?;
    let lower_ca = lower_f64.f64()?;
    let upper_ca = upper_f64.f64()?;

    let lower_is_broadcast = lower_ca.len() == 1;
    let upper_is_broadcast = upper_ca.len() == 1;

    let result = values_list
        .amortized_iter()
        .enumerate()
        .map(|(idx, val_opt)| {
            let lower_idx = if lower_is_broadcast { 0 } else { idx };
            let upper_idx = if upper_is_broadcast { 0 } else { idx };

            let lower_val = lower_ca.get(lower_idx).ok_or_else(|| {
                PolarsError::ComputeError(format!("lower bound at row {} is null", idx).into())
            })?;
            let upper_val = upper_ca.get(upper_idx).ok_or_else(|| {
                PolarsError::ComputeError(format!("upper bound at row {} is null", idx).into())
            })?;

            match val_opt {
                Some(val_series) => {
                    let v = val_series.as_ref().cast(&DataType::Float64)?;
                    let v_ca = v.f64().unwrap();

                    let out: Vec<Option<f64>> = v_ca
                        .iter()
                        .map(|v| v.map(|val| val.max(lower_val).min(upper_val)))
                        .collect();

                    Ok(Some(Float64Chunked::from_iter(out).into_series()))
                }
                None => Ok(Some(Series::new_empty("".into(), &DataType::Float64))),
            }
        })
        .collect::<PolarsResult<ListChunked>>()?;

    Ok(result.into_series())
}
