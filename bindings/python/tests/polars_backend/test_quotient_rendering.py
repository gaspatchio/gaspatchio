# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A quotient kernel is written down as the operator it computes.

``/``, ``//`` and ``%`` over numbers lower to ``ieee_div``, ``ieee_floordiv``
and ``ieee_mod``. The walk-through an export carries and the engine-native
text a fingerprint is taken over both read the engine's rendering, and both
must keep reading ``[(col("x")) / (dyn int: 12)]`` -- exactly what Polars
printed for the operator before the kernel replaced it. Otherwise a reader
is shown a Rust function's name, and every model that divides would record
a new fingerprint for a calculation that has not changed.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio.frame.graph.graph_utils import clean_expression_string
from gaspatchio.frame.lowering._polars.rendering import quotients_as_operators

_NATIVE = {"div": "/", "floordiv": "//", "mod": "%"}


@pytest.mark.parametrize(
    ("receiver", "argument", "native"),
    [
        (pl.col("x"), pl.lit(12), pl.col("x") / pl.lit(12)),
        (pl.col("x") * pl.col("y"), pl.lit(12), (pl.col("x") * pl.col("y")) / 12),
        (pl.lit(1.0), pl.col("x"), pl.lit(1.0) / pl.col("x")),
        (pl.col("x").sum(), pl.lit(12), pl.col("x").sum() / 12),
        (pl.lit(-1.5e-3), pl.col("k"), pl.lit(-1.5e-3) / pl.col("k")),
        (pl.col("price / unit"), pl.col("x"), pl.col("price / unit") / pl.col("x")),
    ],
)
def test_a_kernel_call_reads_exactly_as_polars_prints_the_operator(
    receiver: pl.Expr, argument: pl.Expr, native: pl.Expr
) -> None:
    rendered = f"{receiver}.<plugin>:ieee_div([{argument}])"
    assert quotients_as_operators(rendered) == str(native)


@pytest.mark.parametrize("kernel", ["div", "floordiv", "mod"])
def test_each_kernel_reads_as_its_own_operator(kernel: str) -> None:
    rendered = f'col("x").ieee_{kernel}([dyn float: 0.5])'
    expected = f'[(col("x")) {_NATIVE[kernel]} (dyn float: 0.5)]'
    assert quotients_as_operators(rendered) == expected


def test_nested_and_conditional_quotients_all_read_as_operators() -> None:
    nested = 'col("x").ieee_div([col("y")]).ieee_div([dyn int: 12])'
    assert (
        quotients_as_operators(nested)
        == '[([(col("x")) / (col("y"))]) / (dyn int: 12)]'
    )
    branch = (
        '.when([(col("x")) > (dyn int: 1)]).then(col("x").ieee_div([dyn int: 12]))'
        '.otherwise(col("y").ieee_floordiv([dyn float: 0.5]))'
    )
    assert quotients_as_operators(branch) == (
        '.when([(col("x")) > (dyn int: 1)]).then([(col("x")) / (dyn int: 12)])'
        '.otherwise([(col("y")) // (dyn float: 0.5)])'
    )


def test_a_name_that_spells_the_kernel_is_left_alone() -> None:
    text = 'col("a.ieee_div(").alias("ieee_mod(")'
    assert quotients_as_operators(text) == text


def test_the_export_cleaner_writes_the_operator_after_taking_the_path_out() -> None:
    raw = (
        'col("x")./opt/env/gaspatchio/_internal.cpython-313-darwin.so'
        ":ieee_div([dyn int: 12])"
    )
    assert clean_expression_string(raw) == '[(col("x")) / (dyn int: 12)]'


def test_an_engine_native_record_of_a_quotient_keeps_the_operator_text() -> None:
    """The text a fingerprint is taken over is what it was before the kernel."""
    from gaspatchio.frame.lowering._polars.plugins import ieee_quotient
    from gaspatchio.frame.lowering.ingress import native_node

    node = native_node(ieee_quotient(pl.col("x"), pl.lit(12)))
    assert node.text == str(pl.col("x") / pl.lit(12))
