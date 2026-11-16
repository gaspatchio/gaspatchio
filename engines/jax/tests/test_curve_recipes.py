# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A curve fitted to its knots is not the line between them.

A Smith-Wilson or Svensson curve carries ``interpolation: "linear"`` beside its
parametric block, because its knots are what it was fitted to. Read as a line
between those knots it answers a different curve under the same digest
(section 11.1.31), so this engine refuses it by name at inspection and at the
run alike, on either reading of the curve. A plain knot curve is unaffected.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

import gaspatchio_jax  # noqa: F401 -- turns on 64-bit doubles
from gaspatchio import ActuarialFrame
from gaspatchio.curves import Curve
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

VALUATION = dt.date(2025, 1, 1)
SMITH_WILSON = Curve.fit_smith_wilson(
    tenors=[1.0, 5.0, 10.0], rates=[0.03, 0.035, 0.04]
)


def _svensson_rate(t: float) -> float:
    """Return the spot rate of a smooth, positive Svensson curve at ``t`` years."""
    b0, b1, b2, b3, tau1, tau2 = 0.04, -0.01, 0.01, 0.005, 2.0, 8.0
    x1, x2 = t / tau1, t / tau2
    loading1 = (1.0 - math.exp(-x1)) / x1
    loading2 = (1.0 - math.exp(-x2)) / x2
    return (
        b0
        + b1 * loading1
        + b2 * (loading1 - math.exp(-x1))
        + b3 * (loading2 - math.exp(-x2))
    )


_SVENSSON_TENORS = [1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
SVENSSON = Curve.fit_svensson(
    tenors=_SVENSSON_TENORS, rates=[_svensson_rate(t) for t in _SVENSSON_TENORS]
)
NO_KNOTS = Curve.from_svensson(b0=0.04, b1=-0.01, b2=0.01, b3=0.005, tau1=2.0, tau2=8.0)
LINEAR = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.03, 0.05])

BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "term_months": [6, 6, 6],
        "benefit": [100.0, 200.0, 150.0],
        "tt": [0.5, 2.0, 12.0],
    }
)


def _timeline(af: Any) -> Any:  # noqa: ANN401 -- a proxy handed through
    return af.projection.set(
        valuation_date=VALUATION,
        until="term_months",
        until_value="term_months",
        frequency="monthly",
    )


def _ordinary_line(af: Any, curve: Curve) -> Any:  # noqa: ANN401
    af = _timeline(af)
    af.z = curve.spot_rate(af.tt) * 1.0
    return af


def _in_a_discount_factor(af: Any, curve: Curve) -> Any:  # noqa: ANN401
    af = _timeline(af)
    af.z = af.benefit * curve.discount_factor(af.tt)
    return af


SITES: dict[str, Callable[[Any, Curve], Any]] = {
    "an ordinary line": _ordinary_line,
    "a discount factor": _in_a_discount_factor,
}
CURVES = {"Smith-Wilson": SMITH_WILSON, "Svensson": SVENSSON}


def _document(af: Any) -> dict[str, Any]:  # noqa: ANN401
    af.collect()
    return json.loads(
        GraphExporter(af).export(profile="executable", include_source=False)
    )


@pytest.mark.parametrize("site", list(SITES))
@pytest.mark.parametrize("curve", list(CURVES))
def test_a_fitted_curve_is_refused_at_validate_and_at_the_run(
    curve: str, site: str
) -> None:
    """The report and the run name the fit, in one sentence."""
    document = _document(SITES[site](ActuarialFrame(BOOK), CURVES[curve]))
    engine = engine_named("jax")
    refused = [
        one.condition or ""
        for one in engine.validate_tree(document)
        if one.status == "refused"
    ]
    assert refused, "validate reported a fitted curve lowered"
    assert "fitted parameters" in refused[0]
    with pytest.raises(EngineRefusal) as run:
        engine.run(document, BOOK, FrameSink())
    assert refused[0] in str(run.value)


def test_a_parametric_curve_with_no_knots_is_refused_as_a_fit() -> None:
    """``from_svensson`` holds no knot: the report and the run say the same thing."""
    document = _document(_ordinary_line(ActuarialFrame(BOOK), NO_KNOTS))
    engine = engine_named("jax")
    refused = [
        one.condition or ""
        for one in engine.validate_tree(document)
        if one.status == "refused"
    ]
    assert refused
    assert "svensson curve" in refused[0]
    with pytest.raises(EngineRefusal) as run:
        engine.run(document, BOOK, FrameSink())
    assert refused[0] in str(run.value)


def test_a_plain_knot_curve_is_bit_equal_and_is_linear_by_hand() -> None:
    """A plain knot curve still lowers: linear between knots, flat outside them."""
    af = _ordinary_line(ActuarialFrame(BOOK), LINEAR)
    polars = af.collect().sort("policy_id")["z"].to_list()
    document = json.loads(
        GraphExporter(af).export(profile="executable", include_source=False)
    )
    engine = engine_named("jax")
    assert not [
        one for one in engine.validate_tree(document) if one.status == "refused"
    ]
    answered = (
        engine.run(document, BOOK, FrameSink()).columns.sort("policy_id")["z"].to_list()
    )
    assert answered == polars
    assert answered == pytest.approx(
        [0.03, 0.03 + 0.02 * 1.0 / 29.0, 0.03 + 0.02 * 11.0 / 29.0], abs=1e-15
    )
