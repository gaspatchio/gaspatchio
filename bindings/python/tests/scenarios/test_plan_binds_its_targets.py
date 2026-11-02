# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scenario plan runs the reconciled model unchanged and shocks its targets itself.

Every scenario model in the corpus grew a door for the plan: an override
parameter, a ``model_fn(af, *, tables, drivers)`` wrapper and a guard at every
lookup, and three rooms moved scalars into one-row tables to shock them. Now
the plan binds its targets instead: a read of a table a shock names
is lowered against that table stacked per scenario, a ``column=`` shock
rewrites a model-point column at the frame door, and ``plan.run(af, main)``
runs the model as it was reconciled. Each test here fails on the base, where
a frame-only model under a shocking plan was refused or never ran.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, MortalityTable, when
from gaspatchio._semantic.ir import Call, Col
from gaspatchio.assumptions import Table
from gaspatchio.frame.calculations import CalculationRecord
from gaspatchio.scenarios import (
    AdditiveShock,
    FilteredShock,
    MultiplicativeShock,
    OverrideShock,
    PipelineShock,
    ScenarioRun,
    Sum,
    TimeConditionalShock,
    with_scenarios,
)
from gaspatchio.scenarios._for_each import _BatchRecipe
from gaspatchio.scenarios._stack import stack_shocked_table

if TYPE_CHECKING:
    from gaspatchio.scenarios import ScenarioResult


def _mortality() -> Table:
    return Table(
        name="binds_mortality",
        source=pl.DataFrame(
            {
                "age": [40, 40, 41, 41],
                "duration": [0, 1, 0, 1],
                "q": [0.010, 0.012, 0.020, 0.024],
            }
        ),
        dimensions={"age": "age", "duration": "duration"},
        value="q",
    )


def _lapse() -> Table:
    return Table(
        name="binds_lapse",
        source=pl.DataFrame({"age": [40, 41], "w": [0.05, 0.06]}),
        dimensions={"age": "age"},
        value="w",
    )


def main(af: ActuarialFrame) -> ActuarialFrame:
    """The model as reconciled: it loads and reads its own tables, no door."""
    basis = MortalityTable(
        table=_mortality(),
        age_basis="age_last_birthday",
        structure="select_ultimate",
        select_period=1,
    )
    af.q = basis.at(age=af.age, duration=af.duration)
    af.w = _lapse().lookup(age=af.age)
    af.loss = af.sa * af.q + af.w * 100.0 + af.valuation_rate * 1000.0
    return af


def _book() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "age": [40, 41],
                "duration": [0, 1],
                "sa": [1000.0, 2000.0],
                "valuation_rate": [0.03, 0.04],
            }
        )
    )


_AGG = (Sum("loss").alias("loss").over("scenario_id"),)

_SHOCKS = {
    "BASE": [],
    "MORT_UP": [MultiplicativeShock(1.2, table="binds_mortality")],
    "RATE_UP": [AdditiveShock(0.01, column="valuation_rate")],
    "SA_SOLVED": [OverrideShock(1500.0, column="sa")],
}


def _by_scenario(result: ScenarioResult) -> dict[str, float]:
    return dict(result.aggregations["loss"].iter_rows())


def _expected() -> dict[str, float]:
    base_q = 1000.0 * 0.010 + 2000.0 * 0.024
    base = base_q + (0.05 + 0.06) * 100.0 + (0.03 + 0.04) * 1000.0
    return {
        "BASE": base,
        "MORT_UP": base + 0.2 * base_q,
        "RATE_UP": base + 0.02 * 1000.0,
        "SA_SOLVED": base - base_q + 1500.0 * (0.010 + 0.024),
    }


@pytest.mark.parametrize("batch_size", [1, 2, "auto"])
def test_the_reconciled_model_runs_under_a_shocking_plan(
    batch_size: int | str,
) -> None:
    """main(af) under table and column shocks, with no wrapper, at any batch size."""
    plan = ScenarioRun(shocks=_SHOCKS, aggregations=_AGG)
    result = plan.run(_book(), main, batch_size=batch_size)  # type: ignore[arg-type]
    assert _by_scenario(result) == pytest.approx(_expected())


def _batch(shocks: dict) -> ActuarialFrame:
    recipe = _BatchRecipe(
        scenarios=shocks, shape="shocks", base_tables=None, master_seed=None
    )
    return recipe.compose(_book(), list(shocks), main)


