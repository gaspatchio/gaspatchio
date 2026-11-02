# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What each edge says about the read it stands for.

"What does this reserve depend on?" and "what selected the row?" are
different questions, and a graph whose edges are all one colour answers
the first with the second mixed into it. Every test below is one emission
rule: the line an actuary writes, and the two words the edge that line
mints has to carry.

The formula under test is passed as the source text of the assignment, so
that each test reads as the model line it is about rather than as a tree
built by hand. What is asserted is the classification, never the shape of
the tree behind it: an emission rule is a claim about the model's
sentence, and it should survive the tree being spelled differently.
"""

from __future__ import annotations

import json
from typing import Any, Final

import polars as pl

from gaspatchio import ActuarialFrame, when
from gaspatchio._semantic.ir import BinOp, Call, Col, Lit, OpNode, WhenThen
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.edges import EdgeSubtype, ReadClaim, classify_reads
from gaspatchio.frame.graph.graph_builder import fold

# --- the model the formulas are written against -----------------------------

# One policy, and every column the emission rules below name. The values
# are never asserted on: what each test reads is which column fed which
# node and how, and that is a fact about the formula rather than about the
# numbers it was run over.
_MODEL_POINTS = pl.DataFrame(
    {
        "Issue Age": [45],
        "attained_age": [45.0],
        "cashflow": [1_200.0],
        "combined_decrement": [0.02],
        "duration": [0],
        "mortality_rate": [0.01],
        "month_axis": [[0, 1, 2]],
        "monthly_rate": [[0.004, 0.004, 0.004]],
        "net_cf": [[-1_000.0, 400.0, 400.0, 400.0]],
        "nper": [10.0],
        "period": [1],
        "pmt": [1_000.0],
        "premiums": [1_000.0],
        "rate": [0.05],
        "reserve": [5_000.0],
        "sum_assured": [100_000.0],
    }
)

# The assumption table the lookup rule is written against: one dimension,
# one value, and rows covering the model point above, so the lookup is a
# real lookup rather than one that would miss.
mortality = Table(
    name="edge_vocabulary_mortality",
    source=pl.DataFrame({"age": [45.0, 46.0], "rate": [0.01, 0.02]}),
    dimensions={"age": "age"},
    value="rate",
)


def _edges_for(formula: str) -> dict[tuple[str, str], tuple[str, str]]:
    """Run one model line and return how each edge it minted was classified.

    Keyed by the pair the edge names -- the node its value was read from,
    and the node that read it -- so a test asserts about one read without
    having to know how many others the line made.

    ``pl`` is in the namespace because a raw Polars expression is how a
    model reaches an engine's own language, and several rules below are
    about what happens to a read that arrives that way.
    """
    return {
        (edge.source, edge.target): (edge.relationship, edge.subtype)
        for edge in fold(_frame_after(formula)).edges
    }


def _frame_after(formula: str) -> ActuarialFrame:
    """Return the frame one model line leaves behind."""
    namespace: dict[str, Any] = {
        "af": ActuarialFrame(_MODEL_POINTS),
        "mortality": mortality,
        "pl": pl,
        "when": when,
    }
    exec(formula, namespace)  # noqa: S102 -- the rule under test is a written model line
    frame: ActuarialFrame = namespace["af"]
    return frame


def test_selection_separates_the_value_from_its_position() -> None:
    """The index chooses a value but is not itself part of that value."""
    assert _edges_for("af.picked = af.net_cf.list.get(af.period)") == {
        ("net_cf", "picked@1"): ("DIRECT", "TRANSFORMATION"),
        ("period", "picked@1"): ("INDIRECT", "FILTER"),
    }


def test_a_selection_index_used_as_a_value_is_also_direct() -> None:
    """A second read in the arithmetic outranks its use only as an index."""
    edges = _edges_for("af.picked = af.net_cf.list.get(af.period) + af.period")
    assert edges[("period", "picked@1")] == ("DIRECT", "TRANSFORMATION")


def test_a_selection_inside_a_condition_keeps_its_index_distinct() -> None:
    """An indirect outer context absorbs value reads, retaining the index role."""
    edges = _edges_for(
        "af.flag = when(af.net_cf.list.get(af.period) > 0).then(1).otherwise(0)"
    )
    assert edges[("net_cf", "flag@1")] == ("INDIRECT", "CONDITIONAL")
    assert edges[("period", "flag@1")] == ("INDIRECT", "FILTER")


def test_lookup_and_selection_nesting_preserves_the_lookup_key_role() -> None:
    """Looking up a position does not turn the lookup's key into that position.

    Each claim is asserted whole, offset included: neither of these reads
    crosses a period, and ``None`` there is the read saying it took the
    value from the period being computed.
    """
    indexed_by_lookup = Call("list.get", (Col("cash"), Call("lookup", (Col("key"),))))
    assert classify_reads(indexed_by_lookup) == {
        "cash": ReadClaim(("DIRECT", "TRANSFORMATION"), None),
        "key": ReadClaim(("INDIRECT", "JOIN"), None),
    }
    lookup_by_selection = Call(
        "lookup", (Call("list.get", (Col("keys"), Col("position"))),)
    )
    assert classify_reads(lookup_by_selection) == {
        "keys": ReadClaim(("INDIRECT", "JOIN"), None),
        "position": ReadClaim(("INDIRECT", "JOIN"), None),
    }


# --- one test per emission rule ---------------------------------------------


def test_an_arithmetic_operand_is_a_direct_transformation() -> None:
    """A multiplicand's value is in the answer, changed but carried."""
    edges = _edges_for("af.death_claims = af.sum_assured * af.mortality_rate")

    assert edges[("sum_assured", "death_claims@1")] == ("DIRECT", "TRANSFORMATION")
    assert edges[("mortality_rate", "death_claims@1")] == ("DIRECT", "TRANSFORMATION")


