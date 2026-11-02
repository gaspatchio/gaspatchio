# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The standard normal distribution function, ``norm_cdf``, end to end.

A guarantee priced as an option -- a GMDB valued as a Black-Scholes put --
needs N(d1) and N(d2). The framework had no normal distribution function and
Polars has no error function to compose one from, so the one model in evidence
hand-built a series and a continued fraction of some 190 operations inside a
column accessor: about sixty seconds a call at 100,000 policies, every node of
it engine text, and every node of the valuation downstream with it.

``norm_cdf`` is one operation of section 11.1.12, beside ``exp`` and ``log``,
computed by a native elementwise kernel as ``0.5 * erfc(-x / sqrt 2)``. These
tests hold what the section says of it: the values against Φ worked to 60
digits (the 1e-12 relative contract, the lower tail included), the exact
special values, both shapes, the one identity behind the Excel spelling, the
two refusals that point at core operations, and a GMDB put that is ``core``
from its inputs to its value. The conformance vectors in
``vectors/normal-cdf.json`` hold the same contract for a second engine.
"""

from __future__ import annotations

import json
import math
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact

# Φ at exact doubles: the double nearest the value worked to 60 digits by
# spec/graph-artifact/conformance/make_normal_cdf_vectors.py (series for
# |x| <= 4, Laplace's continued fraction beyond).
_PHI: dict[float, float] = {
    -37.5: 4.605353009581955e-308,
    -37.0: 5.725571222524577e-300,
    -30.0: 4.906713927148187e-198,
    -20.0: 2.7536241186062337e-89,
    -10.0: 7.61985302416053e-24,
    -8.36: 3.1359128294842655e-17,
    -6.0: 9.86587645037698e-10,
    -3.0: 0.0013498980316300946,
    -2.96: 0.0015381952117380587,
    -1.96: 0.024997895148220435,
    -1.0: 0.15865525393145705,
    0.0: 0.5,
    1.0: 0.8413447460685429,
    1.96: 0.9750021048517795,
    3.0: 0.9986501019683699,
    6.0: 0.9999999990134123,
}
_CONTRACT = 1e-12


def _artifact(frame: ActuarialFrame) -> dict[str, Any]:
    """Return ``frame``'s executable artifact, parsed back from the wire."""
    exported: dict[str, Any] = json.loads(
        GraphExporter(frame).export(profile="executable")
    )
    return exported


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


# --- the values ----------------------------------------------------------------


def test_every_normal_result_is_within_the_contract_of_the_true_phi() -> None:
    """11.1.12: 1e-12 relative to Φ wherever Φ is a normal double, -37.5 up."""
    points = sorted(_PHI)
    frame = ActuarialFrame(pl.DataFrame({"z": points}))
    frame.phi = frame.z.norm_cdf()
    answered = frame.collect()["phi"].to_list()

    for point, value in zip(points, answered, strict=True):
        assert value == pytest.approx(_PHI[point], rel=_CONTRACT, abs=0.0), point


def test_the_lower_tail_keeps_its_digits_where_the_textbook_formula_loses_them() -> (
    None
):
    """The one property that makes Φ worth an identifier, on an input that tests it.

    ``0.5 * (1 + erf(z / sqrt 2))`` misses Φ by most of itself at -8.36, where
    Φ is 3.1e-17: it subtracts two nearly equal numbers. ``erf`` there is
    -1 + 6.27e-17, between the doubles -1 and -1 + 2**-53, so an ``erf`` that
    lands on either neighbour (macOS's libm answers -1, glibc's the nearer,
    -1 + 2**-53) leaves the formula 0.0 or 2**-54 = 5.55e-17: 100% or 77% from
    Φ on every platform. An engine that composed Φ that way would pass every
    body value above and fail here, so the contract is a claim that can fail
    rather than one any formula meets.
    """
    textbook = 0.5 * (1.0 + math.erf(-8.36 / math.sqrt(2.0)))
    assert textbook in (0.0, 2.0**-54)
    assert textbook != pytest.approx(_PHI[-8.36], rel=_CONTRACT, abs=0.0)

    frame = ActuarialFrame(pl.DataFrame({"z": [-8.36]}))
    frame.phi = frame.z.norm_cdf()
    assert frame.collect()["phi"].to_list() == pytest.approx(
        [_PHI[-8.36]], rel=_CONTRACT, abs=0.0
    )


