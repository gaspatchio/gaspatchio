"""Tests for the StringNamespaceProxy."""

import polars as pl
import pytest
from gaspatchio_core.column.column_proxy import ColumnProxy
from gaspatchio_core.column.expression_proxy import ExpressionProxy
from gaspatchio_core.column.namespaces.string_proxy import StringNamespaceProxy
from gaspatchio_core.frame.base import ActuarialFrame
from polars.testing import assert_frame_equal


@pytest.fixture
def sample_af() -> ActuarialFrame:
    """Return a sample ActuarialFrame for testing."""
    data = {
        "col_str": ["apple", "banana", None, "orange"],
        "col_int": [1, 2, 3, 4],
    }
    return ActuarialFrame(data)


def test_string_namespace_proxy_instantiation_from_column_proxy(
    sample_af: ActuarialFrame,
):
    """Test that StringNamespaceProxy can be instantiated from a ColumnProxy."""
    col_proxy = sample_af["col_str"]
    assert isinstance(col_proxy, ColumnProxy)
    str_proxy = StringNamespaceProxy(parent_proxy=col_proxy, parent_af=sample_af)
    assert isinstance(str_proxy, StringNamespaceProxy)
    assert str_proxy._parent_proxy is col_proxy
    assert str_proxy._parent_af is sample_af


def test_string_namespace_proxy_instantiation_from_expression_proxy(
    sample_af: ActuarialFrame,
):
    """Test that StringNamespaceProxy can be instantiated from an ExpressionProxy."""
    expr_proxy = sample_af["col_str"].alias("aliased_str")
    assert isinstance(expr_proxy, ExpressionProxy)
    str_proxy = StringNamespaceProxy(parent_proxy=expr_proxy, parent_af=sample_af)
    assert isinstance(str_proxy, StringNamespaceProxy)
    assert str_proxy._parent_proxy is expr_proxy
    assert str_proxy._parent_af is sample_af


def test_get_base_expr_from_column_proxy(sample_af: ActuarialFrame):
    """Test _get_base_expr when parent is ColumnProxy."""
    col_proxy = sample_af["col_str"]
    str_proxy = StringNamespaceProxy(parent_proxy=col_proxy, parent_af=sample_af)
    base_expr = str_proxy._get_base_expr()
    assert isinstance(base_expr, pl.Expr)
    # Check if the expression correctly refers to the column name
    # A simple way to test this is to use it in a select context
    df_collected = sample_af.select(base_expr.alias("test_expr")).collect()
    expected_df = pl.DataFrame({"test_expr": ["apple", "banana", None, "orange"]})
    assert_frame_equal(df_collected, expected_df)


def test_get_base_expr_from_expression_proxy(sample_af: ActuarialFrame):
    """Test _get_base_expr when parent is ExpressionProxy."""
    # To properly test this, we need the .str attribute to be wired up on ExpressionProxy first,
    # or we manually create a StringNamespaceProxy with an ExpressionProxy parent that already
    # underwent a string operation.
    # For now, let's simulate creating StringNamespaceProxy AFTER a string op on ExpressionProxy
    # (even if the .str accessor isn't fully working for direct use like `sample_af["col_str"].str.some_op()` yet)

    # Simulate an existing ExpressionProxy that results from a string operation
    # This requires dispatch to be working for .str to return StringNamespaceProxy,
    # and StringNamespaceProxy to have __getattr__ or explicit methods.
    # Let's assume to_uppercase is an explicit method on StringNamespaceProxy for this setup
    # If not, this setup will fail before it even gets to _get_base_expr in the unit under test.

    # To avoid dependency on full .str wiring, we'll mock less:
    # Create a base ExpressionProxy
    base_expr_proxy = sample_af["col_str"].alias("intermediate_expr")
    # Manually create the StringNamespaceProxy, as if it was accessed via `.str`
    # This is slightly artificial but tests the _get_base_expr part.
    # To make a string operation happen, we'd call a method on StringNamespaceProxy.
    # StringNamespaceProxy itself doesn't *store* the result of an op, it *creates* one.

    # Let's construct a StringNamespaceProxy around a simple ColumnProxy that refers to a string column
    # then call a method that returns an ExpressionProxy, then make a new StringNamespaceProxy from THAT.
    initial_col_proxy = sample_af["col_str"]
    intermediate_str_proxy = StringNamespaceProxy(
        parent_proxy=initial_col_proxy, parent_af=sample_af
    )
    # Now, use an explicit method that returns an ExpressionProxy
    expr_proxy_after_str_op = (
        intermediate_str_proxy.to_uppercase()
    )  # This is now an ExpressionProxy

    # THIS is the StringNamespaceProxy whose _get_base_expr we want to test
    str_proxy_around_expr = StringNamespaceProxy(
        parent_proxy=expr_proxy_after_str_op, parent_af=sample_af
    )

    base_expr = str_proxy_around_expr._get_base_expr()
    assert isinstance(base_expr, pl.Expr)

    # Test the expression's output
    df_collected = sample_af.select(base_expr.alias("test_expr")).collect()
    expected_df = pl.DataFrame({"test_expr": ["APPLE", "BANANA", None, "ORANGE"]})
    assert_frame_equal(df_collected, expected_df)


