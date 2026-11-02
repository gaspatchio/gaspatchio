# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``af.graph``: the questions an actuary asks of a model's own calculations.

The fold turns a frame's calculation log into one node per definition. This
is the surface that puts those nodes in front of a reader: what did this
column read, who read it, what is the whole cone behind it, which versions
exist, which one is live, what cannot the model account for, and what is
this model's content-addressed identity.

Three things the tests below pin, because they are the ones that go wrong
quietly:

- **The answer follows the frame.** A query is answered from a cached fold,
  and the cache has to notice every way the answer can change -- a new
  assignment appending to the log, and a ``drop`` or a plan written
  directly, neither of which appends anything but both of which change the
  schema the fold reads.
- **A name is resolved, not guessed.** A column name answers for whichever
  definition is live; an explicit ``column@ordinal`` answers for that one;
  anything else is refused by name rather than answered with an empty
  tuple.
- **Nothing here runs the model.** Every query is structure, so no query may
  collect the frame.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._identity import SHA256_PREFIX
from gaspatchio.frame.graph import NodeType
from gaspatchio.frame.graph import calc_graph as calc_graph_module
from gaspatchio.frame.graph.calc_graph import _NODE_LINE, node_accounting
from gaspatchio.rollforward import compile_rollforward
from gaspatchio.scenarios import with_scenarios

# --- helpers ----------------------------------------------------------------


def _reassigning_model() -> ActuarialFrame:
    """Build a model that writes ``policies_in_force`` twice.

    The second write is the case the whole node-per-definition rule exists
    for: ``death_claims`` reads the inforce as it stood before the
    decrement was taken off it, and the graph has to keep saying so after
    the name has moved on.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.01, 0.02],
            }
        )
    )
    af.policies_in_force = 1.0 - af.mortality_rate
    af.death_claims = af.sum_assured * af.policies_in_force
    af.policies_in_force = af.policies_in_force - af.death_claims
    return af


def _swap_into_plan(af: ActuarialFrame, *columns: pl.Expr) -> None:
    """Write ``columns`` straight into the frame's query plan.

    Behind every door that records, so nothing appends a log entry: the
    columns exist in the plan, and in the schema it resolves to, and
    nowhere else.
    """
    plan = af._df  # noqa: SLF001 -- the bypass under test
    assert plan is not None
    af._df = plan.with_columns(*columns)  # noqa: SLF001


def _unaccounted_model() -> ActuarialFrame:
    """Build a model holding one column nothing in it accounts for."""
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    af.death_claims = af.sum_assured * 0.01
    _swap_into_plan(af, (pl.col("sum_assured") * 0.02).alias("lapse_reserve"))
    return af


# One mortality basis and its revision, as two right-hand tables. Same
# columns and same keys, so the only thing that differs between models
# built on them is the rates -- which is what makes the fingerprint the
# thing being tested.
_RATES_AS_PRICED = pl.DataFrame({"policy_id": [1, 2], "mortality_rate": [0.01, 0.02]})
_RATES_REVIEWED = pl.DataFrame({"policy_id": [1, 2], "mortality_rate": [0.03, 0.04]})


def _joined_model(rates: pl.DataFrame) -> ActuarialFrame:
    """Build a model whose mortality rate arrives by join rather than formula."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "sum_assured": [1.0, 2.0]}))
    return af.join(rates, on="policy_id")


def _local_fingerprint(af: ActuarialFrame, column: str) -> str | None:
    """Return the stamp on whichever node ``column``'s value comes from."""
    graph = af.graph._graph  # noqa: SLF001 -- the cached fold the stamp landed on
    return graph.nodes[af.graph.latest(column)].data.local_fingerprint


# --- precedents: what one definition read directly --------------------------


def test_precedents_names_the_definitions_a_formula_read() -> None:
    """In the order the formula names them, as node ids rather than columns."""
    af = _reassigning_model()

    assert af.graph.precedents("death_claims") == ("sum_assured", "policies_in_force@1")


def test_precedents_of_a_column_answers_for_the_live_definition() -> None:
    """A bare column name is the value the frame holds now, not its history."""
    af = _reassigning_model()

    assert af.graph.precedents("policies_in_force") == (
        "policies_in_force@1",
        "death_claims@1",
    )


def test_precedents_of_a_versioned_id_answers_for_that_definition() -> None:
    """A superseded version stays reachable by writing its ordinal out."""
    af = _reassigning_model()

    assert af.graph.precedents("policies_in_force@1") == ("mortality_rate",)


def test_precedents_of_an_arriving_column_is_empty() -> None:
    """A model-point field read nothing: it is where the model starts."""
    af = _reassigning_model()

    assert af.graph.precedents("sum_assured") == ()


def test_precedents_of_a_joined_column_is_the_key_it_was_matched_on() -> None:
    """A join key selects the row, and the row it selects is the value.

    So the key is what the joined column read: move a policy's key and its
    joined rate is another row's.
    """
    assert _joined_model(_RATES_AS_PRICED).graph.precedents("mortality_rate") == (
        "policy_id",
    )