def test_a_rename_is_a_direct_identity() -> None:
    """The whole formula is one other column, so the value arrives unchanged."""
    edges = _edges_for("af.issue_age = af['Issue Age']")

    assert edges[("Issue Age", "issue_age@1")] == ("DIRECT", "IDENTITY")


def test_a_column_read_only_by_a_condition_is_an_indirect_conditional() -> None:
    """Duration chose the branch; the premium is what the branch pays."""
    edges = _edges_for(
        "af.commissions = when(af.duration == 0).then(af.premiums).otherwise(0.0)"
    )

    assert edges[("duration", "commissions@1")] == ("INDIRECT", "CONDITIONAL")
    assert edges[("premiums", "commissions@1")] == ("DIRECT", "TRANSFORMATION")


def test_a_lookup_key_is_an_indirect_join() -> None:
    """The attained age found the rate; it is not part of the rate."""
    edges = _edges_for("af.mortality_rate = mortality.lookup(age=af.attained_age)")

    assert edges[("attained_age", "mortality_rate@1")] == ("INDIRECT", "JOIN")


def test_an_accumulated_operand_is_a_direct_aggregation() -> None:
    """Every period's decrement is in the survival curve, not only this one's."""
    edges = _edges_for(
        "af.survival = af.combined_decrement.projection.cumulative_survival()"
    )

    assert edges[("combined_decrement", "survival@1")] == ("DIRECT", "AGGREGATION")


def test_a_column_read_both_ways_takes_the_stronger_claim() -> None:
    """Read in a condition and as an operand, it is a direct transformation."""
    edges = _edges_for(
        "af.capped = when(af.reserve > 0).then(af.reserve).otherwise(0.0)"
    )

    assert edges[("reserve", "capped@1")] == ("DIRECT", "TRANSFORMATION")


# --- which operations accumulate --------------------------------------------


def test_a_discounted_cashflow_is_a_transformation_not_an_accumulation() -> None:
    """``CF / (1 + rate)^period`` reads this period's values and no others.

    The actuarial name says present value; the calculation is a closed form
    over three values standing at one period, and nothing is folded. An
    ``AGGREGATION`` here would tell a reviewer that every period's cashflow
    is inside every period's answer, which is not what the model did.
    """
    edges = _edges_for("af.pv = af.finance.present_value('cashflow', 'rate', 'period')")

    assert edges[("cashflow", "pv@1")] == ("DIRECT", "TRANSFORMATION")
    assert edges[("rate", "pv@1")] == ("DIRECT", "TRANSFORMATION")
    assert edges[("period", "pv@1")] == ("DIRECT", "TRANSFORMATION")


