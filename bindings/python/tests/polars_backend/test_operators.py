# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for polars_backend.operators — especially the scalar^list identity branches."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.polars_backend.operators import (
    dispatch_list_op,
    execute_list_clip,
    execute_list_pow,
)


class TestScalarPowList:
    """The scalar^list = exp(list * log(scalar)) identity has 3 branches."""

    @pytest.mark.parametrize(
        ("base", "expected_present"),
        [(2.0, True), (0.0, True), (-2.0, False)],
    )
    def test_branch_for_each_base_sign(
        self, base: float, expected_present: bool
    ) -> None:
        df = pl.DataFrame({"base": [base], "exp": [[1.0, 2.0, 3.0]]})
        result = (
            df.lazy()
            .select(
                execute_list_pow(
                    pl.col("base"), (pl.col("exp"),), base_is_list=False
                ).alias("r")
            )
            .collect()
        )
        result_list = result["r"][0]
        if expected_present:
            assert result_list is not None
        else:
            # negative base with fractional exponent -> all-null list or null list
            if result_list is not None:
                values = result_list.to_list()
                # must not be the naive negative-power result
                assert values != [-2.0, 4.0, -8.0]


class TestListPowList:
    def test_list_pow_list_works(self) -> None:
        df = pl.DataFrame({"base": [[2.0, 3.0]], "exp": [[2.0, 3.0]]})
        result = (
            df.lazy()
            .select(
                execute_list_pow(
                    pl.col("base"), (pl.col("exp"),), base_is_list=True
                ).alias("r")
            )
            .collect()
        )
        assert result["r"][0].to_list() == pytest.approx([4.0, 27.0])


class TestListClip:
    def test_list_clip_with_scalar_bounds(self) -> None:
        df = pl.DataFrame({"v": [[0.5, 1.5, 2.5, 3.5]]})
        result = (
            df.lazy()
            .select(
                execute_list_clip(
                    pl.col("v"),
                    (pl.lit(1.0), pl.lit(3.0)),
                    {},
                ).alias("r")
            )
            .collect()
        )
        assert result["r"][0].to_list() == pytest.approx([1.0, 1.5, 2.5, 3.0])


class TestDispatchListOp:
    def test_dispatch_pow_routes_to_execute_list_pow(self) -> None:
        df = pl.DataFrame({"base": [[2.0, 3.0]], "exp": [[2.0, 3.0]]})
        via_router = (
            df.lazy()
            .select(
                dispatch_list_op(
                    "pow",
                    pl.col("base"),
                    (pl.col("exp"),),
                    {},
                    base_is_list=True,
                ).alias("r")
            )
            .collect()
        )
        direct = (
            df.lazy()
            .select(
                execute_list_pow(
                    pl.col("base"), (pl.col("exp"),), base_is_list=True
                ).alias("r")
            )
            .collect()
        )
        assert via_router["r"][0].to_list() == direct["r"][0].to_list()

    def test_dispatch_unknown_op_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="No backend handler"):
            dispatch_list_op("unknown_op", pl.col("v"), (), {})


class TestScalarRpowProxyExp:
    """``scalar ** ExpressionProxy(list)`` routes through ``list_pow``.

    Regression guard: ``_method_caller``'s ``pow_arg_is_list`` check
    previously inspected only ``ColumnProxy`` operands. Derived list
    expressions like ``af.month / 12.0`` produce ``ExpressionProxy`` with
    ``shape == "list"``, and ``1.01 ** (af.month / 12.0)`` would fall
    through to native ``pl.Expr.pow`` which Polars rejects for
    ``list[f64]`` exponents (``pow operation not supported for dtype
    list[f64] as exponent``).
    """

    def test_scalar_rpow_expressionproxy_derived_from_list(self) -> None:
        from gaspatchio_core import ActuarialFrame

        af = ActuarialFrame(
            {"pid": [1, 2], "months": [[0, 1, 2, 3], [0, 1, 2, 3]]}
        )
        af.factor = 1.01 ** (af.months / 12.0)
        result = af.collect()["factor"][0].to_list()
        # (1.01)^(0/12) = 1.0; (1.01)^(1/12) ≈ 1.000829896
        assert len(result) == 4
        assert result[0] == pytest.approx(1.0)
        assert result[1] == pytest.approx(1.01 ** (1 / 12))
        assert result[3] == pytest.approx(1.01 ** (3 / 12))

    def test_scalar_rpow_columnproxy_list_still_works(self) -> None:
        """Sanity check the original ``ColumnProxy`` path didn't regress."""
        from gaspatchio_core import ActuarialFrame

        af = ActuarialFrame({"pid": [1], "vals": [[1.0, 2.0, 3.0]]})
        af.r = 2.0 ** af.vals
        result = af.collect()["r"][0].to_list()
        assert result == pytest.approx([2.0, 4.0, 8.0])
