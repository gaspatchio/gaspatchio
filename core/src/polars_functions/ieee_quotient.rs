// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: IEEE-754 division, floor division and modulo for per-policy and per-period columns
// ABOUTME: Divides each element by its own divisor -- never by a hoisted reciprocal

//! `a / b`, `a // b` and `a % b` exactly as binary64 defines them.
//!
//! Polars' float kernels, given one divisor for a whole array, multiply by its
//! reciprocal instead of dividing (`polars-compute` `prim_true_div_scalar`,
//! and the floor-division and modulo kernels beside it). `x * (1 / c)` is not
//! `x / c`: 135.021 / 1000 is 0.13502099999999997, 135.021 * 0.001 is
//! 0.135021, and a floor taken of the product can land on the wrong integer.
//! Which kernel a formula meets depends on the engine and on how it splits the
//! rows, so the same model gave different floats by run mode.
//!
//! This kernel performs one IEEE operation per output element, over either
//! shape the framework has: a per-policy column (one value per row) or a
//! per-period column (one list per row). A side of length one broadcasts
//! across the other. The arithmetic is the one Polars' own element-by-element
//! kernels and section 11.1.25 of the graph-artifact contract state:
//!
//! * `div` — `l / r`
//! * `floordiv` — `floor(l / r)`, the floor of the binary64 quotient
//! * `mod` — `l - r * floor(l / r)`, evaluated in binary64
//!
//! A null on either side is null at that position; a null list is a null
//! result list. A zero divisor follows IEEE: a signed infinity for a nonzero
//! numerator, NaN for zero over zero; `floordiv` keeps that infinity or NaN
//! and `mod` answers NaN.

use polars::prelude::*;
use polars_arrow::array::{Array, PrimitiveArray};
use polars_arrow::bitmap::Bitmap;
use polars_arrow::offset::OffsetsBuffer;
use serde::Deserialize;

use super::slices::{own_rows, same_periods};

/// Which quotient the kernel computes, named as the op-tree names it.
#[derive(Deserialize)]
pub struct QuotientKwargs {
    /// One of `"div"`, `"floordiv"` or `"mod"`.
    pub op: String,
}

/// Compute an IEEE quotient of two numeric columns, element by element.
///
/// # Arguments
/// * `inputs[0]` - The numerator: a numeric column, or a list of numbers.
/// * `inputs[1]` - The divisor: a numeric column, or a list of numbers.
/// * `kwargs.op` - `"div"`, `"floordiv"` or `"mod"`.
///
/// # Returns
/// `Float64` when neither side is a list; `List<Float64>` when either is. A
/// list paired with a per-row value applies that row's value to every element
/// of the row's list.
///
/// # Errors
/// Returns `ComputeError` when an operand is not numeric, when the two sides
/// have different row counts and neither has one row, when two lists in one
/// row have different lengths, or when `op` names no quotient.
pub fn ieee_quotient(inputs: &[Series], kwargs: &QuotientKwargs) -> PolarsResult<Series> {
    let (lhs, rhs) = two_operands(inputs, "ieee_quotient")?;
    match kwargs.op.as_str() {
        "div" => broadcast_binary(lhs, rhs, "ieee_quotient", |l, r| l / r),
        "floordiv" => broadcast_binary(lhs, rhs, "ieee_quotient", |l, r| (l / r).floor()),
        "mod" => broadcast_binary(lhs, rhs, "ieee_quotient", |l, r| l - r * (l / r).floor()),
        other => Err(PolarsError::ComputeError(
            format!("ieee_quotient computes div, floordiv or mod; it was asked for {other:?}")
                .into(),
        )),
    }
}

fn two_operands<'a>(inputs: &'a [Series], kernel: &str) -> PolarsResult<(&'a Series, &'a Series)> {
    match inputs {
        [lhs, rhs] => Ok((lhs, rhs)),
        _ => Err(PolarsError::ComputeError(
            format!("{kernel} takes two operands, got {}", inputs.len()).into(),
        )),
    }
}

/// One operand, reduced to flat binary64 values.
struct Side {
    /// One value per row for a per-row column; every element for a list.
    values: PrimitiveArray<f64>,
    /// The list rows' boundaries in `values`, when this side is a list.
    lists: Option<ListRows>,
    /// How many rows the side has.
    rows: usize,
}