def test_an_annuity_present_value_is_a_transformation_not_an_accumulation() -> None:
    """Excel's ``PV`` is a closed form too: one row's rate, term and payment."""
    edges = _edges_for("af.annuity = af.rate.excel.pv(af.nper, af.pmt)")

    assert edges[("rate", "annuity@1")] == ("DIRECT", "TRANSFORMATION")
    assert edges[("nper", "annuity@1")] == ("DIRECT", "TRANSFORMATION")
    assert edges[("pmt", "annuity@1")] == ("DIRECT", "TRANSFORMATION")


def test_an_internal_rate_of_return_consumes_every_period() -> None:
    """One rate out of a whole cashflow list: every period's value is in it."""
    edges = _edges_for("af.yield_to_maturity = af.net_cf.excel.irr()")

    assert edges[("net_cf", "yield_to_maturity@1")] == ("DIRECT", "AGGREGATION")


def test_a_forward_discount_factor_accumulates_and_a_spot_one_does_not() -> None:
    """The same operation, two methods, and only one of them folds.

    ``forward`` cumulates the per-period reciprocals, so every earlier rate
    is inside every later factor. ``spot`` raises each period's own rate to
    minus that period. The method is on the node, so the edge says which
    calculation the model actually asked for instead of covering both with
    the more alarming of the two words.
    """
    forward = _edges_for(
        "af = af.finance.discount_factor("
        "rate_col='monthly_rate', periods_col='month_axis', "
        "output_col='v_t', method='forward')"
    )
    spot = _edges_for(
        "af = af.finance.discount_factor("
        "rate_col='monthly_rate', periods_col='month_axis', "
        "output_col='v_t', method='spot')"
    )

    assert forward[("monthly_rate", "v_t@1")] == ("DIRECT", "AGGREGATION")
    assert spot[("monthly_rate", "v_t@1")] == ("DIRECT", "TRANSFORMATION")


# --- nesting: one ladder, and nesting order decides nothing ------------------

# A lookup key inside a conditional's test, as an op-tree rather than as a
# model line. It cannot be written as one today: a lookup compared against
# anything degrades to the escape hatch before the classifier sees it (the
# rule below pins exactly that), which takes the lookup node this nesting
# is about out of the tree. The other order still reads as a line, and the
# pair has to be asked the same question to be compared at all.
_LOOKUP_INSIDE_A_TEST: Final[OpNode] = WhenThen(
    cond=BinOp(op="gt", left=Call("lookup", (Col("attained_age"),)), right=Lit(0.0)),
    then=Col("premiums"),
    otherwise=Lit(0.0),
)

# The same two contexts, nested the other way round: a conditional standing
# where the lookup's key goes.
_CONDITIONAL_INSIDE_A_KEY: Final[OpNode] = Call(
    "lookup",
    (
        WhenThen(
            cond=BinOp(op="eq", left=Col("duration"), right=Lit(0)),
            then=Col("attained_age"),
            otherwise=Lit(0.0),
        ),
    ),
)


def test_a_lookup_key_inside_a_conditional_test_is_still_a_key() -> None:
    """Two indirect contexts, and the stronger claim about the read wins."""
    assert classify_reads(_LOOKUP_INSIDE_A_TEST)["attained_age"] == ReadClaim(
        ("INDIRECT", "JOIN"), None
    )


def test_a_conditional_test_inside_a_lookup_key_gives_the_same_answer() -> None:
    """Nesting order decides nothing: one ladder settles both arrangements."""
    inner_lookup = classify_reads(_LOOKUP_INSIDE_A_TEST)["attained_age"]
    outer_lookup = classify_reads(_CONDITIONAL_INSIDE_A_KEY)["duration"]

    assert outer_lookup == inner_lookup == ReadClaim(("INDIRECT", "JOIN"), None)


