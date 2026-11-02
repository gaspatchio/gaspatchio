# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One rule for a NaN: a column holding one makes every statistic over it NaN.

The column ``[-500, -400, nan, 300, 400]`` is the whole argument. Before this
rule three different behaviours shipped side by side. ``Sum``, ``Mean`` and
``Std`` propagated. ``Min`` and ``Max`` passed over the NaN and reported the
smallest and largest *known* value. ``Median``, ``Quantile`` and ``CTE``
answered ``0.00``, ``0.00`` and ``249.99`` -- plausible numbers, and wrong
ones -- because a NaN is neither greater nor less than zero and so fell into
the sketch's exact-zero bucket. Against the same column with the NaN removed
the honest answers are -50.02, -50.02 and 275.49.

Each case below is the rule's answer for one aggregator, driven through its own
``create_accumulator`` / ``add_input`` / ``extract_output`` protocol, beside
the same fold over the NaN-free column so that a change which merely broke the
statistic would be caught too.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio.scenarios._aggregators import (
    CTE,
    Count,
    Max,
    Mean,
    Median,
    Min,
    Quantile,
    QuantileRank,
    Std,
    Sum,
)
from gaspatchio.scenarios._audit import read_audit, write_audit
from gaspatchio.scenarios._period_sketch import (
    PeriodCTE,
    PeriodMedian,
    PeriodQuantile,
    _PeriodSketchAgg,
    build_period_sketches,
)
from gaspatchio.scenarios._sketch import SignedSketch

if TYPE_CHECKING:
    from pathlib import Path

    from gaspatchio.scenarios._metric import Aggregator

_NAN = float("nan")

# The column the rule was measured on, and the same column with the NaN
# taken out -- the honest answer every NaN answer stands in for.
WITH_NAN: list[float] = [-500.0, -400.0, _NAN, 300.0, 400.0]
WITHOUT_NAN: list[float] = [-500.0, -400.0, 300.0, 400.0]


def _fold(aggregator: Aggregator, values: list[float]) -> Any:  # noqa: ANN401
    """Drive one aggregator over ``values`` through its own protocol."""
    state = aggregator.create_accumulator()
    for value in values:
        state = aggregator.add_input(state, value)
    return aggregator.extract_output(state)


# --- the nine, one case each ------------------------------------------------


def test_sum_is_nan() -> None:
    """Sum already propagated; pinned so it stays one of the nine."""
    assert math.isnan(_fold(Sum("v"), WITH_NAN))
    assert _fold(Sum("v"), WITHOUT_NAN) == pytest.approx(-200.0)


def test_mean_is_nan() -> None:
    """Mean already propagated through Welford."""
    assert math.isnan(_fold(Mean("v"), WITH_NAN))
    assert _fold(Mean("v"), WITHOUT_NAN) == pytest.approx(-50.0)


def test_std_is_nan() -> None:
    """Std already propagated through Welford."""
    assert math.isnan(_fold(Std("v"), WITH_NAN))
    assert _fold(Std("v"), WITHOUT_NAN) == pytest.approx(465.4747, abs=1e-4)


def test_min_is_nan() -> None:
    """Min answered -500 before: the smallest *known* value, not the smallest."""
    assert math.isnan(_fold(Min("v"), WITH_NAN))
    assert _fold(Min("v"), WITHOUT_NAN) == pytest.approx(-500.0)


def test_max_is_nan() -> None:
    """Max answered 400 before, for the same reason."""
    assert math.isnan(_fold(Max("v"), WITH_NAN))
    assert _fold(Max("v"), WITHOUT_NAN) == pytest.approx(400.0)


def test_median_is_nan() -> None:
    """Median answered 0.0000 before -- the NaN counted as an exact zero."""
    assert math.isnan(_fold(Median("v"), WITH_NAN))
    assert _fold(Median("v"), WITHOUT_NAN) == pytest.approx(-50.0195, abs=1e-3)


def test_quantile_is_nan() -> None:
    """Quantile(0.5) answered 0.0000 before, and answers per level now."""
    out = _fold(Quantile("v", levels=(0.5,)), WITH_NAN)
    assert math.isnan(out[0.5])
    clean = _fold(Quantile("v", levels=(0.5,)), WITHOUT_NAN)
    assert clean[0.5] == pytest.approx(-50.0195, abs=1e-3)


def test_cte_is_nan() -> None:
    """CTE(0.5, upper) answered 249.9912 before against an honest 275.4891."""
    assert math.isnan(_fold(CTE("v", level=0.5, direction="upper"), WITH_NAN))
    clean = _fold(CTE("v", level=0.5, direction="upper"), WITHOUT_NAN)
    assert clean == pytest.approx(275.4891, abs=1e-3)


