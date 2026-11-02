#![allow(clippy::unused_unit)]

// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

use gaspatchio_core_lib::excel::round::excel_round_output_type as core_excel_round_output_type;
use gaspatchio_core_lib::excel::ExcelRoundKwargs;
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

fn excel_round_output_type(
    input_fields: &[Field],
    kwargs: ExcelRoundKwargs,
) -> PolarsResult<Field> {
    core_excel_round_output_type(input_fields, &kwargs)
}

/// PyO3 wrapper for `.excel.round`: Excel's ROUND over the value's fifteen
/// significant digits, half away from zero -- the rule the rollforward
/// kernel's rounding shares.
#[polars_expr(output_type_func_with_kwargs = excel_round_output_type)]
pub fn excel_round(inputs: &[Series], kwargs: ExcelRoundKwargs) -> PolarsResult<Series> {
    gaspatchio_core_lib::excel::excel_round_series(inputs, &kwargs)
}
