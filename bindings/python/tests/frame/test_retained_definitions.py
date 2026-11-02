# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Where a frame's own working goes, and where it must not.

Reassigning a column overwrites it, so the definition being replaced loses
its numbers unless something carries them forward. The frame carries them
under a hidden name through the collect it was going to run anyway, and an
export reads them there to say what the column held before the override.

Everything below is about the other half of that bargain: the carried values
are the producer's working, not columns of anybody's model, so every door the
frame hands values out of has to be free of them -- the frame a collect
returns, the frame a timing run returns, the batches the memory-safe drivers
fold and write, and the parquet files on the end of those. And the values are
tied to the rows they came from by identity rather than by shape, because two
frames of equal height is a thing that happens constantly and history from
one run beside answers from another is the untruth the whole mechanism exists
to prevent.

The last section says the same of the other hidden family -- the scratch
struct a compiled rollforward materialises -- which reaches those same doors
by a route of its own, and was reaching one of them.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.frame.calculation_log import (
    _RETAINED_PREFIX,
    _kernel_scratch_prefix,
)
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.rollforward import compile_rollforward
from gaspatchio.scenarios import Sum, for_each_scenario
from gaspatchio.scenarios._batch import (
    _collect_with_peak,
    _without_working_columns,
)
from gaspatchio.scenarios._spill import run_to_parquet

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

# A real disk, injected: the spill sink refuses a RAM-backed target, and what
# is under test here is which columns reach the file rather than where it is.
_REAL_DISK = "/dev/disk1 / ext4 rw 0 0\n"


def _a_model_that_writes_a_column_twice(*, retain: bool = True) -> ActuarialFrame:
    """Return a frame whose `net_cashflow` is struck, then shocked.

    The reassignment idiom section 8 of the artifact format calls normal, and
    the shape every supersession in a real model has been: the second
    definition reads the first.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "sum_assured": [100_000.0, 250_000.0],
                "shock": [0.01, -0.02],
            }
        ),
        retain_superseded=retain,
    )
    af.net_cashflow = af.sum_assured * 0.02
    af.net_cashflow = af.net_cashflow * (1.0 + af.shock)
    return af


def _a_model_that_writes_every_column_once(*, retain: bool = True) -> ActuarialFrame:
    """Return the same arithmetic with each step under a name of its own."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "sum_assured": [100_000.0, 250_000.0],
                "shock": [0.01, -0.02],
            }
        ),
        retain_superseded=retain,
    )
    af.gross_cashflow = af.sum_assured * 0.02
    af.net_cashflow = af.gross_cashflow * (1.0 + af.shock)
    return af


def _shock_the_cashflow(af: ActuarialFrame) -> ActuarialFrame:
    """Run the same two definitions over whatever model points arrive."""
    af.net_cashflow = af.sum_assured * 0.02
    af.net_cashflow = af.net_cashflow * (1.0 + af.shock)
    return af


def _model_points() -> pl.DataFrame:
    """Return the policy data the driver tests batch over."""
    return pl.DataFrame(
        {
            "policy_id": [1, 2, 3, 4],
            "sum_assured": [100_000.0, 250_000.0, 500_000.0, 750_000.0],
            "shock": [0.01, -0.02, 0.03, -0.04],
        }
    )


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[node['id'] for node in artifact['nodes']]}"
    return found[0]


def _exported(
    af: ActuarialFrame, values: pl.DataFrame, *, retain_superseded: bool = True
) -> dict[str, Any]:
    """Return ``af``'s artifact, read off ``values``, parsed back from the wire."""
    document: dict[str, Any] = json.loads(
        GraphExporter(af).export(values, retain_superseded=retain_superseded)
    )
    return document


def test_a_collect_hands_back_the_model_s_own_columns() -> None:
    """The carried definition rides the collect and comes straight off it."""
    af = _a_model_that_writes_a_column_twice()

    collected = af.collect()

    assert not [n for n in collected.columns if n.startswith(_RETAINED_PREFIX)]
    assert af._retained_values is not None  # noqa: SLF001 -- the frame's own


