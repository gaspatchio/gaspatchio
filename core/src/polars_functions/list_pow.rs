// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Element-wise power operation for list columns (list ** list and list ** scalar)
// ABOUTME: Eliminates EXPLODE/GROUP_BY pattern for discount factor calculations

use polars::prelude::*;

use super::ieee_quotient::{broadcast_binary, numbers_only};
use super::slices::{rows_per_policy, same_periods};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_list_pow_empty_portfolio_keeps_float_element_type() -> PolarsResult<()> {
        let dtype = DataType::List(Box::new(DataType::Float64));
        let base = Series::new_empty("base".into(), &dtype);
        let exponents = [
            Series::new_empty("periods".into(), &dtype),
            Series::new("power".into(), [-1.0]),
            Series::new_empty("power".into(), &DataType::Float64),
        ];
        for exponent in exponents {
            let result = list_pow(&[base.clone(), exponent])?;
            assert!(result.is_empty());
            assert_eq!(result.dtype(), &dtype);
        }
        Ok(())
    }

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
    fn test_list_pow_null_outer_list_answers_null() -> PolarsResult<()> {
        // Spec 11.1.25: a null outer list yields a null result list, on
        // either side of list ** list, and for a list base raised to a
        // per-row scalar -- not an empty run, which claims zero periods.
        let base = ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.0, 2.0])),
            None,
            Some(Series::new("".into(), vec![3.0])),
        ]);
        let exp = ListChunked::from_iter([
            Some(Series::new("".into(), vec![2.0, 2.0])),
            Some(Series::new("".into(), vec![2.0, 2.0])),
            None,
        ]);
        let pairwise = list_pow(&[base.clone().into_series(), exp.into_series()])?;
        let pairwise = pairwise.list()?;
        assert_eq!(
            pairwise.dtype(),
            &DataType::List(Box::new(DataType::Float64))
        );
        assert!(pairwise.get_as_series(0).is_some());
        assert!(pairwise.get_as_series(1).is_none());
        assert!(pairwise.get_as_series(2).is_none());

        // The exponent is not read for a null base, null or not.
        let scalar_exp = Series::new("".into(), vec![Some(2.0), None, Some(2.0)]);
        let by_scalar = list_pow(&[base.into_series(), scalar_exp])?;
        let by_scalar = by_scalar.list()?;
        assert!(by_scalar.get_as_series(1).is_none());
        assert_eq!(
            by_scalar.get_as_series(2).map(|s| s.f64().unwrap().get(0)),
            Some(Some(9.0))
        );
        Ok(())
    }

    #[test]
    fn test_list_pow_all_null_lists_keep_the_float_list_type() -> PolarsResult<()> {
        let base = ListChunked::from_iter([None::<Series>, None]);
        let exp = Series::new("".into(), vec![2.0, 2.0]);
        let result = list_pow(&[base.into_series(), exp])?;
        assert_eq!(result.dtype(), &DataType::List(Box::new(DataType::Float64)));
        assert_eq!(result.null_count(), 2);
        Ok(())
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
    fn test_list_pow_scalar_base_list_exponent_is_exact() -> PolarsResult<()> {
        // exp(14 * ln 10) is 100000000000000.12; powf is 1e14.
        let base = Series::new("b".into(), vec![10.0_f64, 2.0]);
        let exponents = ListChunked::from_iter([
            Some(Series::new("".into(), vec![14.0, 13.0])),
            Some(Series::new("".into(), vec![0.5])),
        ])
        .into_series();
        let out = list_pow(&[base, exponents])?;
        assert_eq!(out.dtype(), &DataType::List(Box::new(DataType::Float64)));
        let rows: Vec<Vec<Option<f64>>> = out
            .list()?
            .into_iter()
            .map(|row| row.unwrap().f64().unwrap().into_iter().collect())
            .collect();
        assert_eq!(
            rows,
            vec![vec![Some(1e14), Some(1e13)], vec![Some(2.0_f64.powf(0.5))]]
        );
        Ok(())
    }

    #[test]
    fn test_list_pow_literal_base_broadcasts_over_exponent_rows() -> PolarsResult<()> {
        let base = Series::new("b".into(), vec![10_i32]);
        let exponents = ListChunked::from_iter([
            Some(Series::new("".into(), vec![2.0])),
            None,
            Some(Series::new("".into(), vec![Some(3.0), None])),
        ])
        .into_series();
        let out = list_pow(&[base, exponents])?;
        let list = out.list()?;
        assert_eq!(list.len(), 3);
        assert!(list.get_as_series(1).is_none());
        let third: Vec<Option<f64>> = list
            .get_as_series(2)
            .unwrap()
            .f64()
            .unwrap()
            .into_iter()
            .collect();
        assert_eq!(third, vec![Some(1000.0), None]);
        Ok(())
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
/// - Float64 ** list (a per-row base raised to each period's exponent;
///   returns `List<Float64>`)
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
    // Each operand cut to the rows of the slice it arrived as, and a one-row
    // list repeated for every policy, as the streaming engine reads it.
    let operands = rows_per_policy(inputs, false)?;
    let [lhs, rhs] = operands.as_slice() else {
        return Err(polars_err!(
            ComputeError: "list_pow takes two operands, got {}", operands.len()
        ));
    };
    // Text cast to Float64 is nulls, and every path below casts: refuse it
    // first, by name, rather than answer a run of nulls.
    numbers_only(lhs, "list_pow")?;
    numbers_only(rhs, "list_pow")?;

    // Per-row base, per-period exponent: `10 ** af.t`, a discount factor
    // `(1 + r) ** -t`. One powf per element, as for a list base; the identity
    // exp(t * ln b) this replaced rounded twice (10 ** 14 read
    // 100000000000000.12).
    if !matches!(lhs.dtype(), DataType::List(_)) && matches!(rhs.dtype(), DataType::List(_)) {
        return broadcast_binary(lhs, rhs, "list_pow", f64::powf);
    }

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

    // An empty iterator cannot infer its inner type. Keep the advertised
    // List<Float64> output on a zero-policy frame, without another element pass.
    if lhs_list.is_empty() {
        return Ok(Series::new_empty(
            lhs.name().clone(),
            &DataType::List(Box::new(DataType::Float64)),
        ));
    }

    // Case A: RHS is also a List (pairwise operation)
    if matches!(rhs.dtype(), DataType::List(_)) {
        let rhs_list = rhs.list()?;

        // Zip inner lists and compute element-wise pow. A policy whose base or
        // exponent list is null has no periods to raise: its answer is null
        // (spec 11.1.25), never an empty run, which would claim a policy with
        // zero periods.
        let result = lhs_list
            .amortized_iter()
            .zip(rhs_list.amortized_iter())
            .map(|(lhs_inner, rhs_inner)| match (lhs_inner, rhs_inner) {
                (Some(bases), Some(exponents)) => {
                    pow_row(bases.as_ref(), exponents.as_ref()).map(Some)
                }
                _ => Ok(None),
            })
            .collect::<PolarsResult<ListChunked>>()?;

        return as_float_lists(result);
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
            // A null base list answers null (spec 11.1.25), and is answered
            // before the exponent is read: there is nothing to raise.
            let Some(inner_series) = inner_series_opt else {
                return Ok(None);
            };

            let s = inner_series.as_ref().cast(&DataType::Float64)?;
            let ca = s.f64()?;

            // Get the scalar exponent for this row
            // If broadcasting, use index 0, otherwise use the row index
            let lookup_idx = if is_broadcast { 0 } else { idx };
            // A null exponent is a null operand in each of the policy's
            // periods, and "a null element on either side yields null at that
            // position" (graph-artifact spec 11.1.25). It used to refuse the
            // run.
            let Some(rhs_scalar) = rhs_ca.get(lookup_idx) else {
                return Ok(Some(
                    Float64Chunked::full_null("".into(), ca.len()).into_series(),
                ));
            };

            let out: Vec<Option<f64>> = ca
                .iter()
                .map(|opt_val| opt_val.map(|val| val.powf(rhs_scalar)))
                .collect();

            Ok(Some(Float64Chunked::from_iter(out).into_series()))
        })
        .collect::<PolarsResult<ListChunked>>()?;

    as_float_lists(result)
}