def test_an_accumulation_inside_a_conditional_test_only_chose_a_branch() -> None:
    """A decrement folded on the way to a test still only chose a branch."""
    edges = _edges_for(
        "af.premium_holiday = when("
        "af.combined_decrement.projection.cumulative_survival() > 0.5"
        ").then(af.premiums).otherwise(0.0)"
    )

    assert edges[("combined_decrement", "premium_holiday@1")] == (
        "INDIRECT",
        "CONDITIONAL",
    )


def test_an_accumulation_inside_a_branch_is_an_accumulation() -> None:
    """The branch pays the survival curve, so every period's decrement is in it."""
    edges = _edges_for(
        "af.survival = when(af.duration == 0)"
        ".then(af.combined_decrement.projection.cumulative_survival())"
        ".otherwise(0.0)"
    )

    assert edges[("combined_decrement", "survival@1")] == ("DIRECT", "AGGREGATION")
    assert edges[("duration", "survival@1")] == ("INDIRECT", "CONDITIONAL")


# --- the escape hatch, and what it launders ---------------------------------


def test_an_opaque_read_is_claimed_under_the_context_it_sits_in() -> None:
    """The framework cannot read the text, so the surrounding context answers.

    Four placements of the same raw Polars expression, and each one takes
    the claim its position supports. This is the only defensible rule --
    nothing here can see which of an opaque fragment's columns are in its
    answer and which only consulted -- and it is what makes the two tests
    after this one worth pinning.
    """
    bare = _edges_for('af.grown = af.premiums * pl.col("reserve").cum_prod()')
    in_a_test = _edges_for(
        'af.capped = when(pl.col("reserve").cum_prod() > 0.0)'
        ".then(af.premiums).otherwise(0.0)"
    )
    as_a_key = _edges_for(
        'af.mortality_rate = mortality.lookup(age=pl.col("attained_age").cum_max())'
    )
    in_an_accumulation = _edges_for(
        'af.survival = (af.combined_decrement * pl.col("reserve"))'
        ".projection.cumulative_survival()"
    )

    assert bare[("reserve", "grown@1")] == ("DIRECT", "TRANSFORMATION")
    assert in_a_test[("reserve", "capped@1")] == ("INDIRECT", "CONDITIONAL")
    assert as_a_key[("attained_age", "mortality_rate@1")] == ("INDIRECT", "JOIN")
    assert in_an_accumulation[("reserve", "survival@1")] == ("DIRECT", "AGGREGATION")


def test_a_key_inside_a_larger_formula_is_still_read_as_a_key() -> None:
    """A lookup times a number keeps its key, and the key comes back INDIRECT.

    This test used to record the opposite, and said so: the lookup
    dissolved into an engine fragment at emission, the fragment's declared
    dependencies were read under the ordinary multiplication around it, and
    a column that had only *found* a rate came back ``DIRECT`` as though its
    values were in the answer. The classifier was right about the tree it
    was given; the tree was the wrong tree. Emission now keeps the lookup as
    a subtree of the operation around it, so the key is a key wherever the
    lookup happens to stand, and an impact cone drawn through this
    multiplication no longer sweeps in every column that ever found a rate.
    """
    edges = _edges_for("af.doubled = mortality.lookup(age=af.attained_age) * 2.0")

    assert edges[("attained_age", "doubled@1")] == ("INDIRECT", "JOIN")


# --- what the whole vocabulary does, and does not, emit ---------------------

# One line per emission rule this module states, so the battery below can
# ask about all of them at once rather than about one at a time.
_EVERY_RULE: Final[tuple[str, ...]] = (
    "af.issue_age = af['Issue Age']",
    "af.death_claims = af.sum_assured * af.mortality_rate",
    "af.commissions = when(af.duration == 0).then(af.premiums).otherwise(0.0)",
    "af.mortality_rate = mortality.lookup(age=af.attained_age)",
    "af.survival = af.combined_decrement.projection.cumulative_survival()",
    "af.pv = af.finance.present_value('cashflow', 'rate', 'period')",
    "af.annuity = af.rate.excel.pv(af.nper, af.pmt)",
    "af.yield_to_maturity = af.net_cf.excel.irr()",
    (
        "af = af.finance.discount_factor("
        "rate_col='monthly_rate', periods_col='month_axis', "
        "output_col='v_t', method='forward')"
    ),
    'af.grown = af.premiums * pl.col("reserve").cum_prod()',
    "af.doubled = mortality.lookup(age=af.attained_age) * 2.0",
    "af.picked = af.net_cf.list.get(af.period)",
)

