# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Holes: the columns on the frame that nothing in the model explains.

Every column a finished model holds should be one of three things: a
formula the frame recorded, a field the data arrived with, or a located
injection. A hole is the fourth case -- a column that is *there*, in the
frame's own schema, with nobody able to say where it came from. The
canonical way to make one is to write the query plan directly::

    af._df = af._df.with_columns(...)  # behind the framework's back

The framework never saw that assignment, so the calculation log has no
record of it and the graph would otherwise show the column as simply
absent: a reviewer reading the graph would see a model whose outputs
depend on a column the graph does not contain.

So the fold mints a hole *node* for it -- a typed leaf, present in the
graph, reading nothing. A dependency walk that arrives at one stops
there, which is the honest answer: this is where the model's account of
itself ends. ``find_holes`` reads those nodes back off the graph rather
than counting the same difference a second time somewhere else.

Three neighbours a hole is deliberately not:

- **an injected column** -- a series or the array a simulation hands back
  -- is recorded, so it is an input that also says which line of the model
  put it there, strictly more than a spreadsheet's paste-as-values tells
  anyone;
- **a dropped column** left the schema, so it is a ghost: history, kept,
  flagged as not being what the frame holds;
- **a name the arrival history still answers for** -- a vendor field
  renamed away one step back -- is an input to the model, not a column
  sitting unexplained on this frame. A name with no arrival history
  behind it is the opposite: nothing accounts for it either, and the
  fold punches a hole for that too.
"""

from __future__ import annotations

import datetime
import json
import warnings
from typing import TYPE_CHECKING

import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame, GaspatchioWarning
from gaspatchio._semantic.ir import Col
from gaspatchio.frame.calculations import CalculationRecord
from gaspatchio.frame.graph import holes as holes_module
from gaspatchio.frame.graph.calc_graph import GraphExporter
from gaspatchio.frame.graph.graph_builder import fold
from gaspatchio.frame.graph.graph_models import (
    GraphNode,
    NodeData,
    NodeType,
    Provenance,
)
from gaspatchio.frame.graph.holes import Hole, find_holes, holes_in
from gaspatchio.frame.lowering.polars import lower_polars
from gaspatchio.rollforward import compile_rollforward
from gaspatchio.scenarios import with_scenarios

if TYPE_CHECKING:
    from gaspatchio.frame.graph.graph_builder import CalcGraph


def _gaspatchio_warnings(caught: list[warnings.WarningMessage]) -> list[str]:
    """Return the messages of the ``GaspatchioWarning`` among ``caught``.

    The fold says a name nothing accounts for as one of these: a warning the
    user hears whether or not the package's logs are on.
    """
    return [
        str(heard.message)
        for heard in caught
        if issubclass(heard.category, GaspatchioWarning)
    ]


# --- helpers ----------------------------------------------------------------


def _hole_columns(af: ActuarialFrame) -> list[str]:
    """Return the column each reported hole names, in report order."""
    return [hole.column for hole in find_holes(af)]


def _swap_into_plan(af: ActuarialFrame, *columns: pl.Expr) -> None:
    """Write ``columns`` straight into the frame's query plan.

    The bypass every test here is built on, in one place: the columns
    land in the plan, and so in the schema it resolves to, without the
    framework ever seeing an assignment to record.
    """
    plan = af._df  # noqa: SLF001 -- the bypass under test
    assert plan is not None
    af._df = plan.with_columns(*columns)  # noqa: SLF001


def _swapped_frame() -> ActuarialFrame:
    """Build a frame whose last column was written straight into the plan.

    ``lapse_reserve`` never goes through an assignment, so nothing appends
    a record for it: it exists in the plan, and in the schema the plan
    resolves to, and nowhere else.
    """
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    af.death_claims = af.sum_assured * 0.01
    _swap_into_plan(af, (pl.col("sum_assured") * 0.02).alias("lapse_reserve"))
    return af


def _taught_model() -> ActuarialFrame:
    """Build a model the taught way: arriving columns, a rename, assignments.

    Every column here is either one the data arrived with or one an
    assignment recorded, which is what makes the empty hole list an
    auditable claim rather than a default.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "Issue Age": [30, 45],
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.01, 0.02],
            }
        )
    )
    af = af.rename({"Issue Age": "issue_age"})
    af = af.projection.set(
        valuation_date=datetime.date(2026, 1, 1),
        until="term_years",
        until_value=2,
        frequency="annual",
    )
    af.attained_age = af.issue_age + af.month // 12
    af.death_claims = af.sum_assured * af.mortality_rate
    return af


def _swapped_frame_with_dates() -> ActuarialFrame:
    """Return the plan-swapped frame, plus the dates the date accessor needs."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "issue_date": [datetime.date(2026, 1, 1), datetime.date(2026, 1, 1)],
                "expiry_date": [datetime.date(2026, 4, 1), datetime.date(2026, 4, 1)],
            }
        )
    )
    af.death_claims = af.sum_assured * 0.01
    _swap_into_plan(af, (pl.col("sum_assured") * 0.02).alias("lapse_reserve"))
    return af


def _rollforward_frame() -> ActuarialFrame:
    """Build a model whose account value comes from a compiled rollforward.

    The kernel materialises one hidden struct column so it runs once
    however many states are read back out of it. That column is framework
    plumbing: in the plan, in the schema the plan resolves to, and never
    handed back by ``collect()``.
    """
    af = ActuarialFrame(
        {"opening_balance": [100.0], "growth_rate": [0.05], "term_months": [3]}
    )
    af = af.projection.set(
        valuation_date=datetime.date(2026, 1, 31),
        until="term_months",
        until_value="term_months",
        frequency="monthly",
        per_policy=True,
    )
    builder = af.projection.rollforward(states={"account": af["opening_balance"]})
    builder["account"].grow(af["growth_rate"])
    af.account_value = compile_rollforward(builder).expr_for("account")
    return af


def _hidden_columns(af: ActuarialFrame) -> list[str]:
    """Return the rollforward kernel's own scratch columns on ``af``."""
    return [name for name in af._schema or {} if name.startswith("__rollforward_")]  # noqa: SLF001