def test_count_still_counts_the_nan() -> None:
    """Count is untouched: a NaN is an observation, and five values is five."""
    assert _fold(Count("v"), WITH_NAN) == 5
    assert _fold(Count("v"), WITHOUT_NAN) == 4


# --- the tenth, which shares the sketch -------------------------------------


def test_quantile_rank_is_nan() -> None:
    """QuantileRank bisects on quantiles, so it has to say NaN outright.

    Every probe on a sketch holding a NaN comes back NaN, and ``nan < at`` is
    False, so the bisection walks the upper bound down to a confident 0.0 --
    the same plausible wrong number in the one sketch-backed aggregator the
    nine do not name.
    """
    assert math.isnan(_fold(QuantileRank("v", at=0.0), WITH_NAN))
    assert 0.0 <= _fold(QuantileRank("v", at=0.0), WITHOUT_NAN) <= 1.0


# --- the batch path answers what the per-value path answers ------------------


@pytest.mark.parametrize("aggregator", [Min("v"), Max("v"), Sum("v"), Mean("v")])
def test_add_batch_agrees_with_add_input(aggregator: Aggregator) -> None:
    """``add_batch`` is a vectorisation of the fold, not a second opinion.

    Polars' ``min``/``max`` pass over a NaN exactly as Python's do, so the
    batch path needed the same rule as the per-value one or a run would answer
    differently depending on how it was batched.
    """
    state = aggregator.add_batch(
        aggregator.create_accumulator(),
        pl.Series("v", WITH_NAN),
    )
    assert math.isnan(aggregator.extract_output(state))


def test_add_batch_skips_nulls_without_seeing_a_nan() -> None:
    """A null is still dropped; only a NaN takes the answer away."""
    values = pl.Series("v", [-500.0, None, 300.0])
    for aggregator in (Min("v"), Max("v")):
        state = aggregator.add_batch(aggregator.create_accumulator(), values)
        assert not math.isnan(aggregator.extract_output(state))


def test_extremum_over_a_non_float_column_still_works() -> None:
    """Whether a value is NaN is a float question, and only floats are asked.

    ``within="first"`` over a text column hands the fold strings; the NaN test
    has to answer False for them rather than raising.
    """
    state = Min("v").add_batch(Min("v").create_accumulator(), pl.Series("v", [3, 1, 2]))
    assert state == 1


# --- the sketch itself -------------------------------------------------------


def test_zero_bucket_stays_exact_for_real_zeros() -> None:
    """A column of real zeros is unchanged: the NaN has its own count now."""
    sketch = SignedSketch()
    for value in (-2.0, 0.0, 0.0, 3.0):
        sketch.add(value)
    assert sketch.zero_n == 2
    assert sketch.nan_n == 0
    assert not math.isnan(sketch.quantile(0.5))


def test_nan_lands_in_its_own_count_not_the_zero_bucket() -> None:
    """The routing change, said directly."""
    sketch = SignedSketch()
    sketch.add(_NAN)
    assert sketch.nan_n == 1
    assert sketch.zero_n == 0
    assert sketch.n == 1
    assert math.isnan(sketch.quantile(0.5))
    assert math.isnan(sketch.cte(level=0.5, direction="upper"))


def test_merge_carries_the_nan_count_across() -> None:
    """A clean batch merged with a NaN-carrying one is NaN from there on."""
    clean = SignedSketch()
    for value in (-500.0, -400.0):
        clean.add(value)
    dirty = SignedSketch()
    for value in (_NAN, 300.0, 400.0):
        dirty.add(value)
    assert clean.nan_n == 0
    assert dirty.nan_n == 1

    for merged in (
        SignedSketch.merge(clean, dirty),
        SignedSketch.merge(dirty, clean),
    ):
        assert merged.nan_n == 1
        assert merged.zero_n == 0
        assert merged.n == 5
        assert math.isnan(merged.quantile(0.5))

    assert not math.isnan(SignedSketch.merge(clean, clean).quantile(0.5))


def test_the_nan_count_survives_serialisation() -> None:
    """``to_bytes`` is state, so a sketch read back still knows to refuse.

    Refusing to serialise a sketch that has seen a NaN would stop a batched
    run in the middle for a reason the run is meant to carry to the end.
    """
    sketch = SignedSketch()
    for value in (-500.0, _NAN, 400.0):
        sketch.add(value)
    restored = SignedSketch.from_bytes(sketch.to_bytes())
    assert restored.nan_n == 1
    assert math.isnan(restored.quantile(0.5))


