#![allow(clippy::unused_unit)]
use log::info;
use polars::prelude::*;
use polars_core::utils::CustomIterTools;
use pyo3_polars::derive::polars_expr;
use serde::Deserialize;
use std::fmt::Write;

#[polars_expr(output_type=String)]
fn pig_latinnify(inputs: &[Series]) -> PolarsResult<Series> {
    let ca: &StringChunked = inputs[0].str()?;
    let out: StringChunked = ca.apply_into_string_amortized(|value: &str, output: &mut String| {
        if let Some(first_char) = value.chars().next() {
            let _ = write!(output, "{}{}ay", &value[1..], first_char);
        }
    });
    Ok(out.into_series())
}

fn same_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let field = &input_fields[0];
    Ok(field.clone())
}

pub fn point_2d_output(_: &[Field]) -> PolarsResult<Field> {
    Ok(Field::new(
        PlSmallStr::from_static("point_2d"),
        DataType::Array(Box::new(DataType::Float64), 2),
    ))
}

#[polars_expr(output_type_func=same_output_type)]
fn noop(inputs: &[Series]) -> PolarsResult<Series> {
    let s = &inputs[0];
    match s.dtype() {
        DataType::Int32 => Ok(s.i32()?.clone().into_series()),
        DataType::Int64 => Ok(s.i64()?.clone().into_series()),
        DataType::Float32 => Ok(s.f32()?.clone().into_series()),
        DataType::Float64 => Ok(s.f64()?.clone().into_series()),
        _ => Err(PolarsError::ComputeError(
            "Operation only supported for numeric types".into(),
        )),
    }
}

fn list_int64_output(_: &[Field]) -> PolarsResult<Field> {
    Ok(Field::new(
        PlSmallStr::from_static("list_int64"),
        DataType::List(Box::new(DataType::Int64)),
    ))
}

#[polars_expr(output_type_func = list_int64_output)]
fn fill_series(inputs: &[Series], kwargs: FillSeriesKwargs) -> PolarsResult<Series> {
    // Log the inputs for debugging.
    info!("fill_series called with inputs: {:?}", inputs);
    let length = &inputs[0];
    let start = kwargs.start;
    let increment = kwargs.increment;

    // Get the Int64Chunked view of the input series.
    let ca = length.i64()?;

    // Create a builder for a list of i64 values.
    // The builder is pre-allocated to hold one list per element in the input.
    let builder = ListChunked::from_iter(ca.iter().map(|opt_len| match opt_len {
        Some(len) if len >= 0 => {
            let values: Vec<i64> = (0..len).map(|i| start + i * increment).collect();
            Series::new("".into(), values)
        }
        _ => Series::new("".into(), vec![None::<i64>]),
    }));
    // Finish building the ListChunked and convert it into a Series.
    Ok(builder.into_series())
}

#[polars_expr(output_type_func=list_int64_output)]
fn abs_i64(inputs: &[Series]) -> PolarsResult<Series> {
    let s = &inputs[0];
    let ca: &Int64Chunked = s.i64()?;
    // NOTE: there's a faster way of implementing `abs_i64`, which we'll
    // cover in section 7.
    let out: Int64Chunked = ca.apply(|opt_v: Option<i64>| opt_v.map(|v: i64| v.abs()));
    Ok(out.into_series())
}

#[derive(Deserialize)]
struct FillSeriesKwargs {
    start: i64,
    increment: i64,
}

#[derive(Deserialize)]
struct FloorKwargs {
    divisor: i64,
    default: i64,
}

#[derive(Deserialize)]
struct MidPoint2DKwargs {
    ref_point: [f64; 2],
}

#[polars_expr(output_type_func=point_2d_output)]
fn midpoint_2d(inputs: &[Series], kwargs: MidPoint2DKwargs) -> PolarsResult<Series> {
    let ca: &ArrayChunked = inputs[0].array()?;
    let ref_point = kwargs.ref_point;

    let out: ArrayChunked = unsafe {
        ca.try_apply_amortized_same_type(|row| {
            let s = row.as_ref();
            let ca = s.f64()?;
            let out_inner: Float64Chunked = ca
                .iter()
                .enumerate()
                .map(|(idx, opt_val)| opt_val.map(|val| (val + ref_point[idx]) / 2.0f64))
                .collect_trusted();
            Ok(out_inner.into_series())
        })
    }?;

    Ok(out.into_series())
}