def test_a_joined_column_reads_its_key_and_still_tracks_its_table() -> None:
    """The key is the read, and the table is the definition's own identity.

    The join is recorded as the column's own definition and that record
    carries the right-hand table's content hash, so running the same
    model against a revised table moves the column's fingerprint while
    what it reads stays the key it always was.
    """
    as_priced = _joined_model(_RATES_AS_PRICED)
    reviewed = _joined_model(_RATES_REVIEWED)
    as_priced.graph.fingerprint()
    reviewed.graph.fingerprint()

    assert as_priced.graph.precedents("mortality_rate") == ("policy_id",)
    assert reviewed.graph.precedents("mortality_rate") == ("policy_id",)
    assert _local_fingerprint(as_priced, "mortality_rate") != _local_fingerprint(
        reviewed, "mortality_rate"
    )
    assert as_priced.graph.fingerprint() != reviewed.graph.fingerprint()


# --- refusing a name the graph does not hold --------------------------------


def test_an_unknown_column_is_refused_by_name() -> None:
    """Not an empty tuple: a name this model never mentions is a mistake."""
    af = _reassigning_model()

    with pytest.raises(ValueError, match="mortality_rat") as excinfo:
        af.graph.precedents("mortality_rat")

    assert "mortality_rate" in str(excinfo.value)


def test_a_version_that_does_not_exist_names_the_ones_that_do() -> None:
    """The next move is in the message: here are this column's definitions."""
    af = _reassigning_model()

    with pytest.raises(ValueError, match="policies_in_force@7") as excinfo:
        af.graph.precedents("policies_in_force@7")

    message = str(excinfo.value)
    assert "policies_in_force@1" in message
    assert "policies_in_force@2" in message


def test_every_query_refuses_the_same_unknown_name() -> None:
    """One resolution rule, not four that drift apart."""
    af = _reassigning_model()

    for query in (
        af.graph.precedents,
        af.graph.dependents,
        af.graph.trace,
        af.graph.affected,
        af.graph.versions,
        af.graph.latest,
    ):
        with pytest.raises(ValueError, match="never_calculated"):
            query("never_calculated")


# --- dependents: who read it ------------------------------------------------


def test_dependents_names_every_definition_that_read_this_one() -> None:
    """Direct readers only, in the order the model defined them."""
    af = _reassigning_model()

    assert af.graph.dependents("policies_in_force@1") == (
        "death_claims@1",
        "policies_in_force@2",
    )


def test_dependents_of_the_live_definition_excludes_readers_of_the_old_one() -> None:
    """The whole point of one node per definition, asked from the other side."""
    af = _reassigning_model()

    assert af.graph.dependents("policies_in_force") == ()


def test_dependents_of_an_arriving_column_names_its_readers() -> None:
    """An input is read like anything else."""
    af = _reassigning_model()

    assert af.graph.dependents("sum_assured") == ("death_claims@1",)


# --- trace: the whole cone --------------------------------------------------


def test_trace_returns_the_cone_ending_with_the_node_itself() -> None:
    """Everything upstream, in the order the model built it."""
    af = _reassigning_model()

    assert af.graph.trace("policies_in_force") == (
        "sum_assured",
        "mortality_rate",
        "policies_in_force@1",
        "death_claims@1",
        "policies_in_force@2",
    )


def test_trace_stops_at_the_columns_the_data_arrived_with() -> None:
    """A leaf reads nothing, so the walk ends there."""
    af = _reassigning_model()

    assert af.graph.trace("sum_assured") == ("sum_assured",)


def test_trace_stops_at_a_column_nothing_accounts_for() -> None:
    """Where the model's account of itself ends, so does the cone."""
    af = _unaccounted_model()
    af.solvency_margin = af["lapse_reserve"] * 2.0

    assert af.graph.trace("solvency_margin") == (
        "lapse_reserve",
        "solvency_margin@1",
    )


def test_trace_runs_through_a_joined_column_to_its_key() -> None:
    """The join key selected the rate, so the derivation reaches it."""
    af = _joined_model(_RATES_AS_PRICED)
    af.death_claims = af.sum_assured * af.mortality_rate

    assert af.graph.trace("death_claims") == (
        "policy_id",
        "sum_assured",
        "mortality_rate@1",
        "death_claims@1",
    )


def test_trace_holds_each_node_once_however_many_paths_reach_it() -> None:
    """A diamond is a set, not a walk repeated per path."""
    af = _reassigning_model()
    af.net_cashflow = af.death_claims + af.policies_in_force

    assert af.graph.trace("net_cashflow").count("policies_in_force@1") == 1


# --- affected: the whole cone ahead -----------------------------------------


def test_affected_returns_the_forward_cone_starting_with_the_node_itself() -> None:
    """Everything downstream, in the order the model built it."""
    af = _reassigning_model()

    assert af.graph.affected("mortality_rate") == (
        "mortality_rate",
        "policies_in_force@1",
        "death_claims@1",
        "policies_in_force@2",
    )


