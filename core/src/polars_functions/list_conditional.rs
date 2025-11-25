// ABOUTME: Element-wise conditional (when/then/otherwise) for list columns with comparison
// ABOUTME: Eliminates EXPLODE/GROUP_BY pattern for conditional operations

use polars::prelude::*;
use serde::Deserialize;

#[derive(Deserialize)]
pub struct ConditionalKwargs {
    pub operator: String, // "eq", "lt", "gt", "lte", "gte", "ne"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_list_conditional_eq_list_list() {
        // Create test data: month == policy_term_months
        // month: [[0, 1, 2], [0, 1]]
        let left = ListChunked::from_iter([
            Some(Series::new("".into(), vec![0, 1, 2])),
            Some(Series::new("".into(), vec![0, 1])),
        ]);

        // policy_term_months: [[2, 2, 2], [1, 1]]
        let right = ListChunked::from_iter([
            Some(Series::new("".into(), vec![2, 2, 2])),
            Some(Series::new("".into(), vec![1, 1])),
        ]);

        // then_val: [[100.0, 100.0, 100.0], [200.0, 200.0]]
        let then_val = ListChunked::from_iter([
            Some(Series::new("".into(), vec![100.0, 100.0, 100.0])),
            Some(Series::new("".into(), vec![200.0, 200.0])),
        ]);

        // otherwise_val: scalar 0.0
        let otherwise_val = Series::new("otherwise".into(), vec![0.0, 0.0]);

        let kwargs = ConditionalKwargs {
            operator: "eq".to_string(),
        };

        // Expected: [[0.0, 0.0, 100.0], [0.0, 200.0]]
        let result = list_conditional(
            &[
                left.into_series(),
                right.into_series(),
                then_val.into_series(),
                otherwise_val,
            ],
            &kwargs,
        )
        .unwrap();

        let result_list = result.list().unwrap();

        // Verify first list: [0.0, 0.0, 100.0]
        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert_eq!(first_f64.get(0), Some(0.0));
        assert_eq!(first_f64.get(1), Some(0.0));
        assert_eq!(first_f64.get(2), Some(100.0));

        // Verify second list: [0.0, 200.0]
        let second = result_list.get_as_series(1).unwrap();
        let second_f64 = second.f64().unwrap();
        assert_eq!(second_f64.get(0), Some(0.0));
        assert_eq!(second_f64.get(1), Some(200.0));
    }

    #[test]
    fn test_list_conditional_lt_list_scalar() {
        // month < policy_term (scalar per row)
        // month: [[0, 1, 2, 3]]
        let left = ListChunked::from_iter([
            Some(Series::new("".into(), vec![0, 1, 2, 3])),
        ]);

        // policy_term: [2] (scalar)
        let right = Series::new("right".into(), vec![2]);

        // then_val: [[100.0, 100.0, 100.0, 100.0]]
        let then_val = ListChunked::from_iter([
            Some(Series::new("".into(), vec![100.0, 100.0, 100.0, 100.0])),
        ]);

        // otherwise_val: scalar 0.0
        let otherwise_val = Series::new("otherwise".into(), vec![0.0]);

        let kwargs = ConditionalKwargs {
            operator: "lt".to_string(),
        };

        // Expected: [[100.0, 100.0, 0.0, 0.0]] (0<2, 1<2, 2<2 is false, 3<2 is false)
        let result = list_conditional(
            &[
                left.into_series(),
                right,
                then_val.into_series(),
                otherwise_val,
            ],
            &kwargs,
        )
        .unwrap();

        let result_list = result.list().unwrap();
        let first = result_list.get_as_series(0).unwrap();
        let first_f64 = first.f64().unwrap();
        assert_eq!(first_f64.get(0), Some(100.0)); // 0 < 2 = true
        assert_eq!(first_f64.get(1), Some(100.0)); // 1 < 2 = true
        assert_eq!(first_f64.get(2), Some(0.0)); // 2 < 2 = false
        assert_eq!(first_f64.get(3), Some(0.0)); // 3 < 2 = false
    }

    #[test]
    fn test_list_conditional_all_operators() {
        // Test all 6 operators
        let left = ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.0, 2.0, 3.0])),
        ]);

        let right = ListChunked::from_iter([
            Some(Series::new("".into(), vec![2.0, 2.0, 2.0])),
        ]);

        let then_val = ListChunked::from_iter([
            Some(Series::new("".into(), vec![10.0, 10.0, 10.0])),
        ]);

        let otherwise_val = ListChunked::from_iter([
            Some(Series::new("".into(), vec![0.0, 0.0, 0.0])),
        ]);

        // Test each operator
        let test_cases = vec![
            ("eq", vec![0.0, 10.0, 0.0]), // [1==2, 2==2, 3==2]
            ("ne", vec![10.0, 0.0, 10.0]), // [1!=2, 2!=2, 3!=2]
            ("lt", vec![10.0, 0.0, 0.0]),  // [1<2, 2<2, 3<2]
            ("lte", vec![10.0, 10.0, 0.0]), // [1<=2, 2<=2, 3<=2]
            ("gt", vec![0.0, 0.0, 10.0]),  // [1>2, 2>2, 3>2]
            ("gte", vec![0.0, 10.0, 10.0]), // [1>=2, 2>=2, 3>=2]
        ];

        for (op, expected) in test_cases {
            let kwargs = ConditionalKwargs {
                operator: op.to_string(),
            };

            let result = list_conditional(
                &[
                    left.clone().into_series(),
                    right.clone().into_series(),
                    then_val.clone().into_series(),
                    otherwise_val.clone().into_series(),
                ],
                &kwargs,
            )
            .unwrap();

            let result_list = result.list().unwrap();
            let first = result_list.get_as_series(0).unwrap();
            let first_f64 = first.f64().unwrap();

            for (i, exp_val) in expected.iter().enumerate() {
                assert_eq!(
                    first_f64.get(i),
                    Some(*exp_val),
                    "Operator {} failed at index {}",
                    op,
                    i
                );
            }
        }
    }
}