def _fold_a_log_naming_a_column_the_frame_never_saw() -> CalcGraph:
    """Fold a log holding a record that reads a name no frame ever held.

    The reachable shape of a producer bug, built directly because no door
    of the frame will mint it: a record whose formula names
    ``premium_holiday_flag``, on a model where that name is not in the
    data, was not renamed away and was not dropped. There is nothing for
    the fold to resolve the reference to, and it still has to say something
    about the column the record read.
    """
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    af.death_claims = af.sum_assured * 0.01
    read = Col("premium_holiday_flag")
    log = af._calculations  # noqa: SLF001 -- a record no recording door would write
    log.append(
        CalculationRecord(
            column="waived_premiums",
            ordinal=1,
            operation_id=len(log) + 1,
            node=read,
            expr=lower_polars(read),
            dtype=None,
            source=None,
            origin="assignment",
        )
    )
    return fold(af)


def _fold_a_batch_that_failed_on_a_misspelled_column() -> CalcGraph:
    """Fold a frame whose ``with_columns`` batch named a column that is not there.

    The other way a record comes to read a name no frame held, and the
    only one an actuary reaches by typing: ``mortalty_rate`` for
    ``mortality_rate``. The batch reaches the query plan, the eager
    schema resolve throws on the missing name, and the framework records
    the batch the plan already carries -- so the record is a faithful
    transcript of the typo rather than evidence of a producer bug.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001, 0.002],
            }
        )
    )
    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        af.with_columns(
            (pl.col("sum_assured") * pl.col("mortalty_rate")).alias("death_claims")
        )
    return fold(af)


def _fold_a_failed_batch_whose_typo_rides_a_reused_alias() -> CalcGraph:
    """Fold one failed batch whose typo sits under an alias reusing a held name.

    The same misspelling, in a call that also assigns back to a column
    the frame already holds. The door takes each alias's dtype from the
    last schema that resolved, and that schema still knows
    ``sum_assured`` -- so this record comes back typed while its sibling
    in the same failed batch comes back with none, and the reference
    under the typo hangs off the typed one.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001, 0.002],
            }
        )
    )
    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        af.with_columns(
            (pl.col("mortalty_rate") * 2.0).alias("sum_assured"),
            (pl.col("mortality_rate") * 3.0).alias("brand_new"),
        )
    return fold(af)


def _fold_a_failed_batch_whose_typo_rides_a_new_alias() -> CalcGraph:
    """Fold the same mixed batch with the misspelling moved to the new alias.

    The sibling of the fixture above and the half of the pair where the
    marker fires: the reused alias is typed off the stale schema and
    reads nothing wrong, while the new alias carries the typo and comes
    back with no dtype. It is what shows the mark to be per record rather
    than per batch -- a typed record in the same failed call does not
    silence the hint.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001, 0.002],
            }
        )
    )
    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        af.with_columns(
            (pl.col("mortality_rate") * 2.0).alias("sum_assured"),
            (pl.col("mortalty_rate") * 3.0).alias("brand_new"),
        )
    return fold(af)


def _fold_a_bogus_record_reading_the_same_typo() -> CalcGraph:
    """Fold a hand-written record reading the name the failed batches read.

    The producer-bug reading, built on the name the two failed-batch
    fixtures use so the three hints can be compared character for
    character. No door of the frame mints this one: a record whose
    formula names ``mortalty_rate`` on a model where no ``with_columns``
    call ever failed.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001, 0.002],
            }
        )
    )
    af.death_claims = af.sum_assured * 0.01
    read = Col("mortalty_rate")
    log = af._calculations  # noqa: SLF001 -- a record no recording door would write
    log.append(
        CalculationRecord(
            column="waived_premiums",
            ordinal=1,
            operation_id=len(log) + 1,
            node=read,
            expr=lower_polars(read),
            dtype=None,
            source=None,
            origin="assignment",
        )
    )
    return fold(af)


# --- what a hole is ---------------------------------------------------------


def test_a_column_written_straight_into_the_plan_is_a_hole() -> None:
    """Schema minus the arriving columns minus the recorded ones."""
    reported = find_holes(_swapped_frame())

    assert [hole.column for hole in reported] == ["lapse_reserve"]
    assert reported[0].reason == "unrecorded"


def test_the_columns_the_model_did_account_for_are_not_holes() -> None:
    """An arriving column and a recorded calculation both have answers."""
    columns = _hole_columns(_swapped_frame())

    assert "sum_assured" not in columns
    assert "death_claims" not in columns


def test_the_hint_names_the_column_and_both_ways_to_record_it() -> None:
    """The next move is in the message: assign it, or bring it in as data.

    The column really is sitting on the frame here, so the hint says so
    and offers the two remedies that would account for it. Both of those
    are only honest for a column that is actually there.
    """
    (hole,) = find_holes(_swapped_frame())

    assert "lapse_reserve" in hole.hint
    assert "is on the frame" in hole.hint
    assert "af.lapse_reserve = " in hole.hint
    assert "model points" in hole.hint


def test_a_hint_for_a_vendor_column_name_can_actually_be_typed() -> None:
    """A name with a space in it is assigned through brackets, so say that."""
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))
    af.death_claims = af.sum_assured * 0.01
    _swap_into_plan(af, (pl.col("sum_assured") * 0.02).alias("Lapse Reserve"))

    (hole,) = find_holes(af)

    assert "af['Lapse Reserve'] = " in hole.hint


# --- what a hole is not -----------------------------------------------------


