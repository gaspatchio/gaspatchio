// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

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
        let left = ListChunked::from_iter([Some(Series::new("".into(), vec![0, 1, 2, 3]))]);

        // policy_term: [2] (scalar)
        let right = Series::new("right".into(), vec![2]);

        // then_val: [[100.0, 100.0, 100.0, 100.0]]
        let then_val = ListChunked::from_iter([Some(Series::new(
            "".into(),
            vec![100.0, 100.0, 100.0, 100.0],
        ))]);

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
        let left = ListChunked::from_iter([Some(Series::new("".into(), vec![1.0, 2.0, 3.0]))]);

        let right = ListChunked::from_iter([Some(Series::new("".into(), vec![2.0, 2.0, 2.0]))]);

        let then_val =
            ListChunked::from_iter([Some(Series::new("".into(), vec![10.0, 10.0, 10.0]))]);

        let otherwise_val =
            ListChunked::from_iter([Some(Series::new("".into(), vec![0.0, 0.0, 0.0]))]);

        // Test each operator
        let test_cases = vec![
            ("eq", vec![0.0, 10.0, 0.0]),   // [1==2, 2==2, 3==2]
            ("ne", vec![10.0, 0.0, 10.0]),  // [1!=2, 2!=2, 3!=2]
            ("lt", vec![10.0, 0.0, 0.0]),   // [1<2, 2<2, 3<2]
            ("lte", vec![10.0, 10.0, 0.0]), // [1<=2, 2<=2, 3<=2]
            ("gt", vec![0.0, 0.0, 10.0]),   // [1>2, 2>2, 3>2]
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
pub fn list_conditional(inputs: &[Series], kwargs: &ConditionalKwargs) -> PolarsResult<Series> {
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

    // String-valued branches take the dedicated Utf8 path (GSP-110). The
    // condition side (left/right) stays numeric in both paths; only the
    // selected VALUES differ in dtype. Mixed string/numeric branches have no
    // single output dtype — refuse loudly rather than coerce either side.
    let then_is_string = is_string_like(then_val);
    let otherwise_is_string = is_string_like(otherwise_val);
    if then_is_string || otherwise_is_string {
        if !(then_is_string && otherwise_is_string) {
            return Err(PolarsError::ComputeError(
                format!(
                    "list_conditional: mixed branch dtypes — then is {}, otherwise is {}. \
                     A conditional column has one dtype, so both branches must be \
                     string-valued or both numeric. Map the numeric branch to a string \
                     label (or encode the string branch numerically).",
                    then_val.dtype(),
                    otherwise_val.dtype()
                )
                .into(),
            ));
        }
        return list_conditional_str(left_list, right, then_val, otherwise_val, &kwargs.operator);
    }

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
                            PolarsError::ComputeError(
                                format!("then_val at row {} is null", idx).into(),
                            )
                        })?;
                        let otherwise_scalar =
                            otherwise_ca.get(otherwise_lookup_idx).ok_or_else(|| {
                                PolarsError::ComputeError(
                                    format!("otherwise_val at row {} is null", idx).into(),
                                )
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
                            PolarsError::ComputeError(
                                format!("right at row {} is null", idx).into(),
                            )
                        })?;
                        let otherwise_scalar =
                            otherwise_ca.get(otherwise_lookup_idx).ok_or_else(|| {
                                PolarsError::ComputeError(
                                    format!("otherwise_val at row {} is null", idx).into(),
                                )
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
                    PolarsError::ComputeError(
                        format!("otherwise_val at row {} is null", idx).into(),
                    )
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
            .map(
                |(((left_inner, right_inner), then_inner), otherwise_inner)| match (
                    left_inner,
                    right_inner,
                    then_inner,
                    otherwise_inner,
                ) {
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
                },
            )
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
                    PolarsError::ComputeError(
                        format!("otherwise_val at row {} is null", idx).into(),
                    )
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

    // Case 5: Right scalar, then list, otherwise list
    // e.g., when(af.duration_yr <= 5).then(af.qx_select).otherwise(af.qx_ultimate)
    // This is the most common missing case from real models.
    if !right_is_list && then_is_list && otherwise_is_list {
        let right_f64 = right.cast(&DataType::Float64)?;
        let right_ca = right_f64.f64()?;
        let right_is_broadcast = right_ca.len() == 1;

        let then_list = then_val.list()?;
        let otherwise_list = otherwise_val.list()?;

        let result = left_list
            .amortized_iter()
            .zip(then_list.amortized_iter())
            .zip(otherwise_list.amortized_iter())
            .enumerate()
            .map(|(idx, ((left_inner, then_inner), otherwise_inner))| {
                let right_lookup_idx = if right_is_broadcast { 0 } else { idx };
                let right_scalar = right_ca.get(right_lookup_idx).ok_or_else(|| {
                    PolarsError::ComputeError(format!("right at row {} is null", idx).into())
                })?;

                match (left_inner, then_inner, otherwise_inner) {
                    (Some(l_series), Some(t_series), Some(o_series)) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let t = t_series.as_ref().cast(&DataType::Float64)?;
                        let o = o_series.as_ref().cast(&DataType::Float64)?;

                        let l_ca = l.f64().unwrap();
                        let t_ca = t.f64().unwrap();
                        let o_ca = o.f64().unwrap();

                        if l_ca.len() != t_ca.len() || l_ca.len() != o_ca.len() {
                            return Err(PolarsError::ComputeError(
                                format!(
                                    "mismatched inner list lengths at row {}: left={}, then={}, otherwise={}",
                                    idx, l_ca.len(), t_ca.len(), o_ca.len()
                                ).into(),
                            ));
                        }

                        let out: Vec<Option<f64>> = l_ca
                            .iter()
                            .zip(t_ca.iter())
                            .zip(o_ca.iter())
                            .map(|((l, t), o)| match (l, t, o) {
                                (Some(lv), Some(tv), Some(ov)) => {
                                    if compare(lv, right_scalar, &kwargs.operator) {
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

    // Case 6: Right scalar, then scalar, otherwise list
    if !right_is_list && !then_is_list && otherwise_is_list {
        let right_f64 = right.cast(&DataType::Float64)?;
        let then_f64 = then_val.cast(&DataType::Float64)?;
        let right_ca = right_f64.f64()?;
        let then_ca = then_f64.f64()?;
        let right_is_broadcast = right_ca.len() == 1;
        let then_is_broadcast = then_ca.len() == 1;

        let otherwise_list = otherwise_val.list()?;

        let result = left_list
            .amortized_iter()
            .zip(otherwise_list.amortized_iter())
            .enumerate()
            .map(|(idx, (left_inner, otherwise_inner))| {
                let right_lookup_idx = if right_is_broadcast { 0 } else { idx };
                let then_lookup_idx = if then_is_broadcast { 0 } else { idx };
                let right_scalar = right_ca.get(right_lookup_idx).ok_or_else(|| {
                    PolarsError::ComputeError(format!("right at row {} is null", idx).into())
                })?;
                let then_scalar = then_ca.get(then_lookup_idx).ok_or_else(|| {
                    PolarsError::ComputeError(format!("then_val at row {} is null", idx).into())
                })?;

                match (left_inner, otherwise_inner) {
                    (Some(l_series), Some(o_series)) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let o = o_series.as_ref().cast(&DataType::Float64)?;
                        let l_ca = l.f64().unwrap();
                        let o_ca = o.f64().unwrap();

                        if l_ca.len() != o_ca.len() {
                            return Err(PolarsError::ComputeError(
                                format!(
                                    "mismatched inner list lengths at row {}: left={}, otherwise={}",
                                    idx, l_ca.len(), o_ca.len()
                                ).into(),
                            ));
                        }

                        let out: Vec<Option<f64>> = l_ca
                            .iter()
                            .zip(o_ca.iter())
                            .map(|(l, o)| match (l, o) {
                                (Some(lv), Some(ov)) => {
                                    if compare(lv, right_scalar, &kwargs.operator) {
                                        Some(then_scalar)
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

    // Case 7: Right list, then scalar, otherwise list
    if right_is_list && !then_is_list && otherwise_is_list {
        let right_list = right.list()?;
        let then_f64 = then_val.cast(&DataType::Float64)?;
        let then_ca = then_f64.f64()?;
        let then_is_broadcast = then_ca.len() == 1;

        let otherwise_list = otherwise_val.list()?;

        let result = left_list
            .amortized_iter()
            .zip(right_list.amortized_iter())
            .zip(otherwise_list.amortized_iter())
            .enumerate()
            .map(|(idx, ((left_inner, right_inner), otherwise_inner))| {
                let then_lookup_idx = if then_is_broadcast { 0 } else { idx };
                let then_scalar = then_ca.get(then_lookup_idx).ok_or_else(|| {
                    PolarsError::ComputeError(format!("then_val at row {} is null", idx).into())
                })?;

                match (left_inner, right_inner, otherwise_inner) {
                    (Some(l_series), Some(r_series), Some(o_series)) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let r = r_series.as_ref().cast(&DataType::Float64)?;
                        let o = o_series.as_ref().cast(&DataType::Float64)?;

                        let l_ca = l.f64().unwrap();
                        let r_ca = r.f64().unwrap();
                        let o_ca = o.f64().unwrap();

                        if l_ca.len() != r_ca.len() || l_ca.len() != o_ca.len() {
                            return Err(PolarsError::ComputeError(
                                format!(
                                    "mismatched inner list lengths at row {}: left={}, right={}, otherwise={}",
                                    idx, l_ca.len(), r_ca.len(), o_ca.len()
                                ).into(),
                            ));
                        }

                        let out: Vec<Option<f64>> = l_ca
                            .iter()
                            .zip(r_ca.iter())
                            .zip(o_ca.iter())
                            .map(|((l, r), o)| match (l, r, o) {
                                (Some(lv), Some(rv), Some(ov)) => {
                                    if compare(lv, rv, &kwargs.operator) {
                                        Some(then_scalar)
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

    Err(PolarsError::ComputeError(
        format!(
            "Unsupported combination of list/scalar inputs: right_is_list={}, then_is_list={}, otherwise_is_list={}",
            right_is_list, then_is_list, otherwise_is_list
        ).into(),
    ))
}

/// Returns true when the series' value dtype (inner dtype for lists) is
/// string-like: `String`, `Categorical`, or `Enum`.
fn is_string_like(s: &Series) -> bool {
    let dt = match s.dtype() {
        DataType::List(inner) => inner.as_ref(),
        dt => dt,
    };
    matches!(
        dt,
        DataType::String | DataType::Categorical(_, _) | DataType::Enum(_, _)
    )
}

/// A string-valued then/otherwise branch, normalised to `String` storage.
///
/// `Scalar` covers literal broadcasts (length 1) and per-row scalar columns;
/// `PerElement` covers `List(String)` branches selected element-wise.
enum StrBranch {
    Scalar { ca: StringChunked, broadcast: bool },
    PerElement { list: ListChunked },
}

impl StrBranch {
    fn from_series(s: &Series) -> PolarsResult<Self> {
        match s.dtype() {
            DataType::List(_) => {
                let cast = s.cast(&DataType::List(Box::new(DataType::String)))?;
                Ok(Self::PerElement {
                    list: cast.list()?.clone(),
                })
            }
            _ => {
                let cast = s.cast(&DataType::String)?;
                let ca = cast.str()?.clone();
                let broadcast = ca.len() == 1;
                Ok(Self::Scalar { ca, broadcast })
            }
        }
    }

    /// The branch's values for one row: a scalar (repeated per element) or
    /// this row's own inner list, length-checked against the condition.
    fn row(&self, idx: usize, expect_len: usize, what: &str) -> PolarsResult<RowStr> {
        match self {
            Self::Scalar { ca, broadcast } => {
                let lookup = if *broadcast { 0 } else { idx };
                Ok(RowStr::Scalar(ca.get(lookup).map(str::to_string)))
            }
            Self::PerElement { list } => match list.get_as_series(idx) {
                Some(inner) => {
                    if inner.len() != expect_len {
                        return Err(PolarsError::ComputeError(
                            format!(
                                "mismatched inner list lengths at row {}: condition={}, {}={}",
                                idx,
                                expect_len,
                                what,
                                inner.len()
                            )
                            .into(),
                        ));
                    }
                    Ok(RowStr::List(inner.str()?.clone()))
                }
                None => Ok(RowStr::Scalar(None)),
            },
        }
    }
}

/// One row's view of a string branch.
enum RowStr {
    Scalar(Option<String>),
    List(StringChunked),
}

impl RowStr {
    fn get(&self, t: usize) -> Option<&str> {
        match self {
            Self::Scalar(v) => v.as_deref(),
            Self::List(ca) => ca.get(t),
        }
    }
}

/// String-valued `list_conditional`: same comparison semantics as the
/// numeric path (condition operands cast to Float64, element-wise compare),
/// but the selected values are strings and the output is `List(String)`.
///
/// Null semantics: a null condition element yields a null output element
/// (matching the numeric path); a null in the SELECTED branch propagates as
/// a null element — a null label is a visible value, unlike the numeric
/// path's hard error on null scalars, which exists to keep NaN-free
/// arithmetic guarantees that have no string analogue.
fn list_conditional_str(
    left_list: &ListChunked,
    right: &Series,
    then_val: &Series,
    otherwise_val: &Series,
    operator: &str,
) -> PolarsResult<Series> {
    fn compare(left: f64, right: f64, op: &str) -> PolarsResult<bool> {
        Ok(match op {
            "eq" => left == right,
            "ne" => left != right,
            "lt" => left < right,
            "lte" => left <= right,
            "gt" => left > right,
            "gte" => left >= right,
            _ => {
                return Err(PolarsError::ComputeError(
                    format!("Unknown operator: {}", op).into(),
                ))
            }
        })
    }

    let right_is_list = matches!(right.dtype(), DataType::List(_));
    let right_scalar_ca = if right_is_list {
        None
    } else {
        Some(right.cast(&DataType::Float64)?.f64()?.clone())
    };
    let right_list = if right_is_list {
        Some(right.list()?.clone())
    } else {
        None
    };

    let then_branch = StrBranch::from_series(then_val)?;
    let otherwise_branch = StrBranch::from_series(otherwise_val)?;

    let mut out_rows: Vec<Option<Series>> = Vec::with_capacity(left_list.len());
    for idx in 0..left_list.len() {
        let Some(l_series) = left_list.get_as_series(idx) else {
            out_rows.push(None);
            continue;
        };
        let l = l_series.cast(&DataType::Float64)?;
        let l_ca = l.f64()?;
        let n = l_ca.len();

        // This row's right-hand condition values.
        let r_row: Option<Float64Chunked> = match (&right_list, &right_scalar_ca) {
            (Some(rl), _) => match rl.get_as_series(idx) {
                Some(r_inner) => {
                    if r_inner.len() != n {
                        return Err(PolarsError::ComputeError(
                            format!(
                                "mismatched inner list lengths at row {}: left={}, right={}",
                                idx,
                                n,
                                r_inner.len()
                            )
                            .into(),
                        ));
                    }
                    Some(r_inner.cast(&DataType::Float64)?.f64()?.clone())
                }
                None => None,
            },
            (None, Some(rs)) => {
                let lookup = if rs.len() == 1 { 0 } else { idx };
                rs.get(lookup)
                    .map(|v| Float64Chunked::from_iter(std::iter::repeat_n(Some(v), n)))
            }
            (None, None) => unreachable!("right is either list or scalar"),
        };
        let Some(r_ca) = r_row else {
            // Null right side: no comparison possible for this row.
            out_rows.push(None);
            continue;
        };

        let then_row = then_branch.row(idx, n, "then")?;
        let otherwise_row = otherwise_branch.row(idx, n, "otherwise")?;

        let mut builder = StringChunkedBuilder::new("".into(), n);
        for t in 0..n {
            match (l_ca.get(t), r_ca.get(t)) {
                (Some(lv), Some(rv)) => {
                    let selected = if compare(lv, rv, operator)? {
                        then_row.get(t)
                    } else {
                        otherwise_row.get(t)
                    };
                    match selected {
                        Some(v) => builder.append_value(v),
                        None => builder.append_null(),
                    }
                }
                _ => builder.append_null(),
            }
        }
        out_rows.push(Some(builder.finish().into_series()));
    }

    Ok(ListChunked::from_iter(out_rows).into_series())
}
