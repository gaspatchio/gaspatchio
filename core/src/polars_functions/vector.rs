#![allow(clippy::unused_unit)]
use log::info;
use polars::prelude::*;
use serde::Deserialize;

/// Fills a series with incrementing values based on provided parameters.
///
/// # Errors
/// Returns an error if the input series cannot be converted to i64 or if series creation fails.
pub fn fill_series(inputs: &[Series], kwargs: &FillSeriesKwargs) -> PolarsResult<Series> {
    // Log the inputs for debugging.
    info!("fill_series called with inputs: {:?}", inputs);
    let length = &inputs[0];
    let start = kwargs.start;
    let increment = kwargs.increment;

    // Get the Int64Chunked view of the input series.
    let ca = length.i64()?;

    // Create a builder for a list of i64 values.
    // The builder is pre-allocated to hold one list per element in the input.
    let builder: ListChunked = ca
        .iter()
        .map(|opt_len| match opt_len {
            Some(len) if len >= 0 => {
                let values: Vec<i64> = (0..len).map(|i| start + i * increment).collect();
                Series::new("".into(), values)
            }
            _ => Series::new("".into(), vec![None::<i64>]),
        })
        .collect();
    // Finish building the ListChunked and convert it into a Series.
    info!("fill_series completed");
    Ok(builder.into_series())
}

#[allow(clippy::all)]
#[derive(Deserialize)]
pub struct FillSeriesKwargs {
    pub start: i64,
    pub increment: i64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fill_series() -> PolarsResult<()> {
        // Test basic functionality
        let length_values = vec![3i64, 2, 0, 5];
        let length_series = Series::new("length".into(), length_values);
        let kwargs = FillSeriesKwargs {
            start: 10,
            increment: 5,
        };

        let result = fill_series(&[length_series], &kwargs)?;
        let list_ca = result.list()?;

        // Test first list: length=3, start=10, increment=5 -> [10, 15, 20]
        let array1 = list_ca.get(0).unwrap();
        let s1 = Series::from_arrow("s1".into(), array1)?;
        let expected_s1: Vec<Option<i64>> = vec![Some(10), Some(15), Some(20)];
        assert_eq!(s1.i64()?.into_iter().collect::<Vec<_>>(), expected_s1);

        // Test second list: length=2, start=10, increment=5 -> [10, 15]
        let array2 = list_ca.get(1).unwrap();
        let s2 = Series::from_arrow("s2".into(), array2)?;
        let expected_s2: Vec<Option<i64>> = vec![Some(10), Some(15)];
        assert_eq!(s2.i64()?.into_iter().collect::<Vec<_>>(), expected_s2);

        // Test third list: length=0 -> []
        let array3 = list_ca.get(2).unwrap();
        let s3 = Series::from_arrow("s3".into(), array3)?;
        assert_eq!(s3.len(), 0);

        // Test fourth list: length=5, start=10, increment=5 -> [10, 15, 20, 25, 30]
        let array4 = list_ca.get(3).unwrap();
        let s4 = Series::from_arrow("s4".into(), array4)?;
        let expected_s4: Vec<Option<i64>> = vec![Some(10), Some(15), Some(20), Some(25), Some(30)];
        assert_eq!(s4.i64()?.into_iter().collect::<Vec<_>>(), expected_s4);

        Ok(())
    }

    #[test]
    fn test_fill_series_with_nulls() -> PolarsResult<()> {
        // Test with null values
        let length_values: Vec<Option<i64>> = vec![Some(2), None, Some(3)];
        let length_series = Series::new("length".into(), length_values);
        let kwargs = FillSeriesKwargs {
            start: 0,
            increment: 1,
        };

        let result = fill_series(&[length_series], &kwargs)?;
        let list_ca = result.list()?;

        // Test first list: length=2 -> [0, 1]
        let array1 = list_ca.get(0).unwrap();
        let s1 = Series::from_arrow("s1".into(), array1)?;
        let expected_s1: Vec<Option<i64>> = vec![Some(0), Some(1)];
        assert_eq!(s1.i64()?.into_iter().collect::<Vec<_>>(), expected_s1);

        // Test second list: null length -> [null]
        let array2 = list_ca.get(1).unwrap();
        let s2 = Series::from_arrow("s2".into(), array2)?;
        let expected_s2: Vec<Option<i64>> = vec![None];
        assert_eq!(s2.i64()?.into_iter().collect::<Vec<_>>(), expected_s2);

        // Test third list: length=3 -> [0, 1, 2]
        let array3 = list_ca.get(2).unwrap();
        let s3 = Series::from_arrow("s3".into(), array3)?;
        let expected_s3: Vec<Option<i64>> = vec![Some(0), Some(1), Some(2)];
        assert_eq!(s3.i64()?.into_iter().collect::<Vec<_>>(), expected_s3);

        Ok(())
    }

    #[test]
    fn test_fill_series_negative_length() -> PolarsResult<()> {
        // Test with negative length values
        let length_values: Vec<Option<i64>> = vec![Some(-1), Some(2)];
        let length_series = Series::new("length".into(), length_values);
        let kwargs = FillSeriesKwargs {
            start: 5,
            increment: 2,
        };

        let result = fill_series(&[length_series], &kwargs)?;
        let list_ca = result.list()?;

        // Test first list: negative length -> [null]
        let array1 = list_ca.get(0).unwrap();
        let s1 = Series::from_arrow("s1".into(), array1)?;
        let expected_s1: Vec<Option<i64>> = vec![None];
        assert_eq!(s1.i64()?.into_iter().collect::<Vec<_>>(), expected_s1);

        // Test second list: length=2 -> [5, 7]
        let array2 = list_ca.get(1).unwrap();
        let s2 = Series::from_arrow("s2".into(), array2)?;
        let expected_s2: Vec<Option<i64>> = vec![Some(5), Some(7)];
        assert_eq!(s2.i64()?.into_iter().collect::<Vec<_>>(), expected_s2);

        Ok(())
    }
}
