// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: The standard normal distribution function, Phi, one value at a time
// ABOUTME: 0.5 * erfc(-x / sqrt 2): N(d1) and N(d2) of a guarantee priced as an option

//! `norm_cdf`: Φ(x), the probability that a standard normal variable is at
//! most `x` (section 11.1.12 of the graph-artifact contract).
//!
//! A guarantee valued as an option -- a GMDB or GMMB priced as a
//! Black-Scholes put -- needs N(d1) and N(d2), which a workbook writes as
//! `NORM.S.DIST(z, TRUE)`, `NORMSDIST(z)` or `NORM.DIST(z, 0, 1, TRUE)`.
//!
//! The kernel computes `0.5 * erfc(-x / √2)` with the `libm` crate's `erfc`
//! (a port of FreeBSD's `s_erf.c`). The complementary form is the one that
//! keeps its accuracy in the lower tail: the textbook `0.5 * (1 + erf(x / √2))`
//! subtracts two nearly equal numbers there, is right to about eight digits in
//! the body, and answers 0.0 at `x = -8.36`, where Φ is 3.1e-17.
//!
//! **The contract is 1e-12 relative to the mathematical Φ**, wherever Φ is a
//! normal double (`x >= -37.5`), and it is exact at the special values: a null
//! stays null, a NaN stays NaN, `+inf` answers 1.0 and `-inf` answers 0.0.
//! Measured against a 60-digit reference over 2,120 points on [-37.5, 9], the
//! worst relative error is 1.8e-13, near `x = -37.06`, and 6.0e-15 where
//! `|x| <= 6`. The tail error comes from rounding `x / √2`: it grows like
//! `x² · ε` and stays inside the contract. Below `x = -37.5` the answer is
//! subnormal, then zero from about `x = -38.5`; there a relative tolerance means
//! nothing, and the line-scale rule decides.
//!
//! No promise is made about Excel's own bits. Excel's algorithm is
//! unpublished. Its cached values sit within about 1e-14 of the true Φ over
//! the range workbooks use, so a reconciliation against a workbook should
//! expect agreement to that order, not to the last bit.

#![allow(clippy::unused_unit)]
use polars::prelude::*;
use std::f64::consts::SQRT_2;

use super::slices::own_rows;

/// Return Φ(x), the standard normal distribution function, at one value.
///
/// # Arguments
///
/// * `x` - The point at which to evaluate the distribution function.
///
/// # Returns
///
/// The probability that a standard normal variable is at most `x`: within
/// 1e-12 relative of the mathematical value wherever that value is a normal
/// double, 1.0 at `+inf`, 0.0 at `-inf`, and NaN at NaN.
///
/// # Examples
///
/// ```
/// use gaspatchio_core_lib::polars_functions::norm_cdf;
///
/// assert_eq!(norm_cdf(0.0), 0.5);
/// assert_eq!(norm_cdf(f64::INFINITY), 1.0);
/// assert_eq!(norm_cdf(f64::NEG_INFINITY), 0.0);
/// assert!((norm_cdf(1.96) - 0.975_002_104_851_78).abs() < 1e-14);
/// ```
#[inline]
pub fn norm_cdf(x: f64) -> f64 {
    0.5 * libm::erfc(-x / SQRT_2)
}

/// Return the dtype `norm_cdf` answers for one input dtype.
///
/// Every number is evaluated in double precision and answers a double; a
/// list keeps its shape. A column of nothing but nulls (dtype `Null`) answers
/// a column of null doubles.
fn cdf_dtype(dtype: &DataType) -> PolarsResult<DataType> {
    match dtype {
        DataType::List(inner) => Ok(DataType::List(Box::new(cdf_dtype(inner)?))),
        number if number.is_float() || number.is_integer() || number.is_null() => {
            Ok(DataType::Float64)
        }
        other => Err(PolarsError::ComputeError(
            format!(
                "norm_cdf evaluates the normal distribution function at numbers, and this \
                 column holds {other}. Cast it to Float64 first if its values are numbers"
            )
            .into(),
        )),
    }
}