def test_affected_holds_each_node_once_however_many_paths_reach_it() -> None:
    """A diamond is a set, not a walk repeated per path.

    The inforce before the decrement reaches the inforce after it twice --
    directly, and again through the claims taken off it.
    """
    af = _reassigning_model()

    assert af.graph.affected("policies_in_force@1").count("policies_in_force@2") == 1


def test_affected_of_a_column_nothing_reads_is_just_itself() -> None:
    """A leaf at the far end: nothing downstream, so the cone is the node."""
    af = _reassigning_model()

    assert af.graph.affected("policies_in_force") == ("policies_in_force@2",)


def test_affected_of_a_versioned_id_walks_that_definition_forward() -> None:
    """A superseded definition propagates through whatever read *it*."""
    af = _reassigning_model()

    assert af.graph.affected("policies_in_force@1") == (
        "policies_in_force@1",
        "death_claims@1",
        "policies_in_force@2",
    )


def test_affected_carries_past_a_replacement_written_in_terms_of_it() -> None:
    """The reassignment's blast radius runs to the outputs, not to the rewrite.

    ``af.x = f(af.x, ...)`` puts the version it replaces in the
    replacement's ``reads``, so a superseded definition reaches the
    replacement -- and through it everything the live name feeds. The
    reserve below reads only the inforce *after* the decrement, and moves
    all the same when the inforce before it moves.
    """
    af = _reassigning_model()
    af.reserve = af.policies_in_force * 500.0  # reads @2, and only @2

    assert af.graph.precedents("reserve") == ("policies_in_force@2",)
    assert af.graph.affected("policies_in_force@1") == (
        "policies_in_force@1",
        "death_claims@1",
        "policies_in_force@2",
        "reserve@1",
    )


def test_affected_stops_at_a_definition_the_replacement_did_not_read() -> None:
    """The other half: an independent rewrite ends the cone at the old node.

    A replacement written from scratch reads none of what it replaced, so
    nothing carries the old definition forward and the walk stops -- the
    case the reassignment above is routinely mistaken for.
    """
    af = ActuarialFrame(pl.DataFrame({"as_priced": [0.01], "reviewed": [0.03]}))
    af.mortality_rate = af.as_priced * 1.0
    af.mortality_rate = af.reviewed * 1.0  # the basis replaced, not adjusted
    af.death_claims = af.mortality_rate * 100_000.0

    assert af.graph.affected("mortality_rate@1") == ("mortality_rate@1",)


def test_affected_carries_past_the_readers_an_independent_rewrite_left() -> None:
    """An independent rewrite ends the name's line, not the old cone.

    The rewrite reads none of what it replaced, so nothing carries the
    basis as priced into the live name -- but whatever read it before the
    name moved on is in the cone, and so is everything past *that*. The
    margin below is three hops from that basis, never touched it, and
    moves when it moves; the rewrite itself is not in the cone at all.
    """
    af = ActuarialFrame(pl.DataFrame({"as_priced": [0.01], "reviewed": [0.03]}))
    af.mortality_rate = af.as_priced * 1.0
    af.death_claims = af.mortality_rate * 100_000.0  # read @1, before the move
    af.reserve = af.death_claims * 0.5  # one hop past that reader
    af.solvency_margin = af.reserve * 2.0  # two hops past it
    af.mortality_rate = af.reviewed * 1.0  # the basis replaced, not adjusted

    assert af.graph.precedents("solvency_margin") == ("reserve@1",)
    assert af.graph.affected("mortality_rate@1") == (
        "mortality_rate@1",
        "death_claims@1",
        "reserve@1",
        "solvency_margin@1",
    )


def test_affected_stops_at_the_version_that_stopped_reading() -> None:
    """A reassignment carries forward only as far as the reading goes.

    A third definition written from scratch ends the chain: the first
    definition reaches the second, which read it, and stops there. The
    live name and the claims the model reports out of it are the
    consequence of a basis the first definition had no part in, so
    naming them would over-count what a change to it touches.
    """
    af = ActuarialFrame(pl.DataFrame({"as_priced": [0.01], "reviewed": [0.03]}))
    af.mortality_rate = af.as_priced * 1.0  # @1
    af.mortality_rate = af.mortality_rate * 1.1  # @2, written in terms of @1
    af.mortality_rate = af.reviewed * 1.0  # @3, the basis replaced
    af.death_claims = af.mortality_rate * 100_000.0  # reads @3, the live name

    assert af.graph.precedents("mortality_rate@2") == ("mortality_rate@1",)
    assert af.graph.precedents("death_claims") == ("mortality_rate@3",)
    assert af.graph.affected("mortality_rate@1") == (
        "mortality_rate@1",
        "mortality_rate@2",
    )


