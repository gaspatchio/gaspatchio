#![allow(clippy::unused_unit)]
use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

fn list_int64_output(_: &[Field]) -> PolarsResult<Field> {
    Ok(Field::new(
        PlSmallStr::from_static("list_int64"),
        DataType::List(Box::new(DataType::Int64)),
    ))
}

fn same_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let field = &input_fields[0];
    Ok(field.clone())
}

fn int64_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let field = &input_fields[0];
    let name = field.name();
    let output_type = match field.dtype() {
        DataType::List(_) => DataType::List(Box::new(DataType::Int64)),
        _ => DataType::Int64,
    };
    Ok(Field::new(name.clone(), output_type))
}

#[polars_expr(output_type_func = list_int64_output)]
pub fn fill_series(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::FillSeriesKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::vector::fill_series(inputs, kwargs)
}

/// Floor division with a default value
#[polars_expr(output_type_func = same_output_type)]
fn floor(inputs: &[Series], kwargs: gaspatchio_core_lib::FloorKwargs) -> PolarsResult<Series> {
    // Call the implementation from vector.rs
    gaspatchio_core_lib::polars_functions::vector::floor(inputs, kwargs)
}

/// Round numeric values to a specified number of decimal places.
#[polars_expr(output_type_func = same_output_type)]
fn round(inputs: &[Series], kwargs: gaspatchio_core_lib::RoundKwargs) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::vector::round(inputs, kwargs)
}

/// Round numeric values to the nearest integer (Int64).
#[polars_expr(output_type_func = int64_output_type)]
fn round_to_int(inputs: &[Series]) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::vector::round_to_int(inputs)
}
