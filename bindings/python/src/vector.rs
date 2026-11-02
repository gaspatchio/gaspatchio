#![allow(clippy::unused_unit)]

// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

fn list_int64_output(_: &[Field]) -> PolarsResult<Field> {
    Ok(Field::new(
        PlSmallStr::from_static("list_int64"),
        DataType::List(Box::new(DataType::Int64)),
    ))
}

/// Output type for a binary numeric kernel: List<Float64> when either operand
/// is a list column, Float64 when neither is. Named after the first operand.
fn float_or_float_list_output(input_fields: &[Field]) -> PolarsResult<Field> {
    let name = input_fields
        .first()
        .map(|f| f.name().clone())
        .unwrap_or_else(|| PlSmallStr::from_static("value"));
    let any_list = input_fields
        .iter()
        .any(|f| matches!(f.dtype(), DataType::List(_)));
    let dtype = if any_list {
        DataType::List(Box::new(DataType::Float64))
    } else {
        DataType::Float64
    };
    Ok(Field::new(name, dtype))
}

#[polars_expr(output_type_func = list_int64_output)]
pub fn fill_series(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::FillSeriesKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::vector::fill_series(inputs, &kwargs)
}

/// PyO3 wrapper for list_pow - element-wise power on list columns, or a
/// per-row base raised to a list of exponents
#[polars_expr(output_type_func = float_or_float_list_output)]
pub fn list_pow(inputs: &[Series]) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::list_pow(inputs)
}

/// Run the IEEE quotient kernel for one named operation.
fn ieee_quotient_for(inputs: &[Series], op: &str) -> PolarsResult<Series> {
    let kwargs = gaspatchio_core_lib::QuotientKwargs { op: op.to_string() };
    gaspatchio_core_lib::polars_functions::ieee_quotient(inputs, &kwargs)
}

// Three symbols rather than one kernel with an `op` keyword: Polars renders a
// plugin call by its symbol and leaves its keywords out, so the symbol is the
// only place a rendered plan -- the engine's account an audit export carries,
// the walk-through a reader is shown -- can say which quotient ran.

/// PyO3 wrapper for `/` over numbers: IEEE division, one per element
#[polars_expr(output_type_func = float_or_float_list_output)]
pub fn ieee_div(inputs: &[Series]) -> PolarsResult<Series> {
    ieee_quotient_for(inputs, "div")
}

/// PyO3 wrapper for `//` over numbers: the floor of the IEEE quotient
#[polars_expr(output_type_func = float_or_float_list_output)]
pub fn ieee_floordiv(inputs: &[Series]) -> PolarsResult<Series> {
    ieee_quotient_for(inputs, "floordiv")
}

/// PyO3 wrapper for `%` over numbers: `l - r * floor(l / r)` in binary64
#[polars_expr(output_type_func = float_or_float_list_output)]
pub fn ieee_mod(inputs: &[Series]) -> PolarsResult<Series> {
    ieee_quotient_for(inputs, "mod")
}

/// Output type for norm_cdf: Float64, or List<Float64> for a list column.
fn norm_cdf_output(input_fields: &[Field]) -> PolarsResult<Field> {
    gaspatchio_core_lib::polars_functions::norm_cdf_output_type(input_fields)
}

/// PyO3 wrapper for `norm_cdf`: the standard normal distribution function,
/// `0.5 * erfc(-x / sqrt 2)`, one value at a time (section 11.1.12)
#[polars_expr(output_type_func = norm_cdf_output)]
pub fn norm_cdf(inputs: &[Series]) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::norm_cdf_series(inputs)
}

