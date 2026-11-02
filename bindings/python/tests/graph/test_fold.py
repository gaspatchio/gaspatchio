# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Folding the durable calculation log into the graph: one node per definition.

Models reassign. ``af.policies_in_force`` gets written once before the
maturity test and once after it, and those two lines are two different
worksheet columns wearing one Python name. The fold recovers them: every
record in the log mints its own node -- ``column@ordinal`` -- and every
column reference inside that record's formula binds to whichever definition
was live at the moment the line ran, *before* the line's own result
replaces it.

Bind first, advance after. That ordering is the whole mechanism, and it is
what makes the reassignment above read the pre-maturity inforce and publish
the post-maturity one: a self-reference becomes a plain edge between two
nodes rather than a cycle, and every column written afterwards reads the
version that was genuinely in the frame when it ran.

The columns the frame arrived with are the graph's inputs and carry no
version -- nothing on the frame defines them. A column that was recorded
but is not what the frame's column holds at the end (a superseded
definition, or one dropped before the model finished) says so rather than
claiming to be the answer.
"""

from __future__ import annotations

import datetime
import graphlib
import json

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph.calc_graph import GraphExporter
from gaspatchio.frame.graph.graph_builder import CalcGraph, _kernel_column, fold
from gaspatchio.frame.graph.graph_models import NodeType
from gaspatchio.scenarios import with_scenarios
from gaspatchio.schedule import Schedule

# --- helpers ----------------------------------------------------------------


def _reads(graph: CalcGraph, node_id: str) -> tuple[str, ...]:
    """Return the node ids one node binds its column references to."""
    return graph.nodes[node_id].data.reads


def _computed_ids(graph: CalcGraph) -> list[str]:
    """Return every computed node's id, in the order the log defined them."""
    return [node.id for node in graph.nodes.values() if node.kind is NodeType.COMPUTED]


def _input_ids(graph: CalcGraph) -> set[str]:
    """Return every input node's id."""
    return {node.id for node in graph.nodes.values() if node.kind is NodeType.INPUT}


def _ordered_input_ids(graph: CalcGraph) -> list[str]:
    """Return every input node's id, in the order the graph holds them."""
    return [node.id for node in graph.nodes.values() if node.kind is NodeType.INPUT]


def _exported(af: ActuarialFrame) -> dict[str, dict[str, object]]:
    """Export the frame's graph against its own collected values, by node id."""
    artifact = json.loads(GraphExporter(af).export(af.collect()))
    return {node["id"]: node for node in artifact["nodes"]}