def test_the_nan_count_is_not_in_the_canonical_form() -> None:
    """The canonical form names the parameterisation, and no count is in it.

    ``zero_n`` was never in it either. Keeping ``nan_n`` out is what leaves
    every digest taken over a canonical form where it was.
    """
    clean = SignedSketch()
    clean.add(1.0)
    dirty = SignedSketch()
    dirty.add(_NAN)
    assert clean.canonical_form() == dirty.canonical_form()
    assert "nan_n" not in clean.canonical_form()


# --- the sidecar is valid JSON when a fold answers NaN ------------------------


def _refuse_bare_constant(token: str) -> float:
    """Refuse a bare ``NaN``/``Infinity`` token the way a strict reader does."""
    msg = f"bare {token} is not valid JSON"
    raise ValueError(msg)


def _write_sidecar(path: Path, outputs: dict[str, Any]) -> None:
    """Write one record carrying ``outputs`` and nothing else of interest."""
    write_audit(
        path,
        source_sha=f"sha256:{'0' * 64}",
        plan_canonical_form={"kind": "ScenarioRun"},
        run_metadata={"wall_time_s": 1.0},
        aggregator_outputs=outputs,
        aggregator_identity={},
        graph_fingerprint=None,
        graph_fingerprint_by_scenario=None,
        input_data_fingerprint={},
    )


def test_sidecar_writes_the_specification_sentinel(tmp_path: Path) -> None:
    """A non-finite aggregate travels as the string naming itself (§10).

    Before this the writer let the float through to ``json.dumps``, which
    spelled it ``NaN`` -- a token the JSON grammar does not have. The file
    read as valid until somebody parsed it strictly, and then the one number
    that most needed reading took the whole record down with it.
    """
    path = tmp_path / "run.audit.json"
    _write_sidecar(
        path,
        {
            "worst": _NAN,
            "unbounded": math.inf,
            "unbounded_below": -math.inf,
            "total": -200.0,
        },
    )

    # The strict re-read: bare NaN would reach parse_constant and raise.
    payload = json.loads(path.read_text(), parse_constant=_refuse_bare_constant)
    outputs = payload["aggregator_outputs"]
    assert outputs["worst"] == "NaN"
    assert outputs["unbounded"] == "Infinity"
    assert outputs["unbounded_below"] == "-Infinity"
    assert outputs["total"] == -200.0

    # And the ordinary reader still reads it.
    assert read_audit(path)["aggregator_outputs"]["worst"] == "NaN"


def test_sidecar_sentinel_reaches_inside_containers(tmp_path: Path) -> None:
    """A NaN one container deeper is the same defect, so it is coerced too."""
    path = tmp_path / "nested.audit.json"
    _write_sidecar(
        path,
        {
            "by_period": [1.0, _NAN, 3.0],
            "by_level": {0.5: _NAN},
            "by_lob": pl.DataFrame({"lob": ["motor"], "worst": [_NAN]}),
        },
    )
    payload = json.loads(path.read_text(), parse_constant=_refuse_bare_constant)
    outputs = payload["aggregator_outputs"]
    assert outputs["by_period"] == [1.0, "NaN", 3.0]
    assert outputs["by_level"]["0.5"] == "NaN"
    assert outputs["by_lob"] == [{"lob": "motor", "worst": "NaN"}]


def test_sidecar_leaves_finite_numbers_as_numbers(tmp_path: Path) -> None:
    """Only the non-finite ones become strings; an ordinary run is unchanged."""
    path = tmp_path / "finite.audit.json"
    _write_sidecar(path, {"total": -200.0, "count": 5, "worst_scenario": "base"})
    outputs = json.loads(path.read_text(), parse_constant=_refuse_bare_constant)[
        "aggregator_outputs"
    ]
    assert outputs == {"total": -200.0, "count": 5, "worst_scenario": "base"}


# ---------------------------------------------------------------------------
# The same rule, one axis over: the per-period family.
#
# `Median`, `Quantile` and `CTE` above fold a flat column through
# `SignedSketch.add`, one value at a time, and `add` names a NaN before the
# zero bucket can take it. `PeriodMedian`, `PeriodQuantile` and `PeriodCTE`
# never reach `add`: they build each period's sketch from a histogram computed
# in Polars, and that path had nowhere to put a NaN at all. It did not answer
# a plausible wrong number the way the flat path once did -- it failed the
# whole collect, casting `log(NaN)` to a bin index -- so the rule's answer was
# not reachable on this axis by any input.
# ---------------------------------------------------------------------------

_PERIOD_FRAME_COLUMNS = {
    "period": [[0, 1, 2]] * 4,
}


