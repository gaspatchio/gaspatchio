// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Cuts a list column down to the rows a plugin was handed before it reads the flat values
// ABOUTME: A streamed slice keeps the whole column's inner values; reading them is per-morsel waste

//! The rows a plugin was handed, and only those.
//!
//! Polars' streaming engine -- `ActuarialFrame.collect`'s default -- hands an
//! elementwise plugin one slice of a column per morsel. A sliced list column
//! keeps the whole column's inner values array and moves only its offsets, so
//! a kernel that reads the flat values (casting them, checking them for
//! nulls, copying them out) does that for every policy in the frame once per
//! morsel: cost of morsels x column, not of the column. Polars' own list
//! kernels trim to the slice first; [`own_rows`] is that step for ours.
//!
//! The same engine broadcasts a literal before a plugin sees it; the
//! in-memory engine does not. [`rows_per_policy`] gives every kernel the
//! streaming engine's operands either way.

use polars::prelude::*;

/// Return `series` with every list cut down to the elements its rows use.
///
/// A list column whose offsets already start at zero and end at its inner
/// length is returned as it is (a cheap reference-counted clone). A sliced
/// one comes back with offsets starting at zero over just its own elements,
/// without copying them. Any other column is returned unchanged.
pub fn own_rows(series: &Series) -> Series {
    series
        .trim_lists_to_normalized_offsets()
        .unwrap_or_else(|| series.clone())
}

/// Every operand of one per-policy calculation, at one row per policy.
///
/// The in-memory engine hands a plugin a literal -- `pl.lit(date(2025, 1, 1))`,
/// a list literal -- as a single row beside the frame's columns. The streaming
/// engine broadcasts it first. A kernel that walked its operands in step would
/// answer the first policy only, or refuse, in memory, and every policy in
/// streaming. Here a one-row operand beside taller ones is repeated for every
/// policy: always when it is a list, and when `repeat_single_values` is set
/// also when it is one value -- for the kernels that do not broadcast one
/// themselves. Every operand comes back cut to its own rows ([`own_rows`]).
///
/// A frame with no policies is left as it is.
///
/// # Errors
/// Refuses an operand whose height is neither one nor the frame's.
pub fn rows_per_policy(inputs: &[Series], repeat_single_values: bool) -> PolarsResult<Vec<Series>> {
    let trimmed: Vec<Series> = inputs.iter().map(own_rows).collect();
    let height = trimmed.iter().map(|s| s.len()).max().unwrap_or(0);
    if height <= 1 || trimmed.iter().any(|s| s.is_empty()) {
        return Ok(trimmed);
    }
    trimmed
        .into_iter()
        .map(|operand| {
            let rows = operand.len();
            if rows == height {
                return Ok(operand);
            }
            if rows != 1 {
                return Err(policy_height_error(height, rows));
            }
            if repeat_single_values || matches!(operand.dtype(), DataType::List(_)) {
                return Ok(operand.new_from_index(0, height));
            }
            Ok(operand)
        })
        .collect()
}

/// The refusal for an operand that neither covers every policy nor has one
/// row per policy.
pub fn policy_height_error(policies: usize, rows: usize) -> PolarsError {
    PolarsError::ComputeError(
        format!(
            "a per-policy calculation pairs {policies} policies with an operand of {rows} \
             rows; each operand needs one row per policy, or a single row that covers them all"
        )
        .into(),
    )
}

/// Why a kernel's refusal names no row: the row it could count is its batch's.
///
/// The engine hands an elementwise plugin one batch of rows per call and no
/// offset with it, so a position counted here is a position in the batch.
/// Under the default streaming engine that is not the frame's row: a policy
/// at frame row 1 was reported as `row 0`, and a reader who opened row 0
/// found nothing wrong there. The error report finds the policy from the
/// frame itself, where the row is known.
const NO_FRAME_ROW: &str = "No frame row is named: the engine hands this calculation a batch of \
                            rows at a time, and a row counted within a batch is not the frame's.";