/// Return a collected result as the `List<Float64>` this kernel advertises.
///
/// A chunk whose every row is a null list gives the collector nothing to
/// infer an inner type from, so the type is stated rather than inferred.
/// A result already of that type is returned as it is.
pub(crate) fn as_float_lists(result: ListChunked) -> PolarsResult<Series> {
    let target = DataType::List(Box::new(DataType::Float64));
    let series = result.into_series();
    if series.dtype() == &target {
        return Ok(series);
    }
    series.cast(&target)
}

/// Raise one row of bases to one row of exponents, element by element.
///
/// Both rows are promoted to Float64 and must be the same length. A null on
/// either side of an element leaves that element null.
fn pow_row(bases: &Series, exponents: &Series) -> PolarsResult<Series> {
    let bases = bases.cast(&DataType::Float64)?;
    let exponents = exponents.cast(&DataType::Float64)?;
    let bases = bases.f64()?;
    let exponents = exponents.f64()?;

    same_periods("base", bases.len(), "exponent", exponents.len())?;

    let raised: Vec<Option<f64>> = bases
        .iter()
        .zip(exponents.iter())
        .map(|(base, exponent)| Some(base?.powf(exponent?)))
        .collect();

    Ok(Float64Chunked::from_iter(raised).into_series())
}

