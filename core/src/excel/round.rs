// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: Excel-compatible ROUND: the value Excel holds, rounded half away from zero
// ABOUTME: One implementation, shared by .excel.round and the rollforward's rounding

//! Excel's `ROUND`, as Excel computes it.
//!
//! Excel does not round the binary double a cell holds. It rounds the value it
//! shows: the cell's **15-significant-digit decimal**. Then it sends a half
//! **away from zero**, for either sign and for a negative `num_digits` too.
//! The first step is the one a language's rounding misses. In a workbook,
//! `1.5 * 45366.20999999999` is the double `68049.31499999999…`, whose
//! fifteen digits read `68049.3150000000`, so `ROUND(…, 2)` is `68049.32`; a
//! rounding of the double itself answers `68049.31`. The same is true of
//! `0.5 * 161451.33` (`80725.665` in decimal, `80725.66499999999…` as a
//! double): Excel answers `80725.67`.
//!
//! The rule, in full:
//!
//! 1. Take the value's decimal expansion to 15 significant digits, a sixteenth
//!    digit of 5 or more going away from zero -- including a double that is
//!    exactly a sixteen-digit tie, such as `12345678901234.25`, which holds
//!    as `12345678901234.3`.
//! 2. Round that decimal to `num_digits` places, a half going away from zero.
//! 3. Answer the double nearest the result, with the input's sign (a negative
//!    value that rounds to nothing answers `-0.0`).
//!
//! Where the 15 digits are coarser than the step asked for — a value of 10^15
//! or more at whole units, 10^13 or more at cents — step 2 has nothing left to
//! round and the answer is the 15-digit value itself, as in Excel. Non-finite
//! values pass through unchanged, and a value whose 15-digit decimal is past
//! the largest double answers itself.
//!
//! Almost every value is answered without leaving binary arithmetic: unless
//! the scaled value is within a few parts in 10^15 of a half, the fifteen
//! digits cannot move it across one (see [`excel_round`]). Near a half — a
//! decimal tie such as `0.125`, a double just under one — the decision is made
//! exactly in 128-bit integers. Only the magnitudes where fifteen digits are
//! coarser than the step, and places past ten either side of the point, read
//! the decimal digits themselves.

#![allow(clippy::unused_unit)]
use polars::prelude::*;
use serde::Deserialize;

use crate::polars_functions::slices::own_rows;

/// Powers of ten that are exact doubles: `10^0` to `10^22`.
const POW10: [f64; 23] = [
    1e0, 1e1, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12, 1e13, 1e14, 1e15, 1e16,
    1e17, 1e18, 1e19, 1e20, 1e21, 1e22,
];

/// Below this scaled magnitude the fifteen digits are finer than the step, so
/// the decision is which side of a half the value falls.
const FINER_THAN_THE_STEP: f64 = 1e14;

/// How close to a half the binary path refuses to decide, as a fraction of the
/// scaled value. The fifteen digits move a value by at most `5e-15` of itself
/// and the scaling by at most `1.2e-16`; outside `1e-14` neither can carry it
/// across a half, so the binary decision is the decimal one.
const NEAR_A_HALF: f64 = 1e-14;

/// The significant digits Excel keeps.
const DIGITS: i32 = 15;

/// `10^15`: one past the largest 15-digit integer.
const TEN_TO_THE_FIFTEENTH: u64 = 1_000_000_000_000_000;