def _nodes(frame: ActuarialFrame) -> dict[str, object]:
    return {
        entry.column: entry.node
        for entry in frame._calculations
        if isinstance(entry, CalculationRecord)
    }


def test_an_unshocked_read_carries_no_axis_and_a_shocked_one_does() -> None:
    """Only a table a shock names is stacked; every other read is as written."""
    nodes = _nodes(_batch(_SHOCKS))
    lapse = nodes["w"]
    assert isinstance(lapse, Call)
    assert dict(lapse.attrs)["table"] == "binds_lapse"
    assert Col("scenario_id") not in lapse.args
    mortality = nodes["q"]
    assert isinstance(mortality, Call)
    assert dict(mortality.attrs)["table"] == "binds_mortality_stacked"
    assert mortality.args[-1] == Col("scenario_id")


def test_a_bound_read_is_the_explicit_stacked_read_byte_for_byte() -> None:
    """The node the plan binds is the one a model handed the stacked table writes."""
    shocks = {
        "BASE": [],
        "MORT_UP": [MultiplicativeShock(1.2, table="binds_mortality")],
    }
    bound = _nodes(_batch(shocks))["q"]

    stacked = stack_shocked_table(
        _mortality(),
        {sid: list(s) for sid, s in shocks.items()},  # type: ignore[arg-type]
    )
    by_hand = with_scenarios(_book(), list(shocks))
    basis = MortalityTable(
        table=stacked,
        age_basis="age_last_birthday",
        structure="select_ultimate",
        select_period=1,
    )
    by_hand.q = basis.at(
        age=by_hand.age, duration=by_hand.duration, scenario_id=by_hand.scenario_id
    )
    assert bound == _nodes(by_hand)["q"]


def _column_record(frame: ActuarialFrame, column: str) -> CalculationRecord:
    return next(
        entry
        for entry in frame._calculations
        if isinstance(entry, CalculationRecord) and entry.column == column
    )


def test_a_column_shock_is_an_assignment_at_the_plans_line() -> None:
    """The rewrite is recorded, located at the run, its formula what it computes.

    An affine sweep reads per-scenario factors keyed by the axis; any other
    column shock is a when chain over the axis, one branch per scenario.
    """
    frame = _batch(
        {
            "BASE": [],
            "RATE_UP": [AdditiveShock(0.01, column="valuation_rate")],
            "OLD_SA_UP": [
                FilteredShock(
                    MultiplicativeShock(2.0), where={"age": {"gte": 41}}, column="sa"
                )
            ],
        }
    )
    rate = _column_record(frame, "valuation_rate")
    assert rate.origin == "assignment"
    assert rate.source is not None
    assert rate.source.file.endswith("test_plan_binds_its_targets.py")
    factors = (
        "scenario_shocks__valuation_rate.lookup(scenario_id=af.scenario_id, step='1'"
    )
    assert rate.source.rhs == (
        f"when({factors}, part='set') == 1.0).then({factors}, part='b'))"
        f".otherwise(af.valuation_rate * {factors}, part='a') + {factors}, part='b'))"
    )
    sa = _column_record(frame, "sa")
    assert sa.source is not None
    assert sa.source.rhs == (
        "when(af.scenario_id == 'OLD_SA_UP')"
        ".then(when(af.age >= 41).then(af.sa * 2.0).otherwise(af.sa))"
        ".otherwise(af.sa)"
    )


def test_a_large_affine_sweep_runs_in_one_batch_exactly() -> None:
    """A thousand affine scenarios in one batch, each value the direct recipe's bits.

    One when branch per scenario nested a thousand deep, past the recursion
    every tree walk takes; the factor read is flat. Each step is exact: the
    rows equal the recipe computed directly, a signed zero, a NaN under a
    set, and a scenario that leaves the column alone included.
    """
    values = [0.04, float("nan"), -0.0, 123.456]
    book = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3, 4], "v": values}))
    recipes = {f"S{i:04d}": (1.0 + i / 1000, i / 1e5) for i in range(1000)}
    shocks: dict[str, list] = {
        sid: [PipelineShock((MultiplicativeShock(f), AdditiveShock(d)), column="v")]
        for sid, (f, d) in recipes.items()
    }
    shocks["SET"] = [OverrideShock(0.05, column="v")]
    shocks["TIMES"] = [MultiplicativeShock(3.0, column="v")]
    shocks["BASE"] = []

    recipe = _BatchRecipe(
        scenarios=shocks, shape="shocks", base_tables=None, master_seed=None
    )
    rows = recipe.compose(book, list(shocks), lambda af: af).collect()
    got = {
        (sid, pid): v
        for sid, pid, v in rows.select("scenario_id", "policy_id", "v").iter_rows()
    }

    def same(x: float, y: float) -> bool:
        return float(x).hex() == float(y).hex()

    for sid in ("S0000", "S0001", "S0500", "S0999"):
        f, d = recipes[sid]
        for pid, x in enumerate(values, 1):
            assert same(got[sid, pid], x * f + d), (sid, pid)
    for pid, x in enumerate(values, 1):
        assert same(got["SET", pid], 0.05)
        assert same(got["TIMES", pid], x * 3.0)
        assert same(got["BASE", pid], x)