#[cfg(test)]
mod refusal_tests {
    use super::*;

    #[test]
    fn a_short_exponent_list_is_refused_by_both_lengths_and_no_row() {
        let bases = ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.0, 2.0])),
            Some(Series::new("".into(), vec![1.0, 2.0, 3.0])),
        ]);
        let exponents = ListChunked::from_iter([
            Some(Series::new("".into(), vec![2.0, 2.0])),
            Some(Series::new("".into(), vec![2.0, 2.0])),
        ]);
        let err = list_pow(&[bases.into_series(), exponents.into_series()])
            .unwrap_err()
            .to_string();
        assert!(
            err.contains("mismatched inner list lengths in one policy: exponent against base"),
            "{err}"
        );
        assert!(err.contains("base=3, exponent=2 in that policy."), "{err}");
        assert!(!err.contains("at row"), "{err}");
    }

    #[test]
    fn a_text_operand_is_refused_by_name_not_answered_with_nulls() {
        // The base answered [[None, None]] for two of these and refused the
        // third only because the text cast to a null exponent.
        let bases =
            ListChunked::from_iter([Some(Series::new("".into(), vec![1.0, 2.0]))]).into_series();
        let codes =
            ListChunked::from_iter([Some(Series::new("".into(), vec!["A", "B"]))]).into_series();
        let code = Series::new("".into(), vec!["A"]);
        let two = Series::new("".into(), vec![2.0_f64]);
        for (inputs, holds) in [
            ([bases.clone(), code], "this column holds str"),
            ([bases, codes.clone()], "these lists hold str"),
            ([codes, two], "these lists hold str"),
        ] {
            let err = list_pow(&inputs).unwrap_err().to_string();
            assert!(err.contains("list_pow works on numbers"), "{err}");
            assert!(err.contains(holds), "{err}");
        }
    }

    #[test]
    fn a_null_exponent_is_null_in_each_of_its_policys_periods() -> PolarsResult<()> {
        // Spec 11.1.25: a null element on either side yields null at that
        // position. The base refused: "rhs scalar at row 1 is null".
        let bases = ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.0, 2.0])),
            Some(Series::new("".into(), vec![1.0, 2.0, 3.0])),
            None,
        ]);
        let exponents = Series::new("".into(), vec![Some(2.0), None, None]);
        let out = list_pow(&[bases.into_series(), exponents])?;
        assert_eq!(out.dtype(), &DataType::List(Box::new(DataType::Float64)));
        let rows: Vec<Option<Vec<Option<f64>>>> = out
            .list()?
            .into_iter()
            .map(|row| row.map(|s| s.f64().unwrap().into_iter().collect()))
            .collect();
        assert_eq!(
            rows,
            vec![
                Some(vec![Some(1.0), Some(4.0)]),
                Some(vec![None, None, None]),
                None,
            ]
        );
        Ok(())
    }
}

#[cfg(test)]
mod slice_tests {
    use super::*;

    #[test]
    fn a_slice_raises_as_the_whole_column_raises_those_rows() -> PolarsResult<()> {
        let rows: Vec<Series> = (0..4_i64)
            .map(|r| Series::new("".into(), vec![r, r + 1]))
            .collect();
        let exponents = Series::new("t".into(), rows);
        let bases = Series::new("b".into(), vec![2.0_f64, 3.0, 4.0, 5.0]);
        let all = list_pow(&[bases.clone(), exponents.clone()])?;
        let part = list_pow(&[bases.slice(1, 2), exponents.slice(1, 2)])?;
        assert!(part.equals_missing(&all.slice(1, 2)));
        assert_eq!(part.list()?.get_inner().len(), 4);
        let as_bases = list_pow(&[
            exponents.slice(1, 2),
            Series::new("e".into(), vec![2.0_f64]),
        ])?;
        assert!(as_bases.equals_missing(
            &list_pow(&[exponents, Series::new("e".into(), vec![2.0_f64])])?.slice(1, 2)
        ));
        Ok(())
    }
}