struct ListRows {
    offsets: OffsetsBuffer<i64>,
    validity: Option<Bitmap>,
}

impl ListRows {
    /// The `[start, end)` element range of `row`, or `None` for a null list.
    #[inline]
    fn span(&self, row: usize) -> Option<(usize, usize)> {
        if let Some(validity) = &self.validity {
            if !validity.get_bit(row) {
                return None;
            }
        }
        Some((self.offsets[row] as usize, self.offsets[row + 1] as usize))
    }
}

fn is_number(dtype: &DataType) -> bool {
    dtype.is_primitive_numeric() || dtype.is_bool() || dtype.is_null()
}

/// Refuse an operand that is not numbers -- a column of them, or lists of
/// them -- by name, in the words the quotient kernel uses.
///
/// A cast to Float64 turns text into nulls, and a kernel that cast first
/// answered a run of nulls for `af.fund_value ** af.code`: a wrong number
/// with nothing said.
///
/// # Errors
/// `ComputeError` naming the kernel and the dtype it was handed.
pub(crate) fn numbers_only(series: &Series, kernel: &str) -> PolarsResult<()> {
    match series.dtype() {
        DataType::List(inner) if !is_number(inner) => polars_bail!(
            ComputeError: "{} works on numbers, and these lists hold {}", kernel, inner
        ),
        DataType::List(_) => Ok(()),
        dtype if !is_number(dtype) => polars_bail!(
            ComputeError: "{} works on numbers, and this column holds {}", kernel, dtype
        ),
        _ => Ok(()),
    }
}

fn side(series: &Series, kernel: &str) -> PolarsResult<Side> {
    // A streamed slice of a list column keeps the whole column's inner values;
    // the passes below index the flat values, so they are handed the slice's
    // own. The cast after this would trim them too, in Polars 0.53 -- this
    // does not leave the cost of a morsel to that.
    let series = &own_rows(series);
    if let DataType::List(inner) = series.dtype() {
        if !is_number(inner) {
            polars_bail!(
                ComputeError: "{} works on numbers, and these lists hold {}", kernel, inner
            );
        }
        let cast = series.cast(&DataType::List(Box::new(DataType::Float64)))?;
        let rechunked = cast.list()?.rechunk();
        let rows = rechunked.len();
        let Some(array) = rechunked.downcast_iter().next() else {
            // A frame with no policies: no rows, and no elements to divide.
            return Ok(Side {
                values: PrimitiveArray::from_vec(Vec::<f64>::new()),
                lists: Some(ListRows {
                    offsets: OffsetsBuffer::try_from(vec![0_i64]).map_err(|e| {
                        PolarsError::ComputeError(format!("invalid offsets: {e}").into())
                    })?,
                    validity: None,
                }),
                rows: 0,
            });
        };
        let values = array
            .values()
            .as_any()
            .downcast_ref::<PrimitiveArray<f64>>()
            .ok_or_else(|| {
                PolarsError::ComputeError(
                    format!("{kernel}: list values did not become binary64").into(),
                )
            })?
            .clone();
        return Ok(Side {
            values,
            lists: Some(ListRows {
                offsets: array.offsets().clone(),
                validity: array.validity().cloned(),
            }),
            rows,
        });
    }
    if !is_number(series.dtype()) {
        polars_bail!(
            ComputeError: "{} works on numbers, and this column holds {}", kernel, series.dtype()
        );
    }
    let cast = series.cast(&DataType::Float64)?;
    let rechunked = cast.f64()?.rechunk();
    let rows = rechunked.len();
    let values = match rechunked.downcast_iter().next() {
        Some(array) => array.clone(),
        None => PrimitiveArray::from_vec(Vec::<f64>::new()),
    };
    Ok(Side {
        values,
        lists: None,
        rows,
    })
}

#[inline]
fn row_of(side: &Side, row: usize) -> usize {
    if side.rows == 1 {
        0
    } else {
        row
    }
}