def _maturity_zeroing_frame() -> ActuarialFrame:
    """Build the taught reassignment pattern: inforce, then inforce zeroed at maturity.

    Four assignments over five arriving columns. ``policies_in_force`` is
    written twice -- the second time reading itself -- with a claim column
    in between that must keep reading the first version and a payout column
    after it that must read the second.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "surviving_policies": [1.0, 1.0],
                "mortality_rate": [0.01, 0.02],
                "sum_assured": [100_000.0, 250_000.0],
                "policy_term": [10, 20],
                "month": [0, 240],
            }
        )
    )
    af.policies_in_force = af.surviving_policies * 1.0
    af.death_claims = af.policies_in_force * af.mortality_rate
    af.policies_in_force = (
        when(af.month < af.policy_term * 12).then(af.policies_in_force).otherwise(0.0)
    )
    af.expected_payout = af.policies_in_force * af.sum_assured
    return af


# --- one node per definition ------------------------------------------------


def test_every_assignment_mints_its_own_node() -> None:
    """Four assignments, four nodes -- the reassignment does not overwrite a node."""
    graph = fold(_maturity_zeroing_frame())

    assert _computed_ids(graph) == [
        "policies_in_force@1",
        "death_claims@1",
        "policies_in_force@2",
        "expected_payout@1",
    ]


def test_the_columns_the_frame_arrived_with_are_its_inputs() -> None:
    """Nothing on the frame defines a model-point column, so it carries no version."""
    graph = fold(_maturity_zeroing_frame())

    assert _input_ids(graph) == {
        "surviving_policies",
        "mortality_rate",
        "sum_assured",
        "policy_term",
        "month",
    }


def test_each_node_binds_to_the_version_that_was_live_when_it_ran() -> None:
    """The reads table for the reassignment pattern, line by line.

    ``death_claims`` sits between the two writes of ``policies_in_force``
    and reads the *pre*-zeroing inforce; ``expected_payout`` sits after
    both and reads the *post*-zeroing one. The reassignment itself binds
    its own name to the version it is about to replace.
    """
    graph = fold(_maturity_zeroing_frame())

    assert _reads(graph, "policies_in_force@1") == ("surviving_policies",)
    assert _reads(graph, "death_claims@1") == (
        "policies_in_force@1",
        "mortality_rate",
    )
    assert _reads(graph, "policies_in_force@2") == (
        "month",
        "policy_term",
        "policies_in_force@1",
    )
    assert _reads(graph, "expected_payout@1") == (
        "policies_in_force@2",
        "sum_assured",
    )


def test_the_edges_say_the_same_thing_the_reads_do() -> None:
    """Every read is an edge from the version read to the node that read it."""
    graph = fold(_maturity_zeroing_frame())

    edges = {(edge.source, edge.target) for edge in graph.edges}
    assert ("policies_in_force@1", "policies_in_force@2") in edges
    assert ("policies_in_force@1", "death_claims@1") in edges
    assert ("policies_in_force@2", "expected_payout@1") in edges
    assert ("policies_in_force@2", "death_claims@1") not in edges


# --- acyclicity -------------------------------------------------------------


def test_a_self_referential_assignment_leaves_the_graph_acyclic() -> None:
    """Versions are what make ``x = f(x)`` sortable rather than circular."""
    graph = fold(_maturity_zeroing_frame())

    sorter = graphlib.TopologicalSorter(
        {node_id: set(node.data.reads) for node_id, node in graph.nodes.items()}
    )
    ordered = list(sorter.static_order())

    assert len(ordered) == len(graph.nodes)


def test_a_column_name_that_claims_another_columns_version_is_refused() -> None:
    """One id means one thing, and a name that collides with one is named, not merged.

    A column may legally be called ``reserve@1``, which is the id the first
    write of ``reserve`` needs. Silently taking it would drop a node and
    hand its edges to whichever survived.
    """
    af = ActuarialFrame(pl.DataFrame({"reserve@1": [1.0], "reserve": [2.0]}))
    af.reserve = af["reserve"] * 2.0

    with pytest.raises(ValueError, match="reserve@1"):
        fold(af)


def test_no_node_reads_itself() -> None:
    """A column reference always resolves to a definition that predates it."""
    graph = fold(_maturity_zeroing_frame())

    assert [
        node_id for node_id, node in graph.nodes.items() if node_id in node.data.reads
    ] == []


# --- versions ---------------------------------------------------------------


def test_versions_recovers_the_worksheet_columns_one_name_collapsed() -> None:
    """Two writes of one name are two columns; the history keeps both."""
    graph = fold(_maturity_zeroing_frame())

    assert graph.versions("policies_in_force") == (
        "policies_in_force@1",
        "policies_in_force@2",
    )
    assert graph.latest("policies_in_force") == "policies_in_force@2"


def test_an_input_the_model_never_wrote_has_no_versions_but_is_still_the_latest() -> (
    None
):
    """The arriving column IS the answer for a name nothing recalculated."""
    graph = fold(_maturity_zeroing_frame())

    assert graph.versions("mortality_rate") == ()
    assert graph.latest("mortality_rate") == "mortality_rate"


def test_a_name_the_model_never_mentions_has_neither() -> None:
    """Asking about a column that is not there answers nothing, not a guess."""
    graph = fold(_maturity_zeroing_frame())

    assert graph.versions("lapse_rate") == ()
    assert graph.latest("lapse_rate") is None


def test_reassigning_an_arriving_column_keeps_the_arrival_as_its_own_node() -> None:
    """The value that arrived and the value that replaced it are two things."""
    af = ActuarialFrame(pl.DataFrame({"annual_premium": [1200.0, 2400.0]}))
    af.annual_premium = af.annual_premium * 1.1

    graph = fold(af)

    assert graph.nodes["annual_premium"].kind is NodeType.INPUT
    assert _reads(graph, "annual_premium@1") == ("annual_premium",)
    assert graph.nodes["annual_premium"].data.in_final_schema is False
    assert graph.nodes["annual_premium@1"].data.in_final_schema is True


# --- what the frame actually holds at the end -------------------------------


def test_a_superseded_definition_is_not_what_the_frame_holds() -> None:
    """Only the last write of a name survives into the collected frame."""
    graph = fold(_maturity_zeroing_frame())

    assert graph.nodes["policies_in_force@1"].data.in_final_schema is False
    assert graph.nodes["policies_in_force@2"].data.in_final_schema is True
    assert graph.nodes["death_claims@1"].data.in_final_schema is True


def test_a_column_computed_and_then_dropped_stays_in_the_history() -> None:
    """Dropping a column removes it from the frame, never from what was done."""
    af = ActuarialFrame(pl.DataFrame({"annual_premium": [1200.0, 2400.0]}))
    af.monthly_premium = af.annual_premium / 12
    af.rounding_scratch = af.monthly_premium * 0.0
    af = af.drop("rounding_scratch")

    graph = fold(af)

    assert graph.nodes["rounding_scratch@1"].data.in_final_schema is False
    assert graph.nodes["monthly_premium@1"].data.in_final_schema is True


# --- batches ----------------------------------------------------------------


def test_batch_siblings_bind_to_the_versions_that_predate_the_batch() -> None:
    """One ``with_columns`` call is one step: every sibling sees the pre-batch frame.

    ``second`` names ``first`` in the same call that rewrites ``first``.
    Polars hands it the value ``first`` held *before* the call, so the
    graph binds it to that version and not to the sibling being written
    alongside it.
    """
    af = ActuarialFrame(pl.DataFrame({"base": [10.0, 20.0]}))
    af.first = af.base * 2.0

    af = af.with_columns(
        (pl.col("base") * 3.0).alias("first"),
        (pl.col("first") * 10.0).alias("second"),
    )

    graph = fold(af)
    assert _reads(graph, "first@2") == ("base",)
    assert _reads(graph, "second@1") == ("first@1",)


def test_two_consecutive_single_column_calls_see_sequential_state() -> None:
    """Adjacency is not membership: two calls are two steps, whatever their order.

    The same two expressions as the batch above, split across two calls.
    ``second`` now genuinely runs after ``first`` was rewritten, so it
    binds to the rewrite -- the opposite answer from the batch, decided by
    the operation each record declares rather than by how close together
    they landed in the log.
    """
    af = ActuarialFrame(pl.DataFrame({"base": [10.0, 20.0]}))
    af.first = af.base * 2.0

    af = af.with_columns((pl.col("base") * 3.0).alias("first"))
    af = af.with_columns((pl.col("first") * 10.0).alias("second"))

    graph = fold(af)
    assert _reads(graph, "first@2") == ("base",)
    assert _reads(graph, "second@1") == ("first@2",)


# --- the records no assignment wrote ----------------------------------------


def test_a_rename_carries_the_vendor_name_forward_as_lineage() -> None:
    """The name the data arrived under is the new name's one dependency."""
    af = ActuarialFrame(pl.DataFrame({"Issue Age": [30, 45]}))
    af = af.rename({"Issue Age": "issue_age"})
    af.attained_age = af.issue_age + 1

    graph = fold(af)

    assert graph.nodes["Issue Age"].kind is NodeType.INPUT
    assert _reads(graph, "issue_age@1") == ("Issue Age",)
    assert _reads(graph, "attained_age@1") == ("issue_age@1",)


