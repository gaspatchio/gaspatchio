#![allow(clippy::unused_unit)]
use gaspatchio_core_lib::excel::pv::pv_output_type as core_pv_output_type;
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

fn pv_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    core_pv_output_type(input_fields)
}

#[polars_expr(output_type_func = pv_output_type)]
pub fn pv(inputs: &[Series], kwargs: gaspatchio_core_lib::excel::PvKwargs) -> PolarsResult<Series> {
    gaspatchio_core_lib::excel::pv(inputs, &kwargs)
}