/// Apply `f` element by element over two numeric operands of either shape.
///
/// The shared engine of the quotient kernel and of `list_pow`'s per-row base:
/// a side of one row broadcasts across the other, a per-row value applies to
/// every element of its row's list, and two lists in one row pair element by
/// element. `f` is applied to binary64 values; a position where either side
/// is null is computed over whatever its slot holds and then masked null.
pub(crate) fn broadcast_binary<F>(
    lhs: &Series,
    rhs: &Series,
    kernel: &str,
    f: F,
) -> PolarsResult<Series>
where
    F: Fn(f64, f64) -> f64,
{
    let name = lhs.name().clone();
    let any_list =
        matches!(lhs.dtype(), DataType::List(_)) || matches!(rhs.dtype(), DataType::List(_));
    let left = side(lhs, kernel)?;
    let right = side(rhs, kernel)?;

    if left.rows != right.rows && left.rows != 1 && right.rows != 1 {
        return Err(PolarsError::ComputeError(
            format!(
                "{kernel}: the operands have {} and {} rows; each needs one row \
                 per policy, or a single row that covers them all",
                left.rows, right.rows
            )
            .into(),
        ));
    }
    let rows = if left.rows == 0 || right.rows == 0 {
        0
    } else {
        left.rows.max(right.rows)
    };

    let series = if any_list {
        list_result(&left, &right, rows, kernel, &f)?
    } else {
        flat_result(&left, &right, rows, &f)?
    };
    Ok(series.with_name(name))
}

fn flat_result<F>(left: &Side, right: &Side, rows: usize, f: &F) -> PolarsResult<Series>
where
    F: Fn(f64, f64) -> f64,
{
    let lv = left.values.values();
    let rv = right.values.values();
    let out: Vec<f64> = (0..rows)
        .map(|row| f(lv[row_of(left, row)], rv[row_of(right, row)]))
        .collect();
    let validity = if left.values.null_count() > 0 || right.values.null_count() > 0 {
        Some(
            (0..rows)
                .map(|row| {
                    left.values.is_valid(row_of(left, row))
                        && right.values.is_valid(row_of(right, row))
                })
                .collect::<Bitmap>(),
        )
    } else {
        None
    };
    let array = PrimitiveArray::from_vec(out).with_validity(validity);
    Series::from_arrow(PlSmallStr::EMPTY, Box::new(array))
}

/// What a refusal calls the two operands of `kernel`: a power's base and
/// exponent, a quotient's numerator and divisor.
fn operand_names(kernel: &str) -> (&'static str, &'static str) {
    if kernel == "list_pow" {
        ("base", "exponent")
    } else {
        ("numerator", "divisor")
    }
}

/// Where one side's value for element `j` of output row `row` lives.
#[inline]
fn element_index(side: &Side, row: usize, start: Option<usize>, j: usize) -> usize {
    match start {
        Some(start) => start + j,
        None => row_of(side, row),
    }
}

fn list_result<F>(
    left: &Side,
    right: &Side,
    rows: usize,
    kernel: &str,
    f: &F,
) -> PolarsResult<Series>
where
    F: Fn(f64, f64) -> f64,
{
    if let Some(series) = aligned_result(left, right, rows, f)? {
        return Ok(series);
    }
    let lv = left.values.values();
    let rv = right.values.values();
    let track_elements = left.values.null_count() > 0 || right.values.null_count() > 0;

    let mut offsets: Vec<i64> = Vec::with_capacity(rows + 1);
    offsets.push(0);
    let mut out: Vec<f64> = Vec::with_capacity(lv.len().max(rv.len()));
    let mut element_valid: Vec<bool> = Vec::new();
    let mut row_valid: Vec<bool> = Vec::with_capacity(rows);
    let mut any_null_row = false;

    for row in 0..rows {
        let left_span = left.lists.as_ref().map(|l| l.span(row_of(left, row)));
        let right_span = right.lists.as_ref().map(|l| l.span(row_of(right, row)));
        // A null list on either side is a null result list.
        if matches!(left_span, Some(None)) || matches!(right_span, Some(None)) {
            row_valid.push(false);
            any_null_row = true;
            offsets.push(out.len() as i64);
            continue;
        }
        let left_span = left_span.flatten();
        let right_span = right_span.flatten();
        let length = match (left_span, right_span) {
            (Some((ls, le)), Some((rs, re))) => {
                let (left_name, right_name) = operand_names(kernel);
                same_periods(left_name, le - ls, right_name, re - rs)?;
                le - ls
            }
            (Some((s, e)), None) | (None, Some((s, e))) => e - s,
            (None, None) => 0,
        };
        let left_start = left_span.map(|(s, _)| s);
        let right_start = right_span.map(|(s, _)| s);
        for j in 0..length {
            let li = element_index(left, row, left_start, j);
            let ri = element_index(right, row, right_start, j);
            out.push(f(lv[li], rv[ri]));
            if track_elements {
                element_valid.push(left.values.is_valid(li) && right.values.is_valid(ri));
            }
        }
        row_valid.push(true);
        offsets.push(out.len() as i64);
    }

    let element_validity = if track_elements {
        Some(element_valid.into_iter().collect::<Bitmap>())
    } else {
        None
    };
    let offsets = OffsetsBuffer::try_from(offsets)
        .map_err(|e| PolarsError::ComputeError(format!("invalid offsets: {e}").into()))?;
    let row_validity = if any_null_row {
        Some(row_valid.into_iter().collect::<Bitmap>())
    } else {
        None
    };
    list_series(offsets, out, element_validity, row_validity)
}