/// Round `x` to `num_digits` places the way Excel's `ROUND` does.
///
/// Excel rounds the value's 15-significant-digit decimal, half away from zero
/// (see the module documentation for the full rule). `num_digits` counts
/// places after the decimal point; a negative value rounds to tens, hundreds
/// and so on.
///
/// # Arguments
///
/// * `x` - The value to round.
/// * `num_digits` - Places after the decimal point; negative rounds to the left of it.
///
/// # Returns
///
/// The double nearest the rounded decimal, carrying `x`'s sign. Non-finite
/// values come back unchanged.
///
/// # Examples
///
/// ```
/// use gaspatchio_core_lib::excel::excel_round;
///
/// // The double is 68049.31499999999…; Excel holds 68049.3150000000.
/// assert_eq!(excel_round(1.5 * 45366.20999999999, 2), 68049.32);
/// // A decimal tie goes away from zero, for either sign.
/// assert_eq!(excel_round(0.125, 2), 0.13);
/// assert_eq!(excel_round(-0.125, 2), -0.13);
/// // A negative num_digits rounds to the left of the point.
/// assert_eq!(excel_round(1250.0, -2), 1300.0);
/// ```
pub fn excel_round(x: f64, num_digits: i32) -> f64 {
    if !x.is_finite() || x == 0.0 {
        return x;
    }
    let magnitude = x.abs();
    let rounded = binary_decision(magnitude, num_digits)
        .or_else(|| integer_decision(magnitude, num_digits))
        .unwrap_or_else(|| decimal_decision(magnitude, num_digits));
    rounded.copysign(x)
}

/// Answer a positive finite `v` in binary arithmetic, or `None` where only the
/// decimal path can decide.
///
/// The scaled value `y = v * 10^d` is one correctly rounded operation from the
/// exact one, so it is within `1.2e-16 * y` of it. Where the 15 digits are
/// finer than the step (`y < 10^14`) they move `y` by at most `5e-15 * y`, and
/// a 15-digit value that is not itself a half lies at least `5e-16 * y` from
/// one. So a `y` more than `1e-14 * y` from a half is on the same side as the
/// decimal Excel rounds, and the nearest whole step is the answer.
fn binary_decision(v: f64, num_digits: i32) -> Option<f64> {
    let power = *POW10.get(num_digits.unsigned_abs() as usize)?;
    let y = if num_digits >= 0 {
        v * power
    } else {
        v / power
    };
    if y >= FINER_THAN_THE_STEP {
        return None;
    }
    let whole = y.floor();
    let past_the_half = y - whole - 0.5;
    if past_the_half.abs() <= NEAR_A_HALF * y {
        return None;
    }
    let steps = if past_the_half > 0.0 {
        whole + 1.0
    } else {
        whole
    };
    // Both operands are exact, so one IEEE operation gives the nearest double.
    Some(if num_digits >= 0 {
        steps / power
    } else {
        steps * power
    })
}

/// The places either side of the point the integer decision covers. Within
/// them every product it forms fits 128 bits.
const INTEGER_PLACES: i32 = 10;

/// Answer a positive finite `v` exactly in whole numbers, where the fifteen
/// digits are finer than the step, or `None` outside that.
///
/// With `y = v * 10^d` and `m` its whole steps, the answer is `m + 1` exactly
/// when `v` is at or past the point where its fifteen digits become the half
/// `m + 0.5`: `y >= m + 0.5 - w`, `w` half a unit of the fifteenth digit (at
/// that point exactly, a sixteenth digit of 5 goes away from zero and the
/// fifteen digits are the half). Scaled by `2 * 10^(14 - g)`, `g` the decimal
/// exponent of `y`, both sides are whole numbers: `2 * v * 10^K` against
/// `B = (2m + 1) * 10^(14 - g) - 1`, `K = 14 - g + d`. `v` is its mantissa
/// times a power of two, so the comparison is of two 128-bit integers, one
/// shifted. This is the path a decimal tie such as `0.125` takes, without
/// rendering a string.
fn integer_decision(v: f64, num_digits: i32) -> Option<f64> {
    if num_digits.abs() > INTEGER_PLACES {
        return None;
    }
    let power = POW10[num_digits.unsigned_abs() as usize];
    let y = if num_digits >= 0 {
        v * power
    } else {
        v / power
    };
    if y >= FINER_THAN_THE_STEP {
        return None;
    }
    let whole = y.floor();
    // `whole` is below 10^14, so it is an exact whole number of u64.
    let steps_below = whole as u64;
    let exponent = if steps_below == 0 {
        -1
    } else {
        steps_below.ilog10() as i32
    };
    let unit = 10u128.pow((DIGITS - 1 - exponent) as u32);
    let boundary = u128::from(2 * steps_below + 1) * unit - 1;
    let scale = DIGITS - 1 - exponent + num_digits;
    let (mantissa, binary_exponent) = mantissa_and_exponent(v);
    let order = if scale >= 0 {
        compare_shifted(
            u128::from(mantissa) * 5u128.pow(scale as u32),
            binary_exponent + scale + 1,
            boundary,
        )
    } else {
        compare_shifted(
            u128::from(mantissa),
            binary_exponent + 1 + scale,
            boundary * 5u128.pow((-scale) as u32),
        )
    };
    let steps = if order == std::cmp::Ordering::Less {
        whole
    } else {
        whole + 1.0
    };
    Some(if num_digits >= 0 {
        steps / power
    } else {
        steps * power
    })
}