def test_below_the_normal_range_the_answer_is_subnormal_and_then_zero() -> None:
    """Φ(-38) is 2.9e-316, a subnormal; Φ(-40) is below every double: 0.0."""
    frame = ActuarialFrame(pl.DataFrame({"z": [-38.0, -40.0]}))
    frame.phi = frame.z.norm_cdf()
    at_38, at_40 = frame.collect()["phi"].to_list()

    assert 0.0 < at_38 < 2.2250738585072014e-308
    assert at_38 == pytest.approx(2.885428360068784e-316, rel=0.0, abs=1e-320)
    assert math.copysign(1.0, at_40) == 1.0
    assert at_40 == 0.0


def test_the_special_values_are_exact() -> None:
    """A null stays null, a NaN a NaN, and the infinities answer the limits."""
    frame = ActuarialFrame(
        pl.DataFrame({"z": [None, math.nan, math.inf, -math.inf, 0.0, -0.0]})
    )
    frame.phi = frame.z.norm_cdf()
    answered = frame.collect()["phi"].to_list()

    assert answered[0] is None
    assert math.isnan(answered[1])
    assert answered[2:] == [1.0, 0.0, 0.5, 0.5]


def test_a_whole_number_is_evaluated_as_a_double() -> None:
    frame = ActuarialFrame(pl.DataFrame({"z": [0, 1, -1]}))
    frame.phi = frame.z.norm_cdf()
    computed = frame.collect()

    assert computed.schema["phi"] == pl.Float64
    assert computed["phi"].to_list() == pytest.approx(
        [0.5, _PHI[1.0], _PHI[-1.0]], rel=_CONTRACT, abs=0.0
    )