def test_affected_crosses_into_the_live_name_through_an_intermediate() -> None:
    """The cone crosses a rebind whose intermediate was derived from the old version.

    ``af.account_value = af.av_after_charges`` reads the intermediate and
    not the version it replaces, so nothing connects the two definitions
    of the name directly -- and the cone crosses into the live name all
    the same, because the intermediate it rebinds was itself derived from
    the opening account value. Naming a working column and then rebinding
    the name onto it is how a charge gets deducted; the surrender value
    one hop past the live name moves when the opening value moves.
    """
    af = ActuarialFrame(pl.DataFrame({"opening_av": [1000.0], "coi_rate": [0.002]}))
    af.account_value = af.opening_av * 1.0  # @1
    af.coi_charge = af.account_value * af.coi_rate  # reads @1
    af.av_after_charges = af.account_value - af.coi_charge  # reads @1
    af.account_value = af.av_after_charges  # @2, reads the intermediate only
    af.surrender_value = af.account_value * 0.95  # reads @2, the live name

    assert af.graph.precedents("account_value@2") == ("av_after_charges@1",)
    assert af.graph.affected("account_value@1") == (
        "account_value@1",
        "coi_charge@1",
        "av_after_charges@1",
        "account_value@2",
        "surrender_value@1",
    )


def test_affected_reaches_a_version_that_read_only_the_intermediate() -> None:
    """A later version is reached through the reads, not along the name.

    The third definition reads neither of the two before it -- it takes
    the blended rate, which was derived from the first. The cone holds it
    and the claims past it anyway. Which version a definition happens to
    follow decides nothing here; the reads path does.
    """
    af = ActuarialFrame(pl.DataFrame({"as_priced": [0.01], "margin": [1.1]}))
    af.mortality_rate = af.as_priced * 1.0  # @1
    af.blended_rate = af.mortality_rate * 0.5  # reads @1
    af.mortality_rate = af.mortality_rate * af.margin  # @2, reads @1
    af.mortality_rate = af.blended_rate * 1.0  # @3, reads the intermediate only
    af.death_claims = af.mortality_rate * 100_000.0  # reads @3

    assert af.graph.precedents("mortality_rate@3") == ("blended_rate@1",)
    assert af.graph.affected("mortality_rate@1") == (
        "mortality_rate@1",
        "blended_rate@1",
        "mortality_rate@2",
        "mortality_rate@3",
        "death_claims@1",
    )


def test_affected_stops_where_the_intermediate_was_rebound_from_elsewhere() -> None:
    """A rebind reads the definition the name holds by then, not the one that read it.

    The negative counterpart of the bridge above, and the same two lines
    in the same order: a working column derived from the account value,
    then the balance rebound onto that name. In between, the working
    column is written afresh from the statutory-floor column and reads
    nothing of the definition it replaces, so the rebind reads that new
    definition and not the one that read the opening account value. No
    path was laid. The opening value genuinely does not reach the
    surrender value here -- the read the rebind makes of the working
    column carries none of it -- and the cone says so by stopping at the
    definition the rewrite replaced.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "opening_av": [1000.0],
                "coi_charge_in": [5.0],
                "statutory_floor": [900.0],
            }
        )
    )
    af.account_value = af.opening_av * 1.0  # @1
    af.av_after_charges = af.account_value - af.coi_charge_in  # @1, reads av@1
    af.av_after_charges = af.statutory_floor * 1.0  # @2, written afresh
    af.account_value = af.av_after_charges  # @2, reads that new definition
    af.surrender_value = af.account_value * 0.95  # reads av@2, the live name

    assert af.graph.precedents("av_after_charges@2") == ("statutory_floor",)
    assert af.graph.precedents("account_value@2") == ("av_after_charges@2",)
    assert af.graph.affected("account_value@1") == (
        "account_value@1",
        "av_after_charges@1",
    )


def test_affected_crosses_a_rewrite_that_read_the_balance_further_back() -> None:
    """The cone crosses a replacement that reads back to the definition asked about.

    A working column derived from the account value, rewritten afresh
    from a statutory floor, then the balance rebound onto it. The two
    relations the stopping case above asserts hold here too: the rewrite
    names no version of the definition it replaces, and the rebind reads
    only that new definition. What differs is the floor's own version --
    struck off the working column rather than arriving with the data, so
    the rewrite reads ``statutory_floor@1`` where the stopping case read
    the arriving column, and the third assert pins that definition's own
    read. The opening account value reaches the surrender value all the
    same, because the floor the rewrite reads was itself derived from
    the value it is flooring.

    Judged on the read at the head of the replacement rather than on
    everything behind it, this model reads as severed at
    ``av_after_charges@1``, and a cone stopping there loses the four
    nodes the last assert lists past it.
    """
    af = ActuarialFrame(pl.DataFrame({"opening_av": [1000.0], "coi_rate": [0.002]}))
    af.account_value = af.opening_av * 1.0  # @1
    af.coi_charge = af.account_value * af.coi_rate  # reads av@1
    af.av_after_charges = af.account_value - af.coi_charge  # @1, reads av@1
    af.statutory_floor = af.av_after_charges * 0.9  # struck off the working column
    af.av_after_charges = af.statutory_floor * 1.0  # @2, written afresh
    af.account_value = af.av_after_charges  # @2, reads that new definition
    af.surrender_value = af.account_value * 0.95  # reads av@2

    assert af.graph.precedents("av_after_charges@2") == ("statutory_floor@1",)
    assert af.graph.precedents("account_value@2") == ("av_after_charges@2",)
    assert af.graph.precedents("statutory_floor@1") == ("av_after_charges@1",)
    assert af.graph.affected("account_value@1") == (
        "account_value@1",
        "coi_charge@1",
        "av_after_charges@1",
        "statutory_floor@1",
        "av_after_charges@2",
        "account_value@2",
        "surrender_value@1",
    )


def test_affected_runs_through_a_rebind_one_of_whose_reads_was_severed() -> None:
    """A severed read stops its own path and decides nothing about the others.

    The rewritten shape above with one more term on the rebind, which is
    the ordinary one: the balance is restated as the rewritten working
    column less a charge that was itself struck off the opening account
    value. The rewrite still severs the working column's path -- the
    rebind reads that new definition, not the one that read the opening
    value -- and the charge is a path the rewrite never touched, so the
    opening value reaches the surrender value after all. Reading the negative
    case over the name instead of over the path would drop the rebind and
    the surrender value past it, and under-count what a change to the
    opening value moves.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "opening_av": [1000.0],
                "coi_rate": [0.002],
                "statutory_floor": [900.0],
            }
        )
    )
    af.account_value = af.opening_av * 1.0  # @1
    af.coi_charge = af.account_value * af.coi_rate  # reads av@1
    af.av_after_charges = af.account_value - af.coi_charge  # @1, reads av@1
    af.av_after_charges = af.statutory_floor * 1.0  # @2, written afresh
    af.account_value = af.av_after_charges - af.coi_charge  # @2, two reads
    af.surrender_value = af.account_value * 0.95  # reads av@2

    assert af.graph.precedents("av_after_charges@2") == ("statutory_floor",)
    assert af.graph.precedents("account_value@2") == (
        "av_after_charges@2",
        "coi_charge@1",
    )
    assert af.graph.affected("account_value@1") == (
        "account_value@1",
        "coi_charge@1",
        "av_after_charges@1",
        "account_value@2",
        "surrender_value@1",
    )


