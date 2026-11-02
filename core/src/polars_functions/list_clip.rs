// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Element-wise clip operation for list columns (list.clip(lower, upper) with column bounds)
// ABOUTME: Eliminates EXPLODE/GROUP_BY pattern for clipping list elements with per-row bounds

use polars::prelude::*;

use super::list_pow::as_float_lists;
use super::slices::{null_for_one_policy, own_rows, same_periods};

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

    /// Read one row of the result back as a plain `Vec`, nulls included.
    fn row(result: &Series, idx: usize) -> Vec<Option<f64>> {
        let row = result.list().unwrap().get_as_series(idx).unwrap();
        row.f64().unwrap().iter().collect()
    }

    /// The whole of the crossed-bounds rule: the lower bound is tested first.
    ///
    /// `lower = 8`, `upper = 2`. Nothing satisfies both, and the engine answers
    /// the lower bound below it and the upper bound from there up. Composing
    /// `max` then `min` would answer `2.0` seven times.
    #[test]
    fn test_crossed_bounds_answer_lower_below_it_and_upper_from_there_up() {
        let values = ListChunked::from_iter([Some(Series::new(
            "".into(),
            vec![0.0, 1.0, 2.0, 5.0, 8.0, 9.0, 10.0],
        ))]);
        let lower = Series::new("lower".into(), vec![8.0]);
        let upper = Series::new("upper".into(), vec![2.0]);

        let result = list_clip(&[values.into_series(), lower, upper]).unwrap();

        assert_eq!(
            row(&result, 0),
            vec![
                Some(8.0),
                Some(8.0),
                Some(8.0),
                Some(8.0),
                Some(2.0),
                Some(2.0),
                Some(2.0),
            ]
        );
    }

    /// The same rule through the list-bounds path, crossed on one row only.
    #[test]
    fn test_crossed_list_bounds_cross_one_row_at_a_time() {
        let values = ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.0, 5.0, 10.0])),
            Some(Series::new("".into(), vec![1.0, 5.0, 10.0])),
        ]);
        // Row 0 crosses on every element; row 1 does not cross at all.
        let lower = ListChunked::from_iter([
            Some(Series::new("".into(), vec![8.0, 8.0, 8.0])),
            Some(Series::new("".into(), vec![2.0, 2.0, 2.0])),
        ]);
        let upper = ListChunked::from_iter([
            Some(Series::new("".into(), vec![2.0, 2.0, 2.0])),
            Some(Series::new("".into(), vec![8.0, 8.0, 8.0])),
        ]);

        let result = list_clip(&[
            values.into_series(),
            lower.into_series(),
            upper.into_series(),
        ])
        .unwrap();

        assert_eq!(row(&result, 0), vec![Some(8.0), Some(8.0), Some(2.0)]);
        assert_eq!(row(&result, 1), vec![Some(2.0), Some(5.0), Some(8.0)]);
    }

    /// The mixed paths -- one bound a list, the other a per-row scalar.
    #[test]
    fn test_crossed_bounds_hold_on_the_mixed_bound_paths() {
        let values = ListChunked::from_iter([Some(Series::new("".into(), vec![1.0, 5.0, 10.0]))]);
        let lower_list =
            ListChunked::from_iter([Some(Series::new("".into(), vec![8.0, 8.0, 8.0]))]);
        let upper_list =
            ListChunked::from_iter([Some(Series::new("".into(), vec![2.0, 2.0, 2.0]))]);

        let list_lower = list_clip(&[
            values.clone().into_series(),
            lower_list.into_series(),
            Series::new("upper".into(), vec![2.0]),
        ])
        .unwrap();
        assert_eq!(row(&list_lower, 0), vec![Some(8.0), Some(8.0), Some(2.0)]);

        let list_upper = list_clip(&[
            values.into_series(),
            Series::new("lower".into(), vec![8.0]),
            upper_list.into_series(),
        ])
        .unwrap();
        assert_eq!(row(&list_upper, 0), vec![Some(8.0), Some(8.0), Some(2.0)]);
    }

    /// Bounds that touch: every value becomes the one value both allow.
    #[test]
    fn test_touching_bounds_collapse_every_value_onto_them() {
        let values = ListChunked::from_iter([Some(Series::new("".into(), vec![0.0, 5.0, 10.0]))]);
        let lower = Series::new("lower".into(), vec![5.0]);
        let upper = Series::new("upper".into(), vec![5.0]);

        let result = list_clip(&[values.into_series(), lower, upper]).unwrap();

        assert_eq!(row(&result, 0), vec![Some(5.0), Some(5.0), Some(5.0)]);
    }

    /// A NaN passes neither comparison, so it comes back NaN rather than a bound.
    #[test]
    fn test_a_nan_value_comes_back_nan() {
        let values =
            ListChunked::from_iter([Some(Series::new("".into(), vec![f64::NAN, 1.0, 10.0]))]);
        let lower = Series::new("lower".into(), vec![2.0]);
        let upper = Series::new("upper".into(), vec![8.0]);

        let result = list_clip(&[values.into_series(), lower, upper]).unwrap();
        let out = row(&result, 0);

        assert!(out[0].unwrap().is_nan());
        assert_eq!(out[1], Some(2.0));
        assert_eq!(out[2], Some(8.0));
    }

    /// An absent bound is spelled by its infinity and excludes nothing.
    #[test]
    fn test_an_infinite_bound_excludes_nothing_on_its_side() {
        let values = ListChunked::from_iter([Some(Series::new("".into(), vec![-5.0, 5.0, 15.0]))]);

        let floored = list_clip(&[
            values.clone().into_series(),
            Series::new("lower".into(), vec![0.0]),
            Series::new("upper".into(), vec![f64::INFINITY]),
        ])
        .unwrap();
        assert_eq!(row(&floored, 0), vec![Some(0.0), Some(5.0), Some(15.0)]);

        let capped = list_clip(&[
            values.into_series(),
            Series::new("lower".into(), vec![f64::NEG_INFINITY]),
            Series::new("upper".into(), vec![10.0]),
        ])
        .unwrap();
        assert_eq!(row(&capped, 0), vec![Some(-5.0), Some(5.0), Some(10.0)]);
    }

    /// Two rows of values, for the height rules below.
    fn two_rows() -> ListChunked {
        ListChunked::from_iter([
            Some(Series::new("".into(), vec![0.0, 5.0, 10.0])),
            Some(Series::new("".into(), vec![1.0, 2.0, 3.0])),
        ])
    }

    /// A bound of one row covers every row, whichever shape it came in.
    ///
    /// The per-row side always did. The per-element side answered the first
    /// row and then read past the end of its own iterator, which reads as a
    /// null bound row and answers an EMPTY LIST -- the silent wrong answer
    /// this rule exists to forbid.
    #[test]
    fn test_a_one_row_bound_covers_every_row_from_either_shape() {
        let per_element = list_clip(&[
            two_rows().into_series(),
            ListChunked::from_iter([Some(Series::new("".into(), vec![2.0, 2.0, 2.0]))])
                .into_series(),
            Series::new("upper".into(), vec![8.0]),
        ])
        .unwrap();

        let per_row = list_clip(&[
            two_rows().into_series(),
            Series::new("lower".into(), vec![2.0]),
            Series::new("upper".into(), vec![8.0]),
        ])
        .unwrap();

        assert_eq!(row(&per_element, 0), vec![Some(2.0), Some(5.0), Some(8.0)]);
        assert_eq!(row(&per_element, 1), vec![Some(2.0), Some(2.0), Some(3.0)]);
        assert_eq!(row(&per_element, 1), row(&per_row, 1));
    }

    /// Any other height is refused by name, from either shape.
    ///
    /// `pl.Expr.clip` refuses the same input -- "arguments for `clip(min)`
    /// have different lengths (2 != 3)" -- and the two shapes refuse it with
    /// the same words as each other.
    #[test]
    fn test_a_bound_that_is_neither_one_row_nor_the_height_is_refused() {
        let per_element = list_clip(&[
            two_rows().into_series(),
            ListChunked::from_iter([
                Some(Series::new("".into(), vec![2.0, 2.0, 2.0])),
                Some(Series::new("".into(), vec![2.0, 2.0, 2.0])),
                Some(Series::new("".into(), vec![2.0, 2.0, 2.0])),
            ])
            .into_series(),
            Series::new("upper".into(), vec![8.0]),
        ])
        .unwrap_err()
        .to_string();

        let per_row = list_clip(&[
            two_rows().into_series(),
            Series::new("lower".into(), vec![2.0, 2.0, 2.0]),
            Series::new("upper".into(), vec![8.0]),
        ])
        .unwrap_err()
        .to_string();

        assert!(
            per_element.contains("lower bound for list_clip has 3 rows, but the values have 2"),
            "{per_element}"
        );
        assert_eq!(per_element, per_row);
    }

    /// The upper bound is named as the upper bound, and refused before a row.
    #[test]
    fn test_the_refusal_names_which_bound_is_the_wrong_height() {
        let err = list_clip(&[
            two_rows().into_series(),
            Series::new("lower".into(), vec![2.0]),
            Series::new("upper".into(), vec![8.0, 8.0, 8.0]),
        ])
        .unwrap_err()
        .to_string();

        assert!(
            err.contains("upper bound for list_clip has 3 rows, but the values have 2"),
            "{err}"
        );
    }

    /// A null row of a one-row bound still means null, not a height offence.
    #[test]
    fn test_a_one_row_bound_that_is_null_answers_an_empty_list() {
        let result = list_clip(&[
            two_rows().into_series(),
            ListChunked::from_iter([None::<Series>]).into_series(),
            Series::new("upper".into(), vec![8.0]),
        ])
        .unwrap();
        let rows = result.list().unwrap();

        assert_eq!(rows.get_as_series(0).unwrap().len(), 0);
        assert_eq!(rows.get_as_series(1).unwrap().len(), 0);
    }

    // An unpromotable inner dtype -- `List(Struct)`, whose element cast was
    // once `row.f64().unwrap()` and panicked -- is pinned from Python instead,
    // in tests/polars_backend/test_list_clip_bound_height.py, because the two
    // build profiles refuse it in different places. `List(Struct)` reaches the
    // element cast at all only in release: polars' own list cast relabels the
    // inner dtype without converting it and catches that with a
    // `debug_assert_eq!` (polars-core 0.53.0 chunked_array/cast.rs), which
    // aborts a `cargo test` build before this kernel sees a row. The shipped
    // extension is built `--release`, so the message the caller gets is the
    // one that test drives.
}