/// The refusal for a per-period operand whose number of periods is not its
/// policy's, in the words every list kernel uses.
///
/// The first line names the operand and what it was measured against, and
/// nothing that varies from policy to policy: it is the same in every engine
/// and every batch, which is what lets the collect-time replay match the
/// failure to the calculation that raised it. The two lengths are that
/// policy's, and go on the line after (graph-artifact spec 11.1.18: two
/// lists must have equal lengths within each policy).
pub fn period_count_message(
    reference: &str,
    reference_len: usize,
    operand: &str,
    operand_len: usize,
) -> String {
    format!(
        "mismatched inner list lengths in one policy: {operand} against {reference}\n\
         {reference}={reference_len}, {operand}={operand_len} in that policy. Each per-period \
         operand needs its policy's own number of periods, and none is padded or cut to fit. \
         {NO_FRAME_ROW}"
    )
}

/// [`period_count_message`] as the `ComputeError` a kernel refuses with.
pub fn period_count_error(
    reference: &str,
    reference_len: usize,
    operand: &str,
    operand_len: usize,
) -> PolarsError {
    PolarsError::ComputeError(
        period_count_message(reference, reference_len, operand, operand_len).into(),
    )
}

/// Refuse a per-period operand whose number of periods is not its policy's.
///
/// # Errors
/// [`period_count_error`] when the two lengths differ.
#[inline]
pub fn same_periods(
    reference: &str,
    reference_len: usize,
    operand: &str,
    operand_len: usize,
) -> PolarsResult<()> {
    if reference_len == operand_len {
        return Ok(());
    }
    Err(period_count_error(
        reference,
        reference_len,
        operand,
        operand_len,
    ))
}

