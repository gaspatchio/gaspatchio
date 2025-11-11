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
        let base = ListChunked::from_iter([
            Some(Series::new("".into(), vec![Some(1.0), None, Some(3.0)])),
        ]);

        // Exponent: [[2.0, 2.0, 2.0]]
        let exp = ListChunked::from_iter([
            Some(Series::new("".into(), vec![2.0, 2.0, 2.0])),
        ]);

        // Expected: [[1.0, null, 9.0]]
        let result = list_pow(&[base.into_series(), exp.into_series()]).unwrap();
        let result_list = result.list().unwrap();

        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert_eq!(first_f64.get(0), Some(1.0));
        assert_eq!(first_f64.get(1), None);
        assert_eq!(first_f64.get(2), Some(9.0));
    }
}

/// Element-wise power operation on list columns
///
/// Supports:
/// - list ** list (pairwise, same lengths)
/// - list ** scalar (broadcast scalar to each element)
///
/// Always promotes to Float64 output.
///
/// # Arguments
/// * `inputs[0]` - Base values (List column)
/// * `inputs[1]` - Exponent values (List column or scalar)
///
/// # Returns
/// List column with element-wise power results
///
/// # Errors
/// Returns error if:
/// - Base is not a List type
/// - Inner list lengths don't match (for list ** list)
pub fn list_pow(inputs: &[Series]) -> PolarsResult<Series> {
    let lhs = &inputs[0];
    let rhs = &inputs[1];

    // Ensure lhs is a List
    let lhs_list = lhs.list().map_err(|_| {
        PolarsError::ComputeError("lhs must be List dtype for list_pow".into())
    })?;

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
