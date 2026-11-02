// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Element-wise conditional (when/then/otherwise) for list columns with comparison
// ABOUTME: Eliminates EXPLODE/GROUP_BY pattern for conditional operations

use polars::prelude::*;
use serde::Deserialize;

use super::ieee_quotient::list_series;
use super::list_pow::as_float_lists;
use super::slices::{policy_height_error, rows_per_policy, same_periods};
use polars_arrow::array::{Array, PrimitiveArray, Utf8ViewArray};
use polars_arrow::bitmap::Bitmap;
use polars_arrow::offset::OffsetsBuffer;
use std::sync::Arc;

#[derive(Deserialize)]
pub struct ConditionalKwargs {
    pub operator: String, // "eq", "lt", "gt", "lte", "gte", "ne"
    /// Answer NaN in a period whose comparison has a NaN operand, whichever
    /// branch holds there (graph-artifact spec, section 11.1.28: a condition
    /// with no truth value selects neither branch, and a double answer is NaN
    /// there, a null in either branch included). Set only where the answer is
    /// a double; absent, the comparison of a NaN is false, as IEEE has it.
    #[serde(default)]
    pub unknown_is_nan: bool,
}

// Every list operand -- the right-hand side, the `then` branch, the
// `otherwise` branch -- must have as many periods as the left in each policy
// (graph-artifact spec, sections 11.1.18 and 11.1.28: list branches of
// different lengths are not padded or truncated). `same_periods` refuses
// with the operand and both lengths, and names no row: the row this kernel
// can count is its batch's, which under streaming is not the frame's.

/// The comparison a call asks for, read once per call rather than once per
/// period: the six operators, or one this kernel does not know.
#[derive(Clone, Copy)]
enum Comparison<'a> {
    Eq,
    Ne,
    Lt,
    Lte,
    Gt,
    Gte,
    /// Refused where a period is first compared, as it always was: a call
    /// that compares nothing -- every policy empty, or every operand null --
    /// answers rather than refuses.
    Unknown(&'a str),
}

impl<'a> Comparison<'a> {
    /// Read the operator a call names.
    fn of(op: &'a str) -> Self {
        match op {
            "eq" => Self::Eq,
            "ne" => Self::Ne,
            "lt" => Self::Lt,
            "lte" => Self::Lte,
            "gt" => Self::Gt,
            "gte" => Self::Gte,
            _ => Self::Unknown(op),
        }
    }

    /// Whether the comparison holds between two periods' values.
    #[inline]
    fn holds(self, left: f64, right: f64) -> bool {
        match self {
            Self::Eq => left == right,
            Self::Ne => left != right,
            Self::Lt => left < right,
            Self::Lte => left <= right,
            Self::Gt => left > right,
            Self::Gte => left >= right,
            Self::Unknown(op) => panic!("Unknown operator: {}", op),
        }
    }
}

/// The comparison a call asks for, and what it answers where an operand is
/// NaN: the branch IEEE's comparison picks, or -- with `unknown_is_nan` -- a
/// NaN, neither branch being selected (spec 11.1.28).
#[derive(Clone, Copy)]
struct Rule<'a> {
    comparison: Comparison<'a>,
    unknown_is_nan: bool,
}

impl<'a> Rule<'a> {
    /// Read the rule a call names.
    fn of(kwargs: &'a ConditionalKwargs) -> Self {
        Self {
            comparison: Comparison::of(&kwargs.operator),
            unknown_is_nan: kwargs.unknown_is_nan,
        }
    }

    /// Choose between two present periods' branches, or answer the NaN.
    #[inline]
    fn choose<V>(self, left: f64, right: f64, then: V, otherwise: V, nan: V) -> V {
        if self.unknown_is_nan && (left.is_nan() || right.is_nan()) {
            nan
        } else if self.comparison.holds(left, right) {
            then
        } else {
            otherwise
        }
    }
}

/// Decide one period: `then` where the comparison holds, `otherwise` where
/// it does not, and null where the comparison is null.
///
/// Every shape of the numeric kernel decides its periods here, a per-policy
/// value standing in for each of that policy's periods. A null left or
/// right period is a null comparison (graph-artifact spec, section
/// 11.1.26). A null branch is the branch's value where it is selected and
/// is never read where it is not: "a null selected branch stays null; a
/// null unselected branch does not replace the selected value" (11.1.28).
#[inline]
fn decide(
    left: Option<f64>,
    right: Option<f64>,
    then: Option<f64>,
    otherwise: Option<f64>,
    op: Rule<'_>,
) -> Option<f64> {
    match (left, right) {
        (Some(l), Some(r)) => op.choose(l, r, then, otherwise, Some(f64::NAN)),
        _ => None,
    }
}

/// Decide one policy's periods against one right-hand value.
///
/// The value is read once for the policy, not once per period: a null
/// value is a null comparison in each of the `periods` (spec 11.1.26),
/// answered without visiting them, and a present one is handed to `answer`
/// as a plain number.
#[inline]
fn against_value(
    right: Option<f64>,
    periods: usize,
    answer: impl FnOnce(f64) -> PolarsResult<Option<Series>>,
) -> PolarsResult<Option<Series>> {
    match right {
        Some(value) => answer(value),
        None => decided(std::iter::repeat_n(None, periods)),
    }
}

/// One policy's decided periods, as the list element the kernel answers.
#[inline]
fn decided(periods: impl Iterator<Item = Option<f64>>) -> PolarsResult<Option<Series>> {
    Ok(Some(Float64Chunked::from_iter(periods).into_series()))
}

/// A per-policy `then` or `otherwise` value for one policy -- one value
/// serves every policy -- or `None` where it is null, which is null in the
/// periods that select it (spec 11.1.28).
#[inline]
fn branch_value(values: &Float64Chunked, row: usize) -> Option<f64> {
    values.get(if values.len() == 1 { 0 } else { row })
}