/// A list column as the `List<Float64>` the row loop reads, cut to its own rows.
///
/// A streamed slice keeps the whole column's inner values; the promotion
/// reads the slice's own, so a morsel never converts its neighbours' periods.
fn float_lists(series: &Series) -> PolarsResult<Series> {
    own_rows(series).cast(&DataType::List(Box::new(DataType::Float64)))
}

/// Hold one value between its bounds, exactly the way `pl.Expr.clip` does.
///
/// A value below the lower bound becomes the lower bound; a value at or above
/// the lower bound that is above the upper bound becomes the upper bound;
/// anything else comes back unchanged. The lower bound is tested first, and
/// that order is the whole of the rule when the bounds cross. With
/// `lower > upper` no value satisfies both, and the engine answers `lower`
/// below the lower bound and `upper` from there up: `clip(8, 2)` over
/// `[1, 5, 10]` is `[8, 8, 2]`. Composing `max` then `min` instead answers
/// `upper` everywhere -- `[2, 2, 2]` -- which is what this kernel used to give
/// and what the engine never gave.
///
/// An absent bound is spelled by its infinity, which no comparison passes, so
/// a one-sided clip falls straight through the branch it does not have. A NaN
/// value passes neither comparison either and comes back NaN, which is again
/// what the engine does; `f64::max` returns its other operand against a NaN
/// and so used to swallow the NaN into a bound.
#[inline]
fn clip_one(value: f64, lower: f64, upper: f64) -> f64 {
    if value < lower {
        lower
    } else if value > upper {
        upper
    } else {
        value
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
/// A bound of one row covers every row of the values, the way `pl.Expr.clip`
/// broadcasts one; a bound of the values' own height is read row by row. Any
/// other height is refused rather than read until it runs out.
///
/// # Errors
/// Returns error if:
/// - Values is not a List type
/// - A bound has neither one row nor one row per row of the values
/// - Inner list lengths don't match bounds (for list bounds)
/// - The list's elements are not numbers (a struct, text, a nested list)
pub fn list_clip(inputs: &[Series]) -> PolarsResult<Series> {
    // A one-row list of values beside taller bounds -- a literal the in-memory
    // engine hands over unbroadcast -- is repeated for every policy, as the
    // streaming engine reads it. A one-row bound is covered below.
    let height = inputs.iter().map(|s| s.len()).max().unwrap_or(0);
    let values_in = match inputs.first() {
        Some(values) if values.len() == 1 && height > 1 => values.new_from_index(0, height),
        Some(values) => values.clone(),
        None => polars_bail!(ComputeError: "list_clip takes values and two bounds"),
    };
    let listed = values_in
        .list()
        .map_err(|_| PolarsError::ComputeError("values must be List dtype for list_clip".into()))?;
    // Refuse an element type that is not a number BEFORE the cast, by name.
    // Polars casts a struct to Float64 field by field and hands back a struct,
    // which a debug build's own assertion in cast_list turns into a panic and
    // a release build carries on with until a later row read refuses it. The
    // refusal has to be the contract in every build, so it is made here.
    let inner = listed.inner_dtype();
    if !(inner.is_primitive_numeric() || inner.is_bool() || inner.is_null()) {
        polars_bail!(
            ComputeError:
            "invalid series dtype: list_clip clips numbers, and these lists hold {}",
            inner
        );
    }
    // Promote the values and both bounds to Float64 once, here, instead of a
    // row at a time inside the loop that reads them.
    let values = float_lists(&values_in)?;
    let values_list = values.list()?;
    let lower = BoundColumn::new(&inputs[1], "lower")?;
    let upper = BoundColumn::new(&inputs[2], "upper")?;

    // Whether a bound covers the values at all is settled once, here, for both
    // bound shapes, before any row is read.
    let height = values_list.len();
    lower.covers(height)?;
    upper.covers(height)?;

    // A list bound of the values' own height is walked in lockstep with them; a
    // list bound of one row is read once, here, and covers every row. A per-row
    // bound is read by row index and has no iterator to advance.
    let mut lower_rows = lower.stepped_rows().map(ListChunked::amortized_iter);
    let mut upper_rows = upper.stepped_rows().map(ListChunked::amortized_iter);
    let lower_shared = lower.shared_row();
    let upper_shared = upper.shared_row();

    let clipped = values_list
        .amortized_iter()
        .enumerate()
        .map(|(idx, row)| {
            // A list bound yields `Option<AmortSeries>` per row, so the row is
            // flattened: absent because there is no list bound, and absent
            // because that row of one is null, are answered the same way below.
            let lower_step = lower_rows.as_mut().and_then(Iterator::next).flatten();
            let upper_step = upper_rows.as_mut().and_then(Iterator::next).flatten();
            let lower_row = lower_step
                .as_ref()
                .map(|row| row.as_ref())
                .or(lower_shared.as_ref());
            let upper_row = upper_step
                .as_ref()
                .map(|row| row.as_ref())
                .or(upper_shared.as_ref());
            let lower_bound = lower.at_row(idx, lower_row)?;
            let upper_bound = upper.at_row(idx, upper_row)?;

            // A null row of values answers null: "a null value stays null"
            // (graph-artifact spec 11.1.3), and the native route a literal
            // bound takes already answers so. It used to answer an empty run,
            // a policy with no periods.
            let Some(row) = row else {
                return Ok(None);
            };
            // A null row of a list bound still answers an empty run: the spec
            // states nothing for a null bound (11.1.3).
            let (Some(lower_bound), Some(upper_bound)) = (lower_bound, upper_bound) else {
                return Ok(Some(Series::new_empty("".into(), &DataType::Float64)));
            };

            clip_row(row.as_ref().f64()?, &lower_bound, &upper_bound).map(Some)
        })
        .collect::<PolarsResult<ListChunked>>()?;

    // A batch whose every row of values is null keeps the advertised type.
    as_float_lists(clipped)
}

/// One clip bound as the caller supplied it, promoted to Float64 once.
///
/// Either bound reaches `list_clip` as a list column -- one value per element --
/// or as an ordinary column of one value per row, so there are four bound
/// shapes. They differ only in where a row's bound comes from, which is all this
/// type holds; the clipping itself is one loop over the rows.
struct BoundColumn {
    /// Where a row's bound comes from: its own elements, or one value for it.
    shape: BoundShape,
    /// How many rows this bound carries, whichever shape it came in.
    rows: usize,
    /// Whether this bound's single row covers every row of the values.
    ///
    /// A bound of one row is one statement about all of them, which is what
    /// `pl.lit(8.0)` and `pl.lit([8.0, 8.0, 8.0])` each are. Settled in `new`
    /// rather than asked of the shape, because the row loop reads it per row.
    broadcast: bool,
    /// How the bound is spelled back to the caller when it is refused.
    name: &'static str,
}

/// Where a bound carries its values: one per element, or one per row.
enum BoundShape {
    /// One value per element, as the rows of a `List<Float64>` column.
    PerElement(ListChunked),
    /// One value per row.
    PerRow(Float64Chunked),
}

impl BoundColumn {
    /// Promote a bound column to the Float64 shape the row loop reads.
    ///
    /// `name` is how the bound is spelled back to the caller when its height
    /// does not cover the values, or when a row of it is null.
    fn new(bound: &Series, name: &'static str) -> PolarsResult<Self> {
        let shape = if matches!(bound.dtype(), DataType::List(_)) {
            let rows = float_lists(bound)?;
            BoundShape::PerElement(rows.list()?.clone())
        } else {
            let cast = bound.cast(&DataType::Float64)?;
            BoundShape::PerRow(cast.f64()?.clone())
        };
        let rows = match &shape {
            BoundShape::PerElement(rows) => rows.len(),
            BoundShape::PerRow(values) => values.len(),
        };
        Ok(Self {
            shape,
            rows,
            broadcast: rows == 1,
            name,
        })
    }

    /// Refuse a bound that neither covers every row nor carries one row each.
    ///
    /// This is the engine's own rule, and the reason to keep it is that a
    /// caller can already see it: `pl.Expr.clip` broadcasts a bound of one row
    /// over the whole column, and refuses any other height by name --
    /// "arguments for `clip(min)` have different lengths (2 != 3)". Reading a
    /// bound until it runs out, and answering the rows past its end with empty
    /// lists, is the one thing neither the engine nor this kernel does.
    fn covers(&self, height: usize) -> PolarsResult<()> {
        let rows = self.rows;
        if rows == 1 || rows == height {
            return Ok(());
        }
        let name = self.name;
        Err(PolarsError::ComputeError(
            format!(
                "{name} bound for list_clip has {rows} rows, but the values have \
                 {height}; a bound carries one row for each of them, or a single \
                 row that covers them all"
            )
            .into(),
        ))
    }

    /// The rows of a per-element bound, to be taken alongside the values.
    ///
    /// A per-element bound that covers every row has no iterator to advance:
    /// its one row is read once, by `shared_row`, rather than in step.
    fn stepped_rows(&self) -> Option<&ListChunked> {
        match &self.shape {
            BoundShape::PerElement(rows) if !self.broadcast => Some(rows),
            _ => None,
        }
    }

    /// The one row a per-element bound covers every row of the values with.
    ///
    /// `None` when there is no such row to read -- a per-row bound, a bound
    /// taken in step, or a single row that is itself null.
    fn shared_row(&self) -> Option<Series> {
        match &self.shape {
            BoundShape::PerElement(rows) if self.broadcast => rows.get_as_series(0),
            _ => None,
        }
    }

    /// This bound as row `idx` reads it, given that row of the bound.
    ///
    /// `None` says the bound is null for this row, which only a list bound can
    /// be: a per-row bound that is null is refused by name instead, because
    /// there are no elements underneath it to carry the absence.
    fn at_row<'a>(
        &self,
        idx: usize,
        row: Option<&'a Series>,
    ) -> PolarsResult<Option<RowBound<'a>>> {
        match &self.shape {
            BoundShape::PerElement(_) => row.map(|row| Ok(RowBound::Each(row.f64()?))).transpose(),
            BoundShape::PerRow(values) => {
                let name = self.name;
                let value = values
                    .get(if self.broadcast { 0 } else { idx })
                    .ok_or_else(|| null_for_one_policy(&format!("the {name} bound of a clip")))?;
                Ok(Some(RowBound::Same(value)))
            }
        }
    }
}

