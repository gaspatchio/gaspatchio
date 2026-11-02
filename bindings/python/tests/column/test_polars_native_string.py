# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Public-boundary tests for Polars-native string expressions."""

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from gaspatchio._semantic.ir import EngineNative
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.frame.base import ActuarialFrame


@pytest.fixture
def sample_af() -> ActuarialFrame:
    """Return scalar strings and integers for string-expression tests."""
    return ActuarialFrame(
        {
            "col_str": ["apple", "banana", None, "orange"],
            "col_int": [1, 2, 3, 4],
        }
    )


def test_string_namespace_on_a_column_returns_values_and_lineage(
    sample_af: ActuarialFrame,
) -> None:
    """A string escape returns a proxy with an auditable native node."""
    upper = sample_af.col_str.polars_native().str.to_uppercase()

    assert isinstance(upper, ExpressionProxy)
    node = upper._node  # noqa: SLF001 - the calculation record is under test
    assert isinstance(node, EngineNative)
    assert node.engine == "polars"
    assert node.deps == ("col_str",)
    assert ".str.to_uppercase()" in node.text

    sample_af.upper = upper
    actual = sample_af.select(sample_af.upper).collect()
    expected = pl.DataFrame({"upper": ["APPLE", "BANANA", None, "ORANGE"]})
    assert_frame_equal(actual, expected)


def test_string_namespace_preserves_an_expression_receiver(
    sample_af: ActuarialFrame,
) -> None:
    """The namespace can continue an unfinished expression without reflection."""
    normalized = (
        sample_af.col_str.fill_null("Missing").polars_native().str.to_lowercase()
    )

    sample_af.normalized = normalized
    actual = sample_af.select(sample_af.normalized).collect()
    expected = pl.DataFrame({"normalized": ["apple", "banana", "missing", "orange"]})
    assert_frame_equal(actual, expected)


def test_string_method_forwards_positional_arguments(
    sample_af: ActuarialFrame,
) -> None:
    """Arguments keep Polars' native string-method meaning."""
    padded = (
        sample_af.col_int.polars_native().cast(pl.String).polars_native().str.zfill(3)
    )

    sample_af.padded = padded
    actual = sample_af.select(sample_af.padded).collect()
    expected = pl.DataFrame({"padded": ["001", "002", "003", "004"]})
    assert_frame_equal(actual, expected)


@pytest.mark.parametrize(
    ("pattern", "literal", "expected"),
    [
        ("an", True, [False, True, None, True]),
        ("^a", False, [True, False, None, False]),
    ],
)
def test_contains_keeps_literal_and_regex_semantics(
    sample_af: ActuarialFrame,
    pattern: str,
    *,
    literal: bool,
    expected: list[bool | None],
) -> None:
    """The explicit namespace exposes Polars' literal and regex choices."""
    contains = sample_af.col_str.polars_native().str.contains(
        pattern,
        literal=literal,
    )

    sample_af.contains = contains
    actual = sample_af.select(sample_af.contains).collect()
    assert_frame_equal(actual, pl.DataFrame({"contains": expected}))


def test_unknown_and_private_string_methods_are_refused(
    sample_af: ActuarialFrame,
) -> None:
    """Misspellings and implementation details fail at the public boundary."""
    namespace = sample_af.col_str.polars_native().str

    with pytest.raises(
        AttributeError,
        match="Polars namespace 'str' has no method named 'non_existent_string_method'",
    ):
        namespace.non_existent_string_method()

    with pytest.raises(AttributeError, match="is private"):
        namespace._implementation_detail()  # noqa: SLF001 - refusal is under test


def test_string_operation_on_an_integer_fails_when_polars_resolves_it(
    sample_af: ActuarialFrame,
) -> None:
    """The escape preserves Polars' dtype checks."""
    upper = sample_af.col_int.polars_native().str.to_uppercase()
    sample_af.upper = upper

    with pytest.raises(pl.exceptions.PolarsError):
        sample_af.collect()


def test_string_parse_error_retains_the_native_method_context() -> None:
    """A collect-time Polars failure still identifies the escaped operation."""
    frame = ActuarialFrame({"raw": ["1", "two", "3"]})
    frame.parsed = frame.raw.polars_native().str.to_integer()

    with pytest.raises(pl.exceptions.ComputeError, match=r"parse|conversion|digit"):
        frame.collect()