def test_a_timing_run_hands_back_the_model_s_own_columns_too() -> None:
    """``profile`` is still a run, and what it returns is still the model."""
    af = _a_model_that_writes_a_column_twice()

    timed, _ = af.profile()

    assert not [n for n in timed.columns if n.startswith(_RETAINED_PREFIX)]


def test_a_freeze_settles_a_superseded_definition_away() -> None:
    """After a materialize the values are gone, and the node says so.

    A freeze turns the plan into the values it produced, and the definition
    that was written over is not among them. The node keeps its formula, its
    reads and its source location, and carries no number -- which is the
    format's older reading of a superseded definition, and the true one here.
    """
    af = _a_model_that_writes_a_column_twice().materialize()

    artifact = _exported(af, af.collect())

    superseded = _node(artifact, "net_cashflow@1")
    assert "retained" not in superseded
    assert superseded["value_sample"] is None
    assert validate_artifact(artifact).ok


def test_the_memory_safe_drivers_never_carry_a_superseded_definition() -> None:
    """What they return is folded, written or handed back as a grid -- never read.

    The drop is by the names the frame recorded as it minted them, so a model
    that never writes a column twice passes an empty collection and this
    costs a truth test rather than a schema resolve on every batch.
    """
    af = _shock_the_cashflow(ActuarialFrame(_model_points()))

    batch, _ = _collect_with_peak(
        _without_working_columns(af._df, af)  # noqa: SLF001
    )

    assert af._retained_columns  # noqa: SLF001 -- the model did write one twice
    assert not [n for n in batch.columns if n.startswith(_RETAINED_PREFIX)]


def test_a_spilled_parquet_holds_only_the_model_s_columns(tmp_path: Path) -> None:
    """The one path where a carried definition would reach a file on disk."""
    run_to_parquet(
        _shock_the_cashflow,
        _model_points(),
        tmp_path,
        batch_size=2,
        mounts_text=_REAL_DISK,
    )

    written = sorted(tmp_path.glob("batch_*.parquet"))
    assert written
    for batch in written:
        columns = pl.read_parquet_schema(batch)
        assert not [n for n in columns if n.startswith(_RETAINED_PREFIX)]


def test_values_from_another_run_are_not_given_this_one_s_history() -> None:
    """Two frames of one height are not one frame, and the tie says which.

    Both models below compute the same columns over the same rows, so the
    frame one of them collected is indistinguishable from the other's by
    shape. Carrying the first's history onto the second's answers would put a
    number against a formula that did not produce it, which is exactly the
    reading the retention declaration exists to make honest.
    """
    mine = _a_model_that_writes_a_column_twice()
    _ = mine.collect()
    someone_elses = _a_model_that_writes_a_column_twice().collect()

    artifact = _exported(mine, someone_elses)

    superseded = _node(artifact, "net_cashflow@1")
    assert "retained" not in superseded
    assert superseded["value_sample"] is None
    assert validate_artifact(artifact).ok


def test_a_carried_definition_reaches_no_column_list_a_reader_reads() -> None:
    """The values ride to the export under a name nothing else can see.

    Not among the frame's columns, so nobody modelling meets it; not among
    the artifact's, so no reader can mistake a producer's working for a
    column of the model.
    """
    af = _a_model_that_writes_a_column_twice()
    collected = af.collect()

    artifact = _exported(af, collected)
    columns = {node["column"] for node in artifact["nodes"]}

    assert _node(artifact, "net_cashflow@1")["retained"] is True
    assert not [n for n in collected.columns if n.startswith(_RETAINED_PREFIX)]
    assert not [n for n in columns if n and n.startswith(_RETAINED_PREFIX)]