def test_a_joined_column_reads_the_key_it_was_matched_on() -> None:
    """No expression computed it, and the key it was matched on decided it."""
    af = ActuarialFrame(
        pl.DataFrame({"product_code": ["TERM"], "annual_premium": [1200.0]})
    )
    af = af.join(
        pl.DataFrame({"product_code": ["TERM"], "expense_loading": [0.05]}),
        on="product_code",
    )
    af.expenses = af.annual_premium * af.expense_loading

    graph = fold(af)

    assert _reads(graph, "expense_loading@1") == ("product_code",)
    assert _reads(graph, "expenses@1") == ("annual_premium", "expense_loading@1")


def test_an_injected_series_is_data_and_reads_nothing() -> None:
    """A column of values handed over wholesale derives from no other column."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2, 3]}))

    af = af.with_columns(pl.Series("simulated_deaths", [0, 1, 0]))

    graph = fold(af)
    assert _reads(graph, "simulated_deaths@1") == ()


def test_a_materialization_defines_no_column_and_mints_no_node() -> None:
    """Freezing the plan is an event in the log, not a calculation in the graph."""
    af = ActuarialFrame(pl.DataFrame({"annual_premium": [1200.0, 2400.0]}))
    af.monthly_premium = af.annual_premium / 12
    af = af.materialize()
    af.quarterly_premium = af.monthly_premium * 3

    graph = fold(af)

    assert _computed_ids(graph) == ["monthly_premium@1", "quarterly_premium@1"]
    assert _reads(graph, "quarterly_premium@1") == ("monthly_premium@1",)
    assert [boundary.position for boundary in graph.boundaries] == [1]


def test_a_carried_log_naming_a_column_the_new_frame_lacks_still_folds() -> None:
    """A widened frame rebuilds its inputs from the schema it can actually see.

    A vendor column renamed away before the scenario axis is gone from that
    schema and is not itself a recorded calculation, so nothing on the
    widened frame accounts for the name the rename record still names. The
    fold answers with an input node rather than failing: that column
    genuinely was an input to this model, one step back.
    """
    af = ActuarialFrame(pl.DataFrame({"Issue Age": [30, 45]}))
    af = af.rename({"Issue Age": "issue_age"})
    af = with_scenarios(af, ["BASE", "UP"])
    af.attained_age = af.issue_age + 1

    graph = fold(af)

    assert graph.nodes["Issue Age"].kind is NodeType.INPUT
    assert graph.nodes["Issue Age"].data.in_final_schema is False
    assert _reads(graph, "issue_age@1") == ("Issue Age",)
    assert _reads(graph, "attained_age@1") == ("issue_age@1",)


# --- the projection timeline ------------------------------------------------


def _projected() -> ActuarialFrame:
    """Stamp a shared two-year annual timeline on a two-policy frame."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "issue_age": [30, 45]}))
    return af.projection.set(
        valuation_date=datetime.date(2026, 1, 1),
        until="term_years",
        until_value=2,
        frequency="annual",
    )