/// The shapes a projection divides in, done over the flat values in one pass.
///
/// A list over a per-row value (or a single one), the reverse, or two lists
/// laid out on the same periods: the output keeps the list side's own
/// offsets and row validity, and every element is one call of `f` in a loop
/// the compiler can vectorise. `None` hands anything else -- a broadcast
/// list, two lists on different offsets, a null per-row value -- to the
/// general walk, which answers the same numbers one element at a time.
fn aligned_result<F>(left: &Side, right: &Side, rows: usize, f: &F) -> PolarsResult<Option<Series>>
where
    F: Fn(f64, f64) -> f64,
{
    let lv = left.values.values();
    let rv = right.values.values();
    match (&left.lists, &right.lists) {
        (Some(lists), None) => {
            if left.rows != rows || right.values.null_count() > 0 {
                return Ok(None);
            }
            let mut out = vec![0.0_f64; lv.len()];
            for row in 0..rows {
                let divisor = rv[row_of(right, row)];
                let (start, end) = (lists.offsets[row] as usize, lists.offsets[row + 1] as usize);
                for (o, &l) in out[start..end].iter_mut().zip(&lv[start..end]) {
                    *o = f(l, divisor);
                }
            }
            let elements = left.values.validity().cloned();
            list_series(lists.offsets.clone(), out, elements, lists.validity.clone()).map(Some)
        }
        (None, Some(lists)) => {
            if right.rows != rows || left.values.null_count() > 0 {
                return Ok(None);
            }
            let mut out = vec![0.0_f64; rv.len()];
            for row in 0..rows {
                let numerator = lv[row_of(left, row)];
                let (start, end) = (lists.offsets[row] as usize, lists.offsets[row + 1] as usize);
                for (o, &r) in out[start..end].iter_mut().zip(&rv[start..end]) {
                    *o = f(numerator, r);
                }
            }
            let elements = right.values.validity().cloned();
            list_series(lists.offsets.clone(), out, elements, lists.validity.clone()).map(Some)
        }
        (Some(left_lists), Some(right_lists)) => {
            if left.rows != rows
                || right.rows != rows
                || lv.len() != rv.len()
                || left_lists.offsets.as_slice() != right_lists.offsets.as_slice()
            {
                return Ok(None);
            }
            let out: Vec<f64> = lv.iter().zip(rv.iter()).map(|(&l, &r)| f(l, r)).collect();
            let elements = both_valid(left.values.validity(), right.values.validity());
            let lists = both_valid(left_lists.validity.as_ref(), right_lists.validity.as_ref());
            list_series(left_lists.offsets.clone(), out, elements, lists).map(Some)
        }
        (None, None) => Ok(None),
    }
}

/// Valid where both sides are: the intersection of two optional masks.
fn both_valid(left: Option<&Bitmap>, right: Option<&Bitmap>) -> Option<Bitmap> {
    match (left, right) {
        (None, None) => None,
        (Some(mask), None) | (None, Some(mask)) => Some(mask.clone()),
        (Some(l), Some(r)) => Some(polars_arrow::bitmap::and(l, r)),
    }
}