def test_a_join_after_a_reassignment_on_a_wide_frame_brings_only_its_own() -> None:
    """A wide frame's cached schema knows about the carried values too.

    A frame this wide keeps its cached schema one assignment at a time, and
    that update used to leave out the hidden name the same statement carried
    the replaced definition under. A join then took the carried values for a
    column the other table had brought: it recorded one arriving from that
    table and listed it among the model's columns.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1", "P2"],
                "sum_assured": [1000.0, 2000.0],
                **{f"filler_{i}": [0.0, 0.0] for i in range(20)},
            }
        )
    )
    af.claims = af.sum_assured * 0.01
    af.claims = af.sum_assured * 0.02
    carried = f"{_RETAINED_PREFIX}1__claims"
    assert carried in (af._schema or {})  # noqa: SLF001 -- the cache under test

    af.join(
        pl.DataFrame({"policy_id": ["P1", "P2"], "rate": [0.1, 0.2]}), on="policy_id"
    )

    joined = [
        record.column
        for record in af._calculation_records()  # noqa: SLF001 -- the log under test
        if record.origin == "join"
    ]
    assert joined == ["rate"]
    assert carried not in af.columns
    assert af.collect()["claims"].to_list() == [20.0, 40.0]


def test_a_write_over_a_column_keeps_each_number_with_its_own_definition() -> None:
    """On a wide frame, a write in the plan and then an assignment over it.

    The write is a definition of its own -- a hole under the next ordinal --
    so the assignment that replaces it carries what the write left, under the
    write's ordinal, and the frame's cached schema carries the write's type
    for it. The calculation the write replaced keeps no number: nothing
    carried it, and the number in the column after the write is not its.
    Every number in the file is the one its own definition produced.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1", "P2"],
                "sum_assured": [1000.0, 2000.0],
                **{f"filler_{i}": [0.0, 0.0] for i in range(20)},
            }
        )
    )
    af.claims = af.sum_assured * 0.01
    plan = af._df  # noqa: SLF001 -- the route under test
    assert plan is not None
    af._df = plan.with_columns(pl.lit(7).alias("claims"))  # noqa: SLF001
    af.loaded = af.claims + 1
    af.claims = af.sum_assured * 0.02
    carried = f"{_RETAINED_PREFIX}2__claims"
    assert (af._schema or {}).get(carried) == pl.Int32  # noqa: SLF001 -- the cache under test

    values = af.collect()
    artifact = _exported(af, values)

    calculated = _node(artifact, "claims@1")
    written = _node(artifact, "claims@2")
    live = _node(artifact, "claims@3")
    assert calculated["kind"] == "computed"
    assert calculated.get("retained") is None
    assert calculated.get("value_sample") is None
    assert (written["kind"], written["retained"], written["value_sample"]) == (
        "hole",
        True,
        7,
    )
    assert _node(artifact, "loaded@1")["reads"] == ["claims@2"]
    assert _node(artifact, "loaded@1")["value_sample"] == 8
    assert live["value_sample"] == 20.0
    assert carried not in af.columns
    assert carried not in values.columns
    assert validate_artifact(artifact).ok


def test_an_export_that_declines_the_values_lets_go_of_them() -> None:
    """Nothing else was going to read them, so the frame stops holding them."""
    af = _a_model_that_writes_a_column_twice()
    collected = af.collect()
    assert af._retained_values is not None  # noqa: SLF001 -- the frame's own

    _exported(af, collected, retain_superseded=False)

    assert af._retained_values is None  # noqa: SLF001 -- and now released


# --- the lever at the frame, and the one at the export ----------------------

# Two settings of one name, and they answer different questions. The frame's
# says whether the cost is paid at all; the export's says whether the document
# carries what was paid for. Only the first can decline the memory, because by
# the time an exporter exists the collect is over.


def test_the_frame_lever_off_carries_nothing_at_all() -> None:
    """Not paid and discarded -- never paid.

    The plan is where the proof is. ``columns`` would say the same thing with
    the alias sitting in the query behind it, so what is asserted here is the
    lazy plan's own schema: no hidden name entered it, so no hidden column was
    collected and none is held afterwards.
    """
    af = _a_model_that_writes_a_column_twice(retain=False)

    collected = af.collect()

    plan = af._df.collect_schema().names()  # noqa: SLF001 -- the plan itself
    assert not [name for name in plan if name.startswith(_RETAINED_PREFIX)]
    assert af._retained_values is None  # noqa: SLF001 -- nothing to hold
    assert af._retained_columns == set()  # noqa: SLF001 -- nothing minted
    assert not [n for n in collected.columns if n.startswith(_RETAINED_PREFIX)]