def test_the_stamped_period_index_is_a_computed_node_not_an_input() -> None:
    """``month`` has a record, so it is what the framework computed -- never an input.

    Reading it as a model-point field would export a raw input where a
    projection configuration belongs, and hide the horizon that produced
    it from every version diff.
    """
    graph = fold(_projected())

    assert graph.nodes["month@1"].kind is NodeType.COMPUTED
    assert "month" not in graph.nodes
    assert not [
        node
        for node in graph.nodes.values()
        if node.kind is NodeType.INPUT and node.data.column == "month"
    ]


def test_a_shared_calendar_timeline_reads_no_policy_column() -> None:
    """One grid for every policy is built from the configuration alone."""
    graph = fold(_projected())

    assert _reads(graph, "month@1") == ()
    assert _reads(graph, "projection_start_date@1") == ()


def test_a_per_policy_timeline_declares_the_horizon_column_it_reads() -> None:
    """A jagged axis is a function of each policy's own remaining term."""
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "remaining_term_months": [6, 12]})
    )
    af = af.projection.set(
        valuation_date=datetime.date(2026, 1, 31),
        until="term_months",
        until_value="remaining_term_months",
        frequency="monthly",
    )

    graph = fold(af)

    assert _reads(graph, "month@1") == ("remaining_term_months",)
    assert _reads(graph, "num_proj_months@1") == ("remaining_term_months",)


def test_an_inception_anchored_timeline_expression_declares_its_anchor_column() -> None:
    """Boundary dates read each policy's inception, so the graph says so."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "policy_inception": [
                    datetime.date(2020, 6, 15),
                    datetime.date(2021, 3, 1),
                ],
            }
        )
    )
    schedule = Schedule.from_inception(
        inception_column="policy_inception", n_periods=3, frequency="1M"
    )

    af.period_boundaries = schedule.period_dates_expr()

    graph = fold(af)
    assert _reads(graph, "period_boundaries@1") == ("policy_inception",)


def test_a_structural_timeline_mask_declares_no_reads_it_does_not_have() -> None:
    """An anniversary mask depends on the cadence, not on any policy's dates."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "policy_inception": [
                    datetime.date(2020, 6, 15),
                    datetime.date(2021, 3, 1),
                ],
            }
        )
    )
    schedule = Schedule.from_inception(
        inception_column="policy_inception", n_periods=24, frequency="1M"
    )

    af.anniversaries = schedule.anniversary_mask_expr()

    graph = fold(af)
    assert _reads(graph, "anniversaries@1") == ()