def test_affected_holds_a_later_version_over_versions_it_does_not_hold() -> None:
    """Cone membership over one name is not contiguous, and need not be.

    Name the charge, restate the balance from an independent source, roll
    it forward, then apply the charge. The fourth definition reads the
    third -- which the cone does not hold -- and the charge, which it
    does, and one reads path is all it takes. So the cone holds ``@1``
    and ``@4`` and skips ``@2`` and ``@3`` entirely: a change to the
    opening value moves the surrender value across two definitions that
    had nothing to do with it. Neither adjacency direction survives this
    shape, which is why the cone is stated over reads and not over the
    run of versions.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "opening_av": [1000.0],
                "coi_rate": [0.002],
                "restated_av": [1100.0],
                "growth": [0.04],
            }
        )
    )
    af.account_value = af.opening_av * 1.0  # @1
    af.coi_charge = af.account_value * af.coi_rate  # reads @1
    af.account_value = af.restated_av * 1.0  # @2, independent of @1
    af.account_value = af.account_value * (1.0 + af.growth)  # @3, reads @2 only
    af.account_value = af.account_value - af.coi_charge  # @4, reads @3 and the charge
    af.surrender_value = af.account_value * 0.95  # reads @4

    assert af.graph.precedents("account_value@3") == ("account_value@2", "growth")
    assert af.graph.precedents("account_value@4") == ("account_value@3", "coi_charge@1")
    assert af.graph.affected("account_value@1") == (
        "account_value@1",
        "coi_charge@1",
        "account_value@4",
        "surrender_value@1",
    )


def test_affected_stops_where_the_model_stops_reading() -> None:
    """A column nothing accounts for still propagates into what reads it."""
    af = _unaccounted_model()
    af.solvency_margin = af["lapse_reserve"] * 2.0

    assert af.graph.affected("lapse_reserve") == (
        "lapse_reserve",
        "solvency_margin@1",
    )


def test_affected_and_trace_are_one_edge_walked_from_the_two_ends() -> None:
    """The mirror pinned, over every node id in one model that names itself.

    ``b`` is affected by ``a`` exactly when ``a`` traces behind ``b``.

    Stated over ids whose resolution is the identity, which is the shape
    this model has. Both questions resolve a bare name to the live
    definition, so a column that arrives in the data and is later
    redefined has a node id that answers for the redefinition instead of
    for itself -- an asymmetry of the resolution, shared by every question
    on this accessor, not of the two walks. The assertion below says the
    model holds no such id rather than leaving it to be assumed.
    """
    af = _reassigning_model()
    af.net_cashflow = af.death_claims + af.policies_in_force
    nodes = af.graph._graph.nodes  # noqa: SLF001 -- every node, the ids included

    assert all(af.graph._resolve(n) == n for n in nodes)  # noqa: SLF001

    forward = {(a, b) for a in nodes for b in af.graph.affected(a)}
    backward = {(a, b) for b in nodes for a in af.graph.trace(b)}

    assert forward == backward


# --- versions and latest ----------------------------------------------------


def test_versions_lists_every_definition_oldest_first() -> None:
    """The model's own history of one name."""
    af = _reassigning_model()

    assert af.graph.versions("policies_in_force") == (
        "policies_in_force@1",
        "policies_in_force@2",
    )