/// One clip bound as a single row reads it.
enum RowBound<'a> {
    /// The same value for every element of the row.
    Same(f64),
    /// One value per element of the row.
    Each(&'a Float64Chunked),
}

impl<'a> RowBound<'a> {
    /// The row's bound values, when the bound carries one per element.
    fn each(&self) -> Option<&'a Float64Chunked> {
        match self {
            Self::Same(_) => None,
            Self::Each(values) => Some(values),
        }
    }

    /// The one value that covers the whole row, when one does.
    fn same(&self) -> Option<f64> {
        match self {
            Self::Same(value) => Some(*value),
            Self::Each(_) => None,
        }
    }
}

/// Clip one row of values against the bounds resolved for that row.
///
/// A per-element bound must be exactly as long as the row it bounds. A null on
/// any side of an element -- the value, either bound -- leaves that element
/// null, which is what a bound that is null at one element means.
fn clip_row(values: &Float64Chunked, lower: &RowBound, upper: &RowBound) -> PolarsResult<Series> {
    for (name, bound) in [("lower bound", lower.each()), ("upper bound", upper.each())] {
        if let Some(bound) = bound {
            same_periods("values", values.len(), name, bound.len())?;
        }
    }

    // A per-element bound is walked in step with the values, the way the values
    // are; a bound that covers the whole row has no iterator to advance and is
    // read from `same` instead. Exactly one of the two answers, per bound.
    let mut lower_each = lower.each().map(|values| values.iter());
    let mut upper_each = upper.each().map(|values| values.iter());
    let (lower_same, upper_same) = (lower.same(), upper.same());

    let clipped: Vec<Option<f64>> = values
        .iter()
        .map(|value| {
            let lower = lower_each.as_mut().and_then(Iterator::next).flatten();
            let upper = upper_each.as_mut().and_then(Iterator::next).flatten();
            Some(clip_one(
                value?,
                lower.or(lower_same)?,
                upper.or(upper_same)?,
            ))
        })
        .collect();

    Ok(Float64Chunked::from_iter(clipped).into_series())
}