/// The refusal for a per-policy value a kernel cannot read past, null for
/// one policy, named by what it is and never by a row of the batch.
pub fn null_for_one_policy(what: &str) -> PolarsError {
    PolarsError::ComputeError(format!("{what} is null for one policy\n{NO_FRAME_ROW}").into())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Does the message print a row number -- `row 0`, `row 2500` -- anywhere?
    fn names_a_row_number(message: &str) -> bool {
        message.match_indices("row ").any(|(at, _)| {
            message[at + "row ".len()..]
                .chars()
                .next()
                .is_some_and(|c| c.is_ascii_digit())
        })
    }

    #[test]
    fn a_period_count_refusal_names_the_operand_and_both_lengths_and_no_row() {
        let message = period_count_error("left", 3, "then", 2).to_string();
        let first = message.lines().next().unwrap_or_default();
        assert!(
            first.ends_with("mismatched inner list lengths in one policy: then against left"),
            "{message}"
        );
        assert!(
            message.contains("left=3, then=2 in that policy."),
            "{message}"
        );
        assert!(!names_a_row_number(&message), "{message}");
        assert!(same_periods("left", 3, "then", 3).is_ok());
        assert_eq!(
            same_periods("left", 3, "then", 2).unwrap_err().to_string(),
            message
        );
    }

    #[test]
    fn the_first_line_is_the_same_whichever_policy_misfits() {
        // The replay matches a failure by its first line, and two policies
        // that misfit by different lengths are one failure.
        let one = period_count_message("left", 3, "then", 2);
        let other = period_count_message("left", 120, "then", 119);
        assert_eq!(one.lines().next(), other.lines().next());
    }

    #[test]
    fn a_null_refusal_says_one_policy_and_no_row() {
        let message = null_for_one_policy("the exponent of a power").to_string();
        assert!(
            message.contains("the exponent of a power is null for one policy"),
            "{message}"
        );
        assert!(!names_a_row_number(&message), "{message}");
    }

    fn four_rows() -> Series {
        let rows: Vec<Series> = (0..4)
            .map(|r| Series::new("".into(), vec![r as f64, r as f64 + 0.5]))
            .collect();
        Series::new("x".into(), rows)
    }

    #[test]
    fn a_sliced_list_keeps_only_its_own_elements() -> PolarsResult<()> {
        let slice = four_rows().slice(1, 2);
        // The slice as Polars hands it over still carries all eight values.
        assert_eq!(slice.list()?.get_inner().len(), 8);

        let owned = own_rows(&slice);
        let list = owned.list()?;
        assert_eq!(list.get_inner().len(), 4);
        assert_eq!(list.offsets()?.as_slice(), &[0, 2, 4]);
        assert!(owned.equals(&slice));
        Ok(())
    }

    #[test]
    fn a_one_row_list_is_repeated_for_every_policy() -> PolarsResult<()> {
        let frame = four_rows();
        let literal = four_rows().slice(2, 1);
        let value = Series::new("v".into(), vec![9.0_f64]);
        let out = rows_per_policy(&[frame.clone(), literal.clone(), value.clone()], false)?;
        assert!(out[0].equals(&frame));
        assert_eq!(out[1].len(), 4);
        for row in 0..4 {
            assert!(out[1].slice(row, 1).equals(&literal));
        }
        // One value is left for the kernel to broadcast unless asked.
        assert_eq!(out[2].len(), 1);
        let out = rows_per_policy(&[frame, value], true)?;
        assert!(out[1].equals(&Series::new("v".into(), vec![9.0_f64; 4])));
        Ok(())
    }

    #[test]
    fn another_height_is_refused_and_an_empty_frame_left_alone() -> PolarsResult<()> {
        let err = rows_per_policy(&[four_rows(), four_rows().slice(0, 2)], false).unwrap_err();
        assert!(
            err.to_string()
                .contains("pairs 4 policies with an operand of 2 rows"),
            "{err}"
        );
        let empty = four_rows().slice(0, 0);
        let literal = four_rows().slice(0, 1);
        let out = rows_per_policy(&[empty, literal], true)?;
        assert_eq!((out[0].len(), out[1].len()), (0, 1));
        Ok(())
    }

    #[test]
    fn a_whole_column_and_a_per_policy_column_are_left_alone() -> PolarsResult<()> {
        let whole = four_rows();
        assert!(own_rows(&whole).equals(&whole));
        assert_eq!(own_rows(&whole).list()?.get_inner().len(), 8);

        let per_policy = Series::new("s".into(), vec![1.0_f64, 2.0, 3.0]).slice(1, 2);
        assert!(own_rows(&per_policy).equals(&per_policy));
        Ok(())
    }
}

#[cfg(test)]
mod one_row_tests {
    //! A one-row operand -- a literal, as the in-memory engine hands it over --
    //! answers every policy as that operand repeated for each policy does.
    use super::super::{accumulate, list_clip, list_conditional, list_pow, ConditionalKwargs};
    use crate::excel::{irr, pv, yearfrac, IrrKwargs, PvKwargs, YearFracKwargs};
    use polars::prelude::*;

    fn lists(rows: &[[f64; 3]]) -> Series {
        let rows: Vec<Series> = rows
            .iter()
            .map(|r| Series::new("".into(), r.to_vec()))
            .collect();
        Series::new("x".into(), rows)
    }

    fn three_policies() -> Series {
        lists(&[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])
    }

    fn one_row() -> Series {
        lists(&[[2.0, 5.0, 8.0]])
    }

    fn repeated() -> Series {
        lists(&[[2.0, 5.0, 8.0]; 3])
    }

    fn same(left: PolarsResult<Series>, right: PolarsResult<Series>) {
        let (left, right) = (left.unwrap(), right.unwrap());
        assert_eq!(left.len(), 3);
        assert!(left.equals_missing(&right), "{left:?} != {right:?}");
    }