def test_each_period_is_answered_on_a_ragged_book() -> None:
    """One value at a time inside each policy's own list; shapes are kept."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {"z": [[-1.96, 0.0, 1.96], [], None, [3.0, None]]},
            schema={"z": pl.List(pl.Float64)},
        )
    )
    frame.phi = frame.z.norm_cdf()
    computed = frame.collect()

    assert computed.schema["phi"] == pl.List(pl.Float64)
    first, empty, missing, last = computed["phi"].to_list()
    assert first == pytest.approx(
        [_PHI[-1.96], 0.5, _PHI[1.96]], rel=_CONTRACT, abs=0.0
    )
    assert empty == []
    assert missing is None
    assert last[0] == pytest.approx(_PHI[3.0], rel=_CONTRACT, abs=0.0)
    assert last[1] is None


def test_the_streaming_engine_answers_what_the_in_memory_one_does() -> None:
    """The kernel is elementwise, so streaming keeps running and agrees bit for bit."""
    rows = 50_000
    lazy = pl.LazyFrame(
        {
            "z": [((i % 997) - 498) / 83.0 for i in range(rows)],
            "zs": [[(i % 13) / 4.0 - 1.5, -(i % 7) / 2.0] for i in range(rows)],
        }
    )
    frame = ActuarialFrame(lazy)
    frame.phi = frame.z.norm_cdf()
    frame.phis = frame.zs.norm_cdf()

    streamed = frame.collect(engine="streaming")
    in_memory = frame.collect(engine="in-memory")
    assert streamed["phi"].to_list() == in_memory["phi"].to_list()
    assert streamed["phis"].to_list() == in_memory["phis"].to_list()


# --- one function, one identity ---------------------------------------------------


def test_the_excel_spelling_records_the_same_node() -> None:
    """``excel.norm_s_dist()`` is a second door to ``norm_cdf``, not a new identity."""
    data = pl.DataFrame({"policy_id": [1, 2], "d2": [0.24, -0.15]})

    textbook = ActuarialFrame(data)
    textbook.n_minus_d2 = (-textbook.d2).norm_cdf()
    workbook = ActuarialFrame(data)
    workbook.n_minus_d2 = (-workbook.d2).excel.norm_s_dist()

    assert (-textbook.d2).norm_cdf()._node == (-workbook.d2).excel.norm_s_dist()._node  # noqa: SLF001
    one, other = _artifact(textbook), _artifact(workbook)
    assert _node(one, "n_minus_d2@1")["expr"]["name"] == "norm_cdf"
    assert (
        _node(one, "n_minus_d2@1")["local_fingerprint"]
        == _node(other, "n_minus_d2@1")["local_fingerprint"]
    )
    assert one["graph_fingerprint"] == other["graph_fingerprint"]
    assert textbook.collect().equals(workbook.collect())


def test_the_density_is_refused_naming_it_in_core_operations() -> None:
    frame = ActuarialFrame(pl.DataFrame({"z": [0.0]}))

    with pytest.raises(ValueError, match="standard normal density") as refusal:
        frame.z.excel.norm_s_dist(cumulative=False)
    assert "(-z**2 / 2).exp() / (2 * math.pi) ** 0.5" in str(refusal.value)


def test_the_density_written_in_core_operations_is_the_density() -> None:
    """The formula the refusal names computes φ, so following it is safe."""
    frame = ActuarialFrame(pl.DataFrame({"z": [0.0, 1.0, -2.0]}))
    frame.density = (-(frame.z**2) / 2).exp() / (2 * math.pi) ** 0.5
    expected = [math.exp(-z * z / 2) / math.sqrt(2 * math.pi) for z in (0.0, 1.0, -2.0)]
    assert frame.collect()["density"].to_list() == pytest.approx(expected, rel=1e-15)


def test_cumulative_takes_true_or_false_only() -> None:
    frame = ActuarialFrame(pl.DataFrame({"z": [0.0]}))
    with pytest.raises(TypeError, match="takes True or False"):
        frame.z.excel.norm_s_dist(cumulative=1)  # type: ignore[arg-type]


def test_the_inverse_is_reserved_and_not_in_this_release() -> None:
    frame = ActuarialFrame(pl.DataFrame({"p": [0.995]}))
    with pytest.raises(AttributeError, match=r"not in 1\.0") as refusal:
        frame.p.norm_inv()  # type: ignore[attr-defined]
    assert "statistics.NormalDist().inv_cdf(0.995)" in str(refusal.value)
    assert ".polars_native()" not in str(refusal.value)


# --- a GMDB priced as a put is core from its inputs to its value -----------------


def _a_gmdb_put() -> ActuarialFrame:
    """Return a GMDB valued as a Black-Scholes put at every projection period.

    Four calls a row, as a converted workbook makes them: N(-d2) and N(-d1) at
    issue, and again at each period of each policy's remaining term.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "fund": [100_000.0, 80_000.0, 120_000.0],
                "guarantee": [100_000.0, 100_000.0, 100_000.0],
                "rate": [0.03, 0.03, 0.025],
                "vol": [0.18, 0.2, 0.15],
                "term": [10.0, 5.0, 8.0],
                "t": [[0.0, 1.0, 2.0], [0.0, 1.0], [0.0, 1.0, 2.0, 3.0]],
            }
        )
    )
    frame.sd = frame.vol * frame.term.sqrt()
    frame.d1 = (
        (frame.fund / frame.guarantee).log()
        + (frame.rate + frame.vol**2 / 2) * frame.term
    ) / frame.sd
    frame.d2 = frame.d1 - frame.sd
    frame.put_at_issue = (
        frame.guarantee * (-frame.rate * frame.term).exp() * (-frame.d2).norm_cdf()
        - frame.fund * (-frame.d1).excel.norm_s_dist()
    )
    frame.remaining = frame.term - frame.t + 0.5
    frame.sd_t = frame.vol * frame.remaining.sqrt()
    frame.d1_t = (
        (frame.fund / frame.guarantee).log()
        + (frame.rate + frame.vol**2 / 2) * frame.remaining
    ) / frame.sd_t
    frame.d2_t = frame.d1_t - frame.sd_t
    frame.put_t = (
        frame.guarantee
        * (-frame.rate * frame.remaining).exp()
        * (-frame.d2_t).norm_cdf()
        - frame.fund * (-frame.d1_t).norm_cdf()
    )
    return frame


def test_a_gmdb_put_is_core_throughout_and_reads_as_portable_to_jax() -> None:
    """No node is engine text, and the portability reading against jax is clean."""
    artifact = _artifact(_a_gmdb_put())
    computed = [node for node in artifact["nodes"] if node["kind"] == "computed"]

    assert {node["tier"] for node in computed} == {"core"}
    assert all(node["engines"] == [] for node in computed)
    report = validate_artifact(artifact, engine="jax", deep=True)
    assert report.ok, report.findings


def test_a_gmdb_put_values_as_black_scholes_does() -> None:
    """The put at issue against the closed form, evaluated with Python's own erfc."""
    computed = _a_gmdb_put().collect()

    def phi(x: float) -> float:
        return 0.5 * math.erfc(-x / math.sqrt(2.0))

    for row in computed.iter_rows(named=True):
        sd = row["vol"] * math.sqrt(row["term"])
        d1 = (
            math.log(row["fund"] / row["guarantee"])
            + (row["rate"] + row["vol"] ** 2 / 2) * row["term"]
        ) / sd
        d2 = d1 - sd
        put = row["guarantee"] * math.exp(-row["rate"] * row["term"]) * phi(-d2) - row[
            "fund"
        ] * phi(-d1)
        assert row["put_at_issue"] == pytest.approx(put, rel=1e-12)