/// Assemble a `List<Float64>` series from offsets, flat values and masks.
pub(crate) fn list_series(
    offsets: OffsetsBuffer<i64>,
    values: Vec<f64>,
    element_validity: Option<Bitmap>,
    row_validity: Option<Bitmap>,
) -> PolarsResult<Series> {
    let values = PrimitiveArray::from_vec(values).with_validity(element_validity);
    let list = LargeListArray::new(
        ArrowDataType::LargeList(Box::new(ArrowField::new(
            PlSmallStr::from_static("item"),
            ArrowDataType::Float64,
            true,
        ))),
        offsets,
        Box::new(values),
        row_validity,
    );
    Series::from_arrow(PlSmallStr::EMPTY, Box::new(list))
}

#[cfg(test)]
mod tests {
    use super::*;

    const K: f64 = 135.021;
    const D: f64 = 1000.0;

    fn op(name: &str) -> QuotientKwargs {
        QuotientKwargs {
            op: name.to_string(),
        }
    }

    fn list(rows: Vec<Option<Vec<Option<f64>>>>) -> Series {
        let chunked: ListChunked = rows
            .into_iter()
            .map(|row| row.map(|values| Series::new("".into(), values)))
            .collect();
        chunked.into_series()
    }

    fn list_values(series: &Series) -> Vec<Option<Vec<Option<f64>>>> {
        series
            .list()
            .unwrap()
            .into_iter()
            .map(|row| row.map(|s| s.f64().unwrap().into_iter().collect()))
            .collect()
    }

    #[test]
    fn reciprocal_is_a_different_number() {
        // Guards the fixture: without this the tests below could pass vacuously.
        assert_ne!(K / D, K * (1.0 / D));
    }

    #[test]
    fn per_policy_column_over_one_divisor_divides() -> PolarsResult<()> {
        let numerator = Series::new("k".into(), vec![K, K, K]);
        let divisor = Series::new("d".into(), vec![D]);
        let out = ieee_quotient(&[numerator, divisor], &op("div"))?;
        assert_eq!(out.name().as_str(), "k");
        assert_eq!(out.dtype(), &DataType::Float64);
        let values: Vec<Option<f64>> = out.f64()?.into_iter().collect();
        assert_eq!(values, vec![Some(K / D); 3]);
        Ok(())
    }

    #[test]
    fn one_row_over_one_row_stays_one_row() -> PolarsResult<()> {
        // An aggregate divided by a literal keeps its length.
        let out = ieee_quotient(
            &[
                Series::new("s".into(), vec![K]),
                Series::new("d".into(), vec![D]),
            ],
            &op("div"),
        )?;
        assert_eq!(out.len(), 1);
        Ok(())
    }

    #[test]
    fn integers_promote_to_binary64() -> PolarsResult<()> {
        let out = ieee_quotient(
            &[
                Series::new("m".into(), vec![7_i64, 12]),
                Series::new("d".into(), vec![12_i64]),
            ],
            &op("div"),
        )?;
        let values: Vec<Option<f64>> = out.f64()?.into_iter().collect();
        assert_eq!(values, vec![Some(7.0 / 12.0), Some(1.0)]);
        Ok(())
    }

    #[test]
    fn list_over_one_divisor_divides_every_element() -> PolarsResult<()> {
        let numerator = list(vec![Some(vec![Some(K), Some(K)]), Some(vec![Some(1.892)])]);
        let divisor = Series::new("d".into(), vec![D]);
        let out = ieee_quotient(&[numerator, divisor], &op("div"))?;
        assert_eq!(
            list_values(&out),
            vec![
                Some(vec![Some(K / D), Some(K / D)]),
                Some(vec![Some(1.892 / D)])
            ]
        );
        Ok(())
    }

    #[test]
    fn list_over_per_row_divisor_and_list_over_list() -> PolarsResult<()> {
        let numerator = list(vec![
            Some(vec![Some(6.0), Some(9.0)]),
            Some(vec![Some(8.0)]),
        ]);
        let per_row = Series::new("d".into(), vec![3.0, 4.0]);
        let out = ieee_quotient(&[numerator.clone(), per_row], &op("div"))?;
        assert_eq!(
            list_values(&out),
            vec![Some(vec![Some(2.0), Some(3.0)]), Some(vec![Some(2.0)])]
        );
        let per_element = list(vec![
            Some(vec![Some(2.0), Some(3.0)]),
            Some(vec![Some(8.0)]),
        ]);
        let out = ieee_quotient(&[numerator, per_element], &op("div"))?;
        assert_eq!(
            list_values(&out),
            vec![Some(vec![Some(3.0), Some(3.0)]), Some(vec![Some(1.0)])]
        );
        Ok(())
    }