/// Return a positive finite double as a whole-number mantissa and a power of
/// two: `v == mantissa * 2^exponent`, exactly.
fn mantissa_and_exponent(v: f64) -> (u64, i32) {
    let bits = v.to_bits();
    let biased = ((bits >> 52) & 0x7ff) as i32;
    let fraction = bits & ((1u64 << 52) - 1);
    if biased == 0 {
        (fraction, -1074)
    } else {
        (fraction | (1u64 << 52), biased - 1075)
    }
}

/// Compare `x * 2^shift` with `y`, exactly, without leaving 128 bits.
fn compare_shifted(x: u128, shift: i32, y: u128) -> std::cmp::Ordering {
    use std::cmp::Ordering;
    if shift >= 0 {
        if x == 0 {
            return 0u128.cmp(&y);
        }
        // A shift past the leading zeros is at least 2^128, above any y.
        if x.leading_zeros() as i32 <= shift {
            return Ordering::Greater;
        }
        return (x << shift).cmp(&y);
    }
    let lift = -shift;
    if y == 0 {
        return x.cmp(&0);
    }
    if y.leading_zeros() as i32 <= lift {
        return Ordering::Less;
    }
    x.cmp(&(y << lift))
}

/// Answer a positive finite `v` exactly, through its decimal digits.
fn decimal_decision(v: f64, num_digits: i32) -> f64 {
    let (digits, exponent) = fifteen_digits(v);
    // `v` is held as `digits * 10^(exponent - 14)`; the step is `10^-num_digits`.
    let unit = i64::from(exponent) - i64::from(DIGITS - 1);
    let below_the_step = -(unit + i64::from(num_digits));
    if below_the_step <= 0 {
        // The 15 digits are no finer than the step: nothing is left to round.
        let answer = nearest_double(digits, unit);
        return if answer.is_finite() { answer } else { v };
    }
    if below_the_step > i64::from(DIGITS) {
        // Every digit is below half a step.
        return 0.0;
    }
    // `below_the_step` is between 1 and 15 here, so the divisor fits a u64.
    let divisor = 10u64.pow(below_the_step as u32);
    let mut steps = digits / divisor;
    if (digits % divisor) * 2 >= divisor {
        steps += 1;
    }
    nearest_double(steps, -i64::from(num_digits))
}