def test_get_base_expr_invalid_parent():
    """Test _get_base_expr with an invalid parent type."""
    with pytest.raises(
        TypeError,
        match="StringNamespaceProxy parent must be ColumnProxy or ExpressionProxy",
    ):
        # Create a dummy parent that is not ColumnProxy or ExpressionProxy
        class DummyParent:
            pass

        invalid_parent = DummyParent()
        str_proxy = StringNamespaceProxy(parent_proxy=invalid_parent, parent_af=None)  # type: ignore
        str_proxy._get_base_expr()


def test_call_string_method_simple_method_on_column_proxy(sample_af: ActuarialFrame):
    """Test _call_string_method with a simple method like 'to_uppercase' via ColumnProxy."""
    col_proxy = sample_af["col_str"]
    str_proxy = StringNamespaceProxy(parent_proxy=col_proxy, parent_af=sample_af)

    result_expr_proxy = str_proxy._call_string_method("to_uppercase")
    assert isinstance(result_expr_proxy, ExpressionProxy)

    result_af_collected = sample_af.select(
        result_expr_proxy.alias("upper_str")
    ).collect()
    expected_df = pl.DataFrame({"upper_str": ["APPLE", "BANANA", None, "ORANGE"]})
    assert_frame_equal(result_af_collected, expected_df)


def test_call_string_method_simple_method_on_expression_proxy(
    sample_af: ActuarialFrame,
):
    """Test _call_string_method with 'to_lowercase' via ExpressionProxy."""
    # Create an initial expression proxy (e.g., from an alias or another operation)
    expr_proxy_parent = sample_af["col_str"].alias("ignored_alias")
    str_proxy = StringNamespaceProxy(
        parent_proxy=expr_proxy_parent, parent_af=sample_af
    )

    # For this test, let's assume col_str could have mixed case initially
    mixed_case_af = ActuarialFrame({"col_str": ["ApPlE", "BaNaNa", None, "OrAnGe"]})
    col_proxy_mixed = mixed_case_af["col_str"]
    str_proxy_mixed = StringNamespaceProxy(
        parent_proxy=col_proxy_mixed, parent_af=mixed_case_af
    )

    result_expr_proxy = str_proxy_mixed._call_string_method("to_lowercase")
    assert isinstance(result_expr_proxy, ExpressionProxy)

    result_af_collected = mixed_case_af.select(
        result_expr_proxy.alias("lower_str")
    ).collect()
    expected_df = pl.DataFrame({"lower_str": ["apple", "banana", None, "orange"]})
    assert_frame_equal(result_af_collected, expected_df)


def test_call_string_method_with_args_and_kwargs(sample_af: ActuarialFrame):
    """Test _call_string_method with a method that takes args/kwargs, e.g., 'zfill'."""
    col_proxy = sample_af["col_int"].cast(pl.String)  # Cast int to string for zfill
    str_proxy = StringNamespaceProxy(parent_proxy=col_proxy, parent_af=sample_af)

    # Test zfill(3)
    result_expr_proxy = str_proxy._call_string_method("zfill", 3)
    assert isinstance(result_expr_proxy, ExpressionProxy)
    result_af_collected = (
        sample_af.with_columns(col_proxy.alias("str_int"))
        .select(result_expr_proxy.alias("zfilled_str"))
        .collect()
    )
    expected_df = pl.DataFrame({"zfilled_str": ["001", "002", "003", "004"]})
    assert_frame_equal(result_af_collected, expected_df)


def test_call_string_method_nonexistent_method(sample_af: ActuarialFrame):
    """Test _call_string_method with a method that doesn't exist on Polars str namespace."""
    col_proxy = sample_af["col_str"]
    str_proxy = StringNamespaceProxy(parent_proxy=col_proxy, parent_af=sample_af)

    with pytest.raises(
        AttributeError,
        match="Polars 'str' namespace has no method 'non_existent_string_method'",
    ):
        str_proxy._call_string_method("non_existent_string_method")


def test_call_string_method_on_non_string_underlying_type(sample_af: ActuarialFrame):
    """Test _call_string_method when the underlying expression is not string-compatible for .str."""
    # This test might be tricky as Polars might coerce or error differently.
    # The goal is to see if our proxy handles it gracefully if Polars itself errors.
    col_proxy_int = sample_af["col_int"]  # An integer column
    str_proxy_on_int = StringNamespaceProxy(
        parent_proxy=col_proxy_int, parent_af=sample_af
    )

    result_expr_proxy = str_proxy_on_int._call_string_method("to_uppercase")
    assert isinstance(result_expr_proxy, ExpressionProxy)

    # Expect a Polars-level error (like SchemaError or ComputeError) when collecting
    with pytest.raises(pl.exceptions.PolarsError):
        sample_af.select(result_expr_proxy.alias("should_fail")).collect()


