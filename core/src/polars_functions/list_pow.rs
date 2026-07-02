// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Element-wise power operation for list columns (list ** list and list ** scalar)
// ABOUTME: Eliminates EXPLODE/GROUP_BY pattern for discount factor calculations

use polars::prelude::*;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_list_pow_list_list() {
        // Create test data: [[1.0, 2.0, 3.0], [4.0, 5.0]]
        let base = ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.0, 2.0, 3.0])),
            Some(Series::new("".into(), vec![4.0, 5.0])),
        ]);

        // Exponents: [[2.0, 2.0, 2.0], [2.0, 2.0]]
        let exp = ListChunked::from_iter([
            Some(Series::new("".into(), vec![2.0, 2.0, 2.0])),
            Some(Series::new("".into(), vec![2.0, 2.0])),
        ]);

        // Expected: [[1.0, 4.0, 9.0], [16.0, 25.0]]
        let result = list_pow(&[base.into_series(), exp.into_series()]).unwrap();
        let result_list = result.list().unwrap();

        // Verify first list: [1.0, 4.0, 9.0]
        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert_eq!(first_f64.get(0), Some(1.0));
        assert_eq!(first_f64.get(1), Some(4.0));
        assert_eq!(first_f64.get(2), Some(9.0));

        // Verify second list: [16.0, 25.0]
        let second = result_list.get_as_series(1).unwrap();
        let second_f64 = second.f64().unwrap();
        assert_eq!(second_f64.get(0), Some(16.0));
        assert_eq!(second_f64.get(1), Some(25.0));
    }

    #[test]
    fn test_list_pow_list_scalar() {
        // Create base: [[2.0, 3.0], [4.0, 5.0]]
        let base = ListChunked::from_iter([
            Some(Series::new("".into(), vec![2.0, 3.0])),
            Some(Series::new("".into(), vec![4.0, 5.0])),
        ]);

        // Scalar exponent: [2.0, 3.0]
        let exp = Series::new("exp".into(), vec![2.0, 3.0]);

        // Expected: [[4.0, 9.0], [64.0, 125.0]]
        let result = list_pow(&[base.into_series(), exp]).unwrap();
        let result_list = result.list().unwrap();

        // Verify first list: [4.0, 9.0]
        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert_eq!(first_f64.get(0), Some(4.0));
        assert_eq!(first_f64.get(1), Some(9.0));

        // Verify second list: [64.0, 125.0]
        let second = result_list.get_as_series(1).unwrap();
        let second_f64 = second.f64().unwrap();
        assert_eq!(second_f64.get(0), Some(64.0));
        assert_eq!(second_f64.get(1), Some(125.0));
    }

    #[test]
    fn test_list_pow_with_nulls() {
        // Base with null: [[1.0, null, 3.0]]
        let base = ListChunked::from_iter([Some(Series::new(
            "".into(),
            vec![Some(1.0), None, Some(3.0)],
        ))]);

        // Exponent: [[2.0, 2.0, 2.0]]
        let exp = ListChunked::from_iter([Some(Series::new("".into(), vec![2.0, 2.0, 2.0]))]);

        // Expected: [[1.0, null, 9.0]]
        let result = list_pow(&[base.into_series(), exp.into_series()]).unwrap();
        let result_list = result.list().unwrap();

        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert_eq!(first_f64.get(0), Some(1.0));
        assert_eq!(first_f64.get(1), None);
        assert_eq!(first_f64.get(2), Some(9.0));
    }

    #[test]
    fn test_list_pow_scalar_base() {
        // Scalar-column (Float64) base, Float64 exponent → Float64 output.
        // [2.0^2.0, 3.0^3.0] = [4.0, 27.0]
        let base = Series::new("".into(), vec![2.0_f64, 3.0]);
        let exp = Series::new("".into(), vec![2.0_f64, 3.0]);

        let result = list_pow(&[base, exp]).unwrap();

        // Output must be a flat Float64 series, not a List.
        assert_eq!(
            result.dtype(),
            &DataType::Float64,
            "scalar base → Float64 out"
        );

        let v = result.f64().unwrap();
        assert_eq!(v.get(0), Some(4.0));
        assert_eq!(v.get(1), Some(27.0));
    }

    #[test]
    fn test_list_pow_scalar_base_length_mismatch_errors() {
        let base = Series::new("".into(), vec![2.0, 3.0, 4.0]);
        let exp = Series::new("".into(), vec![2.0, 3.0]);
        assert!(list_pow(&[base, exp]).is_err());
    }

    #[test]
    fn test_list_pow_scalar_base_broadcast_exp() {
        // length-1 exponent broadcasts across the base
        let base = Series::new("".into(), vec![2.0, 3.0, 4.0]);
        let exp = Series::new("".into(), vec![2.0]);
        let out = list_pow(&[base, exp]).unwrap();
        let v = out.f64().unwrap();
        assert_eq!(v.get(0), Some(4.0));
        assert_eq!(v.get(2), Some(16.0));
    }
}