/// Return Excel's 15 significant digits of a positive finite `v`, as an
/// integer from `10^14` up to `10^15` and the decimal exponent of its first
/// digit: `v` is held as `digits * 10^(exponent - 14)`.
///
/// The sixteenth digit decides, 5 or more going away from zero. A 17-digit
/// rendering settles it except where its last two digits read exactly `50`,
/// because the rendering is within half a unit of its last place of the exact
/// value: `51` or more is at least `50.5` exactly, `49` or less at most
/// `49.5`. Only at `50` is the exact expansion read.
fn fifteen_digits(v: f64) -> (u64, i32) {
    let (seventeen, mut exponent) = significant_digits(v, 17);
    let tail = seventeen % 100;
    let mut digits = seventeen / 100;
    let away = if tail == 50 {
        sixteenth_digit_exactly(v) >= 5
    } else {
        tail > 50
    };
    if away {
        digits += 1;
    }
    if digits == TEN_TO_THE_FIFTEENTH {
        // 999999999999999.5… carried into a sixteenth digit.
        digits /= 10;
        exponent += 1;
    }
    (digits, exponent)
}

/// Return `count` significant digits of a positive finite `v` (correctly
/// rounded, at most 19) as an integer, and the decimal exponent of the first.
fn significant_digits(v: f64, count: usize) -> (u64, i32) {
    let rendered = format!("{:.*e}", count - 1, v);
    let (mantissa, exponent) = rendered
        .split_once('e')
        .expect("Rust renders a finite float in exponent form with an 'e'");
    let digits = mantissa
        .bytes()
        .filter(u8::is_ascii_digit)
        .fold(0u64, |held, digit| held * 10 + u64::from(digit - b'0'));
    let exponent = exponent
        .parse::<i32>()
        .expect("Rust renders a float's decimal exponent as an integer");
    (digits, exponent)
}

/// Return the sixteenth significant digit of `v`'s exact decimal expansion.
///
/// A double's exact expansion has at most 767 significant digits, so a
/// rendering to 767 is the expansion itself, with no rounding in it.
fn sixteenth_digit_exactly(v: f64) -> u8 {
    let rendered = format!("{:.766e}", v);
    rendered
        .bytes()
        .filter(u8::is_ascii_digit)
        .nth(15)
        .map_or(0, |digit| digit - b'0')
}

/// Return the double nearest `steps * 10^exponent`.
fn nearest_double(steps: u64, exponent: i64) -> f64 {
    format!("{steps}e{exponent}")
        .parse::<f64>()
        .expect("an integer with a decimal exponent is a valid float literal")
}

/// Keyword arguments for the `excel_round` expression plugin.
#[derive(Deserialize, Clone, Copy, Debug)]
pub struct ExcelRoundKwargs {
    /// Places after the decimal point, as in Excel; negative rounds to the left.
    pub num_digits: i32,
}

/// Return the dtype `excel_round` answers for one input dtype.
///
/// Section 11.1.35 states Float64 cells, so a whole-number column answers
/// doubles at every place. A single-precision column keeps its own type at
/// places at or after the point, as it always has; everything else is rounded
/// in double precision and answers a double. A list keeps its shape.
fn rounded_dtype(dtype: &DataType, num_digits: i32) -> PolarsResult<DataType> {
    match dtype {
        DataType::List(inner) => Ok(DataType::List(Box::new(rounded_dtype(inner, num_digits)?))),
        DataType::Float32 if num_digits >= 0 => Ok(DataType::Float32),
        number if number.is_float() || number.is_integer() => Ok(DataType::Float64),
        other => Err(PolarsError::ComputeError(
            format!(
                "excel.round rounds numbers, and this column holds {other}. Cast it to \
                 Float64 first if its values are numbers"
            )
            .into(),
        )),
    }
}

/// Return the output field of the `excel_round` plugin for its input field.
///
/// # Errors
///
/// Returns a `ComputeError` when the input is not numeric (or a list of numbers).
pub fn excel_round_output_type(
    input_fields: &[Field],
    kwargs: &ExcelRoundKwargs,
) -> PolarsResult<Field> {
    let field = input_fields.first().ok_or_else(|| {
        PolarsError::ComputeError("excel.round takes one operand, the value to round".into())
    })?;
    Ok(Field::new(
        field.name().clone(),
        rounded_dtype(field.dtype(), kwargs.num_digits)?,
    ))
}