#[cfg(test)]
mod refusal_tests {
    use super::*;

    fn values() -> Series {
        ListChunked::from_iter([
            Some(Series::new("".into(), vec![1.0, 2.0])),
            Some(Series::new("".into(), vec![1.0, 2.0, 3.0])),
        ])
        .into_series()
    }

    #[test]
    fn a_short_bound_list_is_refused_by_both_lengths_and_no_row() {
        let short = ListChunked::from_iter([
            Some(Series::new("".into(), vec![0.0, 0.0])),
            Some(Series::new("".into(), vec![0.0, 0.0])),
        ])
        .into_series();
        let upper = Series::new("".into(), vec![9.0_f64]);
        let err = list_clip(&[values(), short, upper])
            .unwrap_err()
            .to_string();
        assert!(
            err.contains("mismatched inner list lengths in one policy: lower bound against values"),
            "{err}"
        );
        assert!(
            err.contains("values=3, lower bound=2 in that policy."),
            "{err}"
        );
        assert!(!err.contains("at row"), "{err}");
    }

    #[test]
    fn a_null_row_of_values_is_null_not_an_empty_run() -> PolarsResult<()> {
        // Spec 11.1.3: a null value stays null. The base answered [].
        let values = ListChunked::from_iter([Some(Series::new("".into(), vec![1.0, 12.0])), None])
            .into_series();
        let lower = Series::new("".into(), vec![2.0_f64, 2.0]);
        let upper = Series::new("".into(), vec![9.0_f64, 9.0]);
        let out = list_clip(&[values, lower.clone(), upper.clone()])?;
        let list = out.list()?;
        assert_eq!(out.dtype(), &DataType::List(Box::new(DataType::Float64)));
        assert!(list.get_as_series(1).is_none());
        assert_eq!(
            list.get_as_series(0)
                .unwrap()
                .f64()?
                .into_iter()
                .collect::<Vec<_>>(),
            vec![Some(2.0), Some(9.0)]
        );
        let all_null = ListChunked::from_iter([None::<Series>, None]).into_series();
        let out = list_clip(&[all_null, lower, upper])?;
        assert_eq!(out.dtype(), &DataType::List(Box::new(DataType::Float64)));
        assert_eq!(out.null_count(), 2);
        Ok(())
    }