def test_an_injected_series_is_a_located_input_not_a_hole() -> None:
    """Values handed over wholesale are recorded, so they have a source and a line."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3]}))

    af.simulated_deaths = pl.Series("simulated_deaths", [0, 1, 0])

    assert find_holes(af) == []
    node = fold(af).nodes["simulated_deaths@1"]
    assert node.kind is NodeType.INPUT
    assert node.data.provenance is Provenance.INJECTED
    assert node.data.source_location is not None
    assert "test_holes.py:" in node.data.source_location


def test_an_injected_array_is_a_located_input_not_a_hole() -> None:
    """An array of simulated values is data too, and is classified as data.

    The container the values arrived in is not what makes an injection an
    input -- deriving nothing is. An array recorded as a formula would put
    the words ``Series[literal]`` where a reviewer expects a calculation.
    """
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3]}))

    af.simulated_deaths = np.array([0, 1, 0])

    assert find_holes(af) == []
    node = fold(af).nodes["simulated_deaths@1"]
    assert node.kind is NodeType.INPUT
    assert node.data.provenance is Provenance.INJECTED
    assert node.data.formula is None
    assert node.data.source_location is not None
    assert "test_holes.py:" in node.data.source_location


def test_an_injected_input_shows_no_formula_because_it_derives_nothing() -> None:
    """Data does not get rendered as a derivation just because it was assigned.

    Values handed over wholesale are a source, not a calculation. What the
    node shows instead is where they arrived -- which is the part a
    reviewer of a spreadsheet's pasted values never gets.
    """
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3]}))

    af.simulated_deaths = pl.Series("simulated_deaths", [0, 1, 0])

    node = fold(af).nodes["simulated_deaths@1"]
    assert node.data.formula is None
    assert node.data.reads == ()


def test_no_input_node_anywhere_in_the_graph_claims_a_formula() -> None:
    """The invariant a payload reader is entitled to: inputs derive nothing.

    Asserted over a graph holding all four node shapes at once -- arriving
    columns, an injection, calculations, and a column nothing accounts for
    -- so that "input" means the same thing whichever way the node got
    there.
    """
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    af.death_claims = af.sum_assured * 0.01
    af.simulated_deaths = pl.Series("simulated_deaths", [0, 1])
    _swap_into_plan(af, (pl.col("sum_assured") * 0.02).alias("lapse_reserve"))

    graph = fold(af)

    kinds = {node.kind for node in graph.nodes.values()}
    assert kinds == {NodeType.INPUT, NodeType.COMPUTED, NodeType.HOLE}
    assert [
        node.id
        for node in graph.nodes.values()
        if node.kind is NodeType.INPUT and node.data.formula is not None
    ] == []


def test_an_injected_input_gets_no_trace_but_what_reads_it_still_does() -> None:
    """No formula, no walk-through -- and the calculation below it is unaffected.

    A numeric trace substitutes values into a formula. An injection has
    none, so inventing a walk-through for it would be showing a reviewer
    arithmetic nobody wrote. The claim calculated *from* those values is a
    formula, keeps its trace, and is where the audit trail resumes.
    """
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3]}))
    af.simulated_deaths = pl.Series("simulated_deaths", [0, 1, 0])
    af.death_claims = af.simulated_deaths * 100_000.0

    artifact = json.loads(GraphExporter(af).export(af.collect()))
    nodes = {node["id"]: node for node in artifact["nodes"]}

    assert nodes["simulated_deaths@1"]["trace"] is None
    assert nodes["death_claims@1"]["trace"] is not None


def test_an_injected_series_still_supersedes_and_is_still_a_version() -> None:
    """Calling an injection an input does not take it out of the column's history."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3]}))
    af.simulated_deaths = pl.Series("simulated_deaths", [0, 1, 0])

    graph = fold(af)

    assert graph.versions("simulated_deaths") == ("simulated_deaths@1",)
    assert graph.latest("simulated_deaths") == "simulated_deaths@1"


def test_a_column_computed_and_then_dropped_is_a_ghost_not_a_hole() -> None:
    """Leaving the schema is not the same as never being explained."""
    af = ActuarialFrame(pl.DataFrame({"annual_premium": [1200.0, 2400.0]}))
    af.monthly_premium = af.annual_premium / 12
    af.rounding_scratch = af.monthly_premium * 0.0
    af = af.drop("rounding_scratch")

    assert find_holes(af) == []
    assert fold(af).nodes["rounding_scratch@1"].data.in_final_schema is False


def test_a_taught_model_has_no_holes_at_all() -> None:
    """The empty list is the claim: every column is a formula or a named source."""
    assert find_holes(_taught_model()) == []


def test_a_name_the_arrival_history_still_answers_for_is_an_input_not_a_hole() -> None:
    """A vendor name renamed away one step back is history, not an unexplained column.

    The widened frame's own schema never held ``Issue Age``, so it is not
    a column sitting on this frame with no account of itself -- it is an
    input to the model, one step back, and the fold already says so.
    """
    af = ActuarialFrame(pl.DataFrame({"Issue Age": [30, 45]}))
    af = af.rename({"Issue Age": "issue_age"})
    af = with_scenarios(af, ["BASE", "UP"])
    af.attained_age = af.issue_age + 1

    assert find_holes(af) == []
    assert fold(af).nodes["Issue Age"].kind is NodeType.INPUT


def test_a_column_nothing_accounts_for_is_never_reported_as_data_that_arrived() -> None:
    """The framework used to guess an input here.

    A guess wearing a source is worse than a guess wearing a reason. An
    input node is a positive claim that the policy data supplied the
    column, and the fold has no grounds for it: the name is not in any
    frame's data, was not renamed away and was not dropped. What the fold
    actually observed is that nothing accounts for the name, which is what
    a hole says and the only thing that can be said here.
    """
    graph = _fold_a_log_naming_a_column_the_frame_never_saw()

    guessed = graph.nodes["premium_holiday_flag"]

    assert guessed.kind is NodeType.HOLE
    assert guessed.data.provenance is None
    assert guessed.data.reads == ()