def test_a_column_shock_on_a_column_the_book_does_not_hold_is_refused() -> None:
    plan = ScenarioRun(
        shocks={"UP": [AdditiveShock(0.01, column="valuation_rte")]}, aggregations=_AGG
    )
    with pytest.raises(ValueError, match="Did you mean 'valuation_rate'") as info:
        plan.run(_book(), main, batch_size=1)
    assert "model-point columns" in str(info.value)


def test_a_column_shock_refusal_cites_a_skill_file_that_exists() -> None:
    """The rule is quoted with the reference it comes from, and that file is there.

    It cited "skills/gaspatchio-workbook-conversion, spreadsheet-conversion.md",
    a skill directory that holds no such file; the reference lives under the
    discovery skill.
    """
    plan = ScenarioRun(
        shocks={"UP": [AdditiveShock(0.01, column="valuation_rte")]}, aggregations=_AGG
    )
    with pytest.raises(ValueError, match="model-point columns") as info:
        plan.run(_book(), main, batch_size=1)
    cited = "skills/gaspatchio-model-discovery/references/spreadsheet-conversion.md"
    assert f"({cited})" in str(info.value)
    assert "gaspatchio-workbook-conversion, spreadsheet" not in str(info.value)
    repository = Path(__file__).resolve().parents[4]
    assert (repository / cited).is_file()


def test_a_time_condition_on_a_column_shock_is_refused() -> None:
    shock = TimeConditionalShock(
        AdditiveShock(0.01), when={"t": 0}, column="valuation_rate"
    )
    with pytest.raises(ValueError, match="has no periods|no periods for when="):
        ScenarioRun(shocks={"UP": [shock]}, aggregations=_AGG)


def test_a_shock_naming_two_targets_is_refused_with_the_filter_move() -> None:
    shock = AdditiveShock(0.01, table="binds_lapse", column="x")
    with pytest.raises(ValueError, match="two targets") as info:
        ScenarioRun(shocks={"UP": [shock]}, aggregations=_AGG)
    assert "FilteredShock(shock=..., where=" in str(info.value)
    # The two fields are named on their own; the description says only what
    # the shock does, never a dotted "binds_lapse.x" neither field means.
    assert "column='x' (add +0.01)." in str(info.value)
    assert "binds_lapse.x" not in str(info.value)


def test_a_shocked_tables_rows_are_refused_inside_a_run() -> None:
    """to_dataframe() of a shocked table would be BASE's rows in every scenario."""

    def setup_helper(af: ActuarialFrame) -> ActuarialFrame:
        assert _lapse().to_dataframe().height == 2  # unshocked: read as written
        _mortality().to_dataframe()
        return main(af)

    plan = ScenarioRun(
        shocks={"BASE": [], "UP": [MultiplicativeShock(1.2, table="binds_mortality")]},
        aggregations=_AGG,
    )
    with pytest.raises(ValueError, match="rows differ by scenario"):
        plan.run(_book(), setup_helper, batch_size=2)
    assert _mortality().to_dataframe().height == 4  # outside a run, as ever


def test_a_frame_that_dropped_the_axis_is_refused() -> None:
    def drops_the_axis(af: ActuarialFrame) -> ActuarialFrame:
        af = main(af)
        return af.select("policy_id", "loss")

    plan = ScenarioRun(
        shocks={"BASE": [], "UP": [MultiplicativeShock(1.2, table="binds_mortality")]},
        aggregations=_AGG,
    )
    with pytest.raises(ValueError, match="without the 'scenario_id' column"):
        plan.run(_book(), drops_the_axis, batch_size=2)