def test_every_jagged_timeline_expression_declares_the_horizon_column() -> None:
    """A per-policy axis is that policy's own horizon, whatever is asked of it.

    Unlike a shared grid, nothing about a jagged timeline is structural:
    its length, its cadence marks and its year fractions are all functions
    of each policy's own remaining term, so every expression built on it
    reads that column.
    """
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "remaining_term_months": [6, 12]})
    )
    schedule = Schedule.from_per_policy_grid(
        start_date=datetime.date(2026, 1, 31),
        frequency="1M",
        until_kind="term_months",
        until_value_column="remaining_term_months",
    )

    af.period_boundaries = schedule.per_policy_period_dates_expr()
    af.year_fractions = schedule.year_fractions_expr()
    af.anniversaries = schedule.anniversary_mask_expr()
    af.in_force = schedule.is_in_force_expr()

    graph = fold(af)
    assert _reads(graph, "period_boundaries@1") == ("remaining_term_months",)
    assert _reads(graph, "year_fractions@1") == ("remaining_term_months",)
    assert _reads(graph, "anniversaries@1") == ("remaining_term_months",)
    assert _reads(graph, "in_force@1") == ("remaining_term_months",)


def test_a_contract_boundary_declares_both_columns_it_compares() -> None:
    """The end-date test reads the policy's inception and its termination date."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_inception": [datetime.date(2020, 6, 15)],
                "termination_date": [datetime.date(2021, 6, 15)],
            }
        )
    )
    schedule = Schedule.from_inception(
        inception_column="policy_inception", n_periods=24, frequency="1M"
    )

    af.terminated = schedule.contract_boundary_expr(end_date_column="termination_date")

    graph = fold(af)
    assert _reads(graph, "terminated@1") == (
        "policy_inception",
        "termination_date",
    )


# --- what the export shows against real values ------------------------------


def test_a_node_that_read_a_replaced_value_shows_no_numeric_trace() -> None:
    """Sample values come from the finished frame, so they cannot speak for it.

    ``death_claims`` was taken on the inforce *before* the maturity
    zeroing. The finished frame holds only the zeroed inforce, so
    substituting the column's surviving value would walk the reader
    through arithmetic that does not produce the claim amount sitting
    beside it. What the node computed is still fully stated -- the
    formula, the reads and the source location are all there. Only the
    numbers nobody can supply are absent.
    """
    exported = _exported(_maturity_zeroing_frame())

    assert exported["death_claims@1"]["reads"] == [
        "policies_in_force@1",
        "mortality_rate",
    ]
    assert exported["death_claims@1"]["formula"] is not None
    assert exported["death_claims@1"]["trace"] is None


def test_a_node_whose_reads_all_survive_still_shows_its_trace() -> None:
    """Every value this one read is in the finished frame, so the walk-through holds."""
    exported = _exported(_maturity_zeroing_frame())

    assert exported["expected_payout@1"]["reads"] == [
        "policies_in_force@2",
        "sum_assured",
    ]
    assert exported["expected_payout@1"]["trace"] is not None


# --- determinism ------------------------------------------------------------


def test_input_nodes_come_out_in_the_frames_own_column_order() -> None:
    """The arriving columns are ordered, not merely present.

    The set of arriving columns is a ``frozenset``, whose iteration order
    is fixed within one process and different between processes. Emitting
    the inputs in that order would give two runs of the same model two
    graphs that cannot be diffed -- so the order is the frame's own column
    order, asserted here exactly rather than as "some stable order",
    because that is the only form of the assertion a set could not also
    satisfy by luck.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0],
                "issue_age": [30],
                "policy_term": [20],
                "annual_premium": [1200.0],
                "mortality_rate": [0.01],
                "lapse_rate": [0.05],
                "commission_rate": [0.4],
                "expense_loading": [0.02],
            }
        )
    )
    af.first_year_commission = af.annual_premium * af.commission_rate

    graph = fold(af)

    assert _ordered_input_ids(graph) == [
        "sum_assured",
        "issue_age",
        "policy_term",
        "annual_premium",
        "mortality_rate",
        "lapse_rate",
        "commission_rate",
        "expense_loading",
    ]