# The six an emission rule can produce, and the three that are defined and
# never produced. Spelled out rather than derived from the type, because
# what this asserts is which half of the vocabulary this producer uses.
_CAN_FIRE: Final[frozenset[EdgeSubtype]] = frozenset(
    {"IDENTITY", "TRANSFORMATION", "AGGREGATION", "JOIN", "FILTER", "CONDITIONAL"}
)
_DECLARED_AND_NEVER_EMITTED: Final[frozenset[EdgeSubtype]] = frozenset(
    {"GROUP_BY", "SORT", "WINDOW"}
)


def test_the_rules_between_them_emit_six_subtypes_and_no_others() -> None:
    """Every rule fires, and the remaining three subtypes are never used.

    Both directions matter. A subtype outside the six would be a claim
    this producer has no rule to support; a subtype missing from the six
    would mean a rule stopped firing and every test above it happened to
    keep passing on some other edge.
    """
    emitted = {
        subtype
        for formula in _EVERY_RULE
        for _, subtype in _edges_for(formula).values()
    }

    assert emitted == _CAN_FIRE
    assert not emitted & _DECLARED_AND_NEVER_EMITTED


# --- what the published schema refuses --------------------------------------


def _edge_fields_the_schema_refuses(artifact: dict[str, Any]) -> set[str]:
    """Return the field names the published schema refuses inside ``edges``.

    Named by field rather than by container, for the reason the envelope's
    own guard is: an assertion that a refusal lies *somewhere* inside
    ``edges`` passes just as happily with the wrong field corrupted. An
    empty set is the statement that every edge conforms.
    """
    import jsonschema

    from gaspatchio.schemas import load_schema

    validator = jsonschema.Draft202012Validator(load_schema())
    refused: set[str] = set()
    for error in validator.iter_errors(artifact):
        named = [step for step in error.absolute_path if isinstance(step, str)]
        if named and named[0] == "edges":
            refused.add(named[-1])
    return refused


def _exported_artifact(formula: str) -> dict[str, Any]:
    """Return the artifact one model line exports, parsed back from the wire."""
    exported = GraphExporter(_frame_after(formula)).export()
    artifact: dict[str, Any] = json.loads(exported)
    return artifact


def test_the_edges_a_model_exports_conform_to_the_published_schema() -> None:
    """Nothing an emitted edge says is refused: what makes the next two bite."""
    artifact = _exported_artifact(
        "af.mortality_rate = mortality.lookup(age=af.attained_age)"
    )

    assert _edge_fields_the_schema_refuses(artifact) == set()


# --- the core edge, and where the narrowing went ----------------------------

# The facet the narrowing travels in, on the node that did the reading.
_FACET: Final[str] = "gaspatchio_column_transformation"