/// Element-wise conditional (when/then/otherwise) with comparison
///
/// Supports:
/// - list op list (pairwise comparison)
/// - list op scalar (broadcast scalar)
///
/// # Arguments
/// * `inputs[0]` - Left values for comparison (List column)
/// * `inputs[1]` - Right values for comparison (List or scalar)
/// * `inputs[2]` - Then values (List or scalar - returned when condition is true)
/// * `inputs[3]` - Otherwise values (List or scalar - returned when condition is false)
/// * `kwargs.operator` - Comparison operator: "eq", "ne", "lt", "lte", "gt", "gte"
///
/// # Returns
/// List column with conditional results
///
/// # Errors
/// Returns error if:
/// - Left is not a List type
/// - Inner list lengths don't match
/// - Unknown operator
pub fn list_conditional(
    inputs: &[Series],
    kwargs: &ConditionalKwargs,
) -> PolarsResult<Series> {
    let left = &inputs[0];
    let right = &inputs[1];
    let then_val = &inputs[2];
    let otherwise_val = &inputs[3];

    let left_list = left.list().map_err(|_| {
        PolarsError::ComputeError("left must be List dtype for list_conditional".into())
    })?;

    // Helper function for comparison
    fn compare(left: f64, right: f64, op: &str) -> bool {
        match op {
            "eq" => left == right,
            "ne" => left != right,
            "lt" => left < right,
            "lte" => left <= right,
            "gt" => left > right,
            "gte" => left >= right,
            _ => panic!("Unknown operator: {}", op),
        }
    }

    // Determine if right, then_val, otherwise_val are lists or scalars
    let right_is_list = matches!(right.dtype(), DataType::List(_));
    let then_is_list = matches!(then_val.dtype(), DataType::List(_));
    let otherwise_is_list = matches!(otherwise_val.dtype(), DataType::List(_));

    // Case 1: Right is list, then/otherwise are scalars (most common: test 1)
    if right_is_list && !then_is_list && !otherwise_is_list {
        let right_list = right.list()?;
        let then_f64 = then_val.cast(&DataType::Float64)?;
        let otherwise_f64 = otherwise_val.cast(&DataType::Float64)?;

        let then_ca = then_f64.f64()?;
        let otherwise_ca = otherwise_f64.f64()?;

        // Check if broadcasting is needed
        let then_is_broadcast = then_ca.len() == 1;
        let otherwise_is_broadcast = otherwise_ca.len() == 1;

        let result = left_list
            .amortized_iter()
            .zip(right_list.amortized_iter())
            .enumerate()
            .map(|(idx, (left_inner, right_inner))| {
                match (left_inner, right_inner) {
                    (Some(l_series), Some(r_series)) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let r = r_series.as_ref().cast(&DataType::Float64)?;

                        let l_ca = l.f64().unwrap();
                        let r_ca = r.f64().unwrap();

                        if l_ca.len() != r_ca.len() {
                            return Err(PolarsError::ComputeError(
                                "mismatched inner list lengths".into(),
                            ));
                        }

                        // Get scalar values for this row
                        let then_lookup_idx = if then_is_broadcast { 0 } else { idx };
                        let otherwise_lookup_idx = if otherwise_is_broadcast { 0 } else { idx };

                        let then_scalar = then_ca.get(then_lookup_idx).ok_or_else(|| {
                            PolarsError::ComputeError(format!("then_val at row {} is null", idx).into())
                        })?;
                        let otherwise_scalar = otherwise_ca.get(otherwise_lookup_idx).ok_or_else(|| {
                            PolarsError::ComputeError(format!("otherwise_val at row {} is null", idx).into())
                        })?;

                        let out: Vec<Option<f64>> = l_ca
                            .iter()
                            .zip(r_ca.iter())
                            .map(|(l, r)| match (l, r) {
                                (Some(lv), Some(rv)) => {
                                    if compare(lv, rv, &kwargs.operator) {
                                        Some(then_scalar)
                                    } else {
                                        Some(otherwise_scalar)
                                    }
                                }
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

    // Case 2: Right is scalar, then/otherwise are lists (test 2)
    if !right_is_list && then_is_list && !otherwise_is_list {
        let right_f64 = right.cast(&DataType::Float64)?;
        let then_list = then_val.list()?;
        let otherwise_f64 = otherwise_val.cast(&DataType::Float64)?;

        let right_ca = right_f64.f64()?;
        let otherwise_ca = otherwise_f64.f64()?;

        // Check if broadcasting is needed
        let right_is_broadcast = right_ca.len() == 1;
        let otherwise_is_broadcast = otherwise_ca.len() == 1;

        let result = left_list
            .amortized_iter()
            .zip(then_list.amortized_iter())
            .enumerate()
            .map(|(idx, (left_inner, then_inner))| {
                match (left_inner, then_inner) {
                    (Some(l_series), Some(t_series)) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let t = t_series.as_ref().cast(&DataType::Float64)?;

                        let l_ca = l.f64().unwrap();
                        let t_ca = t.f64().unwrap();

                        // Get scalar values for this row
                        let right_lookup_idx = if right_is_broadcast { 0 } else { idx };
                        let otherwise_lookup_idx = if otherwise_is_broadcast { 0 } else { idx };

                        let right_scalar = right_ca.get(right_lookup_idx).ok_or_else(|| {
                            PolarsError::ComputeError(format!("right at row {} is null", idx).into())
                        })?;
                        let otherwise_scalar = otherwise_ca.get(otherwise_lookup_idx).ok_or_else(|| {
                            PolarsError::ComputeError(format!("otherwise_val at row {} is null", idx).into())
                        })?;

                        let out: Vec<Option<f64>> = l_ca
                            .iter()
                            .zip(t_ca.iter())
                            .map(|(l, t)| match (l, t) {
                                (Some(lv), Some(tv)) => {
                                    if compare(lv, right_scalar, &kwargs.operator) {
                                        Some(tv)
                                    } else {
                                        Some(otherwise_scalar)
                                    }
                                }
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

    // Case 2b: Right is list, then is list, otherwise is scalar (test 1)
    if right_is_list && then_is_list && !otherwise_is_list {
        let right_list = right.list()?;
        let then_list = then_val.list()?;
        let otherwise_f64 = otherwise_val.cast(&DataType::Float64)?;

        // Extract otherwise scalar with broadcasting support
        let otherwise_ca = otherwise_f64.f64()?;
        let otherwise_is_broadcast = otherwise_ca.len() == 1;

        let result = left_list
            .amortized_iter()
            .zip(right_list.amortized_iter())
            .zip(then_list.amortized_iter())
            .enumerate()
            .map(|(idx, ((left_inner, right_inner), then_inner))| {
                // Get otherwise scalar for this row
                let otherwise_lookup_idx = if otherwise_is_broadcast { 0 } else { idx };
                let otherwise_scalar = otherwise_ca.get(otherwise_lookup_idx).ok_or_else(|| {
                    PolarsError::ComputeError(format!("otherwise_val at row {} is null", idx).into())
                })?;

                match (left_inner, right_inner, then_inner) {
                    (Some(l_series), Some(r_series), Some(t_series)) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let r = r_series.as_ref().cast(&DataType::Float64)?;
                        let t = t_series.as_ref().cast(&DataType::Float64)?;

                        let l_ca = l.f64().unwrap();
                        let r_ca = r.f64().unwrap();
                        let t_ca = t.f64().unwrap();

                        if l_ca.len() != r_ca.len() {
                            return Err(PolarsError::ComputeError(
                                "mismatched inner list lengths".into(),
                            ));
                        }

                        let out: Vec<Option<f64>> = l_ca
                            .iter()
                            .zip(r_ca.iter())
                            .zip(t_ca.iter())
                            .map(|((l, r), t)| match (l, r, t) {
                                (Some(lv), Some(rv), Some(tv)) => {
                                    if compare(lv, rv, &kwargs.operator) {
                                        Some(tv)
                                    } else {
                                        Some(otherwise_scalar)
                                    }
                                }
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

    // Case 3: All lists (test 3 - most operators test)
    if right_is_list && then_is_list && otherwise_is_list {
        let right_list = right.list()?;
        let then_list = then_val.list()?;
        let otherwise_list = otherwise_val.list()?;

        let result = left_list
            .amortized_iter()
            .zip(right_list.amortized_iter())
            .zip(then_list.amortized_iter())
            .zip(otherwise_list.amortized_iter())
            .map(|(((left_inner, right_inner), then_inner), otherwise_inner)| {
                match (left_inner, right_inner, then_inner, otherwise_inner) {
                    (Some(l_series), Some(r_series), Some(t_series), Some(o_series)) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let r = r_series.as_ref().cast(&DataType::Float64)?;
                        let t = t_series.as_ref().cast(&DataType::Float64)?;
                        let o = o_series.as_ref().cast(&DataType::Float64)?;

                        let l_ca = l.f64().unwrap();
                        let r_ca = r.f64().unwrap();
                        let t_ca = t.f64().unwrap();
                        let o_ca = o.f64().unwrap();

                        if l_ca.len() != r_ca.len() {
                            return Err(PolarsError::ComputeError(
                                "mismatched inner list lengths".into(),
                            ));
                        }

                        let out: Vec<Option<f64>> = l_ca
                            .iter()
                            .zip(r_ca.iter())
                            .zip(t_ca.iter())
                            .zip(o_ca.iter())
                            .map(|(((l, r), t), o)| match (l, r, t, o) {
                                (Some(lv), Some(rv), Some(tv), Some(ov)) => {
                                    if compare(lv, rv, &kwargs.operator) {
                                        Some(tv)
                                    } else {
                                        Some(ov)
                                    }
                                }
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

    // Case 4: Right scalar, then/otherwise scalar (simplest)
    if !right_is_list && !then_is_list && !otherwise_is_list {
        let right_f64 = right.cast(&DataType::Float64)?;
        let then_f64 = then_val.cast(&DataType::Float64)?;
        let otherwise_f64 = otherwise_val.cast(&DataType::Float64)?;

        // Extract all scalars with broadcasting support
        let right_ca = right_f64.f64()?;
        let then_ca = then_f64.f64()?;
        let otherwise_ca = otherwise_f64.f64()?;

        let right_is_broadcast = right_ca.len() == 1;
        let then_is_broadcast = then_ca.len() == 1;
        let otherwise_is_broadcast = otherwise_ca.len() == 1;

        let result = left_list
            .amortized_iter()
            .enumerate()
            .map(|(idx, left_inner)| {
                // Get scalar values for this row
                let right_lookup_idx = if right_is_broadcast { 0 } else { idx };
                let then_lookup_idx = if then_is_broadcast { 0 } else { idx };
                let otherwise_lookup_idx = if otherwise_is_broadcast { 0 } else { idx };

                let right_scalar = right_ca.get(right_lookup_idx).ok_or_else(|| {
                    PolarsError::ComputeError(format!("right at row {} is null", idx).into())
                })?;
                let then_scalar = then_ca.get(then_lookup_idx).ok_or_else(|| {
                    PolarsError::ComputeError(format!("then_val at row {} is null", idx).into())
                })?;
                let otherwise_scalar = otherwise_ca.get(otherwise_lookup_idx).ok_or_else(|| {
                    PolarsError::ComputeError(format!("otherwise_val at row {} is null", idx).into())
                })?;

                match left_inner {
                    Some(l_series) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let l_ca = l.f64().unwrap();

                        let out: Vec<Option<f64>> = l_ca
                            .iter()
                            .map(|l| match l {
                                Some(lv) => {
                                    if compare(lv, right_scalar, &kwargs.operator) {
                                        Some(then_scalar)
                                    } else {
                                        Some(otherwise_scalar)
                                    }
                                }
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

    Err(PolarsError::ComputeError(
        "Unsupported combination of list/scalar inputs".into(),
    ))
}