/// One policy's periods of a per-period operand, as Float64 values.
///
/// A null row -- a null right-hand list, or a null branch list -- is a null
/// in every one of the left's `periods`: on the right a null operand is a
/// null comparison (graph-artifact spec, section 11.1.26), and as a branch a
/// null is null where it is selected and unread where it is not (11.1.28).
/// It is read as that many nulls rather than as an empty run.
fn periods_or_nulls(row: Option<&Series>, periods: usize) -> PolarsResult<Series> {
    match row {
        Some(values) => values.cast(&DataType::Float64),
        None => Ok(Series::full_null("".into(), periods, &DataType::Float64)),
    }
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
            unknown_is_nan: false,
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
            unknown_is_nan: false,
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
                unknown_is_nan: false,
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

    fn run(inputs: [Series; 4], operator: &str) -> PolarsResult<Series> {
        list_conditional(
            &inputs,
            &ConditionalKwargs {
                operator: operator.to_string(),
                unknown_is_nan: false,
            },
        )
    }

    fn row_f64(result: &Series, row: usize) -> Vec<Option<f64>> {
        let inner = result.list().unwrap().get_as_series(row).unwrap();
        inner.f64().unwrap().into_iter().collect()
    }

    fn run_unknown(inputs: [Series; 4], operator: &str) -> PolarsResult<Series> {
        list_conditional(
            &inputs,
            &ConditionalKwargs {
                operator: operator.to_string(),
                unknown_is_nan: true,
            },
        )
    }

    fn nan_at(values: &[Option<f64>], period: usize) -> bool {
        matches!(values[period], Some(v) if v.is_nan())
    }

    fn one_run(values: &[Option<f64>]) -> Series {
        ListChunked::from_iter([Some(Series::new("".into(), values))]).into_series()
    }

    /// Spec 11.1.28: where a comparison has a NaN operand it has no truth
    /// value and selects neither branch, so a double answer is NaN there --
    /// also where the branch IEEE's comparison would have picked holds a
    /// null, which the producer used to answer.
    #[test]
    fn test_a_nan_operand_answers_nan_whichever_branch_is_null() -> PolarsResult<()> {
        let rates = one_run(&[Some(0.5), Some(f64::NAN), Some(2.0)]);
        let one = Series::new("".into(), &[1.0f64]);
        let with_null = one_run(&[Some(7.5), None, Some(9.5)]);
        let scalar = Series::new("".into(), &[1.5f64]);
        for op in ["lt", "lte", "gt", "gte", "eq", "ne"] {
            for (then, otherwise) in [
                (scalar.clone(), with_null.clone()),
                (with_null.clone(), scalar.clone()),
            ] {
                let got = row_f64(
                    &run_unknown([rates.clone(), one.clone(), then, otherwise], op)?,
                    0,
                );
                assert!(nan_at(&got, 1), "{op}: {got:?}");
                assert!(!nan_at(&got, 0) && !nan_at(&got, 2), "{op}: {got:?}");
            }
        }
        Ok(())
    }

    /// Every shape answers it: both branches present (the fast path), a NaN
    /// per-policy right-hand value, a NaN per-period right-hand run.
    #[test]
    fn test_a_nan_operand_answers_nan_on_every_shape() -> PolarsResult<()> {
        let whole = one_run(&[Some(1.0), Some(5.0), Some(9.0)]);
        let ten = Series::new("".into(), &[10.0f64]);
        let twenty = Series::new("".into(), &[20.0f64]);
        let nan = Series::new("".into(), &[f64::NAN]);
        let rates = one_run(&[Some(0.5), Some(f64::NAN), Some(2.0)]);
        let one = Series::new("".into(), &[1.0f64]);

        let present = row_f64(
            &run_unknown([rates.clone(), one, ten.clone(), twenty.clone()], "lt")?,
            0,
        );
        assert_eq!(present[0], Some(10.0));
        assert!(nan_at(&present, 1));
        assert_eq!(present[2], Some(20.0));

        let against_nan = row_f64(
            &run_unknown([whole.clone(), nan, ten.clone(), twenty.clone()], "gt")?,
            0,
        );
        assert!((0..3).all(|t| nan_at(&against_nan, t)), "{against_nan:?}");

        let against_run = row_f64(&run_unknown([whole, rates, ten, twenty], "gt")?, 0);
        assert_eq!(against_run[0], Some(10.0));
        assert!(nan_at(&against_run, 1));
        assert_eq!(against_run[2], Some(10.0));
        Ok(())
    }

    /// A null operand is still a null comparison with the flag set (11.1.26:
    /// a null wins over a NaN beside it).
    #[test]
    fn test_a_null_operand_stays_null_beside_the_flag() -> PolarsResult<()> {
        let rates = one_run(&[None, Some(f64::NAN)]);
        let got = row_f64(
            &run_unknown(
                [
                    rates,
                    Series::new("".into(), &[1.0f64]),
                    Series::new("".into(), &[10.0f64]),
                    Series::new("".into(), &[20.0f64]),
                ],
                "lt",
            )?,
            0,
        );
        assert_eq!(got[0], None);
        assert!(nan_at(&got, 1));
        Ok(())
    }

    /// Without the flag a comparison of a NaN is false, as IEEE has it, and
    /// the call reads as it always did; a call that names no flag has none.
    #[test]
    fn test_without_the_flag_a_nan_comparison_is_false() -> PolarsResult<()> {
        let rates = one_run(&[Some(0.5), Some(f64::NAN), Some(2.0)]);
        let branches = [
            Series::new("".into(), &[1.0f64]),
            Series::new("".into(), &[10.0f64]),
            Series::new("".into(), &[20.0f64]),
        ];
        let [one, ten, twenty] = branches;
        let lt = run(
            [rates.clone(), one.clone(), ten.clone(), twenty.clone()],
            "lt",
        )?;
        assert_eq!(row_f64(&lt, 0), vec![Some(10.0), Some(20.0), Some(20.0)]);
        let ne = run([rates, one, ten, twenty], "ne")?;
        assert_eq!(row_f64(&ne, 0), vec![Some(10.0), Some(10.0), Some(10.0)]);
        let named: ConditionalKwargs = serde_json::from_str(r#"{"operator": "lt"}"#)
            .map_err(|e| PolarsError::ComputeError(e.to_string().into()))?;
        assert!(!named.unknown_is_nan);
        Ok(())
    }

    /// A per-period text column compared with a text value used to fail as
    /// "right at row 0 is null": the condition was cast to Float64.
    #[test]
    fn test_text_list_compared_with_a_text_value() -> PolarsResult<()> {
        let plan = ListChunked::from_iter([
            Some(Series::new("".into(), &["A", "A", "A"])),
            Some(Series::new("".into(), &["B", "B"])),
        ])
        .into_series();
        let value = Series::new("".into(), &["A"]);
        let one = Series::new("".into(), &[1.0f64]);
        let zero = Series::new("".into(), &[0.0f64]);

        let eq = run(
            [plan.clone(), value.clone(), one.clone(), zero.clone()],
            "eq",
        )?;
        assert_eq!(row_f64(&eq, 0), vec![Some(1.0); 3]);
        assert_eq!(row_f64(&eq, 1), vec![Some(0.0); 2]);

        let ne = run([plan, value, one, zero], "ne")?;
        assert_eq!(row_f64(&ne, 0), vec![Some(0.0); 3]);
        assert_eq!(row_f64(&ne, 1), vec![Some(1.0); 2]);
        Ok(())
    }

    #[test]
    fn test_text_list_compared_per_policy_and_per_period() -> PolarsResult<()> {
        let plan =
            ListChunked::from_iter([Some(Series::new("".into(), &["A", "B"]))]).into_series();
        let per_policy = Series::new("".into(), &["B"]);
        let per_period =
            ListChunked::from_iter([Some(Series::new("".into(), &["A", "A"]))]).into_series();
        let benefit =
            ListChunked::from_iter([Some(Series::new("".into(), &[10.0, 20.0]))]).into_series();
        let zero = Series::new("".into(), &[0.0f64]);

        let by_policy = run(
            [plan.clone(), per_policy, benefit.clone(), zero.clone()],
            "eq",
        )?;
        assert_eq!(row_f64(&by_policy, 0), vec![Some(0.0), Some(20.0)]);

        let by_period = run([plan, per_period, benefit, zero], "eq")?;
        assert_eq!(row_f64(&by_period, 0), vec![Some(10.0), Some(0.0)]);
        Ok(())
    }

    #[test]
    fn test_text_orderings_are_lexicographic() -> PolarsResult<()> {
        let plan =
            ListChunked::from_iter([Some(Series::new("".into(), &["A", "B", "C"]))]).into_series();
        let value = Series::new("".into(), &["B"]);
        let one = Series::new("".into(), &[1.0f64]);
        let zero = Series::new("".into(), &[0.0f64]);
        for (op, expected) in [
            ("lt", [1.0, 0.0, 0.0]),
            ("lte", [1.0, 1.0, 0.0]),
            ("gt", [0.0, 0.0, 1.0]),
            ("gte", [0.0, 1.0, 1.0]),
        ] {
            let out = run([plan.clone(), value.clone(), one.clone(), zero.clone()], op)?;
            let want: Vec<Option<f64>> = expected.iter().copied().map(Some).collect();
            assert_eq!(row_f64(&out, 0), want, "{op}");
        }
        Ok(())
    }

    #[test]
    fn test_categorical_text_list_compares_by_its_labels() -> PolarsResult<()> {
        let plan = ListChunked::from_iter([Some(Series::new("".into(), &["UP", "BASE"]))])
            .into_series()
            .cast(&DataType::List(Box::new(DataType::from_categories(
                Categories::global(),
            ))))?;
        let value = Series::new("".into(), &["BASE"]);
        let one = Series::new("".into(), &[1.0f64]);
        let zero = Series::new("".into(), &[0.0f64]);

        let out = run([plan, value, one, zero], "eq")?;
        assert_eq!(row_f64(&out, 0), vec![Some(0.0), Some(1.0)]);
        Ok(())
    }

    #[test]
    fn test_text_condition_selects_text_branches() -> PolarsResult<()> {
        let plan =
            ListChunked::from_iter([Some(Series::new("".into(), &["A", "B"]))]).into_series();
        let value = Series::new("".into(), &["A"]);
        let then_val = Series::new("".into(), &["death benefit"]);
        let otherwise_val = Series::new("".into(), &["none"]);

        let out = run([plan, value, then_val, otherwise_val], "eq")?;
        let inner = out.list()?.get_as_series(0).unwrap();
        let labels: Vec<Option<&str>> = inner.str()?.into_iter().collect();
        assert_eq!(labels, vec![Some("death benefit"), Some("none")]);
        Ok(())
    }

    #[test]
    fn test_a_null_text_element_yields_a_null_indicator() -> PolarsResult<()> {
        let plan =
            ListChunked::from_iter([Some(Series::new("".into(), &[Some("A"), None::<&str>]))])
                .into_series();
        let value = Series::new("".into(), &["A"]);
        let one = Series::new("".into(), &[1.0f64]);
        let zero = Series::new("".into(), &[0.0f64]);

        let out = run([plan, value, one, zero], "eq")?;
        assert_eq!(row_f64(&out, 0), vec![Some(1.0), None]);
        Ok(())
    }

    #[test]
    fn test_text_against_a_number_is_refused_by_name() {
        let plan = ListChunked::from_iter([Some(Series::new("".into(), &["A"]))]).into_series();
        let number = Series::new("".into(), &[1.0f64]);
        let one = Series::new("".into(), &[1.0f64]);
        let zero = Series::new("".into(), &[0.0f64]);

        let err = run([plan, number, one.clone(), zero.clone()], "eq").unwrap_err();
        assert!(err.to_string().contains("sets text"), "{err}");

        let ages = ListChunked::from_iter([Some(Series::new("".into(), &[40.0f64]))]).into_series();
        let text = Series::new("".into(), &["A"]);
        let err = run([ages, text, one, zero], "eq").unwrap_err();
        assert!(err.to_string().contains("sets text"), "{err}");
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
    // Each operand cut to the rows of the slice it arrived as, and a one-row
    // list (a literal the in-memory engine hands over unbroadcast) repeated
    // for every policy, as the streaming engine reads it (slices.rs).
    let operands = rows_per_policy(inputs, false)?;
    let [left, right, then_val, otherwise_val] = operands.as_slice() else {
        return Err(PolarsError::ComputeError(
            format!(
                "list_conditional takes four operands, got {}",
                operands.len()
            )
            .into(),
        ));
    };

    let left_list = left.list().map_err(|_| {
        PolarsError::ComputeError("left must be List dtype for list_conditional".into())
    })?;

    // A text condition -- a per-period plan code compared with "A" -- is
    // decided here by comparing the strings, and handed on as the same 0/1
    // mask a numeric condition becomes, so every branch shape below serves it
    // unchanged. The paths below cast the condition to Float64, which turns
    // text into nulls and used to fail as "right at row 0 is null".
    if let Some(mask) = text_condition_mask(left_list, right, &kwargs.operator)? {
        let is_true = Series::new("".into(), &[1.0f64]);
        return list_conditional(
            &[mask, is_true, then_val.clone(), otherwise_val.clone()],
            &ConditionalKwargs {
                operator: "eq".to_string(),
                unknown_is_nan: false,
            },
        );
    }

    // The comparison, read once for the whole call.
    let op = Rule::of(kwargs);

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

    // Every shape below answers by graph-artifact spec 11.1.28: a policy
    // whose left list is null answers null, not an empty run; a null
    // per-policy branch value, or a null branch list, is null in the periods
    // that select it and changes nothing in the periods that do not; and a
    // null comparison is null whatever the branches hold (11.1.26).

    // Case 1: Right is list, then/otherwise are scalars (most common: test 1)
    if right_is_list && !then_is_list && !otherwise_is_list {
        let right_list = right.list()?;
        let then_f64 = then_val.cast(&DataType::Float64)?;
        let otherwise_f64 = otherwise_val.cast(&DataType::Float64)?;

        let then_ca = then_f64.f64()?;
        let otherwise_ca = otherwise_f64.f64()?;

        let result = left_list
            .amortized_iter()
            .zip(right_list.amortized_iter())
            .enumerate()
            .map(|(idx, (left_inner, right_inner))| match left_inner {
                Some(l_series) => {
                    let l = l_series.as_ref().cast(&DataType::Float64)?;
                    let l_ca = l.f64().unwrap();
                    let r = periods_or_nulls(right_inner.as_ref().map(AsRef::as_ref), l_ca.len())?;
                    let r_ca = r.f64()?;

                    same_periods("left", l_ca.len(), "right", r_ca.len())?;

                    let then_scalar = branch_value(then_ca, idx);
                    let otherwise_scalar = branch_value(otherwise_ca, idx);

                    decided(
                        l_ca.iter()
                            .zip(r_ca.iter())
                            .map(|(l, r)| decide(l, r, then_scalar, otherwise_scalar, op)),
                    )
                }
                None => Ok(None),
            })
            .collect::<PolarsResult<ListChunked>>()?;

        return as_float_lists(result);
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

        let result = left_list
            .amortized_iter()
            .zip(then_list.amortized_iter())
            .enumerate()
            .map(|(idx, (left_inner, then_inner))| match left_inner {
                Some(l_series) => {
                    let l = l_series.as_ref().cast(&DataType::Float64)?;
                    let l_ca = l.f64().unwrap();
                    let t = periods_or_nulls(then_inner.as_ref().map(AsRef::as_ref), l_ca.len())?;
                    let t_ca = t.f64()?;
                    same_periods("left", l_ca.len(), "then", t_ca.len())?;

                    // Get scalar values for this row
                    let right_lookup_idx = if right_is_broadcast { 0 } else { idx };

                    // A null right-hand value is a null operand: each period's
                    // comparison is null (spec 11.1.26), never a refusal.
                    let right_scalar = right_ca.get(right_lookup_idx);
                    let otherwise_scalar = branch_value(otherwise_ca, idx);

                    against_value(right_scalar, l_ca.len(), |r| {
                        decided(
                            l_ca.iter()
                                .zip(t_ca.iter())
                                .map(|(l, t)| decide(l, Some(r), t, otherwise_scalar, op)),
                        )
                    })
                }
                None => Ok(None),
            })
            .collect::<PolarsResult<ListChunked>>()?;

        return as_float_lists(result);
    }

    // Case 2b: Right is list, then is list, otherwise is scalar (test 1)
    if right_is_list && then_is_list && !otherwise_is_list {
        let right_list = right.list()?;
        let then_list = then_val.list()?;
        let otherwise_f64 = otherwise_val.cast(&DataType::Float64)?;

        let otherwise_ca = otherwise_f64.f64()?;

        let result = left_list
            .amortized_iter()
            .zip(right_list.amortized_iter())
            .zip(then_list.amortized_iter())
            .enumerate()
            .map(
                |(idx, ((left_inner, right_inner), then_inner))| match left_inner {
                    Some(l_series) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let l_ca = l.f64().unwrap();
                        let n = l_ca.len();
                        let r = periods_or_nulls(right_inner.as_ref().map(AsRef::as_ref), n)?;
                        let t = periods_or_nulls(then_inner.as_ref().map(AsRef::as_ref), n)?;
                        let r_ca = r.f64()?;
                        let t_ca = t.f64()?;

                        same_periods("left", n, "right", r_ca.len())?;
                        same_periods("left", n, "then", t_ca.len())?;

                        let otherwise_scalar = branch_value(otherwise_ca, idx);

                        decided(
                            l_ca.iter()
                                .zip(r_ca.iter())
                                .zip(t_ca.iter())
                                .map(|((l, r), t)| decide(l, r, t, otherwise_scalar, op)),
                        )
                    }
                    None => Ok(None),
                },
            )
            .collect::<PolarsResult<ListChunked>>()?;

        return as_float_lists(result);
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
                |(((left_inner, right_inner), then_inner), otherwise_inner)| match left_inner {
                    Some(l_series) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let l_ca = l.f64().unwrap();
                        let n = l_ca.len();
                        let r = periods_or_nulls(right_inner.as_ref().map(AsRef::as_ref), n)?;
                        let t = periods_or_nulls(then_inner.as_ref().map(AsRef::as_ref), n)?;
                        let o = periods_or_nulls(otherwise_inner.as_ref().map(AsRef::as_ref), n)?;
                        let r_ca = r.f64()?;
                        let t_ca = t.f64()?;
                        let o_ca = o.f64()?;

                        same_periods("left", n, "right", r_ca.len())?;
                        same_periods("left", n, "then", t_ca.len())?;
                        same_periods("left", n, "otherwise", o_ca.len())?;

                        decided(
                            l_ca.iter()
                                .zip(r_ca.iter())
                                .zip(t_ca.iter())
                                .zip(o_ca.iter())
                                .map(|(((l, r), t), o)| decide(l, r, t, o, op)),
                        )
                    }
                    None => Ok(None),
                },
            )
            .collect::<PolarsResult<ListChunked>>()?;

        return as_float_lists(result);
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

        let result = left_list
            .amortized_iter()
            .enumerate()
            .map(|(idx, left_inner)| {
                // Get scalar values for this row
                let right_lookup_idx = if right_is_broadcast { 0 } else { idx };

                // A null right-hand value is a null operand: each period's
                // comparison is null (spec 11.1.26), never a refusal.
                let right_scalar = right_ca.get(right_lookup_idx);
                let then_scalar = branch_value(then_ca, idx);
                let otherwise_scalar = branch_value(otherwise_ca, idx);

                match left_inner {
                    Some(l_series) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let l_ca = l.f64().unwrap();

                        against_value(right_scalar, l_ca.len(), |r| {
                            match (then_scalar, otherwise_scalar) {
                                // Both branches present -- every policy of a model
                                // that writes `af.x == 0.0` -- decide each period over
                                // plain numbers, as this shape always did: only the
                                // left period can be null, and a null left period is
                                // a null comparison (spec 11.1.26).
                                (Some(t), Some(o)) => decided(
                                    l_ca.iter()
                                        .map(|l| l.map(|l| op.choose(l, r, t, o, f64::NAN))),
                                ),
                                // A null branch value is null where it is selected and
                                // unread where it is not (11.1.28).
                                _ => decided(l_ca.iter().map(|l| {
                                    decide(l, Some(r), then_scalar, otherwise_scalar, op)
                                })),
                            }
                        })
                    }
                    None => Ok(None),
                }
            })
            .collect::<PolarsResult<ListChunked>>()?;

        return as_float_lists(result);
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
                // A null right-hand value is a null operand: each period's
                // comparison is null (spec 11.1.26), never a refusal.
                let right_scalar = right_ca.get(right_lookup_idx);

                match left_inner {
                    Some(l_series) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let l_ca = l.f64().unwrap();
                        let n = l_ca.len();
                        let t = periods_or_nulls(then_inner.as_ref().map(AsRef::as_ref), n)?;
                        let o = periods_or_nulls(otherwise_inner.as_ref().map(AsRef::as_ref), n)?;
                        let t_ca = t.f64()?;
                        let o_ca = o.f64()?;

                        same_periods("left", n, "then", t_ca.len())?;
                        same_periods("left", n, "otherwise", o_ca.len())?;

                        against_value(right_scalar, n, |r| {
                            decided(
                                l_ca.iter()
                                    .zip(t_ca.iter())
                                    .zip(o_ca.iter())
                                    .map(|((l, t), o)| decide(l, Some(r), t, o, op)),
                            )
                        })
                    }
                    None => Ok(None),
                }
            })
            .collect::<PolarsResult<ListChunked>>()?;

        return as_float_lists(result);
    }

    // Case 6: Right scalar, then scalar, otherwise list
    if !right_is_list && !then_is_list && otherwise_is_list {
        let right_f64 = right.cast(&DataType::Float64)?;
        let then_f64 = then_val.cast(&DataType::Float64)?;
        let right_ca = right_f64.f64()?;
        let then_ca = then_f64.f64()?;
        let right_is_broadcast = right_ca.len() == 1;

        let otherwise_list = otherwise_val.list()?;

        let result = left_list
            .amortized_iter()
            .zip(otherwise_list.amortized_iter())
            .enumerate()
            .map(|(idx, (left_inner, otherwise_inner))| {
                let right_lookup_idx = if right_is_broadcast { 0 } else { idx };
                // A null right-hand value is a null operand: each period's
                // comparison is null (spec 11.1.26), never a refusal.
                let right_scalar = right_ca.get(right_lookup_idx);
                let then_scalar = branch_value(then_ca, idx);

                match left_inner {
                    Some(l_series) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let l_ca = l.f64().unwrap();
                        let o = periods_or_nulls(
                            otherwise_inner.as_ref().map(AsRef::as_ref),
                            l_ca.len(),
                        )?;
                        let o_ca = o.f64()?;

                        same_periods("left", l_ca.len(), "otherwise", o_ca.len())?;

                        against_value(right_scalar, l_ca.len(), |r| {
                            decided(
                                l_ca.iter()
                                    .zip(o_ca.iter())
                                    .map(|(l, o)| decide(l, Some(r), then_scalar, o, op)),
                            )
                        })
                    }
                    None => Ok(None),
                }
            })
            .collect::<PolarsResult<ListChunked>>()?;

        return as_float_lists(result);
    }

    // Case 7: Right list, then scalar, otherwise list
    if right_is_list && !then_is_list && otherwise_is_list {
        let right_list = right.list()?;
        let then_f64 = then_val.cast(&DataType::Float64)?;
        let then_ca = then_f64.f64()?;

        let otherwise_list = otherwise_val.list()?;

        let result = left_list
            .amortized_iter()
            .zip(right_list.amortized_iter())
            .zip(otherwise_list.amortized_iter())
            .enumerate()
            .map(|(idx, ((left_inner, right_inner), otherwise_inner))| {
                let then_scalar = branch_value(then_ca, idx);

                match left_inner {
                    Some(l_series) => {
                        let l = l_series.as_ref().cast(&DataType::Float64)?;
                        let l_ca = l.f64().unwrap();
                        let n = l_ca.len();
                        let r = periods_or_nulls(right_inner.as_ref().map(AsRef::as_ref), n)?;
                        let o = periods_or_nulls(otherwise_inner.as_ref().map(AsRef::as_ref), n)?;
                        let r_ca = r.f64()?;
                        let o_ca = o.f64()?;

                        same_periods("left", n, "right", r_ca.len())?;
                        same_periods("left", n, "otherwise", o_ca.len())?;

                        decided(
                            l_ca.iter()
                                .zip(r_ca.iter())
                                .zip(o_ca.iter())
                                .map(|((l, r), o)| decide(l, r, then_scalar, o, op)),
                        )
                    }
                    None => Ok(None),
                }
            })
            .collect::<PolarsResult<ListChunked>>()?;

        return as_float_lists(result);
    }

    Err(PolarsError::ComputeError(
        format!(
            "Unsupported combination of list/scalar inputs: right_is_list={}, then_is_list={}, otherwise_is_list={}",
            right_is_list, then_is_list, otherwise_is_list
        ).into(),
    ))
}