    #[test]
    fn a_null_bound_is_refused_for_one_policy_and_no_row() {
        let lower = Series::new("".into(), vec![Some(0.0), None]);
        let upper = Series::new("".into(), vec![9.0_f64]);
        let err = list_clip(&[values(), lower, upper])
            .unwrap_err()
            .to_string();
        assert!(
            err.contains("the lower bound of a clip is null for one policy"),
            "{err}"
        );
        assert!(!err.contains("at row"), "{err}");
    }
}

#[cfg(test)]
mod slice_tests {
    use super::*;

    fn middle_two(as_int: bool) -> Series {
        let rows: Vec<Series> = (0..4_i64)
            .map(|r| {
                if as_int {
                    Series::new("".into(), vec![r, r + 5])
                } else {
                    Series::new("".into(), vec![r as f64, r as f64 + 5.0])
                }
            })
            .collect();
        Series::new("x".into(), rows).slice(1, 2)
    }

    #[test]
    fn the_promoted_values_are_the_slices_own() -> PolarsResult<()> {
        for as_int in [false, true] {
            let sliced = middle_two(as_int);
            assert_eq!(sliced.list()?.get_inner().len(), 8);
            let promoted = float_lists(&sliced)?;
            let inner = promoted.list()?.get_inner();
            assert_eq!(
                inner.f64()?.into_no_null_iter().collect::<Vec<_>>(),
                vec![1.0, 6.0, 2.0, 7.0]
            );
        }
        Ok(())
    }

    #[test]
    fn a_slice_clips_as_the_whole_column_clips_those_rows() -> PolarsResult<()> {
        let rows: Vec<Series> = (0..4_i64)
            .map(|r| Series::new("".into(), vec![r, r + 5]))
            .collect();
        let whole = Series::new("x".into(), rows);
        let lower = Series::new("lo".into(), vec![1.0_f64]);
        let upper = Series::new("hi".into(), vec![6.0_f64]);
        let all = list_clip(&[whole.clone(), lower.clone(), upper.clone()])?;
        let part = list_clip(&[whole.slice(1, 2), lower, upper])?;
        assert!(part.equals_missing(&all.slice(1, 2)));
        assert_eq!(part.list()?.get_inner().len(), 4);
        Ok(())
    }
}
