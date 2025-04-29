import datetime

import polars as pl
from gaspatchio_core.dsl.core import ActuarialFrame
from polars.testing import assert_frame_equal


def test_basic_delegation_arithmetic():
    data = {"a": [1, 2, 3], "b": [4, 5, 6]}
    af = ActuarialFrame(data)

    # Test proxied arithmetic (already worked, but good baseline)
    af["c"] = af["a"] + af["b"]
    af["d"] = af["a"] * 2

    # Test newly autopatched method (e.g., abs)
    # Create a negative column to properly test abs
    af["a_neg"] = af["a"] * -1
    af["a_neg_abs"] = af["a_neg"].abs()

    # Test chaining
    af["b_chain"] = af["b"].abs().cast(pl.Float32) * 3

    expected_data = {
        "a": [1, 2, 3],
        "b": [4, 5, 6],
        "c": [5, 7, 9],
        "d": [2, 4, 6],
        "a_neg": [-1, -2, -3],
        "a_neg_abs": [1, 2, 3],
        "b_chain": [12.0, 15.0, 18.0],  # Note float type
    }
    expected_lf = pl.LazyFrame(expected_data).with_columns(
        pl.col("b_chain").cast(pl.Float32)  # Ensure correct type in expected
    )

    # Need to select columns in the same order for comparison
    result_lf = af._df.select(expected_lf.columns)

    assert_frame_equal(result_lf.collect(), expected_lf.collect())


def test_delegation_agg():
    data = {"group": ["x", "x", "y"], "value": [10, 20, 30]}
    af = ActuarialFrame(data)

    # Test aggregation method via proxy
    agg_af = (
        af._df.group_by("group")
        .agg(
            mean_val=af["value"].mean()._expr,  # Use proxy within agg, then unwrap
            sum_val=af["value"].sum()._expr,  # Use proxy within agg, then unwrap
        )
        .sort("group")
    )

    expected = pl.LazyFrame(
        {"group": ["x", "y"], "mean_val": [15.0, 30.0], "sum_val": [30, 30]}
    )

    assert_frame_equal(agg_af.collect(), expected.collect())


def test_namespace_delegation_dt():
    data = {"dates": [datetime.date(2023, 1, 1), datetime.date(2024, 12, 31)]}
    af = ActuarialFrame(data)
    af["year"] = af["dates"].dt.year()
    af["month"] = af["dates"].dt.month()

    expected = pl.LazyFrame(
        {
            "dates": [datetime.date(2023, 1, 1), datetime.date(2024, 12, 31)],
            "year": [2023, 2024],
            "month": [1, 12],
        }
    )
    result_lf = af._df.select(expected.columns)
    assert_frame_equal(result_lf.collect(), expected.collect(), check_dtypes=False)


def test_namespace_delegation_str():
    data = {"text": ["apple", "banana", "orange"]}
    af = ActuarialFrame(data)
    af["contains_a"] = af["text"].str.contains("a")
    af["len"] = af["text"].str.len_bytes()  # Example method

    expected = pl.LazyFrame(
        {
            "text": ["apple", "banana", "orange"],
            "contains_a": [True, True, True],
            "len": [5, 6, 6],  # Length in bytes
        }
    )
    result_lf = af._df.select(expected.columns)
    assert_frame_equal(result_lf.collect(), expected.collect(), check_dtypes=False)


def test_namespace_delegation_list():
    data = {"lists": [[1, 2], [3, 4, 5], []]}
    af = ActuarialFrame(data)
    af["list_sum"] = af["lists"].list.sum()
    af["list_len"] = af["lists"].list.len()

    expected = pl.LazyFrame(
        {
            "lists": [[1, 2], [3, 4, 5], []],
            "list_sum": [3, 12, 0],
            "list_len": [2, 3, 0],
        }
    )
    result_lf = af._df.select(expected.columns)
    # list type can be tricky with nulls/empties, check_dtype=False helps
    assert_frame_equal(result_lf.collect(), expected.collect(), check_dtypes=False)


def test_vector_shim_unary_ops():
    data = {
        "list_float": [[1.1, 2.9], [-3.5, 0.0], [100.2]],
        "list_int": [[1, 2], [-3, 0], [100]],
        "scalar_float": [1.1, -3.5, 100.2],
    }
    af = ActuarialFrame(data)

    # Test floor on list<float> -> should use list.eval via shim
    af["list_float_floor"] = af["list_float"].floor()

    # Test abs on list<int> -> should use list.eval via shim
    af["list_int_abs"] = af["list_int"].abs()

    # Test sqrt on list<float> (ensure positive input or handle errors)
    # Make list positive first for sqrt
    af["list_float_pos"] = af["list_float"].list.eval(
        pl.element().filter(pl.element() > 0)
    )
    # Apply sqrt() to the positive list column
    af["list_float_pos_sqrt"] = af["list_float_pos"].sqrt()

    # Test on scalar -> shim should NOT apply list.eval
    af["scalar_float_floor"] = af["scalar_float"].floor()

    # Test non-unary op on list -> shim should NOT apply list.eval (Polars handles it)
    af["list_float_plus_1"] = af["list_float"] + 1  # Relies on Polars broadcasting

    expected = pl.LazyFrame(
        {
            "list_float": [[1.1, 2.9], [-3.5, 0.0], [100.2]],
            "list_int": [[1, 2], [-3, 0], [100]],
            "scalar_float": [1.1, -3.5, 100.2],
            "list_float_floor": [
                [1.0, 2.0],
                [-4.0, 0.0],
                [100.0],
            ],  # Note: floor result is float
            "list_int_abs": [[1, 2], [3, 0], [100]],
            "list_float_pos": [[1.1, 2.9], [], [100.2]],  # After filter
            # Sqrt result needs careful type checking, Polars usually returns float
            "list_float_pos_sqrt": [[1.0488088, 1.7029386], [], [10.009995]],
            "scalar_float_floor": [1.0, -4.0, 100.0],  # Scalar floor
            # Polars >= 0.19.12 might broadcast differently, adjust if needed
            "list_float_plus_1": [[2.1, 3.9], [-2.5, 1.0], [101.2]],
        }
    )

    # Adjust expected types if necessary based on Polars version
    expected = expected.with_columns(
        pl.col("list_float_pos_sqrt").cast(pl.List(pl.Float64)),
        pl.col("list_float_plus_1").cast(pl.List(pl.Float64)),
    )

    result_lf = af._df.select(expected.columns)
    # Use check_exact=False due to potential float precision issues with sqrt
    assert_frame_equal(
        result_lf.collect(), expected.collect(), check_dtype=False, rtol=1e-5
    )