def test_the_frame_lever_off_writes_the_definition_as_history() -> None:
    """With nothing carried there is nothing to write, whatever the export says."""
    af = _a_model_that_writes_a_column_twice(retain=False)
    collected = af.collect()

    artifact = _exported(af, collected)

    superseded = _node(artifact, "net_cashflow@1")
    assert "retained" not in superseded
    assert superseded["value_sample"] is None
    assert (superseded["dtype"], superseded["shape"]) == ("unknown", "unknown")
    assert validate_artifact(artifact).ok


def test_the_frame_lever_on_and_the_export_declining_gives_the_older_shape() -> None:
    """The values were paid for, this document does not carry them, they go."""
    af = _a_model_that_writes_a_column_twice()
    collected = af.collect()
    assert af._retained_values is not None  # noqa: SLF001 -- paid for

    artifact = _exported(af, collected, retain_superseded=False)

    superseded = _node(artifact, "net_cashflow@1")
    assert "retained" not in superseded
    assert superseded["value_sample"] is None
    assert af._retained_values is None  # noqa: SLF001 -- and released
    assert validate_artifact(artifact).ok


def test_both_levers_on_gives_the_definition_its_own_number() -> None:
    """The honesty check: the retained number is not the one that replaced it."""
    af = _a_model_that_writes_a_column_twice()

    artifact = _exported(af, af.collect())

    superseded = _node(artifact, "net_cashflow@1")
    live = _node(artifact, "net_cashflow@2")
    assert superseded["retained"] is True
    assert superseded["value_sample"] != live["value_sample"]
    assert validate_artifact(artifact).ok


def test_the_frame_lever_moves_no_digest_either_way() -> None:
    """Values are no part of a node's identity, and the lever is about values.

    A reviewer holding two quarters of one model, run under different
    settings, compares them on the fingerprints. That comparison is only
    worth anything if the settings cannot move one.
    """
    with_it = _exported(
        (on := _a_model_that_writes_a_column_twice()),
        on.collect(),
    )
    without_it = _exported(
        (off := _a_model_that_writes_a_column_twice(retain=False)),
        off.collect(),
    )

    assert with_it["graph_fingerprint"] == without_it["graph_fingerprint"]
    assert {
        node["id"]: (node["local_fingerprint"], node["fingerprint"])
        for node in with_it["nodes"]
    } == {
        node["id"]: (node["local_fingerprint"], node["fingerprint"])
        for node in without_it["nodes"]
    }


def test_a_model_that_writes_no_column_twice_cannot_tell_the_lever_moved() -> None:
    """Nearly every model, and the lever costs it nothing and changes nothing."""
    with_it = _exported(
        (on := _a_model_that_writes_every_column_once()),
        on.collect(),
    )
    without_it = _exported(
        (off := _a_model_that_writes_every_column_once(retain=False)),
        off.collect(),
    )

    for artifact in (with_it, without_it):
        # What a re-export moves without the model moving, and nothing else.
        del artifact["created_at"]
        del artifact["document_digest"]

    assert json.dumps(with_it, sort_keys=True) == json.dumps(without_it, sort_keys=True)


# --- the other family: a compiled rollforward's scratch struct --------------

# A superseded definition is not the only thing riding a model's plan that is
# no column of the model. A compiled rollforward materialises one struct so
# its kernel runs once however many states are read back out of it, and every
# door above has to be free of that too -- more so, because the struct is not
# even a number, and a parquet file with one in it is a file no reader can
# make sense of.


def _a_model_with_a_compiled_rollforward(af: ActuarialFrame) -> ActuarialFrame:
    """Grow a fund and charge it, over whatever model points arrive."""
    periods = 4
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31),
        n_periods=periods,
        frequency="monthly",
    )
    builder = af.projection.rollforward(states={"fund_value": af["av_init"]})
    builder["fund_value"].grow(af["fund_return"], label="fund_return").charge(
        af["me_charge"], label="me_charge"
    )
    af.account_value = compile_rollforward(builder).expr_for("fund_value")
    return af