def _period_frame(second_period: list[float]) -> pl.DataFrame:
    """Four scenarios over three periods; ``second_period`` is period 1's column."""
    return pl.DataFrame(
        {
            **_PERIOD_FRAME_COLUMNS,
            "cf": [
                [10.0, second_period[0], 100.0],
                [20.0, second_period[1], 200.0],
                [30.0, second_period[2], 300.0],
                [40.0, second_period[3], 400.0],
            ],
        }
    )


def test_a_nan_in_one_period_is_counted_against_that_period() -> None:
    """The histogram build keeps the count `SignedSketch.add` keeps."""
    sketches = build_period_sketches(
        _period_frame([1.0, 2.0, _NAN, 4.0]), "period", "cf", relative_accuracy=1e-4
    )
    assert [sk.nan_n for sk in sketches] == [0, 1, 0]
    # The NaN is an observation, so the period that saw it has seen four values
    # -- the same total as every other period, not three.
    assert [sk.n for sk in sketches] == [4, 4, 4]


@pytest.mark.parametrize(
    ("name", "aggregator"),
    [
        ("PeriodMedian", PeriodMedian(column="cf")),
        ("PeriodQuantile", PeriodQuantile(column="cf", levels=(0.5, 0.9))),
        ("PeriodCTE", PeriodCTE(column="cf", level=0.5, direction="upper")),
    ],
)
def test_a_nan_in_one_period_makes_that_period_nan_and_no_other(
    name: str, aggregator: _PeriodSketchAgg
) -> None:
    """Period 1 answers NaN; periods 0 and 2 answer what they would have anyway.

    The clean frame is folded beside it for the reason the flat cases above
    give: a change that merely broke the statistic would turn every period NaN
    and pass a test that only checked period 1.
    """
    dirty = build_period_sketches(
        _period_frame([1.0, 2.0, _NAN, 4.0]), "period", "cf", relative_accuracy=1e-4
    )
    clean = build_period_sketches(
        _period_frame([1.0, 2.0, 3.0, 4.0]), "period", "cf", relative_accuracy=1e-4
    )

    got = aggregator.extract_output(dirty)
    want = aggregator.extract_output(clean)
    # PeriodQuantile answers a dict keyed by level; the others answer one array.
    series = list(got.values()) if isinstance(got, dict) else [got]
    clean_series = list(want.values()) if isinstance(want, dict) else [want]

    for out, ref in zip(series, clean_series, strict=True):
        assert math.isnan(out[1]), f"{name}: period 1 saw a NaN and must answer NaN"
        assert not math.isnan(ref[1]), f"{name}: the clean fold must not be NaN"
        # Bit-for-bit, not approximately: the other periods saw no NaN, so
        # nothing about them changed.
        assert out[0] == ref[0]
        assert out[2] == ref[2]


def test_a_period_of_only_nans_is_nan_not_empty() -> None:
    """Every scenario NaN in one period is still an answered NaN, not a gap."""
    sketches = build_period_sketches(
        _period_frame([_NAN, _NAN, _NAN, _NAN]), "period", "cf", relative_accuracy=1e-4
    )
    assert sketches[1].nan_n == 4
    assert math.isnan(PeriodMedian(column="cf").extract_output(sketches)[1])


def test_a_null_is_not_a_nan_on_the_period_path() -> None:
    """A null is an absent observation; only a NaN is an unknown one.

    Nulls were already dropped by the `!= 0` filter and must stay dropped: a
    period whose value is missing in one scenario still has three it can rank.
    """
    frame = pl.DataFrame(
        {
            "period": [[0, 1, 2]] * 4,
            "cf": [
                [10.0, 1.0, 100.0],
                [20.0, 2.0, 200.0],
                [30.0, None, 300.0],
                [40.0, 4.0, 400.0],
            ],
        }
    )
    sketches = build_period_sketches(frame, "period", "cf", relative_accuracy=1e-4)
    assert sketches[1].nan_n == 0
    assert sketches[1].n == 3
    assert not math.isnan(PeriodMedian(column="cf").extract_output(sketches)[1])


def test_from_binned_without_a_nan_count_is_unchanged() -> None:
    """The new argument defaults to nought, so every existing build is bit-equal."""
    a = SignedSketch.from_binned(pos=[(3.0, 2)], neg=[(5.0, 1)], zero_n=4)
    b = SignedSketch.from_binned(
        pos=[(3.0, 2)], neg=[(5.0, 1)], zero_n=4, nan_n=0
    )
    assert a.nan_n == 0
    assert a.to_bytes() == b.to_bytes()
