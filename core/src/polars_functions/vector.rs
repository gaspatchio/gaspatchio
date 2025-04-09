#![allow(clippy::unused_unit)]
use log::info;
use polars::prelude::*;
use serde::Deserialize;

pub fn fill_series(inputs: &[Series], kwargs: FillSeriesKwargs) -> PolarsResult<Series> {
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
    info!("fill_series completed");
    Ok(builder.into_series())
}

#[derive(Deserialize)]
pub struct FillSeriesKwargs {
    pub start: i64,
    pub increment: i64,
}

#[derive(Deserialize, Clone, Copy)]
pub struct FloorKwargs {
    pub divisor: i64,
    pub default: i64,
}

#[derive(Deserialize, Clone, Copy)]
pub struct RoundKwargs {
    #[serde(default)] // Defaults to 0 if not provided
    pub decimal_places: i32,
}

pub fn floor(inputs: &[Series], kwargs: FloorKwargs) -> PolarsResult<Series> {
    // Get the first input series
    let input_series = &inputs[0];
    let divisor = kwargs.divisor;
    let default = kwargs.default;

    info!("floor called with inputs: {:?}", inputs);

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
            info!("floor completed");
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

pub fn round(inputs: &[Series], kwargs: RoundKwargs) -> PolarsResult<Series> {
    let input_series = &inputs[0];
    let decimal_places = kwargs.decimal_places;
    let factor = 10.0_f64.powi(decimal_places); // Precompute factor for floats

    info!(
        "round called with decimal_places: {}, factor: {}",
        decimal_places, factor
    );

    match input_series.dtype() {
        DataType::Int32 => {
            // Rounding decimals doesn't apply directly to integers.
            // We'll perform standard rounding to the nearest integer.
            // A warning could be logged if decimal_places > 0.
            let ca = input_series.i32()?;
            let out: Int32Chunked = ca.apply_values(|v| (v as f64).round() as i32);
            Ok(out.into_series())
        }
        DataType::Int64 => {
            let ca = input_series.i64()?;
            let out: Int64Chunked = ca.apply_values(|v| (v as f64).round() as i64);
            Ok(out.into_series())
        }
        DataType::Float32 => {
            let factor = factor as f32; // Use f32 factor
            let ca = input_series.f32()?;
            let out: Float32Chunked = ca.apply_values(|v| (v * factor).round() / factor);
            Ok(out.into_series())
        }
        DataType::Float64 => {
            let ca = input_series.f64()?;
            let out: Float64Chunked = ca.apply_values(|v| (v * factor).round() / factor);
            Ok(out.into_series())
        }
        DataType::List(_) => {
            let list_col = input_series.list()?;
            let out = list_col.apply_amortized(|inner_series| {
                let series = inner_series.as_ref();
                match series.dtype() {
                    DataType::Int32 => {
                        let ca = series.i32().unwrap();
                        let rounded: Int32Chunked = ca.apply_values(|v| (v as f64).round() as i32);
                        rounded.into_series()
                    }
                    DataType::Int64 => {
                        let ca = series.i64().unwrap();
                        let rounded: Int64Chunked = ca.apply_values(|v| (v as f64).round() as i64);
                        rounded.into_series()
                    }
                    DataType::Float32 => {
                        let factor = factor as f32;
                        let ca = series.f32().unwrap();
                        let rounded: Float32Chunked =
                            ca.apply_values(|v| (v * factor).round() / factor);
                        rounded.into_series()
                    }
                    DataType::Float64 => {
                        let ca = series.f64().unwrap();
                        let rounded: Float64Chunked =
                            ca.apply_values(|v| (v * factor).round() / factor);
                        rounded.into_series()
                    }
                    _ => series.clone(),
                }
            });
            info!("round completed for List type");
            Ok(out.into_series())
        }
        _ => Err(PolarsError::ComputeError(
            format!(
                "round function expects numeric input, got {}",
                input_series.dtype()
            )
            .into(),
        )),
    }
}

pub fn round_to_int(inputs: &[Series]) -> PolarsResult<Series> {
    info!("round_to_int called");
    // Prefix with underscore again to silence warning
    let _input_series = &inputs[0];

    // Define kwargs for rounding to 0 decimal places
    let round_kwargs = RoundKwargs { decimal_places: 0 };

    // Call the existing round function
    let rounded_series = round(inputs, round_kwargs)?;

    // Handle casting based on the type *after* rounding
    let result = match rounded_series.dtype() {
        DataType::List(_) => {
            let list_col = rounded_series.list()?;
            // Apply cast to Int64 to each inner series
            let casted_list = list_col.apply_amortized(|inner_series| {
                let series = inner_series.as_ref();
                // Ensure the inner series is cast correctly
                series.cast(&DataType::Int64).unwrap()
            });
            casted_list.into_series()
        }
        _ => {
            // Cast the non-list result to Int64
            rounded_series.cast(&DataType::Int64)?
        }
    };

    info!("round_to_int completed");
    Ok(result)
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

    #[test]
    fn test_round_floats() -> PolarsResult<()> {
        // Test Float64 rounding
        let values = vec![
            Some(1.2345),  // round 0 -> 1.0
            Some(1.5678),  // round 0 -> 2.0
            Some(-1.2345), // round 0 -> -1.0
            Some(-1.5678), // round 0 -> -2.0
            Some(1.2345),  // round 2 -> 1.23
            Some(1.5678),  // round 2 -> 1.57
            Some(-1.2345), // round 2 -> -1.23
            Some(-1.5678), // round 2 -> -1.57
            None,          // Null
            Some(0.0),
        ];
        let series = Series::new("floats".into(), values.clone());

        // Round to 0 decimal places
        let kwargs_0 = RoundKwargs { decimal_places: 0 };
        let rounded_0 = round(&[series.clone()], kwargs_0)?;
        let ca_0 = rounded_0.f64()?;
        let expected_0: Vec<Option<f64>> = vec![
            Some(1.0),
            Some(2.0),
            Some(-1.0),
            Some(-2.0),
            Some(1.0),
            Some(2.0),
            Some(-1.0),
            Some(-2.0),
            None,
            Some(0.0),
        ];
        assert_eq!(ca_0.into_iter().collect::<Vec<_>>(), expected_0);

        // Round to 2 decimal places
        let kwargs_2 = RoundKwargs { decimal_places: 2 };
        let rounded_2 = round(&[series.clone()], kwargs_2)?;
        let ca_2 = rounded_2.f64()?;
        let expected_2: Vec<Option<f64>> = vec![
            Some(1.23),
            Some(1.57),
            Some(-1.23),
            Some(-1.57),
            Some(1.23),
            Some(1.57),
            Some(-1.23),
            Some(-1.57),
            None,
            Some(0.0),
        ];
        assert_eq!(ca_2.into_iter().collect::<Vec<_>>(), expected_2);

        // Test Float32 rounding (similar logic)
        let values_f32: Vec<Option<f32>> = values.iter().map(|v| v.map(|f| f as f32)).collect();
        let series_f32 = Series::new("floats32".into(), values_f32);
        let rounded_f32_2 = round(&[series_f32.clone()], kwargs_2)?;
        let ca_f32_2 = rounded_f32_2.f32()?;
        let expected_f32_2: Vec<Option<f32>> =
            expected_2.iter().map(|v| v.map(|f| f as f32)).collect();
        assert_eq!(ca_f32_2.into_iter().collect::<Vec<_>>(), expected_f32_2);

        Ok(())
    }

    #[test]
    fn test_round_integers() -> PolarsResult<()> {
        // Test Int64 rounding (should just be standard round)
        let values: Vec<Option<i64>> = vec![Some(1), Some(2), Some(-1), Some(-2), None];
        let series = Series::new("ints64".into(), values.clone());

        // decimal_places > 0 shouldn't affect integers
        let kwargs = RoundKwargs { decimal_places: 2 };
        let rounded = round(&[series.clone()], kwargs)?;
        let ca = rounded.i64()?;
        let expected: Vec<Option<i64>> = vec![Some(1), Some(2), Some(-1), Some(-2), None];
        assert_eq!(ca.into_iter().collect::<Vec<_>>(), expected);

        // Test Int32 rounding
        let values_i32: Vec<Option<i32>> = values.iter().map(|v| v.map(|i| i as i32)).collect();
        let series_i32 = Series::new("ints32".into(), values_i32);
        let rounded_i32 = round(&[series_i32.clone()], kwargs)?;
        let ca_i32 = rounded_i32.i32()?;
        let expected_i32: Vec<Option<i32>> = expected.iter().map(|v| v.map(|i| i as i32)).collect();
        assert_eq!(ca_i32.into_iter().collect::<Vec<_>>(), expected_i32);

        Ok(())
    }

    #[test]
    fn test_round_list() -> PolarsResult<()> {
        // Create a list series with Float64
        let list_series = Series::new(
            "list_floats".into(),
            [
                Series::new("a".into(), vec![Some(1.234), Some(2.789), None]),
                Series::new("b".into(), vec![Some(-3.456), Some(0.123)]),
            ],
        );

        let kwargs = RoundKwargs { decimal_places: 1 };
        let rounded_list = round(&[list_series], kwargs)?;

        // Check the result
        let list_ca = rounded_list.list()?;

        // Get the inner arrays and convert them back to Series
        let array1 = list_ca.get(0).unwrap();
        let s1 = Series::from_arrow("s1".into(), array1)?;
        let array2 = list_ca.get(1).unwrap();
        let s2 = Series::from_arrow("s2".into(), array2)?;

        let expected_s1: Vec<Option<f64>> = vec![Some(1.2), Some(2.8), None];
        let expected_s2: Vec<Option<f64>> = vec![Some(-3.5), Some(0.1)];

        // Now that we have Series, we can call .f64()
        assert_eq!(s1.f64()?.into_iter().collect::<Vec<_>>(), expected_s1);
        assert_eq!(s2.f64()?.into_iter().collect::<Vec<_>>(), expected_s2);

        Ok(())
    }

    #[test]
    fn test_round_to_int() -> PolarsResult<()> {
        // Test with floats
        let float_values: Vec<Option<f64>> = vec![
            Some(1.2),  // -> 1
            Some(1.7),  // -> 2
            Some(-1.2), // -> -1
            Some(-1.7), // -> -2
            Some(0.5),  // -> 1
            Some(-0.5), // -> -1 (rounds away from zero)
            Some(0.0),
            None,
        ];
        let float_series = Series::new("floats".into(), float_values);
        let rounded_float = round_to_int(&[float_series])?;
        let expected_float: Vec<Option<i64>> = vec![
            Some(1),
            Some(2),
            Some(-1),
            Some(-2),
            Some(1),
            Some(-1),
            Some(0),
            None,
        ];
        assert_eq!(
            rounded_float.i64()?.into_iter().collect::<Vec<_>>(),
            expected_float
        );

        // Test with integers (should remain the same after rounding to 0 dp)
        let int_values: Vec<Option<i64>> = vec![Some(1), Some(-2), Some(0), None];
        let int_series = Series::new("ints".into(), int_values.clone());
        let rounded_int = round_to_int(&[int_series])?;
        assert_eq!(
            rounded_int.i64()?.into_iter().collect::<Vec<_>>(),
            int_values
        );

        // Test with List<Float64>
        let list_series = Series::new(
            "list_floats".into(),
            [
                Series::new("a".into(), vec![Some(1.234), Some(2.789), None]), // -> [1, 3, null]
                Series::new("b".into(), vec![Some(-3.456), Some(0.123)]),      // -> [-3, 0]
            ],
        );
        let rounded_list = round_to_int(&[list_series])?;
        let list_ca = rounded_list.list()?;

        let array1 = list_ca.get(0).unwrap();
        let s1 = Series::from_arrow("s1".into(), array1)?;
        let expected_s1: Vec<Option<i64>> = vec![Some(1), Some(3), None];
        assert_eq!(s1.i64()?.into_iter().collect::<Vec<_>>(), expected_s1);

        let array2 = list_ca.get(1).unwrap();
        let s2 = Series::from_arrow("s2".into(), array2)?;
        let expected_s2: Vec<Option<i64>> = vec![Some(-3), Some(0)];
        assert_eq!(s2.i64()?.into_iter().collect::<Vec<_>>(), expected_s2);

        Ok(())
    }
}