def _roll_forward_and_shock_the_cashflow(af: ActuarialFrame) -> ActuarialFrame:
    """Both families at once: a rollforward, and a column written twice."""
    af = _a_model_with_a_compiled_rollforward(af)
    af.net_cashflow = af.av_init * 0.02
    af.net_cashflow = af.net_cashflow * (1.0 + af.shock)
    return af


def _fund_model_points() -> pl.DataFrame:
    """Return policy data a fund rollforward can run over."""
    periods = 4
    return pl.DataFrame(
        {
            "policy_id": [1, 2, 3, 4],
            "av_init": [100_000.0, 250_000.0, 500_000.0, 750_000.0],
            "fund_return": [[0.01] * periods] * 4,
            "me_charge": [[0.001] * periods] * 4,
            "shock": [0.01, -0.02, 0.03, -0.04],
        }
    )


def _scratch_columns(names: Iterable[str]) -> list[str]:
    """Return the names among ``names`` that belong to a rollforward kernel."""
    return [n for n in names if n.startswith(_kernel_scratch_prefix())]


def test_a_spilled_parquet_holds_no_rollforward_scratch_either(
    tmp_path: Path,
) -> None:
    """The policy-axis driver, and the struct that used to reach the file.

    Reproduced before it was fixed: the written schema carried
    ``__rollforward_<fingerprint>`` beside the model's own columns.
    """
    run_to_parquet(
        _a_model_with_a_compiled_rollforward,
        _fund_model_points(),
        tmp_path,
        batch_size=2,
        mounts_text=_REAL_DISK,
    )

    written = sorted(tmp_path.glob("batch_*.parquet"))
    assert written
    for batch in written:
        columns = pl.read_parquet_schema(batch)
        assert "account_value" in columns
        assert _scratch_columns(columns) == []


def test_the_scenario_grid_holds_no_rollforward_scratch(tmp_path: Path) -> None:
    """The scenario-axis driver, asked for the whole grid rather than a fold."""

    def model(
        af: ActuarialFrame,
        *,
        tables: dict[str, Any] | None = None,  # noqa: ARG001
        drivers: dict[str, Any] | None = None,  # noqa: ARG001
    ) -> ActuarialFrame:
        return _a_model_with_a_compiled_rollforward(af)

    for_each_scenario(
        ActuarialFrame(_fund_model_points()),
        scenarios=["base", "stress"],
        model_fn=model,
        aggregations=(Sum("av_init").alias("total_av"),),
        batch_size=1,
        return_full_grid=True,
        sink_dir=tmp_path,
    )

    written = sorted(tmp_path.glob("batch_*.parquet"))
    assert written
    for batch in written:
        columns = pl.read_parquet_schema(batch)
        assert "account_value" in columns
        assert _scratch_columns(columns) == []


def test_a_model_doing_both_loses_both(tmp_path: Path) -> None:
    """One model, two hidden families, and the file carries neither.

    The two are reached differently -- the superseded name off the frame's
    own record, the scratch struct off the prefix it is minted under -- so a
    model that does only one of these cannot tell whether the other half of
    the drop still works.
    """
    af = _roll_forward_and_shock_the_cashflow(ActuarialFrame(_fund_model_points()))

    batch, _ = _collect_with_peak(
        _without_working_columns(af._df, af)  # noqa: SLF001
    )

    assert af._retained_columns  # noqa: SLF001 -- the model did write one twice
    assert _scratch_columns(af._df.collect_schema().names())  # noqa: SLF001 -- and roll
    assert not [n for n in batch.columns if n.startswith(_RETAINED_PREFIX)]
    assert _scratch_columns(batch.columns) == []
    assert {"account_value", "net_cashflow"} <= set(batch.columns)

    run_to_parquet(
        _roll_forward_and_shock_the_cashflow,
        _fund_model_points(),
        tmp_path,
        batch_size=2,
        mounts_text=_REAL_DISK,
    )
    for written in sorted(tmp_path.glob("batch_*.parquet")):
        columns = pl.read_parquet_schema(written)
        assert not [n for n in columns if n.startswith(_RETAINED_PREFIX)]
        assert _scratch_columns(columns) == []
