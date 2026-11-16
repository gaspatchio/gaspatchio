// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Applies a present value's lost periods: null from a cashflow's last hole backwards
// ABOUTME: A book with no null cashflow gets its totals back untouched, at no per-element cost

use polars::prelude::*;

use super::slices::{rows_per_policy, same_periods};

fn float_runs(total: &Series) -> PolarsResult<Series> {
    let dtype = DataType::List(Box::new(DataType::Float64));
    if total.dtype() == &dtype {
        return Ok(total.clone());
    }
    total.cast(&dtype)
}

fn no_cashflow_is_null(cashflows: &ListChunked) -> bool {
    cashflows.null_count() == 0
        && cashflows
            .downcast_iter()
            .all(|chunk| chunk.values().null_count() == 0)
}

/// Returns each run of totals, null from its cashflows' last hole backwards.
///
/// A reverse fold skips a null, so a position at or before a missing cashflow
/// has lost a period the total should have held (section 11.1.21). Positions
/// after the last hole keep the value they had, to the last bit.
///
/// # Arguments
///
/// * `inputs` - The list column of totals and the list column of cashflows.
///
/// # Returns
///
/// The totals as `List(Float64)`.
///
/// # Errors
///
/// Returns a `PolarsError` if either input is not a list column, or if a
/// policy's totals and cashflows differ in length.
pub fn list_null_from_hole_back(inputs: &[Series]) -> PolarsResult<Series> {
    polars_ensure!(
        inputs.len() == 2,
        ComputeError: "list_null_from_hole_back takes the totals and the cashflows"
    );
    let rows = rows_per_policy(inputs, true)?;
    let totals = float_runs(&rows[0])?;
    let cashflows = rows[1].list()?;
    if no_cashflow_is_null(cashflows) {
        return Ok(totals);
    }

    let total_runs = totals.list()?;
    let mut builder = ListPrimitiveChunkedBuilder::<Float64Type>::new(
        totals.name().clone(),
        total_runs.len(),
        total_runs.get_inner().len(),
        DataType::Float64,
    );
    for (total, cashflow) in total_runs.amortized_iter().zip(cashflows.amortized_iter()) {
        let (Some(total), Some(cashflow)) = (total, cashflow) else {
            builder.append_null();
            continue;
        };
        let (total, cashflow) = (total.as_ref(), cashflow.as_ref());
        same_periods("the total", total.len(), "the cashflows", cashflow.len())?;
        let holes = cashflow.is_null();
        let kept_from = holes
            .into_iter()
            .enumerate()
            .filter(|(_, is_hole)| *is_hole == Some(true))
            .last()
            .map_or(0, |(position, _)| position + 1);
        let values: Vec<Option<f64>> = total
            .f64()?
            .into_iter()
            .enumerate()
            .map(|(position, value)| if position < kept_from { None } else { value })
            .collect();
        builder.append_iter(values.into_iter());
    }
    Ok(builder.finish().into_series())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn runs(values: Vec<Option<Vec<Option<f64>>>>) -> Series {
        ListChunked::from_iter(
            values
                .into_iter()
                .map(|run| run.map(|run| Series::new("".into(), run))),
        )
        .into_series()
    }

    #[test]
    fn test_no_hole_returns_the_totals_untouched() -> PolarsResult<()> {
        let totals = runs(vec![Some(vec![Some(-0.0), Some(f64::NAN)])]);
        let cashflows = runs(vec![Some(vec![Some(1.0), Some(1.0)])]);

        let answered = list_null_from_hole_back(&[totals, cashflows])?;

        let run = answered.list()?.get_as_series(0).expect("one policy");
        assert_eq!(
            run.f64()?.get(0).map(f64::to_bits),
            Some((-0.0f64).to_bits())
        );
        assert!(run.f64()?.get(1).is_some_and(f64::is_nan));
        Ok(())
    }

    #[test]
    fn test_null_from_the_last_hole_back() -> PolarsResult<()> {
        let totals = runs(vec![
            Some(vec![Some(4.0), Some(3.0), Some(2.0), Some(1.0)]),
            Some(vec![Some(9.0), Some(8.0)]),
            None,
        ]);
        let cashflows = runs(vec![
            Some(vec![None, Some(1.0), None, Some(1.0)]),
            Some(vec![Some(1.0), Some(1.0)]),
            None,
        ]);

        let answered = list_null_from_hole_back(&[totals, cashflows])?;

        let held = answered.list()?;
        let first = held.get_as_series(0).expect("first policy");
        let first: Vec<Option<f64>> = first.f64()?.into_iter().collect();
        assert_eq!(first, vec![None, None, None, Some(1.0)]);
        let second = held.get_as_series(1).expect("second policy");
        let second: Vec<Option<f64>> = second.f64()?.into_iter().collect();
        assert_eq!(second, vec![Some(9.0), Some(8.0)]);
        assert!(held.get_as_series(2).is_none());
        Ok(())
    }

    #[test]
    fn test_runs_of_two_lengths_are_refused() {
        let totals = runs(vec![Some(vec![Some(1.0)])]);
        let cashflows = runs(vec![Some(vec![None, Some(1.0)])]);

        assert!(list_null_from_hole_back(&[totals, cashflows]).is_err());
    }
}