/// `2^52`: adding and subtracting it rounds a double below it to a whole number.
const TWO_TO_THE_52: f64 = 4_503_599_627_370_496.0;

/// Round one double column, chunk by chunk, keeping each chunk's validity.
///
/// The work is split in two passes so the common case compiles to a straight
/// line over the slice: [`screen`] answers every value the binary path can
/// settle and marks the rest with a NaN, and only the marked values -- a
/// decimal tie, a double just under one, a magnitude past the scaling, a
/// non-finite value -- go through [`excel_round`] one at a time. A value the
/// screen settles is answered exactly as [`binary_decision`] answers it.
fn round_doubles(ca: &Float64Chunked, num_digits: i32) -> Float64Chunked {
    let chunks = ca.downcast_iter().map(|array| {
        let values = array.values().as_slice();
        let mut answers = vec![0.0_f64; values.len()];
        screen(values, num_digits, &mut answers);
        for (answer, &value) in answers.iter_mut().zip(values) {
            if answer.is_nan() {
                *answer = excel_round(value, num_digits);
            }
        }
        polars_arrow::array::PrimitiveArray::from_vec(answers)
            .with_validity(array.validity().cloned())
    });
    ChunkedArray::from_chunk_iter(ca.name().clone(), chunks)
}

/// Answer every value the binary path settles, and leave a NaN where it cannot.
///
/// The same test as [`binary_decision`], written without a branch: the floor
/// of a non-negative double below `2^52` by adding and subtracting `2^52`
/// (which rounds to the nearest whole number) and stepping down where that went
/// up; the step up as a select; the sign restored with `copysign`. A value not
/// below `10^14` steps, or within `1e-14` of itself of a half, or not finite,
/// fails the comparison and is left as a NaN for the caller.
fn screen(values: &[f64], num_digits: i32, answers: &mut [f64]) {
    let Some(&power) = POW10.get(num_digits.unsigned_abs() as usize) else {
        answers.fill(f64::NAN);
        return;
    };
    if num_digits >= 0 {
        screen_with(values, answers, |v| v * power, |steps| steps / power);
    } else {
        screen_with(values, answers, |v| v / power, |steps| steps * power);
    }
}

#[inline(always)]
fn screen_with(
    values: &[f64],
    answers: &mut [f64],
    scale: impl Fn(f64) -> f64,
    unscale: impl Fn(f64) -> f64,
) {
    for (answer, &x) in answers.iter_mut().zip(values) {
        let y = scale(x.abs());
        let nearest = (y + TWO_TO_THE_52) - TWO_TO_THE_52;
        let whole = if nearest > y { nearest - 1.0 } else { nearest };
        let past_the_half = (y - whole) - 0.5;
        let settled = past_the_half.abs() > NEAR_A_HALF * y && y < FINER_THAN_THE_STEP;
        let steps = if past_the_half > 0.0 {
            whole + 1.0
        } else {
            whole
        };
        let rounded = unscale(steps).copysign(x);
        *answer = if settled { rounded } else { f64::NAN };
    }
}

/// Round every value of one numeric series, keeping nulls where they are.
fn round_values(series: &Series, num_digits: i32) -> PolarsResult<Series> {
    let target = rounded_dtype(series.dtype(), num_digits)?;
    let doubles = series.cast(&DataType::Float64)?;
    let rounded = round_doubles(doubles.f64()?, num_digits).into_series();
    if target == DataType::Float64 {
        Ok(rounded)
    } else {
        rounded.cast(&target)
    }
}