    #[test]
    fn number_over_list_divides_by_each_element() -> PolarsResult<()> {
        let out = ieee_quotient(
            &[
                Series::new("one".into(), vec![1.0]),
                list(vec![Some(vec![Some(1.04), Some(1.05)])]),
            ],
            &op("div"),
        )?;
        assert_eq!(
            list_values(&out),
            vec![Some(vec![Some(1.0 / 1.04), Some(1.0 / 1.05)])]
        );
        Ok(())
    }

    #[test]
    fn floordiv_and_mod_use_the_binary64_quotient() -> PolarsResult<()> {
        let numerator = list(vec![Some(vec![Some(0.3), Some(0.7)])]);
        let divisor = Series::new("d".into(), vec![0.1]);
        let floors = ieee_quotient(&[numerator.clone(), divisor.clone()], &op("floordiv"))?;
        assert_eq!(list_values(&floors), vec![Some(vec![Some(2.0), Some(6.0)])]);
        let rems = ieee_quotient(&[numerator, divisor], &op("mod"))?;
        assert_eq!(
            list_values(&rems),
            vec![Some(vec![Some(0.3 - 0.1 * 2.0), Some(0.7 - 0.1 * 6.0)])]
        );
        Ok(())
    }

    #[test]
    fn zero_divisor_follows_ieee() -> PolarsResult<()> {
        let numerator = Series::new("x".into(), vec![1.0, -1.0, 0.0]);
        let zero = Series::new("z".into(), vec![0.0]);
        let quotient = ieee_quotient(&[numerator.clone(), zero.clone()], &op("div"))?;
        let q: Vec<f64> = quotient.f64()?.into_no_null_iter().collect();
        assert_eq!(q[0], f64::INFINITY);
        assert_eq!(q[1], f64::NEG_INFINITY);
        assert!(q[2].is_nan());
        let floors = ieee_quotient(&[numerator.clone(), zero.clone()], &op("floordiv"))?;
        assert_eq!(floors.f64()?.get(0), Some(f64::INFINITY));
        let rems = ieee_quotient(&[numerator, zero], &op("mod"))?;
        assert!(rems.f64()?.into_no_null_iter().all(f64::is_nan));
        Ok(())
    }

    #[test]
    fn nulls_answer_where_they_stand() -> PolarsResult<()> {
        let numerator = list(vec![
            Some(vec![Some(K), None]),
            Some(vec![]),
            None,
            Some(vec![Some(K)]),
        ]);
        let divisor = Series::new("d".into(), vec![Some(D), Some(D), Some(D), None]);
        let out = ieee_quotient(&[numerator, divisor], &op("div"))?;
        assert_eq!(
            list_values(&out),
            vec![
                Some(vec![Some(K / D), None]),
                Some(vec![]),
                None,
                Some(vec![None]),
            ]
        );
        let flat = ieee_quotient(
            &[
                Series::new("x".into(), vec![Some(K), None]),
                Series::new("d".into(), vec![D]),
            ],
            &op("div"),
        )?;
        let values: Vec<Option<f64>> = flat.f64()?.into_iter().collect();
        assert_eq!(values, vec![Some(K / D), None]);
        Ok(())
    }

    #[test]
    fn the_one_pass_shapes_keep_their_nulls() -> PolarsResult<()> {
        // No null divisor, so each of these takes the flat one-pass route.
        let numerator = list(vec![Some(vec![Some(K), None]), None, Some(vec![])]);
        let out = ieee_quotient(
            &[numerator.clone(), Series::new("d".into(), vec![D, D, D])],
            &op("div"),
        )?;
        assert_eq!(
            list_values(&out),
            vec![Some(vec![Some(K / D), None]), None, Some(vec![])]
        );
        let out = ieee_quotient(
            &[Series::new("one".into(), vec![1.0]), numerator.clone()],
            &op("div"),
        )?;
        assert_eq!(
            list_values(&out),
            vec![Some(vec![Some(1.0 / K), None]), None, Some(vec![])]
        );
        let divisors = list(vec![Some(vec![None, Some(D)]), Some(vec![]), Some(vec![])]);
        let out = ieee_quotient(&[numerator, divisors], &op("div"))?;
        assert_eq!(
            list_values(&out),
            vec![Some(vec![None, None]), None, Some(vec![])]
        );
        Ok(())
    }