def test_stated_base_tables_are_a_content_check() -> None:
    """base_tables is optional; given, the model's table must be the stated one."""
    other = Table(
        name="binds_mortality",
        source=pl.DataFrame(
            {"age": [40, 40, 41, 41], "duration": [0, 1, 0, 1], "q": [1.0] * 4}
        ),
        dimensions={"age": "age", "duration": "duration"},
        value="q",
    )
    plan = ScenarioRun(
        shocks={"UP": [MultiplicativeShock(1.2, table="binds_mortality")]},
        base_tables={"binds_mortality": other},
        aggregations=_AGG,
    )
    with pytest.raises(ValueError, match="is not the table the model reads"):
        plan.run(_book(), main, batch_size=1)
    with pytest.raises(ValueError, match="key is the table's own name"):
        ScenarioRun(
            shocks={"UP": []}, base_tables={"mort": _mortality()}, aggregations=_AGG
        )


@pytest.mark.parametrize("batch_size", [1, 2, "auto"])
def test_base_is_the_standalone_model_by_fingerprint(
    tmp_path: Path, batch_size: int | str
) -> None:
    """BASE's fingerprint equals the model run on its own: a check, not a measurement."""
    plan = ScenarioRun(shocks=_SHOCKS, aggregations=_AGG)
    result = plan.run(
        _book(),
        main,
        batch_size=batch_size,  # type: ignore[arg-type]
        audit=tmp_path / "a.json",
    )
    standalone = main(_book()).graph.fingerprint()
    assert result.fingerprint("BASE") == standalone
    others = {result.fingerprint(sid) for sid in ("MORT_UP", "RATE_UP", "SA_SOLVED")}
    assert standalone not in others
    assert len(others) == 3


def test_a_model_reading_the_axis_keeps_an_identity_per_scenario(
    tmp_path: Path,
) -> None:
    """A model that dispatches on scenario_id folds a different calculation per scenario."""

    def dispatches(af: ActuarialFrame) -> ActuarialFrame:
        af = main(af)
        af.rate = when(af.scenario_id == "UP").then(0.05).otherwise(0.03)
        af.loss = af.loss * (1.0 + af.rate)
        return af

    plan = ScenarioRun(shocks={"BASE": [], "UP": []}, aggregations=_AGG)
    result = plan.run(_book(), dispatches, batch_size=2, audit=tmp_path / "a.json")
    assert result.fingerprint("BASE") != result.fingerprint("UP")
    assert None not in (result.fingerprint("BASE"), result.fingerprint("UP"))


def test_the_record_names_the_content_each_shock_was_applied_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sidecar's bases: per shocked table, its content fingerprint and file."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "assumptions").mkdir()
    _mortality().to_dataframe().write_parquet(tmp_path / "assumptions" / "mort.parquet")

    def reads_from_file(af: ActuarialFrame) -> ActuarialFrame:
        mortality = Table(
            name="binds_mortality",
            source=tmp_path / "assumptions" / "mort.parquet",
            dimensions={"age": "age", "duration": "duration"},
            value="q",
        )
        af.q = mortality.lookup(age=af.age, duration=af.duration)
        af.loss = af.q * af.sa
        return af

    plan = ScenarioRun(
        shocks={"BASE": [], "UP": [MultiplicativeShock(1.2, table="binds_mortality")]},
        aggregations=_AGG,
    )
    result = plan.run(_book(), reads_from_file, batch_size=2, audit=tmp_path / "a.json")
    record = json.loads((tmp_path / "a.json").read_text())
    assert record["bases"] == {
        "binds_mortality": {
            "fingerprint": _mortality().fingerprint(),
            "source_file": "assumptions/mort.parquet",
        }
    }
    assert result.bases == record["bases"]
    assert "rng_seed" not in record["plan_canonical_form"]


def test_a_filtered_column_shock_moves_only_the_policies_it_names() -> None:
    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "OLD_SA_UP": [
                FilteredShock(
                    MultiplicativeShock(2.0), where={"age": {"gte": 41}}, column="sa"
                )
            ],
        },
        aggregations=_AGG,
    )
    result = _by_scenario(plan.run(_book(), main, batch_size=2))
    assert result["OLD_SA_UP"] - result["BASE"] == pytest.approx(2000.0 * 0.024)