def test_call_string_method_error_in_polars_method(sample_af: ActuarialFrame):
    """Test that errors from the Polars method itself are propagated correctly."""
    af_invalid_str = ActuarialFrame({"s": ["1", "two", "3"]})
    col_proxy = af_invalid_str["s"]
    str_proxy = StringNamespaceProxy(parent_proxy=col_proxy, parent_af=af_invalid_str)

    result_expr_proxy = str_proxy._call_string_method("to_integer")
    assert isinstance(result_expr_proxy, ExpressionProxy)

    with pytest.raises(
        pl.exceptions.ComputeError,
        match="(Could not parse|Unable to parse string|conversion from `&str` to `i64` failed|strict integer parsing failed|invalid digit found in string)",
    ):
        af_invalid_str.select(
            result_expr_proxy.alias("parsed_int_should_fail")
        ).collect()


# --- Tests for Explicitly Proxied Methods ---


def test_explicit_method_contains_on_column_proxy(sample_af: ActuarialFrame):
    """Test the explicitly proxied 'contains' method via ColumnProxy."""
    col_proxy = sample_af["col_str"]
    # This is how the user would eventually use it, though .str is not wired up yet.
    # For now, we instantiate StringNamespaceProxy directly for testing the method itself.
    str_namespace_proxy = StringNamespaceProxy(
        parent_proxy=col_proxy, parent_af=sample_af
    )

    result_expr_proxy = str_namespace_proxy.contains("an")
    assert isinstance(result_expr_proxy, ExpressionProxy)

    result_af_collected = sample_af.select(
        result_expr_proxy.alias("contains_an")
    ).collect()
    expected_df_contains_an = pl.DataFrame({"contains_an": [False, True, None, True]})
    assert_frame_equal(result_af_collected, expected_df_contains_an)

    # For the literal test, use a fresh ActuarialFrame to avoid issues with modified sample_af._df
    fresh_data = {
        "col_str": ["apple", "banana", None, "orange"],
        "col_int": [1, 2, 3, 4],
    }
    fresh_af = ActuarialFrame(fresh_data)
    fresh_col_proxy = fresh_af["col_str"]
    # Create a new StringNamespaceProxy tied to the fresh_af
    fresh_str_namespace_proxy = StringNamespaceProxy(
        parent_proxy=fresh_col_proxy, parent_af=fresh_af
    )

    result_expr_proxy_literal = fresh_str_namespace_proxy.contains("an", literal=True)
    result_af_lit_collected = fresh_af.select(
        result_expr_proxy_literal.alias("contains_an_lit")
    ).collect()
    expected_df_contains_an_lit = pl.DataFrame(
        {"contains_an_lit": [False, True, None, True]}
    )
    assert_frame_equal(result_af_lit_collected, expected_df_contains_an_lit)


def test_explicit_method_to_uppercase_on_expression_proxy(sample_af: ActuarialFrame):
    """Test the explicitly proxied 'to_uppercase' method via ExpressionProxy."""
    expr_proxy_parent = sample_af["col_str"].alias("some_expr")
    str_namespace_proxy = StringNamespaceProxy(
        parent_proxy=expr_proxy_parent, parent_af=sample_af
    )

    result_expr_proxy = str_namespace_proxy.to_uppercase()
    assert isinstance(result_expr_proxy, ExpressionProxy)

    result_af_collected = sample_af.select(
        result_expr_proxy.alias("upper_str")
    ).collect()
    expected_df = pl.DataFrame({"upper_str": ["APPLE", "BANANA", None, "ORANGE"]})
    assert_frame_equal(result_af_collected, expected_df)


def test_explicit_method_to_lowercase_on_column_proxy(sample_af: ActuarialFrame):
    """Test the explicitly proxied 'to_lowercase' method via ColumnProxy."""
    # Use a frame with mixed case for a better test
    mixed_case_data = {"col_str": ["ApPlE", "BaNaNa", None, "OrAnGe"]}
    mixed_af = ActuarialFrame(mixed_case_data)
    col_proxy = mixed_af["col_str"]
    str_namespace_proxy = StringNamespaceProxy(
        parent_proxy=col_proxy, parent_af=mixed_af
    )

    result_expr_proxy = str_namespace_proxy.to_lowercase()
    assert isinstance(result_expr_proxy, ExpressionProxy)

    result_frame_collected = mixed_af.select(
        result_expr_proxy.alias("lower_str")
    ).collect()
    expected_df = pl.DataFrame({"lower_str": ["apple", "banana", None, "orange"]})
    assert_frame_equal(result_frame_collected, expected_df)