/// Decide a comparison whose operands are text, as a list of 0/1 indicators.
///
/// Returns `None` when neither operand is text, which leaves the numeric
/// paths to decide it. Text compares with text only: exact string equality,
/// and for the orderings lexicographic order by Unicode code point (the byte
/// order of UTF-8), the order scalar text comparison already uses. A null on
/// either side, or a null outer list on the left, yields a null indicator, as
/// a null operand yields a null comparison. Text against a number is refused
/// by name rather than compared, because no answer to it is true.
fn text_condition_mask(
    left_list: &ListChunked,
    right: &Series,
    operator: &str,
) -> PolarsResult<Option<Series>> {
    let left_is_text = list_inner_is_string_like(left_list);
    let right_is_text = is_string_like(right);
    if !left_is_text && !right_is_text {
        return Ok(None);
    }
    // A bare null on the right has no family of its own: it compares as null.
    let right_is_null = matches!(right.dtype(), DataType::Null);
    if left_is_text != right_is_text && !right_is_null {
        let (text, number) = if left_is_text {
            (left_list.dtype(), right.dtype())
        } else {
            (right.dtype(), left_list.dtype())
        };
        return Err(PolarsError::ComputeError(
            format!(
                "a per-period comparison sets text ({text}) against a number ({number}), \
                 and text is never equal to, above or below a number. Compare the text \
                 column with a text value -- af.plan_code == \"A\" -- or the number with \
                 a number."
            )
            .into(),
        ));
    }

    // The indicators are decided over the flat elements in one pass: each
    // element is read where it lies -- a string, or a category's label looked
    // up by its id -- and compared once. Nothing is copied per element and no
    // Series is built per policy; the per-row walk this replaced cloned the
    // right-hand text once per element and cost several times the numeric
    // path. The comparison and its nulls are the same element for element.
    let compare = text_comparison(operator);
    if left_list.is_empty() {
        let offsets = OffsetsBuffer::try_from(vec![0_i64])
            .map_err(|e| PolarsError::ComputeError(format!("invalid offsets: {e}").into()))?;
        return list_series(offsets, Vec::new(), None, None).map(Some);
    }
    let left = left_list.rechunk();
    let left_offsets = left.offsets()?;
    let left_rows_valid = left.rechunk_validity();
    let left_elements = TextElements::of(&left.get_inner())?;

    // A list on the right is read row for row, and a one-row list -- a list
    // literal, which the in-memory engine hands over unbroadcast -- is read
    // for every policy, as a one-value right-hand side is and as the
    // streaming engine's broadcast already reads it. Any other height has no
    // policy to pair each row with, and is refused.
    let right_rows = if matches!(right.dtype(), DataType::List(_)) {
        let lists = right.list()?.rechunk();
        let height = lists.len();
        if height != 1 && height != left_list.len() {
            return Err(policy_height_error(left_list.len(), height));
        }
        Some((
            height == 1,
            lists.offsets()?,
            lists.rechunk_validity(),
            TextElements::of(&lists.get_inner())?,
        ))
    } else {
        None
    };
    let right_is_list = matches!(right.dtype(), DataType::List(_));
    let right_value = if !right_is_list {
        Some(right.cast(&DataType::String)?)
    } else {
        None
    };
    let right_value = right_value.as_ref().map(|s| s.str()).transpose()?;

    let rows = left.len();
    let mut offsets: Vec<i64> = Vec::with_capacity(rows + 1);
    offsets.push(0);
    let mut values: Vec<f64> = Vec::with_capacity(left_elements.len());
    let mut element_valid: Vec<bool> = Vec::with_capacity(left_elements.len());
    let mut row_valid: Vec<bool> = Vec::with_capacity(rows);
    for row in 0..rows {
        if left_rows_valid.as_ref().is_some_and(|v| !v.get_bit(row)) {
            row_valid.push(false);
            offsets.push(values.len() as i64);
            continue;
        }
        let start = left_offsets[row] as usize;
        let n = left_offsets[row + 1] as usize - start;
        match (&right_rows, right_value) {
            (Some((r_broadcast, r_offsets, r_valid, r_elements)), _) => {
                let r_row = if *r_broadcast { 0 } else { row };
                if r_valid.as_ref().is_some_and(|v| !v.get_bit(r_row)) {
                    values.extend(std::iter::repeat_n(0.0, n));
                    element_valid.extend(std::iter::repeat_n(false, n));
                } else {
                    let r_start = r_offsets[r_row] as usize;
                    let r_n = r_offsets[r_row + 1] as usize - r_start;
                    same_periods("left", n, "right", r_n)?;
                    for j in 0..n {
                        let r = r_elements.at(r_start + j);
                        push_indicator(
                            &mut values,
                            &mut element_valid,
                            left_elements.at(start + j),
                            r,
                            compare,
                            operator,
                        )?;
                    }
                }
            }
            (None, Some(ca)) => {
                let r = ca.get(if ca.len() == 1 { 0 } else { row });
                for j in 0..n {
                    push_indicator(
                        &mut values,
                        &mut element_valid,
                        left_elements.at(start + j),
                        r,
                        compare,
                        operator,
                    )?;
                }
            }
            (None, None) => unreachable!("a right-hand list is read above, a value here"),
        }
        row_valid.push(true);
        offsets.push(values.len() as i64);
    }

    let offsets = OffsetsBuffer::try_from(offsets)
        .map_err(|e| PolarsError::ComputeError(format!("invalid offsets: {e}").into()))?;
    let element_validity = element_valid
        .contains(&false)
        .then(|| element_valid.into_iter().collect::<Bitmap>());
    let row_validity = row_valid
        .contains(&false)
        .then(|| row_valid.into_iter().collect::<Bitmap>());
    list_series(offsets, values, element_validity, row_validity).map(Some)
}

