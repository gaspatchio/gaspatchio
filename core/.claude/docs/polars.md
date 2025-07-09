## Rule Details

- **Pattern**: `*.rs`
- **Severity**: Error
- **Category**: Ownership

# Rust Polars Integration

Polars is a fast, multi-threaded DataFrame library designed for Rust. One of the powerful features of Polars is its 
plugin system, which allows developers to write custom expressions for specialized use cases. This document 
focuses on how to specify output data types in expression plugins, ensuring that Polars understands and properly 
handles the data returned by your custom function.

## Output Data Types in Polars Plugins

When building a plugin function, you must define the function's signature, including specifying the expected input 
data type and the function return type. Within Polars, if the output data type isn't specified, Polars tries to 
infer the type from the function return signature. This works fine for well-known types. For advanced or custom 
types, it might be necessary to explicitly specify the function's output data type.

To define the output data type, Polars allows you to set the attribute `#[polars_expr(output_type_func = function_name)]` 
above your function. This attribute points to a helper function returning the `DataType` the plugin will produce.


## Examples:


When creating a dataframe with vectors ensure you call .into()
### Good : Creating a dataframe with vectors ✅

```rust
        let df = df! {
            "id" => [1, 2],
            "scalar" => ["a", "b"],
            "vector" => ListChunked::from_iter([
                Some(Series::new("".into() vec![10, 20])),
                Some(Series::new("".into(), vec![30, 40, 50]))
            ]).into_series()
```

### Bad : Creating a dataframe with vectors ❌

```rust
        let df = df! {
            "id" => [1, 2],
            "scalar" => ["a", "b"],
            "vector" => ListChunked::from_iter([
                Some(Series::new("", vec![10, 20])),
                Some(Series::new("", vec![30, 40, 50]))
            ]).into_series()
```



### Good : filling a series ✅

```rust
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

#[derive(Deserialize)]
struct FillSeriesKwargs {
    start: i64,
    increment: i64,
}
```

## References

- [Polars Rust Documentation](https:/docs.rs/polars/latest/polars)