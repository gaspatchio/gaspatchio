# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Reducing on the card, held to Polars' own fold to 1e-12 of each line's scale.

Levels 4 and 5 at a thousand policies each, folded three ways: by Polars
(``run_aggregated`` with no engine, on the tree's own tutorial model), by this
engine on the committed artifact (the file door's path), and by
``run_aggregated(engine="jax")`` (the core door's path, which builds and
exports the model itself). Every aggregator kind the engine folds is here,
alone and partitioned with ``.over(by)``, over doubles, whole numbers and an
indicator.

**What "agree" means for a total.** Section 11.1.12's rule for a line is a difference
within 1e-12 of the line's scale, the largest magnitude among the line's own
values and the values it reads. A total reads the column it folds, over the
whole book, so its scale is the larger of the total itself and the largest
value in that column -- the magnitudes that were actually added. A variance
is in the column's units squared and takes that square; a rank is a fraction
and takes one. The worst ratio per aggregator kind is printed, so a reader of
the log has the number rather than a claim about it.

The Polars reference runs in this process, from the tutorials in the tree:
with the suite's ``PYTHONPATH`` that is the worktree's core, and without it
the core wheel this venv was built with.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import subprocess
from datetime import date
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jax
import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame, _internal
from gaspatchio.engines.aggregation import alias_of, extract_outputs
from gaspatchio.engines.format import SHA256_PREFIX
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.scenarios import (
    CTE,
    ArgMin,
    Count,
    Max,
    Mean,
    Median,
    Min,
    PeriodCount,
    PeriodCTE,
    PeriodMax,
    PeriodMean,
    PeriodMedian,
    PeriodMin,
    PeriodQuantile,
    PeriodStd,
    PeriodSum,
    PeriodVariance,
    Quantile,
    QuantileRank,
    Std,
    Sum,
    Variance,
    run_aggregated,
)
from gaspatchio_jax.aggregate import (
    Folding,
    fed,
    fold_batch_on_the_device,
    partitions_of,
    queued_beside,
    read_folds,
)
from gaspatchio_jax.engine import JaxEngine
from gaspatchio_jax.plan import ExecutionPlan
from tests.conftest import PROJECT, invocation
from tests.helpers import a_read_that_misses
from tests.models.export import JAGGED_TERMS_YEARS, JAGGED_WIDTHS

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio_jax.plan import Program

MODELS = PROJECT / "tests/models"
CORE = PROJECT.parents[1] / "bindings/python"
GSPIO = PROJECT / ".venv/bin/gspio"
FOLDER = {"level-4": "level-4-lifelib", "level-5": "level-5-scenarios"}
# The agreement band: 1e-12 of a line's scale (specification section 11.1.12).
BAND = 1e-12

# Partitions to rotate through: one text column, two text columns together,
# another text column, and a whole-number column with fifty-five values.
PARTITIONS: tuple[tuple[str, ...], ...] = (
    ("product_id",),
    ("sex", "fund_index"),
    ("plan_id",),
    ("age_at_entry",),
)

# Every kind the engine folds, built over a column. Quantile is here alone:
# ``run_aggregated`` refuses a multi-level quantile under ``.over()``, and so
# does the engine (see the refusals below).
SCALAR: dict[str, Callable[[str], Any]] = {
    "Sum": Sum,
    "Min": Min,
    "Max": Max,
    "Mean": Mean,
    "Variance": Variance,
    "Std": Std,
    "Quantile": lambda column: Quantile(column, levels=(0.05, 0.5, 0.995)),
    "Median": Median,
    "CTE": lambda column: CTE(column, level=0.05),
    "QuantileRank": lambda column: QuantileRank(column, at=0.0),
}
PERIOD: dict[str, Callable[[str], Any]] = {
    "PeriodSum": PeriodSum,
    "PeriodCount": PeriodCount,
    "PeriodMin": PeriodMin,
    "PeriodMax": PeriodMax,
    "PeriodMean": PeriodMean,
    "PeriodVariance": PeriodVariance,
    "PeriodStd": PeriodStd,
}


def aggregations() -> tuple[list[Any], dict[str, tuple[str, str]]]:
    """Return every supported kind alone and partitioned, with each alias's kind.

    Returns:
        The aggregators, and alias to ``(kind, column)`` -- what a ratio is
        attributed to and which column's magnitude it is judged against.

    """
    built: list[Any] = []
    kinds: dict[str, tuple[str, str]] = {}

    def add(alias: str, kind: str, column: str, aggregator: Any) -> None:  # noqa: ANN401 -- any kind
        built.append(aggregator)
        kinds[alias] = (kind, column)

    for turn, (kind, make) in enumerate(SCALAR.items()):
        add(kind, kind, "pv_net_cf", make("pv_net_cf").alias(kind))
        if kind != "Quantile":
            by = PARTITIONS[turn % len(PARTITIONS)]
            add(
                f"{kind}_over",
                kind,
                "pv_claims",
                make("pv_claims").alias(f"{kind}_over").over(by),
            )
    for turn, (kind, make) in enumerate(PERIOD.items()):
        add(kind, kind, "net_cf", make("net_cf").alias(kind))
        by = PARTITIONS[turn % len(PARTITIONS)]
        add(
            f"{kind}_over",
            kind,
            "claims",
            make("claims").alias(f"{kind}_over").over(by),
        )
    # The other carriers: a whole-number input, an indicator, and a per-period
    # whole number alone and partitioned.
    add("Sum_i64", "Sum", "sum_assured", Sum("sum_assured").alias("Sum_i64"))
    add("Mean_bool", "Mean", "has_gmdb", Mean("has_gmdb").alias("Mean_bool"))
    add(
        "PeriodSum_i64",
        "PeriodSum",
        "duration",
        PeriodSum("duration").alias("PeriodSum_i64"),
    )
    add(
        "PeriodMax_i64_over",
        "PeriodMax",
        "duration",
        PeriodMax("duration").alias("PeriodMax_i64_over").over("sex"),
    )
    return built, kinds


def _tutorial(model: str) -> Callable[[ActuarialFrame], ActuarialFrame]:
    """Return the tree's own tutorial model, with its assumptions loaded once."""
    base = CORE / "gaspatchio/tutorials" / FOLDER[model] / "base"
    spec = importlib.util.spec_from_file_location(
        f"aggregate_{model.replace('-', '_')}", base / "model.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if model == "level-5":
        # Level 5 is the model a scenario plan runs unchanged: it loads its
        # own assumptions and takes no override.
        return module.main  # type: ignore[no-any-return]
    assumptions = module.load_assumptions()

    def model_fn(af: ActuarialFrame) -> ActuarialFrame:
        return module.main(af, assumptions_override=assumptions)  # type: ignore[no-any-return]

    return model_fn


def _artifact(model: str) -> dict[str, Any]:
    read: dict[str, Any] = json.loads(
        (MODELS / f"{model}.artifact.json").read_text(encoding="utf-8")
    )
    return read


def _book(model: str) -> pl.DataFrame:
    return pl.read_parquet(MODELS / f"{model}.book.parquet")


def _scale(frame: pl.DataFrame, kind: str, column: str) -> float:
    """Return the magnitude a total of this column was added from."""
    values = frame[column]
    if isinstance(values.dtype, pl.List):
        values = values.explode()
    largest = values.cast(pl.Float64).abs().max()
    magnitude = float(largest) if isinstance(largest, (int, float)) else 0.0
    if kind == "QuantileRank":
        return 1.0
    if kind in ("Variance", "PeriodVariance"):
        return magnitude * magnitude
    return magnitude


def _ratio(reference: object, answer: object, floor: float) -> float:
    """Return the largest difference over the line's scale, holding the shape exactly.

    Partition keys, periods, the positions of NaN and the length of every
    vector are exact; only a finite value is compared to a tolerance.
    """
    if isinstance(reference, pl.DataFrame):
        assert isinstance(answer, pl.DataFrame)
        assert reference.columns == answer.columns
        keys = reference.columns[:-1]
        assert reference.select(keys).equals(answer.select(keys))
        return _ratio(
            reference.get_column(reference.columns[-1]).to_numpy(),
            answer.get_column(answer.columns[-1]).to_numpy(),
            floor,
        )
    if isinstance(reference, dict):
        assert isinstance(answer, dict)
        assert reference.keys() == answer.keys()
        return max(_ratio(reference[key], answer[key], floor) for key in reference)
    expected = np.asarray(reference, dtype=np.float64)
    got = np.asarray(answer, dtype=np.float64)
    assert expected.shape == got.shape
    assert np.array_equal(np.isnan(expected), np.isnan(got))
    finite = ~np.isnan(expected)
    if not finite.any():
        return 0.0
    difference = float(np.max(np.abs(expected[finite] - got[finite])))
    if difference == 0.0:
        return 0.0
    scale = max(
        floor,
        float(np.max(np.abs(expected[finite]))),
        float(np.max(np.abs(got[finite]))),
    )
    return difference / scale if scale else math.inf


@pytest.fixture(scope="module")
def folded() -> dict[str, dict[str, Any]]:
    """Return each model folded by Polars, by the engine, and by the core door."""
    answers: dict[str, dict[str, Any]] = {}
    for model in FOLDER:
        model_fn = _tutorial(model)
        book = _book(model)
        built, kinds = aggregations()
        answers[model] = {
            "kinds": kinds,
            "polars": run_aggregated(model_fn, book, built, batch_size=book.height),
            "engine": JaxEngine().aggregate(_artifact(model), book, built),
            "door": run_aggregated(model_fn, book, built, engine="jax"),
            "frame": model_fn(ActuarialFrame(book)).collect(),
            "fingerprint": model_fn(ActuarialFrame(book)).graph.fingerprint(),
        }
    return answers


@pytest.mark.parametrize("model", list(FOLDER))
def test_the_tree_s_tutorial_and_the_committed_artifact_are_one_model(
    model: str, folded: dict[str, dict[str, Any]]
) -> None:
    assert folded[model]["fingerprint"] == _artifact(model)["graph_fingerprint"]


@pytest.mark.parametrize("model", list(FOLDER))
@pytest.mark.parametrize("door", ["engine", "door"])
def test_every_supported_aggregator_agrees_with_polars_within_the_band(
    model: str, door: str, folded: dict[str, dict[str, Any]]
) -> None:
    """Every kind, alone and partitioned, through both doors, within 1e-12 of scale.

    ``PeriodCount`` is a count of cells and is compared exactly. The worst
    ratio per kind is printed; the assertion is the rule's own bound.
    """
    polars = folded[model]["polars"]
    answer = folded[model][door]
    frame = folded[model]["frame"]
    assert answer.n_policies == polars.n_policies
    assert answer.n_periods == polars.n_periods
    assert list(answer.aggregations) == list(polars.aggregations)
    worst: dict[str, tuple[float, str]] = {}
    for alias, (kind, column) in folded[model]["kinds"].items():
        ratio = _ratio(
            polars.aggregations[alias],
            answer.aggregations[alias],
            _scale(frame, kind, column),
        )
        if kind == "PeriodCount":
            assert ratio == 0.0, alias
        assert ratio < BAND, (alias, ratio)
        if ratio >= worst.get(kind, (-1.0, ""))[0]:
            worst[kind] = (ratio, alias)
    for kind, (ratio, alias) in worst.items():
        print(f"{model} {door} {kind}: worst ratio {ratio:.3e} at {alias}")  # noqa: T201 -- the measurement is the point


def test_what_produced_the_totals_is_on_the_result(
    folded: dict[str, dict[str, Any]],
) -> None:
    produced = folded["level-4"]["engine"].produced_by
    assert produced is not None
    assert produced.engine == "jax"
    assert produced.graph_fingerprint == _artifact("level-4")["graph_fingerprint"]
    assert produced.inputs_digest.startswith("sha256:")
    assert {"engine_version", "jax_version", "jaxlib_version"} <= set(produced.versions)
    # The core is named as the core's own manifests name it: the package as
    # installed and the version its extension was compiled as, apart, and the
    # extension's digest in the core's own form, so the engine's statement and
    # the core's about one install are the same strings.
    assert produced.versions["core_version"] == version("gaspatchio")
    assert produced.versions["extension_version"] == _internal.__version__
    extension = Path(_internal.__file__).read_bytes()
    assert produced.versions["extension_sha256"] == (
        f"{SHA256_PREFIX}{hashlib.sha256(extension).hexdigest()}"
    )
    # A CPU fold and a GPU fold are told apart by the record itself.
    assert produced.versions["backend"] == jax.default_backend()
    assert produced.versions["device"] == ", ".join(
        sorted({one.device_kind for one in jax.devices()})
    )
    assert folded["level-4"]["polars"].produced_by is None


SKETCHED: frozenset[str] = frozenset({"Quantile", "Median", "CTE", "QuantileRank"})

# The core DDSketch's default relative accuracy. A value on a bucket's edge
# can land in the next bucket, which moves an answer by about twice this.
SKETCH_ACCURACY = 1e-4


def test_a_fold_kept_in_a_quantile_sketch_says_what_its_agreement_is(
    folded: dict[str, dict[str, Any]],
) -> None:
    """Each sketch-backed alias carries a note naming its accuracy; no other does.

    The quantile family folds into the core's DDSketch on both paths, so it
    agrees with Polars within the sketch's accuracy rather than to 1e-12 of
    scale. A reviewer reading the record should find that said beside the
    number, and should not find it said of a total that holds to 1e-12.
    """
    produced = folded["level-4"]["engine"].produced_by
    assert produced is not None
    sketched = {
        alias
        for alias, (kind, _column) in folded["level-4"]["kinds"].items()
        if kind in SKETCHED
    }
    noted = {
        note.split(":", 1)[0] for note in produced.notes if "quantile sketch" in note
    }

    assert sketched
    assert noted == sketched
    assert all(
        "relative accuracy 0.0001" in note
        for note in produced.notes
        if "quantile sketch" in note
    )


# Enough policies for eighteen batches of seven, the last of them one policy
# long, and few enough that a batch of seven stays a test rather than a run.
SMALL_BOOK = 120


@pytest.mark.parametrize("model", list(FOLDER))
def test_a_forced_small_batch_equals_one_batch(model: str) -> None:
    """Batches of seven against the whole book in one, within 1e-12 of scale.

    Batching is a memory dial and not a results dial: a total that moved
    with it would be a fold whose answer depends on how the engine was fed.
    Counts, extremes and every partition key are exact; totals move only by
    the order their additions were made in.
    """
    built, kinds = aggregations()
    book = _book(model).head(SMALL_BOOK)
    whole = JaxEngine().aggregate(_artifact(model), book, built)
    sevens = JaxEngine().aggregate(_artifact(model), book, built, batch=7)
    assert sevens.batch_size == 7
    assert whole.batch_size == book.height
    assert sevens.n_periods == whole.n_periods
    for alias, (kind, _column) in kinds.items():
        ratio = _ratio(whole.aggregations[alias], sevens.aggregations[alias], 0.0)
        if kind in ("PeriodCount", "PeriodMin", "PeriodMax", "Min", "Max"):
            assert ratio == 0.0, alias
        assert ratio < BAND, (alias, ratio)


def test_the_fold_is_one_batch_at_a_time_whatever_the_loop() -> None:
    """The same batches folded last to first give the same totals.

    The fold is a function of one batch and the loop that feeds it is one
    function; a loop that hands the batches over in another order -- or as
    they finish rather than when the book is done -- must change nothing but
    the order of additions.
    """
    built, kinds = aggregations()
    book = _book("level-4")
    plan = ExecutionPlan.stage_inspect(_artifact("level-4"))
    folds, refusals = read_folds(plan, built)
    assert refusals == []
    prepared = plan.stage_prepare(plan.stage_validate_inputs(book))
    partitions = {
        one.by: partitions_of(prepared, one.by)
        for one in folds
        if one.by and one.partial is not None
    }
    folding = Folding(
        accumulators={one.alias: one.aggregator.create_accumulator() for one in folds}
    )
    # Held on purpose: the loop under test here is one that hands the
    # batches over last to first, which needs them all. The programs are the
    # engine's own for this fold -- returning the columns folded -- so each
    # policy's values are the ones the forward fold read; and each batch's
    # partials are queued beside its program, as the engine queues them.
    returns = frozenset(one.node_id for one in folds)
    queue = partial(queued_beside, folds=folds, folding=folding, partitions=partitions)
    held = list(fed(plan, prepared, 100, returns=returns, on_dispatch=queue))
    for batched in reversed(held):
        fold_batch_on_the_device(batched, prepared, folds, folding, partitions)
    forward = JaxEngine().aggregate(_artifact("level-4"), book, built, batch=100)
    backward = extract_outputs(
        [one.alias for one in folds],
        [one.aggregator for one in folds],
        folding.accumulators,
    )
    # Every fold, partitioned ones included: a partition's key and its
    # periods must land in the same slot whichever order the batches came in.
    assert any(one.by for one in folds)
    assert set(backward) == set(forward.aggregations)
    for alias, value in backward.items():
        kind = kinds[alias][0]
        ratio = _ratio(forward.aggregations[alias], value, 0.0)
        assert ratio < BAND, (alias, ratio)
        if kind in ("PeriodCount", "Min", "Max", "PeriodMin", "PeriodMax"):
            assert ratio == 0.0, alias


# A term book in miniature, jagged the way test_models.py's is: seven terms
# whose timelines round up to four widths, so four groups, four programs, and
# partitions whose policies stop at different periods inside one batch.
JAGGED_POLICIES = 350


# The per-period columns the jagged book folds. ``net_cf`` is nought past
# every policy's horizon -- the model multiplies it by policies in force --
# so a fold that forgot the horizon would still total it correctly; the other
# four are not, and are what hold the mask to account. ``duration`` is the
# whole-number one, which totals in int64 on the device.
UNPADDED_TO_ZERO: tuple[str, ...] = (
    "disc_factors",
    "mort_rate",
    "av_pp_mid_mth",
    "duration",
)
JAGGED_COLUMNS: tuple[str, ...] = ("net_cf", *UNPADDED_TO_ZERO)


def _jagged_book() -> pl.DataFrame:
    """Return level 4's book in miniature, each policy on one of seven terms."""
    base = CORE / "gaspatchio/tutorials" / FOLDER["level-4"] / "base"
    return (
        pl.read_parquet(base / "model_points_1k.parquet")
        .head(JAGGED_POLICIES)
        .with_columns(
            pl.int_range(1, JAGGED_POLICIES + 1, dtype=pl.Int64).alias("point_id"),
            pl.Series(
                "policy_term",
                [
                    JAGGED_TERMS_YEARS[row % len(JAGGED_TERMS_YEARS)]
                    for row in range(JAGGED_POLICIES)
                ],
                dtype=pl.Int64,
            ),
        )
    )


def test_a_jagged_book_folds_each_policy_to_its_own_timeline() -> None:
    """Totals over a book whose policies stop at different periods.

    Levels 4 and 5 are rectangles; this is not. Each batch's partial is cut
    to the longest timeline among its own policies -- per partition -- and
    that cut is what keeps every later batch's periods where they belong.
    Every closed-form kind folds every column here, alone and partitioned,
    and four of the columns carry values past a policy's horizon that only
    the mask keeps out of a total.
    """
    book = _jagged_book()
    model_fn = _tutorial("level-4")
    built = [
        *(
            make(column).alias(f"{kind}_{column}")
            for kind, make in PERIOD.items()
            for column in JAGGED_COLUMNS
        ),
        *(
            make(column).alias(f"{kind}_{column}_over").over("product_id")
            for kind, make in PERIOD.items()
            for column in JAGGED_COLUMNS
        ),
        Sum("pv_net_cf").alias("Sum"),
    ]
    polars = run_aggregated(model_fn, book, built, batch_size=book.height)
    engine = run_aggregated(model_fn, book, built, batch_size=64, engine="jax")
    frame = model_fn(ActuarialFrame(book)).collect()
    assert engine.n_periods == polars.n_periods < JAGGED_WIDTHS[-1]
    lengths = set(frame["net_cf"].list.len().to_list())
    assert len(lengths) > len(JAGGED_WIDTHS)
    for one in built:
        alias = one.alias if hasattr(one, "by") else one.alias_
        kind = type(one.inner if hasattr(one, "by") else one).__name__
        column = one.inner.column if hasattr(one, "by") else one.column
        ratio = _ratio(
            polars.aggregations[alias],
            engine.aggregations[alias],
            _scale(frame, kind, column),
        )
        if kind == "PeriodCount":
            assert ratio == 0.0, alias
        assert ratio < BAND, (alias, ratio)


def test_the_engine_s_padding_is_not_nought_where_the_mask_matters() -> None:
    """The four columns this suite leans on really do carry values past a horizon.

    Held here rather than assumed: were the model to start zeroing them, the
    jagged test above would stop testing the horizon mask without a word.
    """
    book = _jagged_book()
    af = _tutorial("level-4")(ActuarialFrame(book))
    document, inputs = af._for_an_engine()  # noqa: SLF001 -- the door's own book
    plan = ExecutionPlan.stage_inspect(document)
    folds, _refusals = read_folds(
        plan, [PeriodSum(column).alias(column) for column in UNPADDED_TO_ZERO]
    )
    prepared = plan.stage_prepare(plan.stage_validate_inputs(inputs))
    padded = dict.fromkeys(UNPADDED_TO_ZERO, False)
    for batched in fed(plan, prepared, 64):
        for one in folds:
            value = batched.values[one.node_id]
            assert value.horizon is not None
            past = (
                np.arange(value.array.shape[1])[None, :]
                >= np.asarray(value.horizon.lengths)[:, None]
            )
            cells = np.asarray(value.array)
            padded[alias_of(one.aggregator)] |= bool(np.any(cells[past] != 0))
    assert padded == dict.fromkeys(UNPADDED_TO_ZERO, True)


def _times_one(af: ActuarialFrame) -> ActuarialFrame:
    af.answer = af.flow * 1.0
    return af


@pytest.mark.parametrize("batch", [1, 3], ids=["a-batch-a-policy", "one-batch"])
def test_an_extremum_passes_over_a_nan_unless_a_period_holds_nothing_else(
    batch: int,
) -> None:
    """NaN in a period's least and greatest, exactly as Polars' fold has it.

    Polars' ``min`` and ``max`` pass over a NaN inside one group and answer
    NaN only for a group holding nothing else; the partials then merge across
    batches with NumPy's ``minimum`` and ``maximum``, which carry a NaN on.
    So the answer depends on the batching on both paths alike, and the two
    are compared at one batching and then at another. Partitioned too.
    """
    nan = float("nan")
    one = invocation(
        {
            "op": "binop",
            "kind": "mul",
            "left": {"op": "col", "name": "flow"},
            "right": {"op": "lit", "value": 1.0},
        },
        {
            "flow": {
                "dtype": "list[f64]",
                "values": [[1.0, nan, nan], [3.0, 2.0, nan], [nan, 5.0]],
            },
            "g": {"dtype": "str", "values": ["a", "a", "b"]},
        },
        "list[f64]",
    )
    built = [
        PeriodMin("answer").alias("least"),
        PeriodMax("answer").alias("greatest"),
        PeriodMin("answer").alias("least_by_g").over("g"),
        PeriodMax("answer").alias("greatest_by_g").over("g"),
    ]
    polars = run_aggregated(_times_one, one.inputs, built, batch_size=batch)
    engine = JaxEngine().aggregate(one.document, one.inputs, built, batch=batch)
    for alias in polars.aggregations:
        assert _ratio(polars.aggregations[alias], engine.aggregations[alias], 0.0) == 0
    if batch == len(one.inputs):
        # Within one batch: a NaN among numbers is passed over, and a period
        # of NaN alone answers NaN.
        np.testing.assert_array_equal(engine.least, [1.0, 2.0, nan])
        np.testing.assert_array_equal(engine.greatest, [3.0, 5.0, nan])
        by_g = engine.least_by_g.sort(["g", "period"])
        np.testing.assert_array_equal(
            by_g["least_by_g"].to_numpy(), [1.0, 2.0, nan, nan, 5.0]
        )


def _three_phase(af: ActuarialFrame) -> ActuarialFrame:
    """Return the house three-phase model: a setup phase that collects and derives.

    Phase 1 collects the model points and derives ``issue_age`` from the
    column the file spells ``Issue Age`` before building the frame, which is
    the shape the framework's own guidance writes. The frame then starts with
    a column the caller's book never held.
    """
    mp = af.collect()
    mp = mp.with_columns(pl.col("Issue Age").alias("issue_age"))
    af = ActuarialFrame(mp)
    af = af.projection.set(
        valuation_date=date(2025, 1, 1),
        until="term_months",
        until_value=12,
        frequency="monthly",
    )
    af.claim = af.issue_age * 0.25 * af.month
    af.pv_claim = af.claim.list.sum()
    return af


def test_a_setup_phase_that_collects_folds_as_the_frame_door_runs_it() -> None:
    """The aggregate door hands the engine the book the frame door hands it.

    ``run_aggregated(engine="jax")`` once handed over the caller's raw model
    points, which do not carry the ``issue_age`` the setup phase derived, and
    the engine refused a model ``collect(engine="jax")`` runs. Both doors now
    take the frame's own starting columns through one method.
    """
    book = pl.DataFrame(
        {
            "policy_id": list(range(1, 13)),
            "Issue Age": [30 + (row % 7) for row in range(12)],
            "product": ["TERM", "WL", "TERM"] * 4,
        }
    )
    built = [
        Sum("pv_claim").alias("pv_claim"),
        Sum("pv_claim").alias("pv_claim_by_product").over("product"),
        PeriodSum("claim").alias("claim"),
        PeriodMean("claim").alias("claim_by_product").over("product"),
    ]
    polars = run_aggregated(_three_phase, book, built, batch_size=book.height)
    engine = run_aggregated(_three_phase, book, built, batch_size=5, engine="jax")
    frame = _three_phase(ActuarialFrame(book)).collect(engine="jax")
    assert frame.height == book.height
    for alias in polars.aggregations:
        kind = "PeriodMean" if alias == "claim_by_product" else "Sum"
        ratio = _ratio(
            polars.aggregations[alias],
            engine.aggregations[alias],
            _scale(frame, kind, "claim" if alias.startswith("claim") else "pv_claim"),
        )
        assert ratio < BAND, (alias, ratio)
    produced = engine.produced_by
    assert produced is not None
    assert produced.inputs_digest == frame_door_digest(book)


def _renamed(af: ActuarialFrame) -> ActuarialFrame:
    af = af.rename({"a": "premium"})
    af.total = af.premium + af.b
    return af


def _written_over(af: ActuarialFrame) -> ActuarialFrame:
    af.a = af.a * 2
    af.total = af.a + af.b
    return af


def _dropped(af: ActuarialFrame) -> ActuarialFrame:
    af.total = af.a + af.b
    return af.drop("b")


@pytest.mark.parametrize(
    "model", [_renamed, _written_over, _dropped], ids=["rename", "overwrite", "drop"]
)
def test_an_input_the_frame_no_longer_holds_is_refused_by_both_doors_alike(
    model: Callable[[ActuarialFrame], ActuarialFrame],
) -> None:
    """The reverse of the setup-phase case: what one door refuses, both do.

    A frame that renamed, overwrote or dropped an arriving column no longer
    holds what the artifact's input node names. The frame door refuses that
    by name rather than filling it; the aggregate door, handed the caller's
    raw book, used to run it. One method now answers both.
    """
    book = pl.DataFrame({"a": [1.0, 2.0, 3.0], "b": [10.0, 20.0, 30.0]})
    with pytest.raises(EngineRefusal) as on_collect:
        model(ActuarialFrame(book)).collect(engine="jax")
    with pytest.raises(EngineRefusal) as on_aggregate:
        run_aggregated(model, book, [Sum("total").alias("total")], engine="jax")
    assert [
        (one.group, one.where, one.count) for one in on_aggregate.value.report.refusals
    ] == [(one.group, one.where, one.count) for one in on_collect.value.report.refusals]


def frame_door_digest(book: pl.DataFrame) -> str:
    """Return the inputs digest the frame door's own result manifest carries."""
    from gaspatchio.engines import engine_named
    from gaspatchio.engines.protocol import FrameSink

    af = _three_phase(ActuarialFrame(book))
    document, inputs = af._for_an_engine()  # noqa: SLF001 -- the door under test
    return engine_named("jax").run(document, inputs, FrameSink()).manifest.inputs_digest


# ---------------------------------------------------------------------------
# Refusals, by name, before the book is read
# ---------------------------------------------------------------------------


class _PeriodRange(PeriodSum):
    """A per-period kind of the caller's own, whose partial nothing here knows."""


@pytest.mark.parametrize(
    ("aggregator", "said", "next_step"),
    [
        (
            Count("pv_net_cf").alias("refused"),
            "Count counts the scenarios that contributed",
            "count the policies each period holds with PeriodCount",
        ),
        (
            ArgMin("pv_net_cf").alias("refused"),
            "ArgMin answers which scenario held the value",
            "fold Min for the value itself",
        ),
        (
            Sum.of(pl.lit(1.0)).alias("refused"),
            "Sum.of(...) reduces each batch to one value",
            "write the quantity as a column of the model",
        ),
        (
            PeriodQuantile("net_cf").alias("refused"),
            "whole distribution per period",
            "fold it on Polars",
        ),
        (
            PeriodMedian("net_cf").alias("refused"),
            "whole distribution per period",
            "or use a closed-form kind: PeriodSum",
        ),
        (
            PeriodCTE("net_cf").alias("refused"),
            "whole distribution per period",
            "fold it on Polars",
        ),
        (
            _PeriodRange("net_cf").alias("refused"),
            "whole distribution per period",
            "fold it on Polars",
        ),
        (
            Sum("no_such_column").alias("refused"),
            "not a column of this model",
            "name a column the model ends on",
        ),
        (
            Sum("net_cf").alias("refused"),
            "holds one value per period",
            "or use PeriodSum",
        ),
        (
            PeriodSum("pv_net_cf").alias("refused"),
            "holds one value per policy",
            "or use Sum",
        ),
        (
            Min("product_id").alias("refused"),
            "a fold totals numbers",
            "fold a numeric column",
        ),
        (
            Sum("pv_net_cf").alias("refused").over("mort_table_id"),
            "calculated by the model",
            "partition by a column that arrived with the book",
        ),
        (
            PeriodSum("net_cf").alias("refused").over("no_such_column"),
            "partition column 'no_such_column' is not a column",
            "partition by a column the model ends on",
        ),
    ],
    ids=[
        "Count",
        "ArgMin",
        "of",
        "PeriodQuantile",
        "PeriodMedian",
        "PeriodCTE",
        "a-caller-s-own-period-kind",
        "missing-column",
        "scalar-over-periods",
        "periods-over-scalar",
        "text",
        "computed-partition",
        "missing-partition",
    ],
)
def test_an_aggregator_the_engine_cannot_fold_is_refused_by_name(
    aggregator: Any,  # noqa: ANN401 -- an aggregator of any kind
    said: str,
    next_step: str,
) -> None:
    """Refused by name, with what to fold instead rather than why Polars agrees."""
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().aggregate(_artifact("level-4"), _book("level-4"), [aggregator])
    report = refused.value.report
    # No clause: the specification leaves every aggregate out of the artifact.
    assert [(one.group, one.where, one.clause) for one in report.refusals] == [
        ("tree", "refused", None)
    ]
    assert said in report.refusals[0].what
    assert next_step in report.refusals[0].move
    assert "refuses it on Polars" not in report.refusals[0].move
    assert report.closing_sentence() == "Nothing was computed."


@pytest.mark.parametrize(
    ("partitioned", "kind"),
    [
        (
            lambda: Quantile("pv_net_cf", levels=(0.5, 0.9)).alias("q").over("sex"),
            "Quantile",
        ),
        (lambda: PeriodQuantile("net_cf").alias("q").over("sex"), "PeriodQuantile"),
    ],
    ids=["Quantile-over", "PeriodQuantile-over"],
)
def test_a_multi_level_quantile_is_refused_where_over_is_written(
    partitioned: Any,  # noqa: ANN401 -- a callable building the aggregator
    kind: str,
) -> None:
    """No engine folds one partitioned, so ``.over()`` refuses it before any run."""
    with pytest.raises(
        NotImplementedError, match=rf"^{kind}\.over\(\) \('q'\) is not yet"
    ):
        partitioned()


def test_every_aggregation_refusal_is_in_one_report() -> None:
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().aggregate(
            _artifact("level-4"),
            _book("level-4"),
            [
                Sum("pv_net_cf").alias("fine"),
                Count("pv_net_cf").alias("first"),
                PeriodMedian("net_cf").alias("second"),
                Sum("pv_net_cf").alias("fine"),
                Sum("pv_net_cf"),
            ],
        )
    assert [one.where for one in refused.value.report.refusals] == [
        "first",
        "second",
        "fine",
        "aggregation 5",
    ]


@pytest.mark.parametrize("misses_at", [0, 19], ids=["first-batch", "last-batch"])
def test_a_refusal_in_any_batch_returns_nothing(misses_at: int) -> None:
    """A check that catches a cell in one batch withholds every total.

    The miss is on a computed key, so it is caught in the trace and judged at
    completion, after every batch has run -- the same moment ``run``'s own
    refusal is reached, with the same closing sentence.
    """
    one = a_read_that_misses(20, misses_at)
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().aggregate(
            one.document,
            one.inputs,
            [Sum("answer").alias("total"), Mean("answer").alias("average")],
            batch=7,
        )
    report = refused.value.report
    assert report.closing_sentence() == "No results were published."
    assert all(refusal.group == "completion" for refusal in report.refusals)


@pytest.mark.parametrize(
    "a_later_batch_refuses", [True, False], ids=["refusal", "none"]
)
def test_a_fault_folding_a_batch_is_held_behind_a_refusal(
    monkeypatch: pytest.MonkeyPatch, *, a_later_batch_refuses: bool
) -> None:
    """A defect met folding one batch waits for completion, as the stream's does.

    A later batch may yet refuse, and a refusal is the run's real answer. So
    the fault is held, the remaining batches run for their findings only, and
    completion raises the fault only where nothing refused.
    """
    from gaspatchio_jax import aggregate as aggregate_module

    folded: list[int] = []

    def faulting(*arguments: object, **named: object) -> None:
        del arguments, named
        folded.append(1)
        message = "a defect folding the first batch"
        raise RuntimeError(message)

    monkeypatch.setattr(aggregate_module, "_fold_scalars", faulting)
    one = (
        a_read_that_misses(20, 19)
        if a_later_batch_refuses
        else invocation(
            {"op": "col", "name": "key"},
            {"key": {"dtype": "f64", "values": [float(row) for row in range(20)]}},
            "f64",
        )
    )
    raised: type[Exception] = EngineRefusal if a_later_batch_refuses else RuntimeError
    with pytest.raises(raised):
        JaxEngine().aggregate(
            one.document, one.inputs, [Sum("answer").alias("total")], batch=7
        )
    # Folded once, then held: the later batches ran for their findings only.
    assert folded == [1]


def test_an_empty_book_is_refused_as_polars_refuses_it() -> None:
    empty = _book("level-4").clear()
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().aggregate(
            _artifact("level-4"), empty, [Sum("pv_net_cf").alias("x")]
        )
    assert refused.value.report.refusals[0].group == "inputs"
    assert "no policies" in refused.value.report.refusals[0].what
    assert refused.value.report.refusals[0].clause is None
    model_fn = _tutorial("level-4")
    for engine in (None, "jax"):
        with pytest.raises(ValueError, match="model_points is empty"):
            run_aggregated(
                model_fn, empty, [Sum("pv_net_cf").alias("x")], engine=engine
            )


def test_a_batch_is_a_positive_number_of_policies() -> None:
    with pytest.raises(ValueError, match="at least one"):
        JaxEngine().aggregate(
            _artifact("level-4"),
            _book("level-4"),
            [Sum("pv_net_cf").alias("x")],
            batch=0,
        )


# ---------------------------------------------------------------------------
# The two doors' records
# ---------------------------------------------------------------------------


def test_the_file_door_writes_the_engine_s_totals_and_what_produced_them(
    tmp_path: Path,
) -> None:
    """``gspio run-artifact --aggregate`` in a fresh process, end to end."""
    spec = [
        {"alias": "bel", "kind": "Sum", "column": "pv_net_cf"},
        {"alias": "net_cf", "kind": "PeriodSum", "column": "net_cf"},
        {
            "alias": "net_cf_by_product",
            "kind": "PeriodSum",
            "column": "net_cf",
            "over": ["product_id"],
        },
    ]
    written = tmp_path / "spec.json"
    written.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "totals.json"
    finished = subprocess.run(  # noqa: S603 -- this project's own venv and fixtures
        [
            str(GSPIO),
            "run-artifact",
            str(MODELS / "level-4.artifact.json"),
            str(MODELS / "level-4.book.parquet"),
            "--engine",
            "jax",
            "--aggregate",
            str(written),
            "--results",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    record = json.loads(out.read_text(encoding="utf-8"))
    direct = JaxEngine().aggregate(
        _artifact("level-4"),
        _book("level-4"),
        [
            Sum("pv_net_cf").alias("bel"),
            PeriodSum("net_cf").alias("net_cf"),
            PeriodSum("net_cf").alias("net_cf_by_product").over("product_id"),
        ],
    )
    outputs = record["aggregator_outputs"]
    assert outputs["bel"] == direct.bel
    assert outputs["net_cf"] == direct.net_cf.tolist()
    assert outputs["net_cf_by_product"] == direct.net_cf_by_product.to_dicts()
    assert record["graph_fingerprint"] == _artifact("level-4")["graph_fingerprint"]
    metadata = record["run_metadata"]
    assert metadata["engine"] == "jax"
    assert {
        "jax_version",
        "jaxlib_version",
        "extension_sha256",
        "backend",
        "device",
    } <= set(metadata["engine_versions"])
    assert metadata["n_policies"] == _book("level-4").height


def test_the_core_door_s_audit_record_is_polars_record_with_the_engine_named(
    tmp_path: Path,
) -> None:
    model_fn = _tutorial("level-4")
    book = _book("level-4")
    built = [Sum("pv_net_cf").alias("bel"), PeriodSum("net_cf").alias("net_cf")]
    run_aggregated(model_fn, book, built, engine="jax", audit=tmp_path / "jax.json")
    run_aggregated(model_fn, book, built, audit=tmp_path / "polars.json")
    on_jax = json.loads((tmp_path / "jax.json").read_text(encoding="utf-8"))
    on_polars = json.loads((tmp_path / "polars.json").read_text(encoding="utf-8"))
    for same in ("source_sha", "graph_fingerprint", "input_data_fingerprint"):
        assert on_jax[same] == on_polars[same], same
    assert on_jax["graph_fingerprint"] == _artifact("level-4")["graph_fingerprint"]
    assert on_jax["run_metadata"]["engine"] == "jax"
    assert "engine" not in on_polars["run_metadata"]


# ---------------------------------------------------------------------------
# What a fold's program hands back
# ---------------------------------------------------------------------------

# Three folds over level 4: one per-policy total, one term structure and one
# partitioned extremum -- three of the final schema's hundred and twenty-eight
# columns.
FOLDED: tuple[tuple[str, str], ...] = (
    ("Sum", "pv_net_cf"),
    ("PeriodSum", "net_cf"),
    ("PeriodMax", "claims"),
)


def _three_folds() -> list[Any]:
    return [
        Sum("pv_net_cf").alias("bel"),
        PeriodSum("net_cf").alias("net_cf"),
        PeriodMax("claims").alias("claims_by_product").over("product_id"),
    ]


def _node_of(plan: ExecutionPlan, column: str) -> str:
    """Return the final-schema node a column comes from."""
    return next(
        node_id
        for node_id, record in plan.records.items()
        if record.in_final_schema and record.column == column
    )


def test_a_fold_s_program_hands_back_only_the_columns_it_folds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three columns leave the card, and every check is still carried.

    The program is traced over every node, so a check anywhere in the model
    still runs and still refuses -- the checks it carries are the publishing
    program's, one for one. Built for one batch, the two carry the same
    records to the last field, each mask's shape included, which is what a
    first caught cell is read against; built for the engine's own batches, a
    fold's programs carry the same checks about the same nodes over the same
    periods, and only the number of policies differs. What a fold's program
    no longer hands back is a hundred and twenty-five columns no aggregator
    reads.
    """
    built: list[Any] = []
    compiling = ExecutionPlan.compile_for

    def recorded(self: ExecutionPlan, *arguments: Any) -> Any:  # noqa: ANN401 -- passed through
        answered = compiling(self, *arguments)
        built.append(answered[0])
        return answered

    monkeypatch.setattr(ExecutionPlan, "compile_for", recorded)
    JaxEngine().aggregate(_artifact("level-4"), _book("level-4"), _three_folds())
    plan = ExecutionPlan.stage_inspect(_artifact("level-4"))
    folded = {_node_of(plan, column) for _kind, column in FOLDED}
    assert built
    assert all(set(program.columns) == folded for program in built)

    prepared = plan.stage_prepare(plan.stage_validate_inputs(_book("level-4")))
    settled = plan.stage_settle(prepared, np.arange(64))
    publishing, _outcome = compiling(plan, settled)
    assert len(publishing.columns) == len(
        [one for one in plan.records.values() if one.in_final_schema]
    )

    folding, _outcome = compiling(plan, settled, frozenset(folded))
    assert folding.flags == publishing.flags

    def checks(program: Program) -> list[tuple[object, ...]]:
        return [
            (one.name, one.where, one.judgement, one.note, one.shape[1:])
            for one in program.flags
        ]

    assert all(checks(program) == checks(publishing) for program in built)


def test_a_fold_s_program_and_a_publishing_one_of_one_shape_are_two_programs() -> None:
    """Reused batch after batch, and never handed to the other reader.

    A program that hands back two columns cannot stand in for one that hands
    back every column, however alike their batches are: the process's key and
    the report's key both carry what is returned, and each is reused for the
    reader it was built for.
    """
    from gaspatchio_jax.cache import report_key

    plan = ExecutionPlan.stage_inspect(_artifact("level-4"))
    prepared = plan.stage_prepare(plan.stage_validate_inputs(_book("level-4")))
    settled = plan.stage_settle(prepared, np.arange(64))
    returns = frozenset(_node_of(plan, column) for _kind, column in FOLDED)

    publishing, _first = plan._program_for(settled)  # noqa: SLF001 -- the keying under test
    folding, _second = plan._program_for(settled, returns)  # noqa: SLF001
    again, outcome = plan._program_for(settled, returns)  # noqa: SLF001

    assert folding is not publishing
    assert folding.compiled.as_text() != publishing.compiled.as_text()
    assert again is folding
    assert outcome.process_local
    assert len(plan.programs) == 2
    buckets, count = folding.buckets, settled.count
    assert report_key(plan.document, buckets, count, returns) != report_key(
        plan.document, buckets, count
    )
    assert any(
        "returning the 3 columns folded" in note
        and report_key(plan.document, buckets, count, returns) in note
        for note in plan.notes
    )


def test_a_fold_counts_periods_off_columns_it_never_reads_back() -> None:
    """``n_periods`` is the final schema's longest timeline, not the folded one's.

    A fold of one per-policy total reads no per-period column back at all,
    and Polars still reports the longest per-period double of the frame. So
    does this engine: off the axes those columns stand on, which the host
    already holds.
    """
    model_fn = _tutorial("level-4")
    book = _book("level-4").head(200)
    built = [Sum("pv_net_cf").alias("bel")]
    polars = run_aggregated(model_fn, book, built, batch_size=book.height)
    engine = JaxEngine().aggregate(_artifact("level-4"), book, built)
    assert polars.n_periods > 0
    assert engine.n_periods == polars.n_periods


@pytest.mark.parametrize("model", list(FOLDER))
def test_a_fold_returning_only_its_columns_is_the_fold_returning_every_one(
    model: str, folded: dict[str, dict[str, Any]]
) -> None:
    """Every supported aggregator, whatever the program hands back, within the band.

    The model is the same trace either way; what changes is which buffers
    leave the card -- and with them what the compiler fuses, so a policy's
    value can move in its last bit. So the totals are held to 1e-12 of
    the total's own scale, counts exactly, and the quantile family within
    the sketch's accuracy, as it is held against Polars.
    """
    from gaspatchio_jax.aggregate import aggregate

    built, kinds = aggregations()
    book = _book(model)
    narrow = aggregate(_artifact(model), book, built, batch=256)
    wide = aggregate(_artifact(model), book, built, batch=256, folded_only=False)
    frame = folded[model]["frame"]
    assert narrow.n_periods == wide.n_periods
    assert list(narrow.aggregations) == list(wide.aggregations)
    worst = 0.0
    for alias, (kind, column) in kinds.items():
        ratio = _ratio(
            wide.aggregations[alias],
            narrow.aggregations[alias],
            _scale(frame, kind, column),
        )
        if kind == "PeriodCount":
            assert ratio == 0.0, alias
        bound = 2 * SKETCH_ACCURACY if kind in SKETCHED else BAND
        assert ratio < bound, (alias, ratio)
        if kind not in SKETCHED:
            worst = max(worst, ratio)
    print(f"{model}: worst ratio returning only the folded columns {worst:.3e}")  # noqa: T201 -- the measurement is the point