/// One list column's elements, read as text by their flat position.
///
/// Text is read in place. A categorical or enum column is read by its ids,
/// each id's label looked up in the column's own mapping -- the label a cast
/// to text would write, without writing it.
enum TextElements {
    Text(Utf8ViewArray),
    Labels {
        ids: PrimitiveArray<u32>,
        mapping: Arc<CategoricalMapping>,
    },
    Empty,
}

impl TextElements {
    fn of(inner: &Series) -> PolarsResult<Self> {
        if inner.is_empty() {
            return Ok(Self::Empty);
        }
        if let DataType::Categorical(_, mapping) | DataType::Enum(_, mapping) = inner.dtype() {
            // Each step's value is held by name until the array is cloned out
            // of it, so nothing borrowed outlives what it borrows from.
            let physical = inner.to_physical_repr().cast(&DataType::UInt32)?;
            let rechunked = physical.u32()?.rechunk();
            let first: Option<PrimitiveArray<u32>> = rechunked.downcast_iter().next().cloned();
            return Ok(match first {
                Some(ids) => Self::Labels {
                    ids,
                    mapping: mapping.clone(),
                },
                None => Self::Empty,
            });
        }
        let cast = inner.cast(&DataType::String)?;
        let rechunked = cast.str()?.rechunk();
        let first: Option<Utf8ViewArray> = rechunked.downcast_iter().next().cloned();
        Ok(first.map_or(Self::Empty, Self::Text))
    }