/// Return the output field of the `norm_cdf` plugin for its input field.
///
/// # Errors
///
/// Returns a `ComputeError` when the operand is missing or is not numeric (or
/// a list of numbers).
pub fn norm_cdf_output_type(input_fields: &[Field]) -> PolarsResult<Field> {
    let field = input_fields.first().ok_or_else(one_operand)?;
    Ok(Field::new(field.name().clone(), cdf_dtype(field.dtype())?))
}

fn one_operand() -> PolarsError {
    PolarsError::ComputeError("norm_cdf takes one operand, the value to evaluate at".into())
}

/// Evaluate Φ over one double column, chunk by chunk, keeping each chunk's
/// validity: a null stays null, and the value under it is never read.
fn cdf_doubles(ca: &Float64Chunked) -> Float64Chunked {
    let chunks = ca.downcast_iter().map(|array| {
        let answers: Vec<f64> = array.values().iter().map(|&x| norm_cdf(x)).collect();
        polars_arrow::array::PrimitiveArray::from_vec(answers)
            .with_validity(array.validity().cloned())
    });
    ChunkedArray::from_chunk_iter(ca.name().clone(), chunks)
}

/// Evaluate Φ at every value of one numeric series, keeping nulls where they are.
fn cdf_values(series: &Series) -> PolarsResult<Series> {
    cdf_dtype(series.dtype())?;
    let doubles = series.cast(&DataType::Float64)?;
    Ok(cdf_doubles(doubles.f64()?).into_series())
}

