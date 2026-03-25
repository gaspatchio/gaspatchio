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

/// Output type for list_pow: List<Float64>
fn list_pow_output(input_fields: &[Field]) -> PolarsResult<Field> {
    let name = input_fields
        .get(0)
        .map(|f| f.name().clone())
        .unwrap_or_else(|| PlSmallStr::from_static("list_pow"));

    // Always return List<Float64>
    Ok(Field::new(name, DataType::List(Box::new(DataType::Float64))))
}

#[polars_expr(output_type_func = list_int64_output)]
pub fn fill_series(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::FillSeriesKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::vector::fill_series(inputs, &kwargs)
}

/// PyO3 wrapper for list_pow - element-wise power on list columns
#[polars_expr(output_type_func = list_pow_output)]
pub fn list_pow(inputs: &[Series]) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::list_pow(inputs)
}

/// Output type for list_clip: List<Float64>
fn list_clip_output(input_fields: &[Field]) -> PolarsResult<Field> {
    let name = input_fields
        .first()
        .map(|f| f.name().clone())
        .unwrap_or_else(|| PlSmallStr::from_static("list_clip"));

    // Always return List<Float64>
    Ok(Field::new(name, DataType::List(Box::new(DataType::Float64))))
}

/// PyO3 wrapper for list_clip - element-wise clip on list columns with per-row bounds
#[polars_expr(output_type_func = list_clip_output)]
pub fn list_clip(inputs: &[Series]) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::list_clip(inputs)
}

/// Output type for accumulate: List<Float64>
fn accumulate_output(_: &[Field]) -> PolarsResult<Field> {
    Ok(Field::new(
        PlSmallStr::from_static("accumulate"),
        DataType::List(Box::new(DataType::Float64)),
    ))
}

/// PyO3 wrapper for accumulate - linear recurrence on list columns
#[polars_expr(output_type_func = accumulate_output)]
pub fn accumulate(inputs: &[Series]) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::accumulate(inputs)
}

/// Output type for list_conditional: List<Float64>
fn list_conditional_output(input_fields: &[Field]) -> PolarsResult<Field> {
    let name = input_fields
        .get(0)
        .map(|f| f.name().clone())
        .unwrap_or_else(|| PlSmallStr::from_static("list_conditional"));

    // Always return List<Float64>
    Ok(Field::new(name, DataType::List(Box::new(DataType::Float64))))
}

/// PyO3 wrapper for list_conditional - element-wise conditional on list columns
#[polars_expr(output_type_func = list_conditional_output)]
pub fn list_conditional(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::ConditionalKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::list_conditional(inputs, &kwargs)
}

/// Output type for rollforward: always Struct
/// The actual fields are determined at runtime by the kernel based on kwargs.
fn rollforward_output(_: &[Field]) -> PolarsResult<Field> {
    Ok(Field::new(
        PlSmallStr::from_static("rollforward"),
        DataType::Struct(vec![Field::new(
            PlSmallStr::from_static("result"),
            DataType::List(Box::new(DataType::Float64)),
        )]),
    ))
}

/// PyO3 wrapper for rollforward — non-linear account value projection
#[polars_expr(output_type_func = rollforward_output)]
pub fn rollforward(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::RollforwardKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::rollforward::rollforward(inputs, &kwargs)
}