    fn len(&self) -> usize {
        match self {
            Self::Text(text) => text.len(),
            Self::Labels { ids, .. } => ids.len(),
            Self::Empty => 0,
        }
    }

    /// The element at flat position `i`, or `None` where it is null.
    #[inline]
    fn at(&self, i: usize) -> Option<&str> {
        match self {
            Self::Text(text) => text.is_valid(i).then(|| text.value(i)),
            Self::Labels { ids, mapping } => {
                if ids.is_valid(i) {
                    mapping.cat_to_str(ids.value(i))
                } else {
                    None
                }
            }
            Self::Empty => None,
        }
    }
}

/// Append one element's indicator: 1 or 0 where both sides are text, null
/// where either is null.
#[inline]
fn push_indicator(
    values: &mut Vec<f64>,
    element_valid: &mut Vec<bool>,
    left: Option<&str>,
    right: Option<&str>,
    compare: Option<fn(&str, &str) -> bool>,
    operator: &str,
) -> PolarsResult<()> {
    match (left, right) {
        (Some(l), Some(r)) => {
            let compare = compare.ok_or_else(|| unknown_operator(operator))?;
            values.push(if compare(l, r) { 1.0 } else { 0.0 });
            element_valid.push(true);
        }
        _ => {
            values.push(0.0);
            element_valid.push(false);
        }
    }
    Ok(())
}

/// The text comparison an operator names: exact string equality, and for the
/// orderings lexicographic order by Unicode code point (UTF-8 byte order).
fn text_comparison(operator: &str) -> Option<fn(&str, &str) -> bool> {
    fn eq(l: &str, r: &str) -> bool {
        l == r
    }
    fn ne(l: &str, r: &str) -> bool {
        l != r
    }
    fn lt(l: &str, r: &str) -> bool {
        l < r
    }
    fn lte(l: &str, r: &str) -> bool {
        l <= r
    }
    fn gt(l: &str, r: &str) -> bool {
        l > r
    }
    fn gte(l: &str, r: &str) -> bool {
        l >= r
    }
    let compare: fn(&str, &str) -> bool = match operator {
        "eq" => eq,
        "ne" => ne,
        "lt" => lt,
        "lte" => lte,
        "gt" => gt,
        "gte" => gte,
        _ => return None,
    };
    Some(compare)
}

fn unknown_operator(operator: &str) -> PolarsError {
    PolarsError::ComputeError(format!("Unknown operator: {}", operator).into())
}