def test_versions_of_an_arriving_column_is_empty() -> None:
    """Nothing on the frame defined it -- which is what makes it an input."""
    af = _reassigning_model()

    assert af.graph.versions("sum_assured") == ()


def test_latest_is_the_node_the_column_holds_now() -> None:
    """The last definition of a column something defined."""
    af = _reassigning_model()

    assert af.graph.latest("policies_in_force") == "policies_in_force@2"


def test_latest_of_an_arriving_column_is_the_arriving_node() -> None:
    """Unversioned, because nothing defined it."""
    af = _reassigning_model()

    assert af.graph.latest("sum_assured") == "sum_assured"


def test_a_dropped_calculation_stays_in_the_models_history() -> None:
    """Dropping a column does not unmake the calculation that produced it.

    An intermediate dropped before the results are written was still
    computed, and a graph that forgot it could not answer where an
    earlier number came from. So the name still resolves. Whether the
    frame still *holds* the value is the node's own question, and it
    answers it: this definition is no longer in the final schema.
    """
    af = _reassigning_model()
    af.drop("death_claims")

    assert af.graph.latest("death_claims") == "death_claims@1"
    assert af.graph.versions("death_claims") == ("death_claims@1",)
    graph = af.graph._graph  # noqa: SLF001 -- the cached fold under test
    assert graph.nodes["death_claims@1"].data.in_final_schema is False


# --- holes ------------------------------------------------------------------


def test_holes_reports_the_column_nothing_accounts_for() -> None:
    """The one artifact whose job is to say how each number was made."""
    af = _unaccounted_model()

    assert [hole.column for hole in af.graph.holes()] == ["lapse_reserve"]


def test_holes_is_empty_for_a_model_built_through_the_frames_own_doors() -> None:
    """The empty list is the claim, not a default."""
    assert _reassigning_model().graph.holes() == []


# --- fingerprint ------------------------------------------------------------


def test_fingerprint_returns_the_frameworks_own_stamp_shape() -> None:
    """The same ``sha256:<hex>`` every other stamp in the audit chain takes."""
    fingerprint = _reassigning_model().graph.fingerprint()

    assert fingerprint.startswith(SHA256_PREFIX)
    assert len(fingerprint) == len(SHA256_PREFIX) + 64


def test_fingerprint_stamps_every_node_on_the_way() -> None:
    """Unstamped until asked: folding should not pay to hash."""
    af = _reassigning_model()
    graph = af.graph._graph  # noqa: SLF001 -- the cache under test

    assert all(node.data.fingerprint is None for node in graph.nodes.values())

    af.graph.fingerprint()

    assert all(node.data.fingerprint is not None for node in graph.nodes.values())
    assert all(node.data.local_fingerprint is not None for node in graph.nodes.values())


def test_the_same_model_fingerprints_the_same_twice() -> None:
    """A digest that moved on its own would say nothing when it moved."""
    af = _reassigning_model()

    assert af.graph.fingerprint() == af.graph.fingerprint()


def test_a_changed_formula_moves_the_fingerprint() -> None:
    """Which is the whole question the digest answers."""
    before = _reassigning_model().graph.fingerprint()

    af = _reassigning_model()
    af.death_claims = af.sum_assured * af.policies_in_force * 0.5

    assert af.graph.fingerprint() != before


# --- the cache: one fold per state of the frame -----------------------------