# What a core edge carries and nothing else: the two endpoints and the
# relationship. Spelled out rather than derived, because the point of the
# move is that this set is small and stays small.
_CORE_EDGE_FIELDS: Final[frozenset[str]] = frozenset(
    {"source", "target", "relationship"}
)


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node an artifact records under ``node_id``."""
    (found,) = [node for node in artifact["nodes"] if node["id"] == node_id]
    record: dict[str, Any] = found
    return record


def test_the_core_edge_is_the_endpoints_and_the_relationship() -> None:
    """An edge states who read whom, and whether the value flowed.

    That is the distinction section 9 exists for -- what a reserve depends
    on and what selected the row are different questions -- and it is the
    one an impact cone is drawn through. The narrowing is a different kind
    of claim and travels elsewhere.
    """
    artifact = _exported_artifact(
        "af.mortality_rate = mortality.lookup(age=af.attained_age)"
    )

    assert all(set(edge) == _CORE_EDGE_FIELDS for edge in artifact["edges"])
    assert artifact["edges"][0]["relationship"] == "INDIRECT"


def test_the_narrowing_travels_on_the_reading_node_as_a_facet() -> None:
    """``subtype`` moves whole, in OpenLineage's own spelling.

    ``transformations`` is its array name and ``type`` and ``subtype`` are
    its key names, kept verbatim so that a consumer already reading column
    lineage meets the shape it knows. What is not verbatim is the outer
    indexing: OpenLineage keys by dataset and field, and this keys by node
    id, because that is what an artifact of this format holds.
    """
    artifact = _exported_artifact(
        "af.mortality_rate = mortality.lookup(age=af.attained_age)"
    )

    carried = _node(artifact, "mortality_rate@1")["facets"][_FACET]

    assert carried["reads"] == [
        {
            "source": "attained_age",
            "transformations": [{"type": "INDIRECT", "subtype": "JOIN"}],
        }
    ]


def test_the_facet_reads_in_the_reading_nodes_own_reads_order() -> None:
    """The target's read list is the key, so the two have to agree.

    Section 9 writes one edge per entry of the target's ``reads``, which is
    what makes the read list an index into the facet at all. Two orders
    would leave a consumer pairing the wrong narrowing with the wrong read
    and no sign that it had.
    """
    artifact = _exported_artifact(
        "af.ceded = when(af.sum_assured > 200_000.0)"
        ".then(af.premiums * af.mortality_rate).otherwise(0.0)"
    )

    indexed = {
        node["id"]: [read["source"] for read in node["facets"][_FACET]["reads"]]
        for node in artifact["nodes"]
        if _FACET in node["facets"]
    }

    assert indexed, "no node carried the facet, so nothing here was checked"
    assert indexed == {
        node["id"]: node["reads"] for node in artifact["nodes"] if node["id"] in indexed
    }


def test_a_node_that_reads_nothing_carries_no_narrowing() -> None:
    """A column that arrived read nothing, so there is no narrowing to carry.

    An empty ``reads`` array with a facet holding an empty array beside it
    would be the same claim written twice, and the second copy is the one
    that can fall out of step.
    """
    artifact = _exported_artifact(
        "af.mortality_rate = mortality.lookup(age=af.attained_age)"
    )

    arrived = _node(artifact, "attained_age")

    assert arrived["reads"] == []
    assert arrived["facets"] == {}


def test_the_narrowing_is_announced_and_never_required() -> None:
    """A consumer that has never met the facet loses a narrowing, not a graph.

    That is section 6's own test for what may be optional, and it is why
    the name reaches ``facets_used`` and never ``facets_required``.
    """
    artifact = _exported_artifact(
        "af.mortality_rate = mortality.lookup(age=af.attained_age)"
    )

    assert artifact["facets_used"] == [_FACET]
    assert artifact["facets_required"] == []


# --- what the published schema refuses, now the narrowing has moved ---------


def _narrowing_fields_the_schema_refuses(artifact: dict[str, Any]) -> set[str]:
    """Return the field names the schema refuses inside the narrowing facet.

    Named by field for the reason the edge guard beside it is: a refusal
    somewhere inside a node is a refusal an assertion cannot tell from the
    one it meant. An empty set is the statement that every narrowing this
    artifact carries conforms.
    """
    import jsonschema

    from gaspatchio.schemas import load_schema

    validator = jsonschema.Draft202012Validator(load_schema())
    refused: set[str] = set()
    for error in validator.iter_errors(artifact):
        named = [step for step in error.absolute_path if isinstance(step, str)]
        if _FACET in named:
            refused.add(named[-1])
    return refused


def _refusals(artifact: dict[str, Any]) -> set[str]:
    """Return every message the published schema refuses ``artifact`` with."""
    import jsonschema

    from gaspatchio.schemas import load_schema

    validator = jsonschema.Draft202012Validator(load_schema())
    return {error.message for error in validator.iter_errors(artifact)}


def _the_only_narrowing(artifact: dict[str, Any]) -> dict[str, str]:
    """Return the one transformation object a one-read model's facet carries."""
    carried = _node(artifact, "mortality_rate@1")["facets"][_FACET]
    transformation: dict[str, str] = carried["reads"][0]["transformations"][0]
    return transformation


def test_the_narrowing_a_model_exports_conforms_to_the_published_schema() -> None:
    """Nothing an emitted narrowing says is refused: what makes the next two bite."""
    artifact = _exported_artifact(
        "af.mortality_rate = mortality.lookup(age=af.attained_age)"
    )

    assert _narrowing_fields_the_schema_refuses(artifact) == set()