def test_an_input_the_frame_has_renamed_away_sorts_after_the_ones_it_lists() -> None:
    """A column the frame no longer lists still needs a fixed place in the order.

    Renaming moves the name on, so the vendor name the data arrived under
    is no longer in the frame's column order at all. It still arrived, so
    it is still an input -- placed after every column the frame does
    still list, and alphabetically among its own kind rather than in
    whatever order a set happened to yield.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "zeta": [1.0],
                "Vendor Sex": ["M"],
                "alpha": [2.0],
                "Vendor Age": [30],
            }
        )
    )
    af = af.rename({"Vendor Age": "issue_age", "Vendor Sex": "sex"})

    graph = fold(af)

    assert _ordered_input_ids(graph) == [
        "zeta",
        "alpha",
        "Vendor Age",
        "Vendor Sex",
    ]


def test_folding_one_frame_twice_leaves_nothing_behind() -> None:
    """The fold reads the log and writes nothing back to it."""
    af = _maturity_zeroing_frame()

    assert fold(af).to_dict() == fold(af).to_dict()


def test_two_frames_built_the_same_way_fold_to_the_same_graph() -> None:
    """The graph is a function of the log, not of the object that carried it."""
    assert (
        fold(_maturity_zeroing_frame()).to_dict()
        == fold(_maturity_zeroing_frame()).to_dict()
    )


# --- the kernel's own scratch column ----------------------------------------


def _compiled_rollforward_frame() -> ActuarialFrame:
    """Build a fund rollforward whose result is read through another expression.

    ``expr_for`` returns a reference into a hidden struct column the frame
    materialises behind the model's back. Assigning that reference straight
    to a column never puts the hidden name in front of the fold; wrapping it
    -- as a model does whenever it prepends a period or combines two states
    -- does, which is the shape this fixture builds.
    """
    from gaspatchio.rollforward._compile import compile_rollforward

    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1", "P2"],
                "account_value_initial": [1000.0, 2000.0],
                "growth_rate": [0.01, 0.02],
            }
        )
    )
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=3, frequency="annual"
    )
    builder = af.projection.rollforward(
        states={"fund_value": af["account_value_initial"]}
    )
    builder["fund_value"].grow(af["growth_rate"])
    compiled = compile_rollforward(builder)
    af.account_value = pl.concat_list(
        [
            pl.lit([1.0], dtype=pl.List(pl.Float64)),
            compiled.expr_for("fund_value"),
        ]
    )
    return af


def test_the_rollforward_kernels_scratch_column_is_not_a_node() -> None:
    """It is the kernel's working space, not a column the model reads."""
    graph = fold(_compiled_rollforward_frame())

    minted = [node_id for node_id in graph.nodes if node_id.startswith("__rollforward")]

    assert minted == []


def test_the_column_that_reads_the_rollforward_reads_the_compilation() -> None:
    """The kernel's own column names a compilation, and that is what the node reads.

    A model that wraps an extraction in an expression of its own hands the
    engine a reference to the hidden struct column the frame materialises
    for the kernel, and that name is all the record keeps of what was
    read. It used to be dropped, which left this node saying it read
    nothing while its own formula still named the reference -- a column
    whose account of itself was blank in the one document whose purpose is
    that it can be checked. The name embeds the compilation's
    fingerprint, so it resolves to the compilation instead.
    """
    graph = fold(_compiled_rollforward_frame())
    nodes = _exported(_compiled_rollforward_frame())

    (compilation,) = [
        node_id
        for node_id, node in graph.nodes.items()
        if node.kind is NodeType.ROLLFORWARD
    ]

    assert "account_value@1" in nodes
    assert nodes["account_value@1"]["dtype"] == "list[f64]"
    assert nodes["account_value@1"]["reads"] == [compilation]


def test_the_scratch_guard_matches_only_the_name_the_kernel_mints() -> None:
    """The guard matches the name the kernel mints, not everything resembling it.

    What the kernel mints is the prefix and sixteen hex characters of a
    fingerprint, and nothing else. A model's own column cannot take a name
    under that prefix at all -- the frame refuses one at every door a column
    comes through, see ``tests/frame/test_reserved_column_prefixes.py`` --
    but the fold does not lean on that: a name that only begins like the
    kernel's is never resolved to a compilation, so a calculation reading
    one would keep the lineage its own formula names.
    """
    assert _kernel_column("__rollforward_0123456789abcdef")
    assert not _kernel_column("__rollforward_notes")
    assert not _kernel_column("__rollforward_0123456789abcdef0")
    assert not _kernel_column("__rollforward_0123456789ABCDEF")
    with pytest.raises(ValueError, match="'__rollforward_' is a prefix the frame"):
        ActuarialFrame(
            pl.DataFrame({"sum_assured": [100_000.0], "__rollforward_notes": [0.5]})
        )