    #[test]
    fn mismatched_rows_and_periods_refuse() {
        let three = Series::new("x".into(), vec![1.0, 2.0, 3.0]);
        let two = Series::new("y".into(), vec![1.0, 2.0]);
        assert!(ieee_quotient(&[three, two], &op("div")).is_err());
        let a = list(vec![Some(vec![Some(1.0), Some(2.0)])]);
        let b = list(vec![Some(vec![Some(1.0)])]);
        assert!(ieee_quotient(&[a, b], &op("div")).is_err());
    }

    #[test]
    fn unknown_op_and_text_refuse() {
        let x = Series::new("x".into(), vec![1.0]);
        assert!(ieee_quotient(&[x.clone(), x.clone()], &op("pow")).is_err());
        let text = Series::new("t".into(), vec!["a"]);
        assert!(ieee_quotient(&[text, x], &op("div")).is_err());
    }

    #[test]
    fn empty_frames_keep_their_shape() -> PolarsResult<()> {
        let dtype = DataType::List(Box::new(DataType::Float64));
        let out = ieee_quotient(
            &[
                Series::new_empty("k".into(), &dtype),
                Series::new("d".into(), vec![D]),
            ],
            &op("div"),
        )?;
        assert!(out.is_empty());
        assert_eq!(out.dtype(), &dtype);
        let out = ieee_quotient(
            &[
                Series::new_empty("x".into(), &DataType::Float64),
                Series::new("d".into(), vec![D]),
            ],
            &op("div"),
        )?;
        assert!(out.is_empty());
        assert_eq!(out.dtype(), &DataType::Float64);
        Ok(())
    }
}

#[cfg(test)]
mod slice_tests {
    use super::*;

    /// Four policies of two periods each, sliced to the middle two: offsets
    /// 2..6 into an inner values array that still holds all eight values.
    fn middle_two_f64() -> Series {
        let rows: Vec<Series> = (0..4)
            .map(|r| Series::new("".into(), vec![r as f64 + 1.0, r as f64 + 2.0]))
            .collect();
        Series::new("x".into(), rows).slice(1, 2)
    }

    fn middle_two_i64() -> Series {
        let rows: Vec<Series> = (0..4_i64)
            .map(|r| Series::new("".into(), vec![r + 1, r + 2]))
            .collect();
        Series::new("ix".into(), rows).slice(1, 2)
    }

    #[test]
    fn a_side_reads_only_its_slices_own_values() -> PolarsResult<()> {
        for sliced in [middle_two_f64(), middle_two_i64()] {
            assert_eq!(sliced.list()?.get_inner().len(), 8);
            let side = side(&sliced, "test")?;
            assert_eq!(side.values.len(), 4, "{}", sliced.dtype());
            let lists = side.lists.as_ref().expect("a list side");
            assert_eq!(lists.offsets.as_slice(), &[0, 2, 4]);
            assert_eq!(side.values.values().as_slice(), &[2.0, 3.0, 3.0, 4.0]);
        }
        Ok(())
    }

    #[test]
    fn a_quotient_of_a_slice_holds_only_the_slices_values() -> PolarsResult<()> {
        let div = QuotientKwargs {
            op: "div".to_string(),
        };
        let per_policy = Series::new("d".into(), vec![2.0_f64, 4.0]);
        for (lhs, rhs) in [
            (middle_two_f64(), per_policy.clone()),
            (per_policy.clone(), middle_two_f64()),
            (middle_two_f64(), middle_two_i64()),
        ] {
            let out = ieee_quotient(&[lhs, rhs], &div)?;
            assert_eq!(out.list()?.get_inner().len(), 4);
        }
        let out = ieee_quotient(&[middle_two_f64(), per_policy], &div)?;
        let rows: Vec<Vec<f64>> = out
            .list()?
            .into_iter()
            .map(|row| row.unwrap().f64().unwrap().into_no_null_iter().collect())
            .collect();
        assert_eq!(rows, vec![vec![1.0, 1.5], vec![0.75, 1.0]]);
        Ok(())
    }
}