/// The `excel_round` expression plugin: Excel's `ROUND` over a numeric column
/// or a list column of numbers, element-wise, nulls staying null.
///
/// # Errors
///
/// Returns a `ComputeError` when the operand is missing or not numeric.
pub fn excel_round_series(inputs: &[Series], kwargs: &ExcelRoundKwargs) -> PolarsResult<Series> {
    let series = inputs.first().ok_or_else(|| {
        PolarsError::ComputeError("excel.round takes one operand, the value to round".into())
    })?;
    let num_digits = kwargs.num_digits;
    match series.dtype() {
        DataType::List(_) => {
            // Validate the element type before touching the values, so a list
            // of text is refused by name rather than by a cast error.
            rounded_dtype(series.dtype(), num_digits)?;
            // The streaming engine hands a plugin a slice of a list column,
            // whose inner values are still the whole column's: rounding them
            // as they stand rounds every morsel's neighbours too, once per
            // morsel. Cut to the slice's own rows first (own_rows), each value
            // is rounded once.
            let rounded = own_rows(series)
                .list()?
                .apply_to_inner(&|inner: Series| round_values(&inner, num_digits))?;
            Ok(rounded.into_series())
        }
        _ => round_values(series, num_digits),
    }
}

#[cfg(test)]
mod paths {
    use super::{decimal_decision, excel_round, integer_decision, round_doubles};
    use polars::prelude::*;

    #[test]
    fn the_column_pass_answers_what_the_value_rule_answers() {
        // Every kind of value through the two-pass column kernel and through
        // excel_round one at a time, bit for bit, at places from -400 to 400.
        let mut values = vec![
            0.0,
            -0.0,
            f64::INFINITY,
            f64::NEG_INFINITY,
            5e-324,
            -5e-324,
            f64::MAX,
            f64::MIN,
            4_503_599_627_370_496.0,
            1e14,
            99_999_999_999_999.5,
            0.125,
            -0.125,
            2.675,
            1.005,
            0.49999999999999994,
            12_345_678_901_234.25,
            1.5 * 45366.20999999999,
            0.5 * 161451.33,
            5657268.499999999 * 0.03,
        ];
        let mut seed = 0x9e37_79b9_7f4a_7c15_u64;
        for _ in 0..20_000 {
            // A fixed xorshift stream: any double's bits, and short decimals.
            seed ^= seed << 13;
            seed ^= seed >> 7;
            seed ^= seed << 17;
            values.push(f64::from_bits(seed));
            values.push((seed % 10_000_000) as f64 / 1000.0);
        }
        let column = Float64Chunked::from_vec("x".into(), values.clone());
        for places in [-400, -23, -22, -10, -3, -1, 0, 1, 2, 4, 10, 15, 22, 23, 400] {
            let answered = round_doubles(&column, places);
            for (value, got) in values.iter().zip(answered.into_no_null_iter()) {
                let want = excel_round(*value, places);
                assert!(
                    got.to_bits() == want.to_bits() || (got.is_nan() && want.is_nan()),
                    "ROUND({value:?}, {places}): column {got:?}, value {want:?}"
                );
            }
        }
    }

    /// Step one unit of the last place up (`+1`) or down (`-1`).
    fn nudged(v: f64, units: i64) -> f64 {
        f64::from_bits((v.to_bits() as i64 + units) as u64)
    }

    #[test]
    fn the_integer_and_the_decimal_decisions_agree_at_every_kind_of_half() {
        // Decimal ties at every place from -10 to 10, each exact and a few
        // units either side, at magnitudes from a cent to 10^13 steps.
        for places in -10..=10_i32 {
            for steps in [0_u64, 1, 7, 12, 499, 6_804_931, 123_456_789, 99_999_999_999] {
                let half = (steps as f64 + 0.5) * 10f64.powi(-places);
                for units in -3..=3 {
                    let v = nudged(half, units);
                    if v <= 0.0 || v * 10f64.powi(places) >= 1e14 {
                        continue;
                    }
                    assert_eq!(
                        integer_decision(v, places).map(f64::to_bits),
                        Some(decimal_decision(v, places).to_bits()),
                        "ROUND({v:?}, {places})"
                    );
                }
            }
        }
    }
}