def test_the_unresolvable_name_is_warned_about_and_what_read_it_binds_to_it() -> None:
    """Loudly, because the reachable way to get here is a bug in the producer.

    A record naming a column that never existed anywhere is something the
    framework minted wrongly, and a graph that recorded it silently would
    export the mistake as data. The calculation that named it still binds
    to the node, so the walk from it reaches the hole and stops.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        graph = _fold_a_log_naming_a_column_the_frame_never_saw()
    heard = _gaspatchio_warnings(caught)

    assert len(heard) == 1
    assert "premium_holiday_flag" in heard[0]
    assert "unexplained" in heard[0]
    assert graph.nodes["waived_premiums@1"].data.reads == ("premium_holiday_flag",)


def test_the_hint_for_an_unresolvable_name_says_the_record_is_wrong() -> None:
    """The other route needs the opposite advice, and the graph knows which route.

    Nothing is on the frame to record here, so the on-frame remedies are
    the wrong ones twice over: they are untypeable advice about a column
    that is not there, and following either would resolve the reference
    and leave whatever minted the record still minting it. The hint is
    where that is decided: the fold's own warning names both readings
    and picks neither, because at bind time it has only the name.
    """
    (hole,) = holes_in(_fold_a_log_naming_a_column_the_frame_never_saw())

    assert hole.column == "premium_holiday_flag"
    assert "no frame in this model ever held a column by that name" in hole.hint
    assert "the record naming it is wrong" in hole.hint
    assert "is on the frame" not in hole.hint
    assert "af.premium_holiday_flag = " not in hole.hint
    assert "model points" not in hole.hint


def test_a_misspelled_column_in_a_failed_batch_is_still_a_hole() -> None:
    """Nothing supplies the name, so the reference binds to a hole and says so.

    The reference is unresolvable however it got written, and suppressing
    the hole because the framework can see how it got there would be the
    fold guessing that a record it cannot explain is fine.
    """
    (hole,) = holes_in(_fold_a_batch_that_failed_on_a_misspelled_column())

    assert hole.column == "mortalty_rate"
    assert hole.reason == "unrecorded"


def test_the_hint_for_a_name_a_failed_batch_read_points_at_the_spelling() -> None:
    """A faithful transcript of a typo needs the reader sent to the typo.

    The record here is not wrong -- it says exactly what the failing
    ``with_columns`` call said -- so telling the reader to fix whatever
    wrote it points at the framework for a mistake in their own
    expression. The graph knows the difference: a batch record with no
    dtype is always a failed batch's, because the door types its aliases
    off the last schema that resolved and a failed batch never advanced
    it. Only in that direction --
    ``test_the_failed_batch_marker_misses_a_typo_under_a_reused_alias``
    below has the alias that reuses a name that schema holds, where the
    marker misses.
    """
    (hole,) = holes_in(_fold_a_batch_that_failed_on_a_misspelled_column())

    assert "with_columns" in hole.hint
    assert "failed" in hole.hint
    assert "spelled" in hole.hint
    assert "the record naming it is wrong" not in hole.hint
    assert "is on the frame" not in hole.hint


def test_the_hint_names_the_alias_the_failed_statement_defines() -> None:
    """Sending a reader to "that statement" is a search; the alias is an address.

    The graph is holding the answer already: the record the reference
    hangs off is a definition of one column, and that column is the
    alias in the call the reader has to go and read. Naming it is the
    difference between "find the with_columns() call" and "go to the
    line that defines death_claims".
    """
    (hole,) = holes_in(_fold_a_batch_that_failed_on_a_misspelled_column())

    assert "death_claims" in hole.hint
    assert "spelled" in hole.hint


def test_the_failed_batch_marker_misses_a_typo_under_a_reused_alias() -> None:
    """The marker holds one way round, and this is the shape that shows it.

    A marked record is always a failed batch's; a failed batch's record
    is not always marked. The dtype comes from the last schema that
    resolved, and ``sum_assured`` is in that schema because it arrived
    with the data -- so the alias reusing it comes back typed, and a
    reference read under it takes the general wording even though the
    batch it came from is the same one whose sibling record is marked.
    The set that misses is the names that schema holds, which need not
    be the names the frame holds: an alias records whatever the last
    resolved schema holds for its name, which may be ``None`` for a name
    the frame itself holds. What resolves that schema is enumerated in
    ``base.py``'s ``_record_batch_calculations`` docstring, which also
    names the pin on each door; on a model of any real size something
    usually has resolved it, which makes this miss the ordinary case
    rather than the edge. A false negative, never a false positive: an
    actuary is told less here, not told something untrue.
    """
    (hole,) = holes_in(_fold_a_failed_batch_whose_typo_rides_a_reused_alias())

    assert hole.column == "mortalty_rate"
    assert "the record naming it is wrong" in hole.hint
    assert "spelled" not in hole.hint


def test_the_marker_still_fires_for_a_new_alias_beside_a_typed_sibling() -> None:
    """The other half of the pair: move the typo and the mark moves with it.

    Same batch, same failure, the misspelling under the new alias
    instead. The mark flips with the typo, which is what makes the hint
    above a miss rather than the rule.

    What this half alone buys is narrower than "a marker keyed on the
    batch", and worth stating so nobody has to re-derive it. Three
    batch-keyed markers were measured against the pair. One that marks
    the whole batch but still answers with each record's own alias, and
    one that answers with the marked record's alias throughout, both go
    red on the miss half above and leave this one green. Only the
    variant that hands back the batch's *first* alias reaches this test
    -- it names ``sum_assured`` in the hint where ``brand_new`` belongs,
    so the assertion below that trips first is the one on ``brand_new``
    and the one on ``sum_assured`` catches it too. The alias handed back
    has to be the one whose own expression reads the name, so the typed
    sibling in the same call is not the one an actuary is sent to open.
    """
    (hole,) = holes_in(_fold_a_failed_batch_whose_typo_rides_a_new_alias())

    assert hole.column == "mortalty_rate"
    assert "brand_new" in hole.hint
    assert "spelled" in hole.hint
    assert "sum_assured" not in hole.hint
    assert "the record naming it is wrong" not in hole.hint


def test_the_folds_warning_does_not_contradict_the_hint_beside_it() -> None:
    """One ``af.graph.holes()`` call puts both on the screen; they must agree.

    The warning is minted while the reference is being bound, where the
    fold cannot yet tell a bogus record from a faithful transcript of a
    failed call -- so it must not decide between them. Ending on the
    record being wrong, in the same call whose hint sends the actuary to
    their own spelling, is one terminal giving two opposite next moves.

    The opening clause is pinned here too, because two places describe
    the warning by it rather than by its ending -- ``drop``'s comment in
    ``ActuarialFrame`` and
    ``test_a_dropped_inputs_arrival_name_still_answers_for_what_read_it``
    below. Both were paraphrases of the ending until it was reworded and
    both went stale silently; describing the opening instead only helps
    while something holds the opening still.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        graph = _fold_a_batch_that_failed_on_a_misspelled_column()

    (warning,) = [
        line for line in _gaspatchio_warnings(caught) if "mortalty_rate" in line
    ]
    (hole,) = holes_in(graph)

    assert "spelled" in hole.hint
    assert warning.startswith("Nothing accounts for ")
    assert not warning.endswith("the record naming it is wrong.")
    assert "with_columns()" in warning
    assert "af.graph.holes()" in warning