def test_repeated_queries_fold_the_log_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fold is the expensive half; asking it four questions is not."""
    af = _reassigning_model()
    folds: list[ActuarialFrame] = []
    real_fold = calc_graph_module.fold

    def counting_fold(frame: ActuarialFrame, *, refuse_unnamed: bool) -> object:
        folds.append(frame)
        return real_fold(frame, refuse_unnamed=refuse_unnamed)

    monkeypatch.setattr(calc_graph_module, "fold", counting_fold)

    af.graph.precedents("death_claims")
    af.graph.dependents("sum_assured")
    af.graph.trace("policies_in_force")
    af.graph.affected("mortality_rate")
    af.graph.holes()

    assert len(folds) == 1


def test_a_new_assignment_is_visible_to_the_next_query() -> None:
    """The log grew, so the cached answer is history."""
    af = _reassigning_model()
    assert af.graph.versions("policies_in_force") == (
        "policies_in_force@1",
        "policies_in_force@2",
    )

    af.policies_in_force = af.policies_in_force * 0.9

    assert af.graph.versions("policies_in_force") == (
        "policies_in_force@1",
        "policies_in_force@2",
        "policies_in_force@3",
    )


def test_a_dropped_column_is_visible_to_the_next_query() -> None:
    """A drop appends nothing to the log and still changes every answer.

    The column that nothing accounted for is gone from the schema, so the
    model has nothing left to explain -- and a cache keyed on the log
    alone would still be reporting the hole.
    """
    af = _unaccounted_model()
    assert [hole.column for hole in af.graph.holes()] == ["lapse_reserve"]

    af.drop("lapse_reserve")

    assert af.graph.holes() == []


def test_a_plan_written_directly_is_visible_to_the_next_query() -> None:
    """The other half of the same gap: a column appears, nothing is logged."""
    af = _reassigning_model()
    assert af.graph.holes() == []

    _swap_into_plan(af, (pl.col("sum_assured") * 0.02).alias("lapse_reserve"))

    assert [hole.column for hole in af.graph.holes()] == ["lapse_reserve"]


def test_a_derived_frame_answers_for_itself() -> None:
    """A scenario axis is the same model one step on, with its own columns."""
    af = _reassigning_model()
    af.graph.trace("death_claims")

    wide = with_scenarios(af, ["BASE", "UP"])

    assert wide.graph is not af.graph
    # Versioned, because the cross-join records the axis as the column it
    # handed the model rather than letting it pass as an arrival.
    assert wide.graph.latest("scenario_id") == "scenario_id@1"
    with pytest.raises(ValueError, match="scenario_id"):
        af.graph.latest("scenario_id")


def test_the_accessor_is_the_same_object_each_time() -> None:
    """Otherwise the cache would be rebuilt on every attribute access."""
    af = _reassigning_model()

    assert af.graph is af.graph


# --- structure only ---------------------------------------------------------


def test_no_query_collects_the_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reading how a model is built must never run it."""
    af = _unaccounted_model()

    def refuse_to_collect(*_args: object, **_kwargs: object) -> object:
        msg = "a graph query collected the frame"
        raise AssertionError(msg)

    monkeypatch.setattr(pl.LazyFrame, "collect", refuse_to_collect)

    assert af.graph.precedents("death_claims") == ("sum_assured",)
    assert af.graph.dependents("sum_assured") == ("death_claims@1",)
    assert af.graph.trace("death_claims") == ("sum_assured", "death_claims@1")
    assert af.graph.affected("sum_assured") == ("sum_assured", "death_claims@1")
    assert af.graph.versions("death_claims") == ("death_claims@1",)
    assert af.graph.latest("death_claims") == "death_claims@1"
    assert [hole.column for hole in af.graph.holes()] == ["lapse_reserve"]
    assert af.graph.tiers().counts == {"core": 1, "engine_native": 0, "opaque": 0}
    assert af.graph.fingerprint().startswith(SHA256_PREFIX)


# --- what the CLI prints ----------------------------------------------------


def test_the_node_line_accounts_for_every_node() -> None:
    """A breakdown that does not add up is a graph nobody can read."""
    nodes = [
        {"kind": "input"},
        {"kind": "input"},
        {"kind": "computed"},
        {"kind": "hole"},
    ]

    assert node_accounting(nodes) == "4 nodes: 2 inputs, 1 computed, 1 unaccounted for"


def test_the_node_line_states_a_clean_model_positively() -> None:
    """Nothing unaccounted for is a claim worth printing, not an absence."""
    nodes = [{"kind": "input"}, {"kind": "computed"}]

    assert node_accounting(nodes) == "2 nodes: 1 input, 1 computed, 0 unaccounted for"


def test_the_node_line_names_a_compiled_rollforward_and_its_running_states() -> None:
    """A state machine's nodes are counted too, so the parts still add up.

    Neither is an account of a column, and a model that never escalated to
    a state machine has neither, so they are named only where there are any.
    """
    nodes = [
        {"kind": "input"},
        {"kind": "computed"},
        {"kind": "rollforward"},
        {"kind": "state"},
        {"kind": "state"},
    ]

    assert node_accounting(nodes) == (
        "5 nodes: 1 input, 1 computed, 1 compiled rollforward, "
        "2 running states, 0 unaccounted for"
    )


def test_the_node_line_counts_every_compiled_rollforward() -> None:
    """Two compilations are two nodes, and the line says so in the plural."""
    nodes = [{"kind": "rollforward"}, {"kind": "rollforward"}, {"kind": "state"}]

    assert node_accounting(nodes) == (
        "3 nodes: 0 inputs, 0 computed, 2 compiled rollforwards, "
        "1 running state, 0 unaccounted for"
    )


def test_the_node_line_has_words_for_every_kind_the_format_defines() -> None:
    """A kind added to the format is named on the line before it can be counted."""
    assert {kind for kind, *_ in _NODE_LINE} == set(NodeType)


def test_the_node_line_refuses_a_kind_the_format_does_not_define() -> None:
    """A node it cannot place would leave the parts short of the total."""
    nodes = [{"id": "death_claims@1", "kind": "computed"}, {"id": "x", "kind": "misc"}]

    with pytest.raises(ValueError, match=r"'x'.*'misc'.*gspio validate"):
        node_accounting(nodes)


# --- a column that is a running balance materialised ------------------------