/// Output type for list_clip: List<Float64>
fn list_clip_output(input_fields: &[Field]) -> PolarsResult<Field> {
    let name = input_fields
        .first()
        .map(|f| f.name().clone())
        .unwrap_or_else(|| PlSmallStr::from_static("list_clip"));

    // Always return List<Float64>
    Ok(Field::new(
        name,
        DataType::List(Box::new(DataType::Float64)),
    ))
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

/// Output type for list_conditional: List<Float64>, or List<String> when a
/// branch (then/otherwise, fields 2/3) is string-valued — the kernel's Utf8
/// path (GSP-110). Mixed string/numeric branches are rejected at run time;
/// declaring String here whenever either branch is string-like keeps the
/// schema consistent with every input the kernel accepts.
fn list_conditional_output(input_fields: &[Field]) -> PolarsResult<Field> {
    let name = input_fields
        .first()
        .map(|f| f.name().clone())
        .unwrap_or_else(|| PlSmallStr::from_static("list_conditional"));

    fn is_string_like(field: &Field) -> bool {
        let dt = match field.dtype() {
            DataType::List(inner) => inner.as_ref(),
            dt => dt,
        };
        matches!(
            dt,
            DataType::String | DataType::Categorical(_, _) | DataType::Enum(_, _)
        )
    }
    let stringy = input_fields.get(2).map(is_string_like).unwrap_or(false)
        || input_fields.get(3).map(is_string_like).unwrap_or(false);
    let inner = if stringy {
        DataType::String
    } else {
        DataType::Float64
    };
    Ok(Field::new(name, DataType::List(Box::new(inner))))
}

/// PyO3 wrapper for list_conditional - element-wise conditional on list columns
#[polars_expr(output_type_func = list_conditional_output)]
pub fn list_conditional(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::ConditionalKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::list_conditional(inputs, &kwargs)
}

/// Output type for rollforward: Struct with one List<Float64> field per
/// capture slot, named ``"{state}@{point}"`` — derived from kwargs at lazy-plan
/// time so ``plugin.struct.field("av@eop")`` resolves against a real schema.
fn rollforward_output(
    _input_fields: &[Field],
    kwargs: gaspatchio_core_lib::RollforwardKwargs,
) -> PolarsResult<Field> {
    let states = kwargs
        .ir
        .get("states")
        .and_then(|v| v.as_array())
        .ok_or_else(|| {
            PolarsError::ComputeError(
                "rollforward: kwargs.ir.states missing or not an array".into(),
            )
        })?;
    let state_names: Vec<String> = states
        .iter()
        .map(|s| {
            s.get("name")
                .and_then(|v| v.as_str())
                .map(str::to_string)
                .ok_or_else(|| {
                    PolarsError::ComputeError("rollforward: ir.states[i].name missing".into())
                })
        })
        .collect::<PolarsResult<Vec<_>>>()?;
    let points = kwargs
        .ir
        .get("points")
        .and_then(|v| v.as_array())
        .ok_or_else(|| {
            PolarsError::ComputeError(
                "rollforward: kwargs.ir.points missing or not an array".into(),
            )
        })?;
    let point_names: Vec<String> = points
        .iter()
        .map(|p| {
            p.as_str().map(str::to_string).ok_or_else(|| {
                PolarsError::ComputeError("rollforward: ir.points entry not str".into())
            })
        })
        .collect::<PolarsResult<Vec<_>>>()?;

    let mut fields: Vec<Field> = kwargs
        .captures_resolved
        .iter()
        .map(|cap| {
            let name = format!("{}@{}", state_names[cap.state], point_names[cap.point]);
            Field::new(
                PlSmallStr::from(name.as_str()),
                DataType::List(Box::new(DataType::Float64)),
            )
        })
        .collect();

    // Increment fields (track_increments): the same helper the kernel's
    // emission uses, so the declared schema and the emitted struct cannot
    // drift apart. One per Op — a structural step under its reserved
    // `{kind}@{ordinal}` key, everything else under its label.
    for (_, key) in gaspatchio_core_lib::polars_functions::rollforward::tracked_increments(&kwargs)?
    {
        let name = format!("increment_{key}");
        fields.push(Field::new(
            PlSmallStr::from(name.as_str()),
            DataType::List(Box::new(DataType::Float64)),
        ));
    }

    Ok(Field::new(
        PlSmallStr::from_static("rollforward"),
        DataType::Struct(fields),
    ))
}

/// PyO3 wrapper for rollforward — the IR-driven rollforward kernel.
#[polars_expr(output_type_func_with_kwargs = rollforward_output)]
pub fn rollforward(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::RollforwardKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::rollforward::rollforward_kernel(inputs, &kwargs)
}

/// Output type for curve_eval: mirrors input shape (List<Float64> for list input, Float64 for scalar).
fn curve_eval_output(input_fields: &[Field]) -> PolarsResult<Field> {
    let field = &input_fields[0];
    let dtype = match field.dtype() {
        DataType::List(_) => DataType::List(Box::new(DataType::Float64)),
        _ => DataType::Float64,
    };
    Ok(Field::new(field.name().clone(), dtype))
}

/// PyO3 wrapper for curve_eval — yield-curve evaluation over list columns of year-fractions.
#[polars_expr(output_type_func = curve_eval_output)]
pub fn curve_eval(
    inputs: &[Series],
    kwargs: gaspatchio_core_lib::polars_functions::CurveEvalKwargs,
) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::curve_eval::curve_eval(inputs, &kwargs)
}