def test_the_warning_promises_only_what_the_marked_record_delivers() -> None:
    """Where the mark is missing the two readings come back identical.

    The warning names two readings and must not claim the hole report
    decides between them on every shape: it decides off the marked
    record, and where the mark is missing the producer-bug hint comes
    back character for character. A sentence promising a decision anyway
    sends an actuary looking for a distinction the report cannot draw --
    and, on this shape, hands them "fix whatever wrote that record" for
    their own typo. The equality and the sentence that admits it are
    pinned together so neither can drift from the other.

    Both halves of the sentence are asserted, and the second half is why:
    the qualifier says what the report does where the mark survives, and
    only "and the record itself where it does not" says what it does where
    the mark is gone. With the qualifier pinned alone, a rewrite
    could keep it, delete the admission, re-promise the decision in words
    other than the retired one and stay green -- measured, not supposed.
    What the three assertions on the sentence catch is the retired
    phrase, a lost qualifier and a lost admission. What they cannot
    catch is a rewrite that keeps all three and still oversells: a pin
    is a pin, not a proof that every future sentence here is honest.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        marked = _fold_a_batch_that_failed_on_a_misspelled_column()

    (bogus,) = holes_in(_fold_a_bogus_record_reading_the_same_typo())
    (missed,) = holes_in(_fold_a_failed_batch_whose_typo_rides_a_reused_alias())
    (fired,) = holes_in(marked)

    assert bogus.hint == missed.hint
    assert bogus.hint != fired.hint

    (warning,) = [
        line for line in _gaspatchio_warnings(caught) if "mortalty_rate" in line
    ]
    assert "af.graph.holes()" in warning
    assert "where the failed call's record shows the failure" in warning
    assert "and the record itself where it does not" in warning
    assert "tells the two apart" not in warning


def test_the_folds_warning_is_plain_english() -> None:
    """Said in a reader's words: what is missing, the two causes, what to check."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _fold_a_batch_that_failed_on_a_misspelled_column()

    (warning,) = [
        line for line in _gaspatchio_warnings(caught) if "mortalty_rate" in line
    ]
    assert "no input column has that name" in warning
    assert "usually a misspelling" in warning
    for jargon in ("arrived under", "a field the data supplied", "carries the mark"):
        assert jargon not in warning


def test_the_rollforward_kernels_own_scratch_column_is_not_a_hole() -> None:
    """A hidden column the finished frame never hands back is nobody's question.

    A compiled rollforward materialises one struct column so the kernel
    runs once; ``collect()`` strips it again. It is not part of the
    model's own schema, so reporting it as unexplained would put framework
    plumbing in front of a reviewer looking for their own columns.
    """
    af = _rollforward_frame()

    assert _hidden_columns(af)
    assert find_holes(af) == []


# --- the hole in the graph --------------------------------------------------


def test_a_hole_is_a_typed_leaf_node_in_the_graph() -> None:
    """The graph carries the hole itself, so a reader needs no second artifact."""
    graph = fold(_swapped_frame())

    node = graph.nodes["lapse_reserve"]
    assert node.kind is NodeType.HOLE
    assert node.data.reads == ()
    assert node.data.column == "lapse_reserve"
    assert node.data.in_final_schema is True
    assert node.data.dtype == "f64"


def test_a_hole_claims_no_source_because_it_has_none() -> None:
    """An input names where its data came from; a hole is the absence of that."""
    graph = fold(_swapped_frame())

    assert graph.nodes["lapse_reserve"].data.provenance is None
    assert graph.nodes["lapse_reserve"].data.formula is None


def test_a_calculation_that_reads_a_hole_binds_to_it_and_stops_there() -> None:
    """The dependency walk reaches the hole and finds nothing behind it.

    The node it stops at has to be the hole itself. A column read before
    anything explained it is also how a name one step back in the model's
    history reaches the fold, and that one becomes an input -- so a
    reserve that depends on an unexplained column must not come out
    reading a model-point field that was never in the data.
    """
    af = _swapped_frame()
    af.total_outgo = af["lapse_reserve"] + af.death_claims

    graph = fold(af)

    assert graph.nodes["total_outgo@1"].data.reads == (
        "lapse_reserve",
        "death_claims@1",
    )
    read = graph.nodes["lapse_reserve"]
    assert read.kind is NodeType.HOLE
    assert read.data.provenance is None
    assert read.data.reads == ()