/// The `norm_cdf` expression plugin: Φ over a numeric column or a list column
/// of numbers, element-wise, nulls staying null.
///
/// Each output value depends on its own input value only, so the plugin is
/// registered elementwise and the streaming engine keeps running.
///
/// # Errors
///
/// Returns a `ComputeError` when the operand is missing or not numeric.
pub fn norm_cdf_series(inputs: &[Series]) -> PolarsResult<Series> {
    let series = inputs.first().ok_or_else(one_operand)?;
    match series.dtype() {
        DataType::List(_) => {
            // Refuse a list of text by name before touching the values.
            cdf_dtype(series.dtype())?;
            // The streaming engine hands a plugin a slice of a list column
            // whose inner values are still the whole column's; cut to the
            // slice's own rows first so each value is evaluated once.
            let answered = own_rows(series)
                .list()?
                .apply_to_inner(&|inner: Series| cdf_values(&inner))?;
            Ok(answered.into_series())
        }
        _ => cdf_values(series),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Φ at exact doubles, to 40 significant digits, from a 60-digit reference
    /// (the Maclaurin series of Φ for |x| <= 4, Laplace's continued fraction
    /// beyond; the two agree to 1e-96 where both converge): a grid at every
    /// half from -37.5 to 9, the worst points of a 2,120-point sweep, the
    /// textbook formula's trap at -8.36, and the gmdb room's split point.
    const REFERENCE: &[(f64, &str)] = &[
        (-37.5, "4.6053530095819548438279690976109e-308"),
        (-37.06111373289287, "5.9465064242716153440695158757247e-301"),
        (-37.0, "5.7255712225245768226831925482732e-300"),
        (-36.5, "5.5447257130748445537928380931838e-292"),
        (-36.0, "4.1826240657972833317423323318102e-284"),
        (-35.5, "2.4576915406619369142141012641207e-276"),
        (-35.0, "1.1249107064724062439792427675351e-268"),
        (-34.5, "4.0107289665772619693485012703990e-261"),
        (-34.0, "1.1138987855743793865819505555930e-253"),
        (-33.5, "2.4098386951203853936638469036018e-246"),
        (-33.0, "4.0611856209158550885033000261502e-239"),
        (-32.5, "5.3314243596788040992781032626481e-232"),
        (-32.0, "5.4520806035123960919623525038697e-225"),
        (-31.5, "4.3432326010317719588118840957028e-218"),
        (-31.0, "2.6952500812005000785938913224644e-211"),
        (-30.5, "1.3029379131780763509227548786269e-204"),
        (-30.0, "4.9067139271481870595338092565802e-198"),
        (-29.5, "1.4394745522291791685652105394810e-191"),
        (-29.0, "3.2897852667043801617189731530352e-185"),
        (-28.5, "5.8571412538063375481306797526959e-179"),
        (-28.0, "8.1238694696594265935983570310504e-173"),
        (-27.5, "8.7781705568780837723482408687595e-167"),
        (-27.0, "7.3894810068850182575179440052160e-161"),
        (-26.5, "4.8461626603033202928079133273738e-155"),
        (-26.0, "2.4760633155033892857869305955706e-149"),
        (-25.5, "9.8562365189639287943171921172387e-144"),
        (-25.0, "3.0566967063825609164027486712615e-138"),
        (-24.5, "7.3857068614894077942806076750734e-133"),
        (-24.0, "1.3903921185497030595658274117211e-127"),
        (-23.5, "2.0393675632499762304763573187807e-122"),
        (-23.0, "2.3306370062206487985735846704332e-117"),
        (-22.5, "2.0753107990663545830192927972794e-112"),
        (-22.0, "1.4398924351450790457225238303743e-107"),
        (-21.5, "7.7843970771826337686879664115499e-103"),
        (-21.0, "3.2792780189790359397356806810375e-98"),
        (-20.5, "1.0764673258790960335306866502021e-93"),
        (-20.0, "2.7536241186062336950756227808575e-89"),
        (-19.5, "5.4891154756604099475477642778787e-85"),
        (-19.0, "8.5272239526309765105061186326148e-81"),
        (-18.5, "1.0323698689563289608656803842002e-76"),
        (-18.0, "9.7409489189371504825918951899715e-73"),
        (-17.5, "7.1634587662350358453606437501964e-69"),
        (-17.0, "4.1059962020989062895946551938627e-65"),
        (-16.5, "1.8344630031647311099545808427968e-61"),
        (-16.0, "6.3887544005380872812754825749177e-58"),
        (-15.5, "1.7344607917938700513404475926637e-54"),
        (-15.0, "3.6709661993127508857860896553347e-51"),
        (-14.5, "6.0574947644152207796334497855129e-48"),
        (-14.0, "7.7935368191928002543596818388951e-45"),
        (-13.5, "7.8188073056578912157056309155213e-42"),
        (-13.0, "6.1171643995498796822752097725441e-39"),
        (-12.5, "3.7325642988777133772258363380314e-36"),
        (-12.0, "1.7764821120776789976961710018456e-33"),
        (-11.5, "6.5957714461136750790524721059232e-31"),
        (-11.0, "1.9106595744986757111504156337078e-28"),
        (-10.5, "4.3190063178092303465478171572942e-26"),
        (-10.0, "7.6198530241605260659733432515993e-24"),
        (-9.5, "1.0494515075362607492834780171577e-21"),
        (-9.0, "1.1285884059538406477355020759687e-19"),
        (-8.5, "9.4795348222033183541510504678476e-18"),
        (-8.36, "3.1359128294842654529699316552391e-17"),
        (-8.0, "6.2209605742717841235159951725882e-16"),
        (-7.5, "3.1908916729108962277672883447264e-14"),
        (-7.0, "1.2798125438858350043836236907808e-12"),
        (-6.5, "4.0160005838591178083461454224007e-11"),
        (-6.0, "9.8658764503769814070086413239804e-10"),
        (-5.790467201510147, "3.5095452151125979188876654356982e-9"),
        (-5.5, "1.8989562465887719383851274033580e-8"),
        (-5.0, "2.8665157187919391167375233287465e-7"),
        (-4.5, "3.3976731247300604016874491908715e-6"),
        (-4.0, "3.1671241833119921253770756722151e-5"),
        (-3.5, "2.3262907903552503634992588672798e-4"),
        (-3.0, "1.3498980316300945266518147675950e-3"),
        (-2.96, "1.5381952117380588286004171832958e-3"),
        (-2.9, "1.8658133003840384790013686460640e-3"),
        (-2.5, "6.2096653257761351669781045741922e-3"),
        (-2.0, "2.2750131948179207200282637166533e-2"),
        (-1.96, "2.4997895148220436212823692395554e-2"),
        (-1.5, "6.6807201268858066004494040979886e-2"),
        (-1.0, "1.5865525393145705141476745436796e-1"),
        (-0.84, "2.0045419326044966957927057648353e-1"),
        (-0.5, "3.0853753872598689636229538939166e-1"),
        (-1e-300, "5.0000000000000000000000000000000e-1"),
        (0.0, "5.0000000000000000000000000000000e-1"),
        (1e-300, "5.0000000000000000000000000000000e-1"),
        (0.25, "5.9870632568292372424085379158103e-1"),
        (0.5, "6.9146246127401310363770461060834e-1"),
        (0.6, "7.2574688224992641230656468488922e-1"),
        (1.0, "8.4134474606854294858523254563204e-1"),
        (1.3, "9.0319951541438967445828443926063e-1"),
        (1.5, "9.3319279873114193399550595902011e-1"),
        (1.96, "9.7500210485177956378717630760445e-1"),
        (2.0, "9.7724986805182079279971736283347e-1"),
        (2.5, "9.9379033467422386483302189542581e-1"),
        (3.0, "9.9865010196836990547334818523241e-1"),
        (3.5, "9.9976737092096447496365007411327e-1"),
        (4.0, "9.9996832875816688007874622924328e-1"),
        (4.5, "9.9999660232687526993959831255081e-1"),
        (5.0, "9.9999971334842812080608832624767e-1"),
        (5.5, "9.9999998101043753411228061614873e-1"),
        (6.0, "9.9999999901341235496230185929914e-1"),
        (6.5, "9.9999999995983999416140882191654e-1"),
        (7.0, "9.9999999999872018745611416499562e-1"),
        (7.5, "9.9999999999996809108327089103772e-1"),
        (8.0, "9.9999999999999937790394257282159e-1"),
        (8.5, "9.9999999999999999052046517779668e-1"),
        (9.0, "9.9999999999999999988714115940462e-1"),
    ];

    fn reference(text: &str) -> f64 {
        text.parse::<f64>()
            .expect("a reference value is a decimal float literal")
    }

    fn relative_error(got: f64, want: f64) -> f64 {
        ((got - want) / want).abs()
    }

    #[test]
    fn every_normal_result_is_within_the_contract_of_the_true_phi() {
        // Section 11.1.12: 1e-12 relative wherever Phi is a normal double.
        let mut worst = (0.0_f64, 0.0_f64);
        for &(x, text) in REFERENCE {
            let want = reference(text);
            assert!(want.is_normal(), "Phi({x:?}) is a normal double");
            let error = relative_error(norm_cdf(x), want);
            if error > worst.0 {
                worst = (error, x);
            }
            assert!(
                error <= 1e-12,
                "Phi({x:?}) = {} against {text}: relative error {error:e}",
                norm_cdf(x)
            );
        }
        // A binary64 port of this algorithm measured 1.8e-13, at -37.06.
        assert!(
            worst.0 > 0.0,
            "the comparison compared something (worst {:e} at {:?})",
            worst.0,
            worst.1
        );
    }

    #[test]
    fn the_body_is_held_far_inside_the_contract() {
        // Where a workbook evaluates Phi (|x| <= 6) the measured worst is
        // 6.0e-15; 2e-14 leaves room for the last place of libm's exp.
        for &(x, text) in REFERENCE.iter().filter(|(x, _)| x.abs() <= 6.0) {
            let error = relative_error(norm_cdf(x), reference(text));
            assert!(error <= 2e-14, "Phi({x:?}): relative error {error:e}");
        }
    }

    #[test]
    fn the_textbook_trap_is_not_this_formula() {
        // 0.5 * (1 + erf(x / sqrt 2)) answers 0.0 at -8.36, where Phi is
        // 3.1359e-17; the complementary form keeps every digit.
        let want = reference("3.135912829484265452969931655239149186947e-17");
        let textbook = 0.5 * (1.0 + libm::erf(-8.36 / SQRT_2));
        assert!(relative_error(textbook, want) > 0.5);
        assert!(relative_error(norm_cdf(-8.36), want) <= 2e-14);
    }

    #[test]
    fn the_deep_tail_is_normal_to_minus_37_5_and_then_falls_to_zero() {
        // -37.5: the last half-step where Phi is a normal double.
        let at_37_5 = norm_cdf(-37.5);
        assert!(at_37_5.is_normal());
        let want = reference("4.605353009581954843827969097610896238921e-308");
        assert!(relative_error(at_37_5, want) <= 1e-12);
        // -38: Phi is 2.885e-316, subnormal. A relative tolerance means
        // nothing at that magnitude; the answer is within a few units of the
        // smallest subnormal, which no line scale can see.
        let at_38 = norm_cdf(-38.0);
        let want = reference("2.885428360068784308350970481566904094662e-316");
        assert!(at_38 > 0.0 && !at_38.is_normal());
        assert!((at_38 - want).abs() <= 4.0 * f64::from_bits(1));
        // -40: Phi is 3.7e-350, below the smallest subnormal: positive zero.
        let at_40 = norm_cdf(-40.0);
        assert_eq!(at_40.to_bits(), 0.0_f64.to_bits());
    }

    #[test]
    fn the_special_values_are_exact() {
        assert_eq!(norm_cdf(f64::INFINITY), 1.0);
        assert_eq!(norm_cdf(f64::NEG_INFINITY).to_bits(), 0.0_f64.to_bits());
        assert!(norm_cdf(f64::NAN).is_nan());
        assert_eq!(norm_cdf(0.0), 0.5);
        assert_eq!(norm_cdf(-0.0), 0.5);
        assert_eq!(norm_cdf(1e-300), 0.5);
        assert_eq!(norm_cdf(-1e-300), 0.5);
        // Phi(8.3) is 1 - 5.2e-17, nearer 1.0 than the double below it.
        assert_eq!(norm_cdf(8.3), 1.0);
        assert_eq!(norm_cdf(9.0), 1.0);
        assert_eq!(norm_cdf(f64::MAX), 1.0);
        assert_eq!(norm_cdf(f64::MIN).to_bits(), 0.0_f64.to_bits());
    }

    #[test]
    fn the_two_tails_are_complements() {
        // Phi(x) + Phi(-x) = 1, to the rounding of the larger term.
        for k in 0..=120 {
            let x = f64::from(k) * 0.05;
            let sum = norm_cdf(x) + norm_cdf(-x);
            assert!((sum - 1.0).abs() <= 4.0 * f64::EPSILON, "x = {x}: {sum}");
        }
    }

    #[test]
    fn the_plugin_keeps_nulls_and_answers_every_value() -> PolarsResult<()> {
        let column = Series::new(
            "z".into(),
            vec![
                Some(0.0),
                None,
                Some(f64::NAN),
                Some(f64::INFINITY),
                Some(f64::NEG_INFINITY),
                Some(1.96),
            ],
        );
        let out = norm_cdf_series(&[column])?;
        assert_eq!(out.name().as_str(), "z");
        assert_eq!(out.dtype(), &DataType::Float64);
        let values: Vec<Option<f64>> = out.f64()?.into_iter().collect();
        assert_eq!(values[0], Some(0.5));
        assert_eq!(values[1], None);
        assert!(values[2].is_some_and(f64::is_nan));
        assert_eq!(values[3], Some(1.0));
        assert_eq!(values[4], Some(0.0));
        assert_eq!(values[5], Some(norm_cdf(1.96)));
        Ok(())
    }

    #[test]
    fn whole_numbers_answer_doubles() -> PolarsResult<()> {
        let column = Series::new("n".into(), vec![0_i64, 1, -1]);
        let out = norm_cdf_series(&[column])?;
        assert_eq!(out.dtype(), &DataType::Float64);
        let values: Vec<Option<f64>> = out.f64()?.into_iter().collect();
        assert_eq!(
            values,
            vec![Some(0.5), Some(norm_cdf(1.0)), Some(norm_cdf(-1.0))]
        );
        Ok(())
    }

    #[test]
    fn a_column_of_nothing_but_nulls_answers_null_doubles() -> PolarsResult<()> {
        let column = Series::full_null("z".into(), 3, &DataType::Null);
        let out = norm_cdf_series(&[column])?;
        assert_eq!(out.dtype(), &DataType::Float64);
        assert_eq!(out.null_count(), 3);
        Ok(())
    }

    #[test]
    fn a_list_keeps_its_shape_its_nulls_and_its_empty_rows() -> PolarsResult<()> {
        let rows: ListChunked = vec![
            Some(Series::new("".into(), vec![Some(0.0), None, Some(-1.96)])),
            None,
            Some(Series::new("".into(), Vec::<Option<f64>>::new())),
            Some(Series::new("".into(), vec![Some(f64::NEG_INFINITY)])),
        ]
        .into_iter()
        .collect();
        let out = norm_cdf_series(&[rows.into_series()])?;
        assert_eq!(out.dtype(), &DataType::List(Box::new(DataType::Float64)));
        let answered: Vec<Option<Vec<Option<f64>>>> = out
            .list()?
            .into_iter()
            .map(|row| row.map(|s| s.f64().unwrap().into_iter().collect()))
            .collect();
        assert_eq!(
            answered,
            vec![
                Some(vec![Some(0.5), None, Some(norm_cdf(-1.96))]),
                None,
                Some(vec![]),
                Some(vec![Some(0.0)]),
            ]
        );
        Ok(())
    }

    #[test]
    fn the_plugin_answers_only_the_slice_of_a_list_column_it_is_handed() -> PolarsResult<()> {
        // The streaming engine passes a slice whose inner values are the whole
        // column's; the answer is the slice's lists, and its values its own.
        let inners: Vec<Series> = (0..4)
            .map(|row| Series::new("".into(), vec![f64::from(row), -f64::from(row)]))
            .collect();
        let column = Series::new("x".into(), inners).slice(1, 2);
        let out = norm_cdf_series(&[column])?;
        assert_eq!(out.list()?.get_inner().len(), 4);
        let rows: Vec<Vec<f64>> = out
            .list()?
            .into_iter()
            .map(|row| row.unwrap().f64().unwrap().into_no_null_iter().collect())
            .collect();
        assert_eq!(
            rows,
            vec![
                vec![norm_cdf(1.0), norm_cdf(-1.0)],
                vec![norm_cdf(2.0), norm_cdf(-2.0)],
            ]
        );
        Ok(())
    }

    #[test]
    fn a_column_that_is_not_numbers_is_refused_by_name() {
        let text = Series::new("z".into(), vec!["1.96"]);
        let refusal = norm_cdf_series(&[text]).unwrap_err();
        assert!(refusal.to_string().contains("norm_cdf evaluates"));
        let listed: ListChunked = vec![Some(Series::new("".into(), vec!["a"]))]
            .into_iter()
            .collect();
        assert!(norm_cdf_series(&[listed.into_series()]).is_err());
        assert!(norm_cdf_series(&[]).is_err());
    }

    #[test]
    fn the_output_type_follows_the_input() {
        let typed = |dtype: DataType| {
            norm_cdf_output_type(&[Field::new("z".into(), dtype)])
                .unwrap()
                .dtype()
                .clone()
        };
        assert_eq!(typed(DataType::Float64), DataType::Float64);
        assert_eq!(typed(DataType::Float32), DataType::Float64);
        assert_eq!(typed(DataType::Int64), DataType::Float64);
        assert_eq!(
            typed(DataType::List(Box::new(DataType::Float64))),
            DataType::List(Box::new(DataType::Float64))
        );
        assert_eq!(
            typed(DataType::List(Box::new(DataType::Int32))),
            DataType::List(Box::new(DataType::Float64))
        );
        assert!(norm_cdf_output_type(&[Field::new("z".into(), DataType::String)]).is_err());
        assert!(norm_cdf_output_type(&[]).is_err());
    }
}