/// Returns true when a list column's elements are string-like.
fn list_inner_is_string_like(list: &ListChunked) -> bool {
    matches!(
        list.inner_dtype(),
        DataType::String | DataType::Categorical(_, _) | DataType::Enum(_, _)
    )
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
                    same_periods("left", expect_len, what, inner.len())?;
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
/// Null semantics, the numeric path's too (graph-artifact spec 11.1.28): a
/// null condition element, or a null right-hand value or row, yields a null
/// output element in each period; a null in the SELECTED branch propagates
/// as a null element, and a null in the branch not selected changes
/// nothing; a null policy answers null.
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

        // This row's right-hand condition values. A null right-hand value or
        // row is a null operand in each of this policy's periods, so each
        // period's comparison -- and the label it selects -- is null, as the
        // numeric path and the text path answer (spec 11.1.26). It used to
        // null the whole policy instead.
        let r_ca: Float64Chunked = match (&right_list, &right_scalar_ca) {
            (Some(rl), _) => {
                let r_inner = rl.get_as_series(idx);
                let r_ca = periods_or_nulls(r_inner.as_ref(), n)?.f64()?.clone();
                same_periods("left", n, "right", r_ca.len())?;
                r_ca
            }
            (None, Some(rs)) => {
                let lookup = if rs.len() == 1 { 0 } else { idx };
                Float64Chunked::from_iter(std::iter::repeat_n(rs.get(lookup), n))
            }
            (None, None) => unreachable!("right is either list or scalar"),
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

    // A batch whose every policy is null gives the collector no inner type to
    // infer, and answered List(Null) where the plugin declares List(String);
    // the type is stated rather than inferred, as the numeric shapes state
    // theirs (as_float_lists).
    let series = ListChunked::from_iter(out_rows).into_series();
    let target = DataType::List(Box::new(DataType::String));
    if series.dtype() == &target {
        return Ok(series);
    }
    series.cast(&target)
}

#[cfg(test)]
mod slice_tests {
    use super::*;

    fn run(inputs: [Series; 4], op: &str) -> PolarsResult<Series> {
        list_conditional(
            &inputs,
            &ConditionalKwargs {
                operator: op.to_string(),
                unknown_is_nan: false,
            },
        )
    }

    #[test]
    fn a_slice_chooses_as_the_whole_column_chooses_for_those_rows() -> PolarsResult<()> {
        let months: Vec<Series> = (0..4_i64)
            .map(|r| Series::new("".into(), vec![r, r + 1, r + 2]))
            .collect();
        let months = Series::new("m".into(), months);
        let plans: Vec<Series> = (0..4)
            .map(|r| {
                Series::new(
                    "".into(),
                    if r % 2 == 0 {
                        ["A", "B", "A"]
                    } else {
                        ["B", "A", "B"]
                    },
                )
            })
            .collect();
        let plans = Series::new("p".into(), plans);
        let two = Series::new("".into(), &[2_i64]);
        let a = Series::new("".into(), &["A"]);
        let one = Series::new("".into(), &[1.0_f64]);
        let zero = Series::new("".into(), &[0.0_f64]);

        let all = run(
            [months.clone(), two.clone(), one.clone(), zero.clone()],
            "gte",
        )?;
        let part = run([months.slice(1, 2), two, one.clone(), zero.clone()], "gte")?;
        assert!(part.equals_missing(&all.slice(1, 2)));

        let all = run([plans.clone(), a.clone(), one.clone(), zero.clone()], "eq")?;
        let part = run([plans.slice(1, 2), a, one, zero], "eq")?;
        assert!(part.equals_missing(&all.slice(1, 2)));
        Ok(())
    }
}

#[cfg(test)]
mod text_mask_tests {
    use super::*;

    type Rows = Vec<Option<Vec<Option<f64>>>>;

    const OPERATORS: [&str; 6] = ["eq", "ne", "lt", "lte", "gt", "gte"];

    /// Seven policies of text periods: case, accents and code points above
    /// the BMP, a null period, a null policy and an empty one.
    fn plans() -> Series {
        let rows: Vec<Option<Vec<Option<&str>>>> = vec![
            Some(vec![Some("A"), Some("B"), Some("a")]),
            Some(vec![Some("é"), Some("z"), Some("Z")]),
            Some(vec![None, Some("A"), Some("")]),
            None,
            Some(vec![Some("😀"), Some("A"), Some("AB")]),
            Some(vec![]),
            Some(vec![Some("B"), Some("A"), Some("é")]),
        ];
        let lists: ListChunked = rows
            .into_iter()
            .map(|row| row.map(|values| Series::new("".into(), values)))
            .collect();
        lists.into_series()
    }

    /// A per-period right-hand column with each policy's own period count.
    fn other_plans() -> Series {
        let rows: Vec<Option<Vec<Option<&str>>>> = vec![
            Some(vec![Some("A"), Some("A"), Some("b")]),
            Some(vec![Some("e"), None, Some("Z")]),
            Some(vec![Some("A"), Some("A"), Some("A")]),
            Some(vec![Some("A")]),
            None,
            Some(vec![]),
            Some(vec![Some("é"), Some("😀"), Some("")]),
        ];
        let lists: ListChunked = rows
            .into_iter()
            .map(|row| row.map(|values| Series::new("".into(), values)))
            .collect();
        lists.into_series()
    }

    fn categorical(s: &Series) -> Series {
        let cat = DataType::from_categories(Categories::global());
        let target = match s.dtype() {
            DataType::List(_) => DataType::List(Box::new(cat)),
            _ => cat,
        };
        s.cast(&target).unwrap()
    }

    fn rows_of(s: &Series) -> Rows {
        s.list()
            .unwrap()
            .into_iter()
            .map(|row| row.map(|row| row.f64().unwrap().into_iter().collect()))
            .collect()
    }

    /// The per-row walk the flat pass replaced, kept as the oracle: every
    /// row's text cast and read element by element.
    fn walked(left: &Series, right: &Series, op: &str) -> Rows {
        let left = left
            .cast(&DataType::List(Box::new(DataType::String)))
            .unwrap();
        let right_is_list = matches!(right.dtype(), DataType::List(_));
        let right = if right_is_list {
            right.cast(&DataType::List(Box::new(DataType::String)))
        } else {
            right.cast(&DataType::String)
        }
        .unwrap();
        let decide = |a: &str, b: &str| match op {
            "eq" => a == b,
            "ne" => a != b,
            "lt" => a < b,
            "lte" => a <= b,
            "gt" => a > b,
            _ => a >= b,
        };
        (0..left.len())
            .map(|i| {
                let row = left.list().unwrap().get_as_series(i)?;
                let periods: Vec<Option<String>> = row
                    .str()
                    .unwrap()
                    .into_iter()
                    .map(|v| v.map(str::to_string))
                    .collect();
                // Where the walk indexed a one-row list by policy -- a panic past
                // its one row -- the oracle reads that row for every policy, as
                // the walk read a one-value right-hand side.
                let against: Vec<Option<String>> = if right_is_list {
                    let at = if right.len() == 1 { 0 } else { i };
                    match right.list().unwrap().get_as_series(at) {
                        Some(r) => r
                            .str()
                            .unwrap()
                            .into_iter()
                            .map(|v| v.map(str::to_string))
                            .collect(),
                        None => vec![None; periods.len()],
                    }
                } else {
                    let ca = right.str().unwrap();
                    let at = if ca.len() == 1 { 0 } else { i };
                    vec![ca.get(at).map(str::to_string); periods.len()]
                };
                Some(
                    periods
                        .iter()
                        .zip(&against)
                        .map(|(a, b)| match (a, b) {
                            (Some(a), Some(b)) => Some(if decide(a.as_str(), b.as_str()) {
                                1.0
                            } else {
                                0.0
                            }),
                            _ => None,
                        })
                        .collect(),
                )
            })
            .collect()
    }

    fn flat(left: &Series, right: &Series, op: &str) -> Rows {
        let mask = text_condition_mask(left.list().unwrap(), right, op)
            .unwrap()
            .expect("a text comparison");
        rows_of(&mask)
    }

    fn rights() -> Vec<(&'static str, Series)> {
        let per_policy = Series::new(
            "r".into(),
            vec![
                Some("A"),
                Some("é"),
                None,
                Some("A"),
                Some("AB"),
                Some(""),
                Some("B"),
            ],
        );
        vec![
            ("one value", Series::new("r".into(), &["A"])),
            ("one accented value", Series::new("r".into(), &["é"])),
            ("a value per policy", per_policy.clone()),
            ("a null", Series::new_null("r".into(), 1)),
            ("a list per policy", other_plans()),
            (
                "a categorical value",
                categorical(&Series::new("r".into(), &["A"])),
            ),
            ("a categorical list per policy", categorical(&other_plans())),
            ("a categorical value per policy", categorical(&per_policy)),
        ]
    }

    #[test]
    fn the_flat_pass_decides_every_element_as_the_per_row_walk_did() {
        for left in [plans(), categorical(&plans())] {
            for (what, right) in rights() {
                for op in OPERATORS {
                    assert_eq!(
                        flat(&left, &right, op),
                        walked(&left, &right, op),
                        "{} {op} {what}",
                        left.dtype()
                    );
                }
            }
        }
    }

    #[test]
    fn a_slice_is_decided_as_the_whole_column_decides_those_rows() {
        for left in [plans(), categorical(&plans())] {
            for (what, right) in rights() {
                if right.len() != left.len() {
                    continue;
                }
                for op in OPERATORS {
                    let whole = flat(&left, &right, op);
                    let part = flat(&left.slice(2, 4), &right.slice(2, 4), op);
                    assert_eq!(part, whole[2..6].to_vec(), "{} {op} {what}", left.dtype());
                }
            }
        }
    }

    #[test]
    fn the_refusals_are_the_walks_refusals() {
        // Lists of different period counts in one policy are refused by their
        // lengths, and the batch row is not named.
        let left = plans().slice(0, 2);
        let right = other_plans().slice(2, 2);
        let err = text_condition_mask(left.list().unwrap(), &right, "eq").unwrap_err();
        assert!(
            err.to_string().contains("left=3, right=1 in that policy"),
            "{err}"
        );

        // An unknown operator is refused at the first pair it would compare,
        // and not before: a comparison with no pair has nothing to decide.
        let err = text_condition_mask(
            plans().list().unwrap(),
            &Series::new("r".into(), &["A"]),
            "xx",
        )
        .unwrap_err();
        assert!(err.to_string().contains("Unknown operator: xx"), "{err}");
        let nothing = text_condition_mask(
            plans().list().unwrap(),
            &Series::new_null("r".into(), 1),
            "xx",
        )
        .unwrap()
        .expect("a text comparison");
        assert_eq!(
            rows_of(&nothing),
            walked(&plans(), &Series::new_null("r".into(), 1), "eq")
        );

        // Text against a number is still refused by name.
        let err = text_condition_mask(
            plans().list().unwrap(),
            &Series::new("r".into(), &[1.0_f64]),
            "eq",
        )
        .unwrap_err();
        assert!(err.to_string().contains("sets text"), "{err}");
    }

    #[test]
    fn a_one_row_list_is_read_for_every_policy_and_another_height_is_refused() {
        // A one-row list beside seven policies answers as that row repeated.
        let one = Series::new("r".into(), vec![Series::new("".into(), &["A", "A", "b"])]);
        let rows: Vec<Series> = (0..7)
            .map(|_| Series::new("".into(), &["A", "A", "b"]))
            .collect();
        let repeated = Series::new("r".into(), rows);
        for left in [plans().slice(0, 3), categorical(&plans().slice(0, 3))] {
            for op in OPERATORS {
                assert_eq!(
                    flat(&left, &one, op),
                    flat(&left, &repeated.slice(0, 3), op),
                    "{op}"
                );
            }
        }
        let two = repeated.slice(0, 2);
        let err = text_condition_mask(plans().list().unwrap(), &two, "eq").unwrap_err();
        assert!(
            err.to_string()
                .contains("pairs 7 policies with an operand of 2 rows"),
            "{err}"
        );
    }

    #[test]
    fn an_empty_frame_answers_an_empty_float_list() {
        let empty = plans().slice(0, 0);
        let mask = text_condition_mask(
            empty.list().unwrap(),
            &Series::new("r".into(), &["A"]),
            "eq",
        )
        .unwrap()
        .expect("a text comparison");
        assert_eq!(mask.len(), 0);
        assert_eq!(mask.dtype(), &DataType::List(Box::new(DataType::Float64)));
    }
}

#[cfg(test)]
mod fixtures {
    //! The operands the length, null-operand and branch-length tests build.
    use super::*;

    /// Run the kernel with one comparison operator.
    pub(super) fn run_with(operator: &str, inputs: [Series; 4]) -> PolarsResult<Series> {
        list_conditional(
            &inputs,
            &ConditionalKwargs {
                operator: operator.to_string(),
                unknown_is_nan: false,
            },
        )
    }

    /// A per-period column: one run of periods per policy, or a null policy.
    pub(super) fn list(rows: &[Option<&[f64]>]) -> Series {
        ListChunked::from_iter(
            rows.iter()
                .map(|row| row.map(|values| Series::new("".into(), values))),
        )
        .into_series()
    }

    /// A per-period column in which every policy has its run of periods.
    pub(super) fn periods(rows: &[&[f64]]) -> Series {
        let present: Vec<Option<&[f64]>> = rows.iter().map(|values| Some(*values)).collect();
        list(&present)
    }

    /// A per-period text column in which every policy has its run of periods.
    pub(super) fn text_periods(rows: &[&[&str]]) -> Series {
        ListChunked::from_iter(
            rows.iter()
                .map(|values| Some(Series::new("".into(), *values))),
        )
        .into_series()
    }

    /// One value, for every policy.
    pub(super) fn scalar(value: f64) -> Series {
        Series::new("".into(), &[value])
    }
}

#[cfg(test)]
mod length_refusal_tests {
    //! A right-hand row of another length is refused naming both lengths and
    //! no row, in every branch shape, as the text path names them.
    use super::fixtures::{list, scalar};
    use super::*;

    fn run(inputs: [Series; 4]) -> PolarsResult<Series> {
        super::fixtures::run_with("eq", inputs)
    }

    #[test]
    fn a_right_hand_row_of_another_length_is_refused_by_its_lengths() {
        let short = list(&[Some(&[1.0, 2.0][..]), Some(&[1.0][..])]);
        let long = list(&[Some(&[1.0, 2.0][..]), Some(&[1.0, 2.0, 3.0][..])]);
        let then_list = list(&[Some(&[10.0, 20.0][..]), Some(&[30.0][..])]);
        let otherwise_list = list(&[Some(&[-1.0, -2.0][..]), Some(&[-3.0][..])]);
        let message = "left=1, right=3 in that policy";
        for (shape, then_val, otherwise_val) in [
            ("scalar then, scalar otherwise", scalar(1.0), scalar(0.0)),
            (
                "list then, scalar otherwise",
                then_list.clone(),
                scalar(0.0),
            ),
            (
                "list then, list otherwise",
                then_list,
                otherwise_list.clone(),
            ),
            (
                "text branches",
                Series::new("".into(), &["hit"]),
                Series::new("".into(), &["miss"]),
            ),
        ] {
            let err = run([short.clone(), long.clone(), then_val, otherwise_val]).unwrap_err();
            assert!(err.to_string().contains(message), "{shape}: {err}");
        }
        // The shape that already named its lengths names the otherwise list too.
        let err = run([short, long, scalar(1.0), otherwise_list]).unwrap_err();
        assert!(
            err.to_string().contains("left=1, right=3 in that policy"),
            "{err}"
        );
    }
}

#[cfg(test)]
mod null_operand_tests {
    //! A null right-hand operand -- one value, a value per policy, or a whole
    //! right-hand row -- is a null comparison in each of the policy's periods
    //! (graph-artifact spec, section 11.1.26), in every branch shape and in
    //! the text-branch path.
    use super::fixtures::{list, scalar};
    use super::*;

    type Rows = Vec<Option<Vec<Option<f64>>>>;

    fn run(inputs: [Series; 4]) -> PolarsResult<Series> {
        super::fixtures::run_with("eq", inputs)
    }

    fn rows(result: &Series) -> Rows {
        let lists = result.list().unwrap();
        (0..lists.len())
            .map(|i| {
                lists
                    .get_as_series(i)
                    .map(|inner| inner.f64().unwrap().into_iter().collect())
            })
            .collect()
    }

    /// Two policies: two periods, then one.
    fn left() -> Series {
        list(&[Some(&[1.0, 2.0][..]), Some(&[3.0][..])])
    }

    /// Each branch shape the kernel serves, as (name, then, otherwise, the
    /// first policy's answer when its first period matches and its second
    /// does not).
    fn branch_shapes() -> Vec<(&'static str, Series, Series, Vec<Option<f64>>)> {
        let then_list = list(&[Some(&[10.0, 20.0][..]), Some(&[30.0][..])]);
        let otherwise_list = list(&[Some(&[-1.0, -2.0][..]), Some(&[-3.0][..])]);
        vec![
            (
                "scalar then, scalar otherwise",
                scalar(10.0),
                scalar(-1.0),
                vec![Some(10.0), Some(-1.0)],
            ),
            (
                "list then, scalar otherwise",
                then_list.clone(),
                scalar(-1.0),
                vec![Some(10.0), Some(-1.0)],
            ),
            (
                "scalar then, list otherwise",
                scalar(10.0),
                otherwise_list.clone(),
                vec![Some(10.0), Some(-2.0)],
            ),
            (
                "list then, list otherwise",
                then_list,
                otherwise_list,
                vec![Some(10.0), Some(-2.0)],
            ),
        ]
    }

    #[test]
    fn a_null_value_per_policy_is_a_null_comparison_in_each_period() -> PolarsResult<()> {
        let right = Series::new("".into(), &[Some(1.0_f64), None]);
        for (shape, then_val, otherwise_val, first) in branch_shapes() {
            let out = run([left(), right.clone(), then_val, otherwise_val])?;
            assert_eq!(rows(&out), vec![Some(first), Some(vec![None])], "{shape}");
        }
        Ok(())
    }

    #[test]
    fn a_null_value_for_every_policy_is_null_in_every_period() -> PolarsResult<()> {
        let right = Series::new("".into(), &[None::<f64>]);
        for (shape, then_val, otherwise_val, _) in branch_shapes() {
            let out = run([left(), right.clone(), then_val, otherwise_val])?;
            assert_eq!(
                rows(&out),
                vec![Some(vec![None, None]), Some(vec![None])],
                "{shape}"
            );
        }
        Ok(())
    }

    #[test]
    fn a_null_right_hand_row_is_a_null_comparison_in_each_period() -> PolarsResult<()> {
        let right = list(&[Some(&[1.0, 5.0][..]), None]);
        for (shape, then_val, otherwise_val, first) in branch_shapes() {
            let out = run([left(), right.clone(), then_val, otherwise_val])?;
            assert_eq!(rows(&out), vec![Some(first), Some(vec![None])], "{shape}");
        }
        Ok(())
    }

    #[test]
    fn a_null_policy_answers_null_and_an_empty_one_an_empty_run() -> PolarsResult<()> {
        // A null policy answers null, as null outer lists remain null (spec
        // 11.1.28); it used to answer an empty run, a policy with no
        // periods. A policy with no periods still answers an empty run,
        // whatever the right-hand side holds: there is no period to compare.
        let empty: &[f64] = &[];
        let policies = list(&[None, Some(empty)]);
        for right in [
            Series::new("".into(), &[None::<f64>]),
            Series::new("".into(), &[Some(1.0_f64), None]),
            Series::full_null("".into(), 2, &DataType::List(Box::new(DataType::Float64))),
            list(&[Some(&[1.0][..]), Some(empty)]),
        ] {
            let out = run([policies.clone(), right, scalar(1.0), scalar(0.0)])?;
            assert_eq!(rows(&out), vec![None, Some(vec![])]);
        }
        Ok(())
    }

    #[test]
    fn text_branches_answer_a_null_label_in_each_period() -> PolarsResult<()> {
        let hit = Series::new("".into(), &["hit"]);
        let miss = Series::new("".into(), &["miss"]);
        for right in [
            Series::new("".into(), &[Some(1.0_f64), None]),
            list(&[Some(&[1.0, 5.0][..]), None]),
        ] {
            let out = run([left(), right, hit.clone(), miss.clone()])?;
            let lists = out.list()?;
            let labels: Vec<Option<Vec<Option<String>>>> = (0..lists.len())
                .map(|i| {
                    lists.get_as_series(i).map(|inner| {
                        inner
                            .str()
                            .unwrap()
                            .into_iter()
                            .map(|v| v.map(str::to_string))
                            .collect()
                    })
                })
                .collect();
            assert_eq!(
                labels,
                vec![
                    Some(vec![Some("hit".to_string()), Some("miss".to_string())]),
                    Some(vec![None]),
                ]
            );
        }
        Ok(())
    }
}

#[cfg(test)]
mod null_branch_tests {
    //! Graph-artifact spec 11.1.28: "A null selected branch stays null; a
    //! null unselected branch does not replace the selected value. Empty
    //! lists remain empty and null outer lists remain null." The numeric
    //! kernel refused a null per-policy branch value ("then_val at row N is
    //! null"), answered a null branch list or a null policy with an empty
    //! run, and nulled a period whose unselected branch was null.
    use super::fixtures::{list, scalar};
    use super::*;

    type Rows = Vec<Option<Vec<Option<f64>>>>;

    fn rows(result: &Series) -> Rows {
        let lists = result.list().unwrap();
        (0..lists.len())
            .map(|i| {
                lists
                    .get_as_series(i)
                    .map(|inner| inner.f64().unwrap().into_iter().collect())
            })
            .collect()
    }

    /// Two policies of two periods: `x > 1` is false then true in each.
    fn left() -> Series {
        list(&[Some(&[1.0, 2.0][..]), Some(&[1.0, 2.0][..])])
    }

    /// The comparison's right side in each shape: one value, or a list.
    fn rights() -> [(&'static str, Series); 2] {
        [
            ("a value on the right", scalar(1.0)),
            (
                "a list on the right",
                list(&[Some(&[1.0, 1.0][..]), Some(&[1.0, 1.0][..])]),
            ),
        ]
    }

    /// A per-policy value null for the second policy.
    fn null_for_the_second() -> Series {
        Series::new("".into(), &[Some(7.0_f64), None])
    }

    /// A per-period branch whose second policy's list is null.
    fn null_list_for_the_second() -> Series {
        list(&[Some(&[7.0, 7.0][..]), None])
    }

    fn run(inputs: [Series; 4]) -> PolarsResult<Series> {
        super::fixtures::run_with("gt", inputs)
    }

    #[test]
    fn a_null_then_is_null_where_selected_and_unread_where_not() -> PolarsResult<()> {
        let periods = list(&[Some(&[-1.0, -2.0][..]), Some(&[-1.0, -2.0][..])]);
        for (shape, right) in rights() {
            for then in [null_for_the_second(), null_list_for_the_second()] {
                for (otherwise, second) in [
                    (scalar(0.0), vec![Some(0.0), None]),
                    (periods.clone(), vec![Some(-1.0), None]),
                ] {
                    let out = run([left(), right.clone(), then.clone(), otherwise])?;
                    assert_eq!(rows(&out)[1], Some(second), "{shape}, then {then:?}");
                }
            }
        }
        Ok(())
    }

    #[test]
    fn a_null_otherwise_is_null_where_selected_and_unread_where_not() -> PolarsResult<()> {
        let periods = list(&[Some(&[9.0, 8.0][..]), Some(&[9.0, 8.0][..])]);
        for (shape, right) in rights() {
            for otherwise in [null_for_the_second(), null_list_for_the_second()] {
                for (then, second) in [
                    (scalar(5.0), vec![None, Some(5.0)]),
                    (periods.clone(), vec![None, Some(8.0)]),
                ] {
                    let out = run([left(), right.clone(), then, otherwise.clone()])?;
                    assert_eq!(
                        rows(&out)[1],
                        Some(second),
                        "{shape}, otherwise {otherwise:?}"
                    );
                }
            }
        }
        Ok(())
    }

    #[test]
    fn a_null_policy_answers_null_in_every_shape() -> PolarsResult<()> {
        let left = list(&[Some(&[1.0, 2.0][..]), None]);
        let periods = list(&[Some(&[7.0, 7.0][..]), Some(&[7.0][..])]);
        for (shape, right) in rights() {
            let right = if matches!(right.dtype(), DataType::List(_)) {
                list(&[Some(&[1.0, 1.0][..]), Some(&[1.0][..])])
            } else {
                right
            };
            for (then, otherwise) in [
                (scalar(5.0), scalar(0.0)),
                (periods.clone(), scalar(0.0)),
                (scalar(5.0), periods.clone()),
                (periods.clone(), periods.clone()),
            ] {
                let out = run([left.clone(), right.clone(), then, otherwise])?;
                let answer = rows(&out);
                assert_eq!(answer[1], None, "{shape}");
                assert!(answer[0].is_some(), "{shape}");
            }
        }
        Ok(())
    }

    #[test]
    fn a_batch_of_null_policies_keeps_its_float_list_type() -> PolarsResult<()> {
        let left = list(&[None, None]);
        let out = run([left, scalar(1.0), scalar(5.0), scalar(0.0)])?;
        assert_eq!(out.dtype(), &DataType::List(Box::new(DataType::Float64)));
        assert_eq!(out.null_count(), 2);
        Ok(())
    }

    #[test]
    fn a_null_comparison_is_null_whatever_the_branches_hold() -> PolarsResult<()> {
        let left = ListChunked::from_iter([
            Some(Series::new("".into(), &[Some(1.0_f64), None])),
            Some(Series::new("".into(), &[2.0_f64])),
        ])
        .into_series();
        let out = run([left, scalar(1.0), scalar(5.0), scalar(0.0)])?;
        assert_eq!(
            rows(&out),
            vec![Some(vec![Some(0.0), None]), Some(vec![Some(5.0)])]
        );
        Ok(())
    }
}

#[cfg(test)]
mod text_branch_type_tests {
    use super::fixtures::{list, scalar};
    use super::*;

    #[test]
    fn a_batch_of_null_policies_with_text_branches_keeps_its_text_list_type() -> PolarsResult<()> {
        let left = list(&[None, None]);
        let then_val = Series::new("".into(), &["a", "b"]);
        let otherwise_val = Series::new("".into(), &["z"]);
        let out = super::fixtures::run_with("gt", [left, scalar(1.0), then_val, otherwise_val])?;
        assert_eq!(out.dtype(), &DataType::List(Box::new(DataType::String)));
        assert_eq!(out.null_count(), 2);
        Ok(())
    }
}

#[cfg(test)]
mod branch_length_tests {
    //! A `then` or `otherwise` list with another number of periods than its
    //! policy is refused by its name and both lengths, in every
    //! shape that takes one, text branches included: list branches of
    //! different lengths are not padded or truncated (graph-artifact spec,
    //! sections 11.1.18 and 11.1.28). Three shapes used to zip the two and
    //! answer a run cut to the shorter.
    use super::fixtures::{periods as list, scalar, text_periods as text_list};
    use super::*;

    fn run(inputs: [Series; 4]) -> PolarsResult<Series> {
        super::fixtures::run_with("gt", inputs)
    }

    /// Two policies, of two and three periods.
    fn left() -> Series {
        list(&[&[1.0, 2.0][..], &[1.0, 2.0, 3.0][..]])
    }

    /// Per-period values that fit each policy.
    fn fits() -> Series {
        list(&[&[10.0, 20.0][..], &[10.0, 20.0, 30.0][..]])
    }

    /// Per-period values one period short in the second policy.
    fn short() -> Series {
        list(&[&[10.0, 20.0][..], &[10.0, 20.0][..]])
    }

    /// Per-period values one period long in the second policy.
    fn long() -> Series {
        list(&[&[10.0, 20.0][..], &[10.0, 20.0, 30.0, 40.0][..]])
    }

    fn refusal(inputs: [Series; 4]) -> String {
        run(inputs).unwrap_err().to_string()
    }

    #[test]
    fn a_then_list_of_another_length_is_refused_in_every_shape() {
        let short_then = "left=3, then=2 in that policy";
        for (shape, right, otherwise_val) in [
            ("a value on the right", scalar(1.0), scalar(0.0)),
            ("a list on the right", fits(), scalar(0.0)),
            ("all lists", fits(), fits()),
            (
                "a value on the right, a list otherwise",
                scalar(1.0),
                fits(),
            ),
        ] {
            let err = refusal([left(), right.clone(), short(), otherwise_val.clone()]);
            assert!(err.contains(short_then), "{shape}: {err}");
            let err = refusal([left(), right.clone(), long(), otherwise_val.clone()]);
            assert!(
                err.contains("left=3, then=4 in that policy"),
                "{shape}: {err}"
            );
            assert!(
                run([left(), right, fits(), otherwise_val]).is_ok(),
                "{shape}: matching lengths still answer"
            );
        }
    }

    #[test]
    fn an_otherwise_list_of_another_length_is_refused_in_every_shape() {
        let short_otherwise = "left=3, otherwise=2 in that policy";
        for (shape, right, then_val) in [
            (
                "a value on the right, a value then",
                scalar(1.0),
                scalar(1.0),
            ),
            ("a value on the right, a list then", scalar(1.0), fits()),
            ("a list on the right, a value then", fits(), scalar(1.0)),
            ("all lists", fits(), fits()),
        ] {
            let err = refusal([left(), right.clone(), then_val.clone(), short()]);
            assert!(err.contains(short_otherwise), "{shape}: {err}");
            assert!(
                run([left(), right, then_val, fits()]).is_ok(),
                "{shape}: matching lengths still answer"
            );
        }
    }

    #[test]
    fn a_short_branch_answers_nothing_rather_than_a_shorter_run() {
        // The base answered policy 1 with two periods, the left has three.
        let err = run([left(), scalar(1.0), short(), scalar(0.0)]).unwrap_err();
        assert!(err.to_string().contains("then=2"), "{err}");
    }

    #[test]
    fn a_text_branch_list_of_another_length_is_refused_by_its_name() {
        let fits_text = text_list(&[&["a", "b"][..], &["a", "b", "c"][..]]);
        let short_text = text_list(&[&["a", "b"][..], &["a", "b"][..]]);
        let none = Series::new("".into(), &["none"][..]);

        let err = refusal([left(), scalar(1.0), short_text.clone(), none.clone()]);
        assert!(err.contains("left=3, then=2 in that policy"), "{err}");
        let err = refusal([left(), scalar(1.0), none.clone(), short_text]);
        assert!(err.contains("left=3, otherwise=2 in that policy"), "{err}");
        assert!(run([left(), scalar(1.0), fits_text, none]).is_ok());
    }
}