def _the_ratchet_model() -> ActuarialFrame:
    """Build a GMDB whose benefit base ratchets to the fund's high-water mark.

    The guarantee reads the fund's end-of-period balance inside the
    recursion rather than off the frame, so nothing on the frame reads the
    ``fund`` column at all. That is what made it the model the two forward
    questions answered wrongly: the honest answer to "if this fund moves,
    what moves with it?" is the guarantee, and an edge walk from the column
    could not reach it.
    """
    af = ActuarialFrame(
        {
            "fund_init": [100_000.0],
            "gmdb_init": [100_000.0],
            "fund_return": [[0.008] * 24],
            "anniversary": [[(period + 1) % 12 == 0 for period in range(24)]],
        }
    )
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=24, frequency="monthly"
    )
    builder = af.projection.rollforward(
        states={"account_value": af["fund_init"], "benefit_base": af["gmdb_init"]}
    )
    builder["account_value"].grow(af["fund_return"], label="fund_growth")
    builder["benefit_base"].ratchet(
        to=pl.col("account_value@eop"),
        when=af["anniversary"],
        label="gmdb_ratchet",
    )
    compiled = compile_rollforward(builder)
    af.fund = compiled.expr_for("account_value")
    af.gmdb = compiled.expr_for("benefit_base")
    return af


def test_affected_of_a_materialised_balance_reaches_the_guarantee() -> None:
    """Move the fund and the benefit base struck against it moves with it."""
    af = _the_ratchet_model()
    (compilation,) = af.graph.precedents("fund")

    assert af.graph.affected("fund") == (
        "state:account_value@eop",
        compilation,
        "fund@1",
        "gmdb@1",
    )


def test_dependents_of_a_materialised_balance_reaches_the_state_machine() -> None:
    """One hop from the balance is what reads it, which is the compilation.

    The one-hop arrow answered nothing at all before: the compilation reads
    the *state*, so a column with no reader of its own had none to report.
    It reports the state's reader now, and the cone above carries that on
    to the guarantee.
    """
    af = _the_ratchet_model()
    (compilation,) = af.graph.precedents("fund")

    assert af.graph.dependents("fund") == (compilation,)


def test_the_forward_questions_asked_of_the_state_itself_are_unchanged() -> None:
    """A state id resolves to a node carrying no extraction, so nothing moves.

    The column is asked with the state; the state is asked as it always
    was, and the two answers agree because they are the same walk opened at
    the same places.
    """
    af = _the_ratchet_model()
    (compilation,) = af.graph.precedents("fund")

    assert af.graph.dependents("state:account_value@eop") == (compilation,)
    assert af.graph.affected("state:account_value@eop") == af.graph.affected("fund")


def test_the_forward_questions_of_a_plain_column_are_unchanged() -> None:
    """A column beside a compilation that extracts none of it answers as before.

    Asked in the model that has a state machine in it, because "unchanged"
    is only worth pinning where the change had somewhere to leak into.
    """
    af = _the_ratchet_model()
    (compilation,) = af.graph.precedents("fund")

    assert af.graph.dependents("fund_return") == (compilation,)
    assert af.graph.affected("fund_return") == (
        "fund_return",
        compilation,
        "fund@1",
        "gmdb@1",
    )
    assert af.graph.dependents("month") == ()
    assert af.graph.affected("month") == ("month@1",)


def test_the_backward_questions_are_untouched_by_the_pairing() -> None:
    """A derivation walk already arrived at the state and needed no rule.

    The column reads its compilation and the compilation reads its states,
    so ``precedents`` and ``trace`` reach the balance along edges that were
    always there. The mirror ``affected``/``trace`` holds elsewhere is
    deliberately not a mirror here: the forward walk opens at a node the
    backward walk reaches one hop further down.
    """
    af = _the_ratchet_model()
    (compilation,) = af.graph.precedents("fund")

    assert af.graph.precedents("fund") == (compilation,)
    assert af.graph.trace("fund") == (
        "fund_init",
        "gmdb_init",
        "fund_return",
        "anniversary",
        "state:account_value@eop",
        "state:benefit_base@eop",
        compilation,
        "fund@1",
    )


def test_a_balance_no_operation_consulted_has_no_node_to_open_at() -> None:
    """A state the graph minted no node for is dropped rather than answered for.

    ``states`` names every balance a compilation declares; the graph mints a
    node for the ones an operation actually consults. A fund topped up by a
    premium and never read is one of the second kind, so the column states
    the balance it materialises and the forward walk has nowhere further to
    open.
    """
    af = ActuarialFrame({"av_init": [100.0], "premium": [[10.0] * 6]})
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=6, frequency="monthly"
    )
    builder = af.projection.rollforward(states={"fund_value": af["av_init"]})
    builder["fund_value"].add(af["premium"], label="premium")
    af.fund = compile_rollforward(builder).expr_for("fund_value")
    stated = af.graph._graph.nodes["fund@1"].data.extracts  # noqa: SLF001 -- the record

    assert stated is not None
    assert [one.state for one in stated] == ["fund_value@eop"]
    assert "state:fund_value@eop" not in af.graph._graph.nodes  # noqa: SLF001
    assert af.graph.affected("fund") == ("fund@1",)
    assert af.graph.dependents("fund") == ()