/// Element-wise power operation on list or scalar columns
///
/// Supports:
/// - list ** list (pairwise, same inner lengths)
/// - list ** scalar (broadcast scalar exponent to each element)
/// - Float64 ** Float64 (element-wise; returns a flat `Float64` series, not a `List`)
///
/// For the Float64-base case a length-1 operand on either side broadcasts across
/// the other; a true length mismatch (neither is length 1) returns an error.
///
/// Always promotes to Float64 output.
///
/// # Arguments
/// * `inputs[0]` - Base values (List column or Float64 scalar column)
/// * `inputs[1]` - Exponent values (List column, scalar column, or expression)
///
/// # Returns
/// - `Float64` series when the base is a Float64 scalar column
/// - `List<Float64>` series when the base is a List column
///
/// # Errors
/// Returns error if:
/// - Base is a Float64 scalar column and lengths differ (neither is length 1)
/// - Inner list lengths don't match (for list ** list)
pub fn list_pow(inputs: &[Series]) -> PolarsResult<Series> {
    let lhs = &inputs[0];
    let rhs = &inputs[1];

    // Scalar-column (Float64) base: element-wise pow, Float64 output. Used by the
    // Curve discount_factor scalar-column Expr path; mirrors the list-base semantics.
    if !matches!(lhs.dtype(), DataType::List(_)) {
        let l = lhs.cast(&DataType::Float64)?;
        let r = rhs.cast(&DataType::Float64)?;
        let l_ca = l.f64()?;
        let r_ca = r.f64()?;
        let l_broadcast = l_ca.len() == 1;
        let r_broadcast = r_ca.len() == 1;
        if !l_broadcast && !r_broadcast && l_ca.len() != r_ca.len() {
            return Err(polars_err!(
                ComputeError: "list_pow: base and exponent lengths differ ({} vs {})",
                l_ca.len(), r_ca.len()
            ));
        }
        let n = l_ca.len().max(r_ca.len());
        let out: Float64Chunked = (0..n)
            .map(|i| {
                let b = if l_broadcast {
                    l_ca.get(0)
                } else {
                    l_ca.get(i)
                };
                let e = if r_broadcast {
                    r_ca.get(0)
                } else {
                    r_ca.get(i)
                };
                match (b, e) {
                    (Some(b), Some(e)) => Some(b.powf(e)),
                    _ => None,
                }
            })
            .collect();
        return Ok(out.into_series());
    }

    // Ensure lhs is a List
    let lhs_list = lhs
        .list()
        .map_err(|_| PolarsError::ComputeError("lhs must be List dtype for list_pow".into()))?;

    // Case A: RHS is also a List (pairwise operation)
    if matches!(rhs.dtype(), DataType::List(_)) {
        let rhs_list = rhs.list()?;

        // Zip inner lists and compute element-wise pow
        let result = lhs_list
            .amortized_iter()
            .zip(rhs_list.amortized_iter())
            .map(|(lhs_inner, rhs_inner)| {
                match (lhs_inner, rhs_inner) {
                    (Some(lhs_series), Some(rhs_series)) => {
                        // Cast inner values to Float64
                        let l = lhs_series.as_ref().cast(&DataType::Float64)?;
                        let r = rhs_series.as_ref().cast(&DataType::Float64)?;

                        let l_ca = l.f64().unwrap();
                        let r_ca = r.f64().unwrap();

                        // Verify same length
                        if l_ca.len() != r_ca.len() {
                            return Err(PolarsError::ComputeError(
                                "mismatched inner list lengths for list_pow".into(),
                            ));
                        }

                        // Compute v[i] = l[i].powf(r[i])
                        let out: Vec<Option<f64>> = l_ca
                            .iter()
                            .zip(r_ca.iter())
                            .map(|(a, b)| match (a, b) {
                                (Some(base), Some(exp)) => Some(base.powf(exp)),
                                _ => None,
                            })
                            .collect();

                        Ok(Some(Float64Chunked::from_iter(out).into_series()))
                    }
                    _ => Ok(Some(Series::new_empty("".into(), &DataType::Float64))),
                }
            })
            .collect::<PolarsResult<ListChunked>>()?;

        return Ok(result.into_series());
    }

    // Case B: RHS is a scalar (broadcast to each element in each list)
    // Cast RHS to Float64 and extract values per row
    let rhs_f64 = rhs.cast(&DataType::Float64)?;
    let rhs_ca = rhs_f64.f64()?;

    // Check if rhs is a single scalar value that needs broadcasting
    let is_broadcast = rhs_ca.len() == 1;

    // Apply scalar power to each inner list
    let result = lhs_list
        .amortized_iter()
        .enumerate()
        .map(|(idx, inner_series_opt)| {
            // Get the scalar exponent for this row
            // If broadcasting, use index 0, otherwise use the row index
            let lookup_idx = if is_broadcast { 0 } else { idx };
            let rhs_scalar = rhs_ca.get(lookup_idx).ok_or_else(|| {
                PolarsError::ComputeError(format!("rhs scalar at row {} is null", idx).into())
            })?;

            match inner_series_opt {
                Some(inner_series) => {
                    let s = inner_series.as_ref().cast(&DataType::Float64).unwrap();
                    let ca = s.f64().unwrap();

                    let out: Vec<Option<f64>> = ca
                        .iter()
                        .map(|opt_val| opt_val.map(|val| val.powf(rhs_scalar)))
                        .collect();

                    Ok(Some(Float64Chunked::from_iter(out).into_series()))
                }
                None => Ok(Some(Series::new_empty("".into(), &DataType::Float64))),
            }
        })
        .collect::<PolarsResult<ListChunked>>()?;

    Ok(result.into_series())
}