def test_a_hole_is_held_before_whatever_reads_it() -> None:
    """The graph's own order stays a topological one with holes minted into it.

    Every reader downstream -- a fingerprint, a dependency walk, a diff --
    is entitled to find a node's inputs already in hand by the time it
    reaches the node itself.
    """
    af = _swapped_frame()
    af.total_outgo = af["lapse_reserve"] + af.death_claims

    held = list(fold(af).nodes)

    assert held.index("lapse_reserve") < held.index("total_outgo@1")


def test_the_reported_holes_are_the_graphs_own_hole_nodes() -> None:
    """Read off the graph, not counted a second time beside it."""
    af = _swapped_frame()
    _swap_into_plan(af, (pl.col("sum_assured") * 0.03).alias("expense_reserve"))

    graph = fold(af)

    assert _hole_columns(af) == [
        node.data.column for node in graph.nodes.values() if node.kind is NodeType.HOLE
    ]


def test_the_report_follows_the_graph_when_the_graph_and_the_frame_disagree() -> None:
    """The graph is the source, not a second opinion that happens to agree.

    A report recomputed from the frame would answer identically to one read
    off the graph on every honest model, so agreement proves nothing. Here
    the folded graph is edited afterwards -- one hole removed, one that no
    frame ever had put in its place -- and the report follows the graph
    both ways. Nothing recomputed from ``af`` could do that.
    """
    graph = fold(_swapped_frame())
    del graph.nodes["lapse_reserve"]
    graph.nodes["expense_reserve"] = GraphNode(
        id="expense_reserve",
        kind=NodeType.HOLE,
        data=NodeData(id="expense_reserve", column="expense_reserve"),
    )

    assert [hole.column for hole in holes_in(graph)] == ["expense_reserve"]