def test_the_schema_refuses_a_direct_read_narrowed_by_a_key() -> None:
    """``DIRECT``/``JOIN`` is not a pair: the two halves have to agree.

    The pairing is the whole content of the two words, and it survived the
    move into the facet. A read claiming a value flowed into the answer,
    narrowed with the name for a read that only found a row, is a
    contradiction the schema is where a consumer finds out about.
    """
    artifact = _exported_artifact(
        "af.mortality_rate = mortality.lookup(age=af.attained_age)"
    )
    _the_only_narrowing(artifact)["type"] = "DIRECT"

    assert _narrowing_fields_the_schema_refuses(artifact) == {"subtype"}


def test_the_schema_refuses_a_subtype_it_has_never_defined() -> None:
    """The narrowing comes from a closed list, and a stranger is named."""
    artifact = _exported_artifact(
        "af.mortality_rate = mortality.lookup(age=af.attained_age)"
    )
    _the_only_narrowing(artifact)["subtype"] = "PROBABLY_A_JOIN"

    assert _narrowing_fields_the_schema_refuses(artifact) == {"subtype"}


def test_the_schema_refuses_a_relationship_it_has_never_defined() -> None:
    """The core edge's own vocabulary is two words and closed."""
    artifact = _exported_artifact(
        "af.mortality_rate = mortality.lookup(age=af.attained_age)"
    )
    artifact["edges"][0]["relationship"] = "PROBABLY_INDIRECT"

    assert _edge_fields_the_schema_refuses(artifact) == {"relationship"}


def test_the_schema_requires_the_relationship_on_every_edge() -> None:
    """An edge without one states a dependency and refuses to say which kind.

    That is the one thing section 9 exists to keep apart, so it is required
    rather than defaulted: a consumer meeting an edge with no relationship
    would have to guess, and the guess an impact cone wants is the one that
    makes the cone wrong.
    """
    artifact = _exported_artifact(
        "af.mortality_rate = mortality.lookup(age=af.attained_age)"
    )
    del artifact["edges"][0]["relationship"]

    assert "'relationship' is a required property" in _refusals(artifact)


# --- a broadcast's axis -----------------------------------------------------


def test_a_broadcast_reads_its_axis_for_its_length_alone() -> None:
    """The rate is in every cell; the axis says only how many cells there are.

    Section 11.1.32 takes nothing from the ``like=`` list but its length,
    so restating a policy year moves no rate broadcast along it. The read
    was claimed ``DIRECT``/``TRANSFORMATION`` -- a value in the number --
    which put the axis in the impact cone of everything the rate reaches.
    """
    edges = _edges_for(
        "af.rate_by_period = af.rate.projection.broadcast_to_periods("
        "like=af.month_axis)"
    )

    assert edges[("rate", "rate_by_period@1")] == ("DIRECT", "TRANSFORMATION")
    assert edges[("month_axis", "rate_by_period@1")] == ("INDIRECT", "WINDOW")


def test_an_axis_that_is_also_a_value_is_a_value() -> None:
    """One read that puts the column in the number settles the edge."""
    broadcast = Call(
        "projection.broadcast_to_periods", (Col("rate"), Col("monthly_rate"))
    )
    claims = classify_reads(BinOp("mul", broadcast, Col("monthly_rate")))

    assert claims["monthly_rate"] == ReadClaim(("DIRECT", "TRANSFORMATION"), None)


def test_an_axis_inside_a_conditional_test_chose_a_branch() -> None:
    """``WINDOW`` is the weakest claim, so a test around it says more."""
    broadcast = Call(
        "projection.broadcast_to_periods", (Col("rate"), Col("monthly_rate"))
    )
    claims = classify_reads(
        WhenThen(BinOp("gt", broadcast, Lit(0.0)), Col("premiums"), Lit(0.0))
    )

    assert claims["monthly_rate"] == ReadClaim(("INDIRECT", "CONDITIONAL"), None)
    assert claims["rate"] == ReadClaim(("INDIRECT", "CONDITIONAL"), None)
