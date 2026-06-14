# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Verifies .of() aggregators emit __expr__ sentinel in canonical_form.
# ABOUTME: Guards against silent YAML round-trip breakage for all aggregator classes.
"""YAML round-trip guard: .of() aggregators must flag __expr__ in canonical_form."""

from __future__ import annotations

import polars as pl
import pytest

import gaspatchio_core.scenarios._aggregators as _agg_module
from gaspatchio_core.scenarios._aggregators import _AGGREGATOR_REGISTRY, _BaseAggregator
from gaspatchio_core.scenarios._config import parse_aggregations
from gaspatchio_core.scenarios._run import _agg_to_dict

# Only exercise aggregators shipped in the core module; custom aggregators
# registered by test helpers (e.g. Skewness in test_governance_cross_process)
# are third-party and not covered by this guard.
_CORE_MODULE = _agg_module.__name__
_CORE_AGGREGATORS = [
    (n, c)
    for n, c in _AGGREGATOR_REGISTRY.items()
    if issubclass(c, _BaseAggregator) and getattr(c, "__module__", "") == _CORE_MODULE
]


@pytest.mark.parametrize(("name", "cls"), _CORE_AGGREGATORS)
def test_of_aggregator_yaml_round_trip_fails_loudly(name: str, cls: type) -> None:
    """An .of(...) aggregator must either serialise faithfully OR raise on reload.

    Today, .of() aggregators emit ``within: '__expr__'`` which parse_aggregations
    rejects with ValueError. Silently rebuilding a Mean / Min / etc. pointing
    at a phantom ``__expr__`` column would be a footgun.
    """
    try:
        agg = cls.of(pl.col("loss").sum()).alias("x")  # type: ignore[call-arg]
    except TypeError:
        pytest.skip(f"{name} needs extra constructor args; covered by per-class tests")
    recipe = agg.canonical_form()
    recipe["alias"] = "x"
    # If within was emitted, it must be the sentinel, and parse_aggregations
    # must reject it loudly.
    if "within" in recipe:
        assert recipe["within"] == "__expr__", (
            f"{name}.canonical_form() did not flag the .of() escape hatch — "
            f"got within={recipe['within']!r}. YAML round-trip would silently "
            f"reload an aggregator pointing at column '__expr__'."
        )
        with pytest.raises(ValueError, match="__expr__|within must be"):
            parse_aggregations([recipe])


@pytest.mark.parametrize(("name", "cls"), _CORE_AGGREGATORS)
def test_of_aggregator_to_dict_raises_at_write_time(name: str, cls: type) -> None:
    """``.of()`` aggregators must raise at serialisation time, not on reload.

    A user calling ``plan.to_yaml(path)`` with an ``.of(expr)`` aggregator
    should get an immediate, informative ``NotImplementedError`` rather than
    a YAML file that fails to reload weeks later in an audit context.
    """
    try:
        agg = cls.of(pl.col("loss").sum()).alias("x")  # type: ignore[call-arg]
    except TypeError:
        pytest.skip(f"{name} needs extra constructor args; covered by per-class tests")
    with pytest.raises(NotImplementedError, match=r"\.of\(expr\)"):
        _agg_to_dict(agg)