def test_the_report_a_frame_asks_for_is_the_one_its_own_graph_carries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asking the frame answers from the fold it ran, not from a second count.

    Recomputing the same subtraction from the frame would agree with the
    graph on every honest model, so agreement is not evidence of where the
    answer came from. This puts a hole into the graph on its way back from
    the fold -- one no reading of the frame could produce, on a model that
    has none -- and then asks the frame. Getting it back is the evidence.
    """

    def _fold_then_add_a_hole(af: ActuarialFrame, *, refuse_unnamed: bool) -> CalcGraph:
        graph = fold(af, refuse_unnamed=refuse_unnamed)
        graph.nodes["reinsurance_recovery"] = GraphNode(
            id="reinsurance_recovery",
            kind=NodeType.HOLE,
            data=NodeData(id="reinsurance_recovery", column="reinsurance_recovery"),
        )
        return graph

    monkeypatch.setattr(holes_module, "fold", _fold_then_add_a_hole)

    reported = find_holes(_taught_model())

    assert [hole.column for hole in reported] == ["reinsurance_recovery"]


def test_the_export_shows_a_hole_as_a_hole() -> None:
    """A hole survives export intact rather than crashing it or hiding in it."""
    af = _swapped_frame()

    artifact = json.loads(GraphExporter(af).export(af.collect()))
    nodes = {node["id"]: node for node in artifact["nodes"]}

    assert nodes["lapse_reserve"]["kind"] == "hole"
    assert nodes["lapse_reserve"]["formula"] is None
    assert nodes["lapse_reserve"]["value_sample"] is not None
    assert [hole["column"] for hole in artifact["holes"]] == ["lapse_reserve"]


# --- determinism ------------------------------------------------------------


def test_holes_come_out_in_the_frames_own_schema_order() -> None:
    """Two runs of one model must produce graphs anybody can diff."""
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))
    _swap_into_plan(
        af,
        (pl.col("sum_assured") * 0.02).alias("zeta_reserve"),
        (pl.col("sum_assured") * 0.03).alias("alpha_reserve"),
    )
    af.total_outgo = af.sum_assured * 0.0

    assert _hole_columns(af) == ["zeta_reserve", "alpha_reserve"]


def test_folding_a_frame_with_a_hole_twice_gives_the_same_graph() -> None:
    """The hole is a function of the log and the schema, not of when you asked."""
    af = _swapped_frame()

    assert fold(af).to_dict() == fold(af).to_dict()


# --- terminal classification: what the framework cannot read ----------------


def test_a_raw_engine_expression_records_which_engine_it_needs() -> None:
    """An escape hatch runs on one engine, and the graph says which."""
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))

    af.running_total = pl.col("sum_assured").cum_sum()

    data = fold(af).nodes["running_total@1"].data
    assert data.engines == ("polars",)
    assert data.period_reference == "unknown"


def test_engine_text_anywhere_in_a_formula_makes_its_period_reference_unknown() -> None:
    """Opaque text in one operand is enough: the whole column's timing is unreadable.

    Every other node's period reference is derived from its own structure
    -- ``previous_period`` *is* the period reference. Engine text is the
    one thing the framework cannot read, so it is the one thing that has
    to be annotated.
    """
    af = ActuarialFrame(
        pl.DataFrame({"sum_assured": [100_000.0], "mortality_rate": [0.01]})
    )

    af.death_claims = af.mortality_rate * pl.col("sum_assured").cum_sum()

    data = fold(af).nodes["death_claims@1"].data
    assert data.engines == ("polars",)
    assert data.period_reference == "unknown"


def test_a_formula_the_framework_built_itself_claims_no_engine() -> None:
    """A portable calculation carries no engine tag and no timing annotation."""
    af = ActuarialFrame(
        pl.DataFrame({"sum_assured": [100_000.0], "mortality_rate": [0.01]})
    )

    af.death_claims = af.sum_assured * af.mortality_rate

    data = fold(af).nodes["death_claims@1"].data
    assert data.engines == ()
    assert data.period_reference is None


def test_a_hole_is_reported_with_the_reason_the_fold_can_honestly_give() -> None:
    """One reason, because the fold cannot tell a plan swap from a recording gap.

    It is also the type's own default: there is no second value for a
    caller to choose between, which is the point of the single reason
    rather than an enum that guesses.
    """
    (hole,) = find_holes(_swapped_frame())

    assert hole.column == "lapse_reserve"
    assert hole.reason == "unrecorded"
    assert Hole(column="lapse_reserve").reason == hole.reason


# --- a hole outlives every step that derives a frame ------------------------


def test_a_hole_survives_a_scenario_axis() -> None:
    """A cross-joined scenario axis widens the model; it explains nothing.

    Deriving a frame carries the calculation log onto the successor, which
    then works out which of its own columns arrived with its data. A
    column nothing accounts for is not one of them. Sweeping it in with
    them would erase the hole and -- worse than erasing it -- have the
    graph state positively that the model points supplied a column the
    model cannot account for at all.
    """
    af = with_scenarios(_swapped_frame(), ["BASE", "UP"])

    assert _hole_columns(af) == ["lapse_reserve"]
    node = fold(af).nodes["lapse_reserve"]
    assert node.kind is NodeType.HOLE
    assert node.data.provenance is None


def test_the_column_the_scenario_axis_really_added_is_an_injection() -> None:
    """The other half of the same rule, in one graph.

    Three columns, three different answers, and the point is that the graph
    gives each of them its own. ``sum_assured`` came with the model points.
    ``lapse_reserve`` is unexplained and stays a hole. ``scenario_id`` came
    from the cross-join, which is neither: the model-points file never held
    it, so it is an input the model was handed at a known line -- and the
    node says exactly that.
    """
    graph = fold(with_scenarios(_swapped_frame(), ["BASE", "UP"]))
    axis = graph.nodes["scenario_id@1"]

    assert axis.kind is NodeType.INPUT
    assert axis.data.provenance is Provenance.INJECTED
    assert axis.data.source_location is not None
    assert graph.nodes["sum_assured"].kind is NodeType.INPUT
    assert graph.nodes["lapse_reserve"].kind is NodeType.HOLE


def test_a_renamed_vendor_field_survives_the_scenario_axis_as_a_source_field() -> None:
    """A scenario axis widens the model; it does not cost it the source's names.

    The model renames its vendor columns on the way in, calculates from
    them, and only then cross-joins a scenario axis -- the ordinary shape
    of a sensitivity run. The rename record still reads ``Issue Age``, so
    the derived frame carries a record naming the vendor field, and the
    graph has to be able to say that what it names is a field the model
    points supplied. Left to work its arrival history out from its own
    schema alone, the successor knows nothing of a name its data no longer
    answers to: the vendor field is demoted to a column the graph says the
    model cannot account for, behind a warning saying the record naming it
    is wrong, on a model that did nothing unusual.
    """
    af = ActuarialFrame(pl.DataFrame({"Issue Age": [30, 45]}))
    af = af.rename({"Issue Age": "issue_age"})
    af.attained_age = af.issue_age + 1

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        graph = fold(with_scenarios(af, ["BASE", "UP"]))

    assert graph.nodes["Issue Age"].kind is NodeType.INPUT
    assert graph.nodes["Issue Age"].data.provenance is Provenance.MODEL_POINTS
    assert graph.nodes["scenario_id@1"].data.provenance is Provenance.INJECTED
    assert _gaspatchio_warnings(caught) == []


def test_a_hole_survives_a_projection_timeline() -> None:
    """Declaring the projection axis stamps the model's own frame in place.

    Nothing is re-derived and nothing is reseeded, so the column stays
    exactly as unexplained as it was before the axis existed.
    """
    af = _swapped_frame()
    af = af.projection.set(
        valuation_date=datetime.date(2026, 1, 1),
        until="term_years",
        until_value=2,
        frequency="annual",
    )

    assert _hole_columns(af) == ["lapse_reserve"]
    assert fold(af).nodes["lapse_reserve"].kind is NodeType.HOLE


def test_a_hole_survives_a_rename() -> None:
    """Renaming an unexplained column moves the hole; it does not fill it.

    A rename records ``new = Col(old)`` so the graph can follow a
    name-move, and that record is honest exactly when the old name had an
    account of itself. Mint one for a column nothing accounts for and the
    hole vanishes twice over: the old name has left the schema, so nothing
    seeds a hole for it, and the new name now carries a record, so the
    frame reads it as a calculation. What the model would then export is a
    plan-bypassed column dressed as a model-point field, under a name the
    frame never held.

    The second half of the rule is the narrow one: a column the log does
    account for still mints its name-move, in the same call.
    """
    af = _swapped_frame()
    assert _hole_columns(af) == ["lapse_reserve"]

    af = af.rename({"lapse_reserve": "reserve_held", "death_claims": "claims_paid"})

    assert _hole_columns(af) == ["reserve_held"]
    graph = fold(af)
    assert graph.nodes["reserve_held"].kind is NodeType.HOLE
    assert graph.nodes["reserve_held"].data.provenance is None
    assert "lapse_reserve" not in graph.nodes
    assert graph.latest("claims_paid") == "claims_paid@1"


def test_rename_keeps_the_arriving_set_current() -> None:
    """A renamed input's old name must not linger as an arriving name.

    The set of names the frame's data arrived with is a set of *names*,
    and a rename moves one. Leave the old name in it and the name is
    still claimed by the model points after nothing on the frame answers
    to it -- so a column written into the plan under that name later
    reads as a field the actuary supplied.
    """
    af = ActuarialFrame(
        {"policy_id": [1], "sum_assured": [100.0], "lapse_reserve": [5.0]}
    )

    af = af.rename({"sum_assured": "sa"})

    assert af._initial_columns == frozenset({"policy_id", "sa", "lapse_reserve"})  # noqa: SLF001

    _swap_into_plan(af, pl.lit(1.0).alias("sum_assured"))

    assert _hole_columns(af) == ["sum_assured"]


def test_a_hole_under_a_renamed_away_name_survives_the_projection_carry() -> None:
    """The stale name must not launder the hole one derivation step later.

    The successor's arriving set is worked out afresh from its own
    schema, so a name this frame wrongly still calls an input is a name
    the timeline would call one too -- and by then the column is a
    model-point field on the frame the model exports.
    """
    af = ActuarialFrame({"policy_id": [1], "issue_age": [40], "sum_assured": [100.0]})
    af = af.rename({"sum_assured": "sa"})
    _swap_into_plan(af, pl.lit(1.0).alias("sum_assured"))

    af = af.projection.set(
        valuation_date=datetime.date(2026, 1, 1),
        until="term_years",
        until_value=1,
        frequency="annual",
    )

    assert _hole_columns(af) == ["sum_assured"]
    assert fold(af).nodes["sum_assured"].kind is NodeType.HOLE


def test_drop_keeps_the_arriving_set_current() -> None:
    """A dropped input's name must not linger as an arriving name either.

    The same false clean through a different door: the name leaves the
    frame, so a column written into the plan under it afterwards is a new
    column nothing accounts for, not the field the model points supplied.
    """
    af = ActuarialFrame(
        {"policy_id": [1], "sum_assured": [100.0], "lapse_reserve": [5.0]}
    )

    af = af.drop("sum_assured")

    assert af._initial_columns == frozenset({"policy_id", "lapse_reserve"})  # noqa: SLF001

    _swap_into_plan(af, pl.lit(1.0).alias("sum_assured"))

    assert _hole_columns(af) == ["sum_assured"]


def test_a_dropped_inputs_arrival_name_still_answers_for_what_read_it() -> None:
    """Dropping a column must not cost the calculations that read it their source.

    The name stops accounting for columns the frame holds -- that is the
    half above -- but the record of a calculation made before the drop
    still reads the dropped column by name, and the graph still has to say
    that what it read was a field the model points supplied. Shrink the
    arrival history along with the arriving set and that input becomes a
    column the graph reports the model as unable to account for, behind a
    warning that nothing accounts for the name: the same damage the
    arriving set's staleness used to do, done to every model that drops a
    column it calculated from.
    """
    af = ActuarialFrame({"policy_id": [1], "sum_assured": [100.0]})
    af.death_claims = af.sum_assured * 0.01

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        af = af.drop("sum_assured")
        graph = fold(af)

    assert graph.nodes["sum_assured"].kind is NodeType.INPUT
    assert graph.nodes["sum_assured"].data.provenance is Provenance.MODEL_POINTS
    assert graph.nodes["death_claims@1"].data.reads == ("sum_assured",)
    assert _gaspatchio_warnings(caught) == []


def test_a_hole_survives_a_join_that_brings_a_column_of_its_own() -> None:
    """An arriving join column is recorded; the unexplained one is untouched."""
    af = _swapped_frame()
    af = af.join(
        pl.DataFrame(
            {"sum_assured": [100_000.0, 250_000.0], "expense_pct": [0.05, 0.08]}
        ),
        on="sum_assured",
    )

    assert _hole_columns(af) == ["lapse_reserve"]
    graph = fold(af)
    assert graph.nodes["lapse_reserve"].kind is NodeType.HOLE
    assert graph.latest("expense_pct") == "expense_pct@1"


def test_a_hole_survives_freezing_the_calculations_into_values() -> None:
    """Materializing turns the plan into data and answers for the same columns."""
    af = _swapped_frame().materialize()

    assert _hole_columns(af) == ["lapse_reserve"]
    assert fold(af).nodes["lapse_reserve"].kind is NodeType.HOLE


def test_the_rollforward_kernels_scratch_column_is_no_ones_input_either() -> None:
    """Framework plumbing stays out of the graph on both sides of a cross-join.

    The hidden struct column is not part of the model's own schema, so it
    is not a hole -- and for the same reason it is not a model-point field
    either. A derived frame that called it one would put the kernel's own
    scratch space in front of a reviewer as data the actuary supplied.
    """
    af = _rollforward_frame()
    assert _hidden_columns(af)

    wide = with_scenarios(af, ["BASE", "UP"])

    assert _hidden_columns(wide)
    assert find_holes(wide) == []
    kernel_nodes = [
        node for node in fold(wide).nodes if node.startswith("__rollforward_")
    ]
    assert kernel_nodes == []


def test_a_hole_survives_a_date_offset_frame() -> None:
    """``add_duration`` stamps this frame, and it is still the same model.

    Three things the frame owes its reader after the call, all in one
    graph: the column nothing accounts for is still unaccounted for, the
    calculation made before the call is still a calculation rather than
    something the data arrived with, and the column the call itself added
    is accounted for -- as the formula it is, not as a model-point field.
    """
    af = _swapped_frame_with_dates()

    derived = af.date.add_duration(
        af.issue_date, "1y", new_col_name="first_anniversary"
    )

    assert derived is af
    assert _hole_columns(derived) == ["lapse_reserve"]
    graph = fold(derived)
    assert graph.nodes["lapse_reserve"].kind is NodeType.HOLE
    assert graph.nodes["death_claims@1"].kind is NodeType.COMPUTED
    assert graph.latest("first_anniversary") == "first_anniversary@1"
    assert "first_anniversary" not in graph.nodes
    assert graph.nodes["first_anniversary@1"].data.reads == ("issue_date",)


def test_a_hole_survives_a_timeline_frame() -> None:
    """``create_timeline`` explodes the frame into periods; the model is the same.

    The row count changes and every earlier column is repeated down the new
    rows, but nothing about how those columns were made changes with it.
    """
    af = _swapped_frame_with_dates()

    derived = af.date.create_timeline(
        af.issue_date, af.expiry_date, freq="1mo", new_col_name="period_date"
    )

    assert derived is af
    assert _hole_columns(derived) == ["lapse_reserve"]
    graph = fold(derived)
    assert graph.nodes["lapse_reserve"].kind is NodeType.HOLE
    assert graph.nodes["death_claims@1"].kind is NodeType.COMPUTED
    assert graph.latest("period_date") == "period_date@1"
    assert "period_date" not in graph.nodes
    assert graph.nodes["period_date@1"].data.reads == ("issue_date", "expiry_date")