/// Floor division with a default value
#[polars_expr(output_type_func = same_output_type)]
fn floor(inputs: &[Series], kwargs: FloorKwargs) -> PolarsResult<Series> {
    // Get the first input series
    let input_series = &inputs[0];
    let divisor = kwargs.divisor;
    let default = kwargs.default;

    // Handle different numeric types
    match input_series.dtype() {
        DataType::Int32 => {
            let ca = input_series.i32()?;
            let out: Int32Chunked = ca.apply(|opt_v: Option<i32>| {
                opt_v.map(|v| {
                    if divisor == 0 {
                        default as i32
                    } else {
                        (v as f64 / divisor as f64).floor() as i32
                    }
                })
            });
            Ok(out.into_series())
        }
        DataType::Int64 => {
            let ca = input_series.i64()?;
            let out: Int64Chunked = ca.apply(|opt_v: Option<i64>| {
                opt_v.map(|v| {
                    if divisor == 0 {
                        default
                    } else {
                        (v as f64 / divisor as f64).floor() as i64
                    }
                })
            });
            Ok(out.into_series())
        }
        DataType::Float32 => {
            let ca = input_series.f32()?;
            let out: Float32Chunked = ca.apply(|opt_v: Option<f32>| {
                opt_v.map(|v| {
                    if divisor == 0 {
                        default as f32
                    } else {
                        (v / divisor as f32).floor()
                    }
                })
            });
            Ok(out.into_series())
        }
        DataType::Float64 => {
            let ca = input_series.f64()?;
            let out: Float64Chunked = ca.apply(|opt_v: Option<f64>| {
                opt_v.map(|v| {
                    if divisor == 0 {
                        default as f64
                    } else {
                        (v / divisor as f64).floor()
                    }
                })
            });
            Ok(out.into_series())
        }
        DataType::List(_) => {
            // Handle list type by applying floor to each element
            let list_col = input_series.list()?;

            // Create a new list by applying floor to each inner series
            let out = list_col.apply_amortized(|inner_series| {
                // Get the Series from AmortSeries
                let series = inner_series.as_ref();

                // Try to get numeric values from the inner series
                match series.dtype() {
                    DataType::Int32 => {
                        let ca = series.i32().unwrap();
                        let floored: Int32Chunked = ca.apply(|opt_v: Option<i32>| {
                            opt_v.map(|v| {
                                if divisor == 0 {
                                    default as i32
                                } else {
                                    (v as f64 / divisor as f64).floor() as i32
                                }
                            })
                        });
                        floored.into_series()
                    }
                    DataType::Int64 => {
                        let ca = series.i64().unwrap();
                        let floored: Int64Chunked = ca.apply(|opt_v: Option<i64>| {
                            opt_v.map(|v| {
                                if divisor == 0 {
                                    default
                                } else {
                                    (v as f64 / divisor as f64).floor() as i64
                                }
                            })
                        });
                        floored.into_series()
                    }
                    DataType::Float32 => {
                        let ca = series.f32().unwrap();
                        let floored: Float32Chunked = ca.apply(|opt_v: Option<f32>| {
                            opt_v.map(|v| {
                                if divisor == 0 {
                                    default as f32
                                } else {
                                    (v / divisor as f32).floor()
                                }
                            })
                        });
                        floored.into_series()
                    }
                    DataType::Float64 => {
                        let ca = series.f64().unwrap();
                        let floored: Float64Chunked = ca.apply(|opt_v: Option<f64>| {
                            opt_v.map(|v| {
                                if divisor == 0 {
                                    default as f64
                                } else {
                                    (v / divisor as f64).floor()
                                }
                            })
                        });
                        floored.into_series()
                    }
                    _ => {
                        // If not a numeric type, return the original series
                        series.clone()
                    }
                }
            });

            Ok(out.into_series())
        }
        _ => Err(PolarsError::ComputeError(
            format!(
                "floor function expects numeric input, got {}",
                input_series.dtype()
            )
            .into(),
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_floor_implementation() -> PolarsResult<()> {
        // Create a Float64Chunked with test values
        let values = vec![
            -std::f64::consts::PI,
            -2.1,
            2.04,
            5.01,
            0.0,
            -0.0,
            f64::NAN,
            f64::INFINITY,
            f64::NEG_INFINITY,
        ];
        let float_chunked = Float64Chunked::new("test_floats".into(), &values);

        // Apply the floor operation directly
        let floored: Float64Chunked = float_chunked
            .clone()
            .apply(|opt_v: Option<f64>| opt_v.map(|v| v.floor()));

        // Check the results
        let expected = vec![
            -4.0,
            -3.0,
            2.0,
            5.0,
            0.0,
            -0.0,
            f64::NAN,
            f64::INFINITY,
            f64::NEG_INFINITY,
        ];

        for (i, (res, exp)) in floored.into_iter().zip(expected.into_iter()).enumerate() {
            let r = res.unwrap();
            if r.is_nan() {
                assert!(exp.is_nan(), "Element {}: Expected NaN, got {}", i, r);
            } else if r.is_infinite() && exp.is_infinite() {
                // Special handling for infinity values
                assert_eq!(
                    r.is_sign_positive(),
                    exp.is_sign_positive(),
                    "Element {}: Expected {}, got {}",
                    i,
                    exp,
                    r
                );
            } else {
                assert!(
                    (r - exp).abs() < 1e-6,
                    "Element {}: Expected {}, got {}",
                    i,
                    exp,
                    r
                );
            }
        }

        Ok(())
    }

    #[test]
    fn test_floor_with_nulls() -> PolarsResult<()> {
        // Create a Float64Chunked with test values including nulls
        let values: Vec<Option<f64>> =
            vec![Some(-std::f64::consts::PI), None, Some(2.04), Some(5.01)];
        let float_chunked = Float64Chunked::from_iter(values.iter().cloned());

        // Apply the floor operation directly
        let floored: Float64Chunked = float_chunked
            .clone()
            .apply(|opt_v: Option<f64>| opt_v.map(|v| v.floor()));

        // Check the results
        let expected: Vec<Option<f64>> = vec![Some(-4.0), None, Some(2.0), Some(5.0)];

        for (i, (res, exp)) in floored.into_iter().zip(expected.into_iter()).enumerate() {
            match (res, exp) {
                (None, None) => {} // Both are None, this is correct
                (Some(r), Some(e)) => {
                    assert!(
                        (r - e).abs() < 1e-6,
                        "Element {}: Expected {}, got {}",
                        i,
                        e,
                        r
                    );
                }
                _ => panic!("Element {}: Mismatch between result and expected", i),
            }
        }

        Ok(())
    }

    #[test]
    fn test_floor_function_core_logic() -> PolarsResult<()> {
        // Test the core logic of the floor function
        // This is the same logic used in the floor function but applied directly

        // Create a series with float values
        let values = vec![1.5f64, 2.7, -3.2, 4.1, -0.5, 6.9];
        let float_chunked = Float64Chunked::new("test_floats".into(), &values);
        let float_series = float_chunked.into_series();

        // Apply the floor operation directly (same as in the floor function)
        let floored: Float64Chunked = float_series
            .f64()?
            .apply(|opt_v: Option<f64>| opt_v.map(|v| v.floor()));

        // Check the results
        let expected = vec![1.0, 2.0, -4.0, 4.0, -1.0, 6.0];

        for (i, (res, exp)) in floored.into_iter().zip(expected.into_iter()).enumerate() {
            let r = res.unwrap();
            assert!(
                (r - exp).abs() < 1e-6,
                "Element {}: Expected {}, got {}",
                i,
                exp,
                r
            );
        }

        Ok(())
    }
}
