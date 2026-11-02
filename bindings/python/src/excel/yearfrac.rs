#![allow(clippy::unused_unit)]

// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

use gaspatchio_core_lib::excel::yearfrac::yearfrac_output_type as core_yearfrac_output_type;
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

fn yearfrac_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    // Use the same sophisticated type checking as the core implementation
    core_yearfrac_output_type(input_fields)
}

#[polars_expr(output_type_func = yearfrac_output_type)]
pub fn yearfrac(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::excel::YearFracKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::excel::yearfrac(inputs, &kwargs)
}