    #[test]
    fn a_numeric_condition_reads_a_one_row_list_on_any_side_for_every_policy() {
        let kw = ConditionalKwargs {
            operator: "gt".to_string(),
            unknown_is_nan: false,
        };
        let x = three_policies();
        let four = Series::new("".into(), &[4.0_f64]);
        let zero = Series::new("".into(), &[0.0_f64]);
        for (one, all) in [
            (
                [x.clone(), one_row(), x.clone(), zero.clone()],
                [x.clone(), repeated(), x.clone(), zero.clone()],
            ),
            (
                [x.clone(), four.clone(), one_row(), zero.clone()],
                [x.clone(), four.clone(), repeated(), zero.clone()],
            ),
            (
                [x.clone(), four.clone(), zero.clone(), one_row()],
                [x.clone(), four.clone(), zero.clone(), repeated()],
            ),
            (
                [one_row(), x.clone(), one_row(), one_row()],
                [repeated(), x.clone(), repeated(), repeated()],
            ),
        ] {
            same(list_conditional(&one, &kw), list_conditional(&all, &kw));
        }
    }

    #[test]
    fn a_power_and_a_recurrence_read_a_one_row_list_for_every_policy() {
        let x = three_policies();
        same(
            list_pow(&[x.clone(), one_row()]),
            list_pow(&[x.clone(), repeated()]),
        );
        same(
            list_pow(&[one_row(), x.clone()]),
            list_pow(&[repeated(), x.clone()]),
        );
        let initial = Series::new("i".into(), vec![1.0_f64, 2.0, 3.0]);
        same(
            accumulate(&[initial.clone(), one_row(), x.clone()]),
            accumulate(&[initial.clone(), repeated(), x.clone()]),
        );
        same(
            accumulate(&[initial.clone(), x.clone(), one_row()]),
            accumulate(&[initial, x, repeated()]),
        );
    }

    #[test]
    fn a_clip_and_a_present_value_read_a_one_row_list_for_every_policy() {
        let x = three_policies();
        let upper = Series::new("u".into(), vec![10.0_f64, 10.0, 10.0]);
        same(
            list_clip(&[one_row(), x.clone(), upper.clone()]),
            list_clip(&[repeated(), x.clone(), upper]),
        );
        let kw = PvKwargs {
            fv: Some(0.0),
            typ: Some(0),
        };
        let nper = Series::new("n".into(), vec![10.0_f64, 20.0, 30.0]);
        let pmt = Series::new("p".into(), vec![100.0_f64, 200.0, 300.0]);
        let rates = |rows: usize| lists(&vec![[0.02, 0.05, 0.08]; rows]);
        same(
            pv(&[rates(1), nper.clone(), pmt.clone()], &kw),
            pv(&[rates(3), nper, pmt], &kw),
        );
    }

    #[test]
    fn a_year_fraction_and_an_irr_read_one_value_for_every_policy() {
        let days = |d: &[i32]| {
            Series::new("d".into(), d.to_vec())
                .cast(&DataType::Date)
                .unwrap()
        };
        let start = days(&[18_262, 18_628, 18_993]);
        let valuation = days(&[20_089]);
        let kw = YearFracKwargs { basis: Some(1) };
        same(
            yearfrac(&[start.clone(), valuation.clone()], &kw),
            yearfrac(&[start.clone(), days(&[20_089; 3])], &kw),
        );
        same(
            yearfrac(&[valuation, start.clone()], &kw),
            yearfrac(&[days(&[20_089; 3]), start], &kw),
        );
        let cashflows = lists(&[
            [-100.0, 60.0, 60.0],
            [-100.0, 50.0, 70.0],
            [-100.0, 10.0, 120.0],
        ]);
        let kw = IrrKwargs { guess: None };
        same(
            irr(
                &[cashflows.clone(), Series::new("g".into(), &[0.1_f64])],
                &kw,
            ),
            irr(&[cashflows, Series::new("g".into(), vec![0.1_f64; 3])], &kw),
        );
    }
}
