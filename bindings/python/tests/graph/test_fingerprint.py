# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Content-addressed identity for a model's calculations.

Two runs of the same model, a quarter apart. One assumption moved. The
question a reviewer actually asks is not "did anything change?" -- it is
"which numbers can no longer be the same, and which ones have no business
moving at all?" A fingerprint answers it by construction: every node gets a
hash of *what it computes*, and a second hash folding in the hashes of
everything it reads. The first says whether this line was edited; the
second says whether its answer can still be the same. A change that moves
more of the second kind than it should is a bug someone gets to see before
the valuation does.

The bytes being hashed are the op-tree and nothing else -- not where the
line was written, not how the formula happens to render, not the name of
the column being defined. That is what makes reformatting a model a no-op
and what makes a renamed column recognisably the same calculation. It is
also why two columns computed the same way share a local fingerprint: the
graph tells them apart by hashing the *pairs* of name and fingerprint, the
way every Merkle tree that has to survive a swap does.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import struct

import numpy as np
import numpy.typing as npt
import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio._identity import SHA256_PREFIX, content_sha_of, source_sha_of
from gaspatchio._semantic.ir import (
    AttrValue,
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    OpNode,
    State,
    WhenThen,
)
from gaspatchio.assumptions import Table
from gaspatchio.frame.base import _holds_python_objects
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.fingerprint import (
    DISPLAY_WIDTH,
    HEX_WIDTH,
    _scalar,
    canonical_bytes,
    fingerprint,
    fingerprints_for,
    graph_fingerprint,
    local_fingerprint,
    short_fingerprint,
    stamp_fingerprints,
)
from gaspatchio.frame.graph.graph_builder import CalcGraph, fold
from gaspatchio.frame.graph.op_json import op_node_from_json, op_node_to_json
from gaspatchio.scenarios import with_scenarios

# --- helpers ----------------------------------------------------------------


def _premium_frame() -> ActuarialFrame:
    """Return the two-column frame the formatting fixtures both start from."""
    return ActuarialFrame(
        pl.DataFrame({"gross_premium": [100.0, 250.0], "expense_loading": [5.0, 9.0]})
    )


def _tidy_frame() -> ActuarialFrame:
    """Write the model the way it comes out of the formatter."""
    af = _premium_frame()
    af.net_premium = af.gross_premium - af.expense_loading
    af.reserve = af.net_premium * 0.9
    return af


def _untidy_frame() -> ActuarialFrame:
    """Write the same two formulas over more lines, with the operands named.

    Different line numbers, different statement text, an intervening
    comment -- and the identical pair of op-trees.
    """
    af = _premium_frame()

    # A comment nobody should be able to hash.
    gross = af.gross_premium
    loading = af.expense_loading

    af.net_premium = gross - loading
    af.reserve = af.net_premium * 0.9
    return af


def _horizon_frame(until_value: int) -> ActuarialFrame:
    """Build the worked case: one projection horizon, three columns below it."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "issue_age": [40, 55],
                "sum_assured": [100_000.0, 250_000.0],
            }
        )
    )
    af = af.projection.set(
        valuation_date=datetime.date(2026, 1, 1),
        until="maximum_age",
        until_value=until_value,
        frequency="annual",
    )
    af.attained_age = af.issue_age + af.month // 12
    af.mortality_rate = af.attained_age * 0.001
    af.death_claims = af.sum_assured * af.mortality_rate
    return af


def _locals(graph: CalcGraph) -> dict[str, bytes]:
    """Return every node's local fingerprint, keyed by node id."""
    return {node_id: fps.local for node_id, fps in fingerprints_for(graph).items()}


def _merkles(graph: CalcGraph) -> dict[str, bytes]:
    """Return every node's Merkle fingerprint, keyed by node id."""
    return {node_id: fps.merkle for node_id, fps in fingerprints_for(graph).items()}


def _frame_with_an_unexplained_column() -> ActuarialFrame:
    """Write one column straight into the query plan, behind every recording door.

    Nothing appends a record for it, so the fold has no account of it and
    mints a hole -- the leaf this module has to keep distinct from an
    arriving column of the same name.
    """
    af = ActuarialFrame(pl.DataFrame({"a": [1.0]}))
    af.total = af.a * 2.0
    plan = af._df  # noqa: SLF001 -- the bypass under test
    assert plan is not None
    af._df = plan.with_columns((pl.col("a") * 2.0).alias("lapse_reserve"))  # noqa: SLF001
    return af


def _model_with_injection(
    values: list[float | None], *, series_name: str = ""
) -> ActuarialFrame:
    """Hand a whole column of values over wholesale, the way a simulation does."""
    af = ActuarialFrame({"policy_id": [1, 2, 3]})
    af.shock = pl.Series(series_name, values)
    return af


def _model_with_array_injection(values: npt.NDArray[np.float64]) -> ActuarialFrame:
    """Hand a whole column of values over as the array a simulation returns."""
    af = ActuarialFrame({"policy_id": [1, 2, 3]})
    af.shock = values
    return af


def _node_for(frame: ActuarialFrame, column: str) -> OpNode:
    """Return the op-tree node the frame recorded for ``column``."""
    return next(r for r in frame._calculation_records() if r.column == column).node  # noqa: SLF001


def _injection_attrs(frame: ActuarialFrame) -> tuple[tuple[str, AttrValue], ...]:
    """Return the attributes recorded for the injected ``shock`` column."""
    record = next(r for r in frame._calculation_records() if r.column == "shock")  # noqa: SLF001
    assert isinstance(record.node, Call)
    return record.node.attrs


def _injection_local(frame: ActuarialFrame) -> bytes:
    """Return the local fingerprint of the injected ``shock`` node."""
    return _locals(fold(frame))["shock@1"]


def _mortality_table(name: str, base_rate: float) -> Table:
    """Build a one-dimension mortality table at a stated base rate."""
    ages = list(range(20, 121))
    return Table(
        name=name,
        source=pl.DataFrame(
            {
                "age": ages,
                "rate": [round(base_rate + 0.0004 * (age - 20), 6) for age in ages],
            }
        ),
        dimensions={"age": "age"},
        value="rate",
    )


def _lookup_frame(table: Table) -> ActuarialFrame:
    """Read one rate per policy out of ``table``."""
    af = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    af.mortality_rate = table.lookup(age=af.issue_age)
    return af


# --- the canonical bytes: what one node encodes to --------------------------


def test_a_column_reference_encodes_as_its_tag_and_its_name() -> None:
    """The whole encoding of a leaf, spelled out once so the rest can be read."""
    assert canonical_bytes(Col("age")) == b"\x01\x03age"


def test_every_node_type_carries_its_own_tag() -> None:
    """Seven node types, seven leading bytes -- no two kinds share a prefix."""
    nodes: list[OpNode] = [
        Col("a"),
        Lit(1),
        BinOp("add", Col("a"), Col("b")),
        Call("f", (Col("a"),)),
        WhenThen(Col("a"), Col("b"), Col("c")),
        State("balance"),
        EngineNative("polars", "text", ("a",)),
    ]
    tags = {canonical_bytes(node)[:1] for node in nodes}

    assert len(tags) == len(nodes)


def test_a_float_literal_encodes_as_big_endian_ieee_754_bits() -> None:
    """A tenth is its own eight bytes, most significant first.

    Little-endian would spell the same number ``9a99999999999b3f``. Pinning
    the byte order is what makes a fingerprint taken on one machine
    comparable with one taken on another.
    """
    encoded = canonical_bytes(Lit(0.1))

    assert encoded == b"\x02\x13" + struct.pack(">d", 0.1)
    assert encoded[2:].hex() == "3fb999999999999a"


def test_a_tenth_is_not_the_sum_that_almost_makes_three_tenths() -> None:
    """0.1 + 0.2 is 0.30000000000000004, and the bytes say so.

    Rounding a literal for display before hashing it would make these two
    the same fingerprint, which is how a rounding change gets to move a
    valuation without moving anything a reviewer can see.
    """
    assert canonical_bytes(Lit(0.1)) != canonical_bytes(Lit(0.1 + 0.2))
    assert canonical_bytes(Lit(0.3)) != canonical_bytes(Lit(0.1 + 0.2))


def test_an_integer_literal_is_not_its_own_text() -> None:
    """A term of thirty years is the integer, never the string."""
    assert canonical_bytes(Lit(1)) != canonical_bytes(Lit("1"))
    assert canonical_bytes(Lit(1)) != canonical_bytes(Lit(1.0))


def test_a_boolean_literal_is_not_the_integer_one() -> None:
    """Python says ``True == 1``; a fingerprint must not."""
    assert canonical_bytes(Lit(value=True)) != canonical_bytes(Lit(1))


def test_a_signed_integer_encodes_as_a_zigzag_varint() -> None:
    """-1 and 1 are one byte each, and they are not the same byte.

    An ``at_period`` offset is routinely negative. Two's complement would
    spell -1 as eight bytes of ones; zigzag keeps small magnitudes small in
    both directions.
    """
    assert canonical_bytes(Lit(1)) == b"\x02\x12\x02"
    assert canonical_bytes(Lit(-1)) == b"\x02\x12\x01"


def test_two_different_bands_are_two_different_calculations() -> None:
    """The failure this closes: every list literal used to fingerprint alike.

    A sequence written into a formula -- the age boundaries of a banded
    lookup, a schedule of loadings -- used to enter the tree as engine
    text, and that text is the engine's own abbreviated display of the
    values, not the values. Two bands that differ get one fingerprint,
    which is a positive claim of sameness about a model that changed.
    """
    forty_fives = local_fingerprint(Lit((45, 50, 55)))
    sixties = local_fingerprint(Lit((60, 65, 70)))

    assert forty_fives != sixties


def test_a_boundary_that_moves_in_the_middle_of_a_band_moves_the_fingerprint() -> None:
    """The case the engine's own display hid outright.

    Polars abbreviates a long sequence to its first two entries, an
    ellipsis and its last -- so two eight-boundary bands differing only
    in the middle rendered as one string and hashed as one calculation.
    An assumption change is exactly that shape.
    """
    before = Lit((18, 25, 35, 45, 55, 65, 75, 85))
    after = Lit((18, 25, 35, 46, 56, 66, 75, 85))

    assert local_fingerprint(before) != local_fingerprint(after)


def test_a_sequence_literal_and_the_same_scalar_do_not_collide() -> None:
    """A band holding one boundary is not that boundary."""
    assert local_fingerprint(Lit((45,))) != local_fingerprint(Lit(45))


def test_a_sequence_literal_encodes_as_a_counted_run_of_tagged_scalars() -> None:
    """The whole encoding of a sequence literal, spelled out byte by byte.

    The literal tag, then the sequence tag, then how many members, then
    each member behind its own scalar tag. The sequence tag is what keeps
    a one-member band from encoding as the scalar it holds.
    """
    assert canonical_bytes(Lit((1, 2))) == b"\x02\x15\x02\x12\x02\x12\x04"


def test_one_band_boundary_is_never_two() -> None:
    """One member spelled ``ab`` is not two spelled ``a`` and ``b``.

    The same claim the argument and dependency lists make, made for a
    sequence literal: the count is what delimits the run.
    """
    one = Lit(("ab",))
    two = Lit(("a", "b"))

    assert canonical_bytes(one) != canonical_bytes(two)


def test_a_reordered_band_is_a_different_band() -> None:
    """Order is part of what a sequence literal means, so it is in the bytes."""
    assert canonical_bytes(Lit((45, 50))) != canonical_bytes(Lit((50, 45)))


def test_a_sequence_member_keeps_its_own_type() -> None:
    """Inside a band, a whole number, its text and a flag stay three things."""
    variants = [Lit((1,)), Lit(("1",)), Lit((1.0,)), Lit((True,))]
    encoded = {canonical_bytes(node) for node in variants}

    assert len(encoded) == len(variants)


def test_multiplication_is_not_commutative_to_the_encoding() -> None:
    """``a * b`` and ``b * a`` are different structures, so different bytes.

    They are the same number. Fingerprints are structural identity, not
    numerical equivalence -- claiming otherwise would need an algebra the
    op-tree does not carry.
    """
    left = BinOp("mul", Col("a"), Col("b"))
    right = BinOp("mul", Col("b"), Col("a"))

    assert canonical_bytes(left) != canonical_bytes(right)


def test_a_call_encodes_its_name_then_a_counted_argument_list() -> None:
    """The whole encoding of a call, spelled out byte by byte.

    Tag, name behind its length, how many arguments, each argument, then
    how many attributes. Counting the arguments is what makes the run
    self-delimiting on its own terms rather than by an argument about
    which tag bytes happen not to collide with which length bytes.
    """
    assert canonical_bytes(Call("f", (Col("a"),))) == b"\x04\x01f\x01\x01\x01a\x00"


def test_an_engine_fragment_encodes_a_counted_dependency_list() -> None:
    """The declared reads are counted the same way an argument list is."""
    node = EngineNative("jax", "t", ("a",))

    assert canonical_bytes(node) == b"\x07\x03jax\x01t\x01\x01a"


def test_one_argument_is_never_two_arguments() -> None:
    """One argument called ``ab`` is not two called ``a`` and ``b``."""
    one = Call("f", (Col("ab"),))
    two = Call("f", (Col("a"), Col("b")))

    assert canonical_bytes(one) != canonical_bytes(two)


def test_one_declared_read_is_never_two() -> None:
    """The same claim for an engine fragment's declared reads."""
    one = EngineNative("polars", "t", ("ab",))
    two = EngineNative("polars", "t", ("a", "b"))

    assert canonical_bytes(one) != canonical_bytes(two)


def test_attributes_are_ordered_by_key_not_by_how_they_were_written() -> None:
    """Two records configured identically fingerprint identically."""
    one = Call("f", (), (("offset", -1), ("method", "compound")))
    two = Call("f", (), (("method", "compound"), ("offset", -1)))

    assert canonical_bytes(one) == canonical_bytes(two)


def test_an_attribute_value_keeps_its_own_type() -> None:
    """Five ways to say "one" that a lowering would treat as five things."""
    variants: list[AttrValue] = [1, "1", 1.0, True, None]
    encoded = {canonical_bytes(Call("f", (), (("n", value),))) for value in variants}

    assert len(encoded) == len(variants)


def test_an_attribute_value_that_moves_moves_the_bytes() -> None:
    """The whole worked case rests on this: a horizon is an attribute."""
    ninety_nine = Call("projection_set", (), (("until_value", 99),))
    hundred = Call("projection_set", (), (("until_value", 100),))

    assert canonical_bytes(ninety_nine) != canonical_bytes(hundred)


def test_a_non_finite_attribute_value_still_encodes() -> None:
    """An attribute is not validated the way a literal is, so it must not raise.

    ``Lit`` refuses a NaN at construction; a ``Call`` attribute has no such
    gate. Every NaN encodes the same way -- two runs that both produced one
    have not drifted -- and the two infinities stay distinct from it and
    from each other.
    """

    def encoded(value: float) -> bytes:
        return canonical_bytes(Call("f", (), (("x", value),)))

    distinct = {encoded(float("nan")), encoded(float("inf")), encoded(-float("inf"))}

    assert encoded(float("nan")) == encoded(float("nan"))
    assert len(distinct) == 3


def test_a_signed_zero_literal_has_its_own_bytes() -> None:
    """The two zeros are one number in the arithmetic and two literals here.

    Section 12.1 wrote them alike until ``gspv0-preview-3``, and the reason
    that was wrong is the vocabulary beside it: ``to_text`` spells them
    apart, ``sign`` reads the sign, and 11.1.25 gives a signed zero
    observable division semantics. An identity must not equate what an
    admitted operation can tell apart.
    """
    positive = canonical_bytes(Lit(0.0))
    negative = canonical_bytes(Lit(-0.0))

    assert positive != negative
    assert negative == b"\x02\x13" + struct.pack(">d", -0.0)
    assert positive == b"\x02\x13" + struct.pack(">d", 0.0)


def test_a_signed_zero_attribute_has_its_own_bytes_too() -> None:
    """An attribute reaches the same encoder and must not be normalised either."""

    def encoded(value: float) -> bytes:
        return canonical_bytes(Call("f", (), (("x", value),)))

    assert encoded(0.0) != encoded(-0.0)


def test_the_two_zeros_move_the_reading_nodes_and_nothing_else() -> None:
    """The finding this closes, end to end: one minus sign, one model change.

    The review's own model. A literal zero is written out and compared, and
    the comparison decides the answer -- so the two exports differ in what
    they computed, and used to agree in every digest they published.
    """

    def fingerprints(zero: float) -> dict[str, str]:
        frame = ActuarialFrame(pl.DataFrame({"point_id": [1]}))
        frame.zero = zero
        frame.text = frame.zero.to_text()
        frame.result = when(frame.text == "-0.0").then(100.0).otherwise(0.0)
        artifact = json.loads(GraphExporter(frame).export(frame.collect()))
        return {node["id"]: node["fingerprint"] for node in artifact["nodes"]}

    positive, negative = fingerprints(0.0), fingerprints(-0.0)

    assert positive["zero@1"] != negative["zero@1"]
    # And its readers, which is what makes the change report say so.
    assert positive["text@1"] != negative["text@1"]
    assert positive["result@1"] != negative["result@1"]


def test_engine_text_engine_and_dependencies_all_count() -> None:
    """An escape hatch is identified by all three of the things it carries."""
    base = EngineNative("polars", "col('a').cum_sum()", ("a",))
    variants = [
        EngineNative("jax", "col('a').cum_sum()", ("a",)),
        EngineNative("polars", "col('a').cum_prod()", ("a",)),
        EngineNative("polars", "col('a').cum_sum()", ("b",)),
    ]

    assert all(canonical_bytes(base) != canonical_bytes(v) for v in variants)


def test_a_literal_refuses_the_values_the_encoding_would_have_to_guess_at() -> None:
    """The gate the encoding relies on, asserted rather than assumed."""
    for bad in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError, match="not finite"):
            Lit(bad)


# --- what the bytes deliberately leave out ----------------------------------


def test_the_bytes_never_mention_the_column_being_defined() -> None:
    """A node hashes what it computes, not what it is called.

    This is what makes a rename a rename instead of a deletion and a new
    calculation, and it is why the graph digest has to hash name/hash
    *pairs* rather than a bag of hashes.
    """
    graph = fold(_tidy_frame())
    encoded = canonical_bytes(graph.op_trees["net_premium@1"])

    assert b"gross_premium" in encoded
    assert b"net_premium" not in encoded


def test_the_same_model_written_differently_fingerprints_identically() -> None:
    """Reformatting a model is not a model change.

    The two fixtures put their assignments on different lines, name their
    operands differently and disagree about comments. The graphs say so --
    the source locations differ -- and every fingerprint matches.
    """
    tidy, untidy = fold(_tidy_frame()), fold(_untidy_frame())

    locations = {
        graph.nodes["net_premium@1"].data.source_location for graph in (tidy, untidy)
    }
    assert len(locations) == 2, "the fixtures must really differ in the source"

    assert _locals(tidy) == _locals(untidy)
    assert _merkles(tidy) == _merkles(untidy)
    assert graph_fingerprint(tidy) == graph_fingerprint(untidy)


def test_two_columns_computed_the_same_way_share_a_local_fingerprint() -> None:
    """A collision by design, not an accident: the formula is the identity."""
    af = ActuarialFrame(pl.DataFrame({"a": [1.0, 2.0]}))
    af.x = af.a + 1
    af.y = af.a + 1
    locals_ = _locals(fold(af))

    assert locals_["x@1"] == locals_["y@1"]


# --- local, Merkle, and the leaves that have no formula ---------------------


def test_a_local_fingerprint_is_the_hash_of_the_canonical_bytes() -> None:
    """One layer, stated, so the framing below it can be read."""
    node = BinOp("mul", Col("a"), Lit(2.0))

    assert local_fingerprint(node) == hashlib.sha256(canonical_bytes(node)).digest()
    assert len(local_fingerprint(node)) == HEX_WIDTH // 2


def test_a_node_that_reads_nothing_still_hashes_its_local_fingerprint() -> None:
    """The Merkle layer is always applied, so every node is hashed alike."""
    node = Lit(1.0)

    assert fingerprint(node, ()) == hashlib.sha256(local_fingerprint(node)).digest()


def test_a_merkle_fingerprint_folds_in_what_the_node_reads_in_order() -> None:
    """Read order is bind order, and swapping two reads is a different node."""
    node = BinOp("sub", Col("a"), Col("b"))
    first, second = local_fingerprint(Col("a")), local_fingerprint(Col("b"))

    assert fingerprint(node, (first, second)) != fingerprint(node, (second, first))


def test_an_input_is_fingerprinted_by_its_name_and_its_type() -> None:
    """A column the data arrived with has no formula to hash, so it hashes itself."""

    def arriving(name: str, values: list[int] | list[float]) -> bytes:
        af = ActuarialFrame(pl.DataFrame({name: values}))
        af.total = af[name] * 2
        return _locals(fold(af))[name]

    age = arriving("issue_age", [40, 55])

    assert age != arriving("entry_age", [40, 55])
    assert age != arriving("issue_age", [40.0, 55.0])


def test_a_hole_and_an_input_of_the_same_name_are_different_leaves() -> None:
    """A column nothing accounts for is not the same claim as an arriving field.

    Both are leaves with a name and a dtype and no formula. Hashing them
    the same way would make "we cannot explain this column" and "the data
    supplied it" indistinguishable to anything comparing two quarters.
    """
    arrived = ActuarialFrame(pl.DataFrame({"a": [1.0], "lapse_reserve": [2.0]}))
    arrived.total = arrived.a * 2.0

    swapped = _frame_with_an_unexplained_column()

    explained = _locals(fold(arrived))["lapse_reserve"]

    assert explained != _locals(fold(swapped))["lapse_reserve"]


def test_a_hole_keeps_its_leaf_identity_on_a_frame_derived_from_it() -> None:
    """Adding a scenario axis is not the model starting to explain a column.

    The two leaf tags are what make "we cannot account for this" and "the
    data supplied it" different bytes. If a derived frame relabelled the
    first as the second, the quarter that added a scenario axis would
    report the column as changed -- and changed in the direction of being
    better explained than it is.
    """
    swapped = _frame_with_an_unexplained_column()
    arrived = ActuarialFrame(pl.DataFrame({"a": [1.0], "lapse_reserve": [2.0]}))
    arrived.total = arrived.a * 2.0

    before = _locals(fold(swapped))["lapse_reserve"]
    after = _locals(fold(with_scenarios(swapped, ["BASE", "UP"])))["lapse_reserve"]

    assert after == before
    assert after != _locals(fold(arrived))["lapse_reserve"]


# --- the graph digest -------------------------------------------------------


def test_folding_the_same_model_twice_gives_the_same_fingerprints() -> None:
    """Determinism, at every layer, on two independently built frames."""
    first, second = fold(_horizon_frame(100)), fold(_horizon_frame(100))

    assert _locals(first) == _locals(second)
    assert _merkles(first) == _merkles(second)
    assert graph_fingerprint(first) == graph_fingerprint(second)


def test_swapping_which_column_holds_which_formula_moves_the_graph() -> None:
    """The two models compute the same two numbers under swapped names.

    Every fingerprint in the first graph appears in the second, so a digest
    over a bag of hashes could not tell them apart. Hashing the name/hash
    pairs can, which is the point.
    """
    one = ActuarialFrame(pl.DataFrame({"base": [100.0]}))
    one.net_premium = one.base * 1.0
    one.net_expense = one.base * 2.0

    other = ActuarialFrame(pl.DataFrame({"base": [100.0]}))
    other.net_premium = other.base * 2.0
    other.net_expense = other.base * 1.0

    first, second = fold(one), fold(other)

    assert sorted(_merkles(first).values()) == sorted(_merkles(second).values())
    assert graph_fingerprint(first) != graph_fingerprint(second)


def test_the_graph_digest_names_the_column_each_fingerprint_belongs_to() -> None:
    """The same formula under a different column name is a different model.

    Both graphs hold the same two fingerprints, so a digest over the
    fingerprints alone -- in any order, sorted or not -- cannot tell them
    apart. Only hashing each fingerprint together with the name it belongs
    to can, which is why the digest hashes pairs.
    """
    one = ActuarialFrame(pl.DataFrame({"base": [100.0]}))
    one.net_premium = one.base * 1.0

    other = ActuarialFrame(pl.DataFrame({"base": [100.0]}))
    other.premium_net = other.base * 1.0

    first, second = fold(one), fold(other)

    assert sorted(_merkles(first).values()) == sorted(_merkles(second).values())
    assert graph_fingerprint(first) != graph_fingerprint(second)


def test_the_graph_digest_tracks_which_binding_a_later_read_resolved_to() -> None:
    """Same node ids, same local fingerprints -- but a genuinely different model.

    ``y`` is defined once in each graph as ``x * 3.0``, but whether that
    happens before or after ``x`` is redefined changes which binding of
    ``x`` the read resolves to at fold time: the redefinition is not
    written yet in one graph, and already written in the other. The two
    models compute different numbers -- 600.0 against 1500.0 -- from the
    same source lines in a different order.

    Every node id is the same set in both graphs, and every id's local
    fingerprint agrees between them: ``x@1`` is ``base * 2.0`` in both,
    ``x@2`` is ``base * 5.0`` in both, and ``y@1`` is the identical
    ``Col("x") * 3.0`` formula wherever it sits in the source. A digest
    built from local-fingerprint pairs instead of Merkle-fingerprint pairs
    could not tell these two graphs apart -- every pair would match. Only
    ``y@1``'s Merkle fingerprint differs, because it folds in the
    fingerprint of whichever binding of ``x`` it actually read, and that is
    exactly what has to move the graph digest.
    """

    def build(*, y_reads_early: bool) -> ActuarialFrame:
        af = ActuarialFrame(pl.DataFrame({"base": [100.0]}))
        af.x = af.base * 2.0
        if y_reads_early:
            af.y = af.x * 3.0
            af.x = af.base * 5.0
        else:
            af.x = af.base * 5.0
            af.y = af.x * 3.0
        return af

    early_value = build(y_reads_early=True).collect()["y"][0]
    late_value = build(y_reads_early=False).collect()["y"][0]
    assert (early_value, late_value) == (600.0, 1500.0), (
        "the fixture must compute two different numbers"
    )

    early, late = fold(build(y_reads_early=True)), fold(build(y_reads_early=False))

    # Non-vacuity: the failure this pins is invisible unless both graphs
    # share every node id and agree on every local fingerprint.
    assert set(early.nodes) == set(late.nodes) == {"base", "x@1", "x@2", "y@1"}
    assert _locals(early) == _locals(late)

    assert graph_fingerprint(early) != graph_fingerprint(late)


def test_a_column_nothing_accounts_for_moves_the_graph_fingerprint() -> None:
    """A model that stopped explaining one of its columns is a changed model."""
    explained = ActuarialFrame(pl.DataFrame({"a": [1.0]}))
    explained.total = explained.a * 2.0

    unexplained = _frame_with_an_unexplained_column()

    assert graph_fingerprint(fold(explained)) != graph_fingerprint(fold(unexplained))


def test_the_assumption_table_a_lookup_reads_is_part_of_the_graphs_identity() -> None:
    """Same table name, same model code, different rates -- a different model.

    The table's content hash rides on the lookup node, so this moves the
    node's own local fingerprint as well as the graph digest. An actuary
    who reloads an updated mortality basis and reruns gets a graph that
    says the basis moved.
    """
    before = fold(_lookup_frame(_mortality_table("fingerprint_mortality", 0.0005)))
    after = fold(_lookup_frame(_mortality_table("fingerprint_mortality", 0.0009)))

    assert _locals(before)["mortality_rate@1"] != _locals(after)["mortality_rate@1"]
    assert graph_fingerprint(before) != graph_fingerprint(after)


def test_handing_over_hashes_already_taken_leaves_the_digest_alone() -> None:
    """The same answer, one pass instead of two.

    An export stamps every node and then needs one string standing for the
    model, and both are the same digests. Handing the stamp's own answer
    over saves hashing every operation tree a second time, and the digest
    a reader compares quarter to quarter must not depend on which of the
    two the producer happened to do.
    """
    graph = fold(_tidy_frame())

    taken_here = graph_fingerprint(graph)
    handed_over = graph_fingerprint(graph, prints=stamp_fingerprints(graph))

    assert handed_over == taken_here


# --- an injected column is identified by its contents -----------------------


def test_two_injections_with_different_values_fingerprint_differently() -> None:
    """Two models handed different data under one column name are two models.

    A stochastic model injects its simulated series wholesale, and nothing
    upstream of that column can report the change: an injection reads
    nothing, so the Merkle layer has nothing to fold in. The values
    themselves are the only thing that can carry the difference.
    """
    a = _model_with_injection([1.0, 2.0, 3.0])
    b = _model_with_injection([1.0, 2.0, 4.0])

    assert _injection_local(a) != _injection_local(b)
    assert a.graph.fingerprint() != b.graph.fingerprint()


def test_two_injections_with_the_same_values_fingerprint_alike() -> None:
    """The same values injected twice are one model, rerun."""
    a = _model_with_injection([1.0, 2.0, 3.0])
    b = _model_with_injection([1.0, 2.0, 3.0])

    assert _injection_local(a) == _injection_local(b)
    assert a.graph.fingerprint() == b.graph.fingerprint()


def test_the_series_own_name_is_not_part_of_its_identity() -> None:
    """The column's name is the assignment key; the series' name is incidental."""
    a = _model_with_injection([1.0, 2.0, 3.0], series_name="x")
    b = _model_with_injection([1.0, 2.0, 3.0], series_name="y")

    assert a.graph.fingerprint() == b.graph.fingerprint()


def test_an_injection_records_a_content_stamp() -> None:
    """The record says both that values were injected and which values."""
    af = _model_with_injection([1.0, 2.0, 3.0])

    attrs = dict(_injection_attrs(af))

    assert attrs["origin"] == "series"
    assert isinstance(attrs["content"], str)
    assert re.fullmatch(rf"{SHA256_PREFIX}[0-9a-f]{{64}}", attrs["content"])


def test_the_stamp_is_the_content_hash_of_the_values_under_a_fixed_name() -> None:
    """The recipe, written out, so two processes agree on the same values.

    The framework's one content-identity primitive over a one-column frame
    built under a fixed name -- which is what keeps the series' own name
    out of the answer while the values, their type and their count stay in
    it.
    """
    af = _model_with_injection([1.0, 2.0, 3.0], series_name="simulated_deaths")

    assert dict(_injection_attrs(af))["content"] == content_sha_of(
        pl.Series("injected", [1.0, 2.0, 3.0]).to_frame()
    )


def test_a_missing_value_is_not_a_zero_at_the_same_position() -> None:
    """A rate nobody supplied and a rate of nought are different assumptions.

    They project differently -- one propagates a null, the other multiplies
    a reserve to zero -- so a run on one is not a run on the other, and the
    stamp has to be able to say so.
    """
    missing = _model_with_injection([1.0, None, 3.0])
    zeroed = _model_with_injection([1.0, 0.0, 3.0])

    assert _injection_local(missing) != _injection_local(zeroed)


def test_a_single_precision_column_is_the_rounding_it_did_not_the_width() -> None:
    """Storage width is not the identity; the numbers that width changed are.

    Injecting simulated returns as Float32 to halve the memory is a real
    decision with real rounding behind it, and a reviewer comparing this
    quarter to last should see the rounding -- which is a set of moved
    numbers, visible wherever narrowing actually moved one. Half the width
    with nothing rounded is a storage decision and nothing else, and
    stamping it as a model change would fire the alarm over a column
    holding exactly the values it held last quarter.
    """
    exact = ActuarialFrame({"policy_id": [1, 2, 3]})
    exact.shock = pl.Series("", [1.0, 2.0, 3.0], dtype=pl.Float32)
    rounded = ActuarialFrame({"policy_id": [1, 2, 3]})
    rounded.shock = pl.Series("", [0.1, 0.2, 0.3], dtype=pl.Float32)

    assert _injection_local(exact) == _injection_local(
        _model_with_injection([1.0, 2.0, 3.0])
    )
    assert _injection_local(rounded) != _injection_local(
        _model_with_injection([0.1, 0.2, 0.3])
    )


def test_a_reordered_series_is_a_different_injection() -> None:
    """Row order *is* the identity of an injection, because position is meaning.

    An injected column lands on the frame's rows by position: the second
    value belongs to the second policy. Two orderings of the same numbers
    are two different assignments of values to policies. This is
    deliberately the opposite of the stamp a join's right side carries,
    which sorts the rows first -- a lookup table is reached by key, so the
    order it happened to be loaded in means nothing.
    """
    ascending = _model_with_injection([1.0, 2.0, 3.0])
    descending = _model_with_injection([3.0, 2.0, 1.0])

    assert _injection_local(ascending) != _injection_local(descending)


def test_a_column_of_python_objects_is_refused_at_the_assignment() -> None:
    """The one dtype that cannot be a column of a model is refused, not stamped.

    Nothing can project, discount or stamp a column of Python objects, so
    the assignment is turned back at the line that wrote it rather than
    accepted and found unusable later.
    """
    af = ActuarialFrame({"policy_id": [1, 2, 3]})

    with pytest.raises(TypeError, match="Object"):
        af.shock = pl.Series("", [object(), object(), object()], dtype=pl.Object)


# --- an injected array is identified the same way ---------------------------


def test_two_arrays_with_different_values_fingerprint_differently() -> None:
    """The array is the shape a simulation actually hands back.

    ``rng.binomial(...)`` returns an array, not a series, so the input
    class the stochastic pattern teaches is the one that most needs its
    values in the stamp. Nothing upstream can carry the difference for it:
    an injection reads nothing however it arrived.
    """
    a = _model_with_array_injection(np.array([1.0, 2.0, 3.0]))
    b = _model_with_array_injection(np.array([1.0, 2.0, 4.0]))

    assert _injection_local(a) != _injection_local(b)
    assert a.graph.fingerprint() != b.graph.fingerprint()


def test_two_arrays_with_the_same_values_fingerprint_alike() -> None:
    """The same simulated paths injected twice are one model, rerun."""
    a = _model_with_array_injection(np.array([1.0, 2.0, 3.0]))
    b = _model_with_array_injection(np.array([1.0, 2.0, 3.0]))

    assert _injection_local(a) == _injection_local(b)
    assert a.graph.fingerprint() == b.graph.fingerprint()


def test_an_array_and_a_series_of_the_same_values_carry_one_stamp() -> None:
    """The stamp is over the values, so the container it arrived in is not in it.

    ``origin`` is the only thing that separates the two records, and it is
    audit detail rather than identity: it says how the values reached the
    column, which is the part a reviewer reading the record wants back.
    """
    from_array = _model_with_array_injection(np.array([1.0, 2.0, 3.0]))
    from_series = _model_with_injection([1.0, 2.0, 3.0])

    assert (
        dict(_injection_attrs(from_array))["content"]
        == dict(_injection_attrs(from_series))["content"]
    )


def test_an_injected_array_records_where_the_values_came_from() -> None:
    """The record says both which values were injected and how they arrived."""
    af = _model_with_array_injection(np.array([1.0, 2.0, 3.0]))

    attrs = dict(_injection_attrs(af))

    assert attrs["origin"] == "array"
    assert isinstance(attrs["content"], str)
    assert re.fullmatch(rf"{SHA256_PREFIX}[0-9a-f]{{64}}", attrs["content"])


def test_the_array_stamp_is_the_content_hash_of_its_values_under_a_fixed_name() -> None:
    """The recipe, written out, so an array and a series can be compared at all."""
    af = _model_with_array_injection(np.array([1.0, 2.0, 3.0]))

    assert dict(_injection_attrs(af))["content"] == content_sha_of(
        pl.Series("injected", [1.0, 2.0, 3.0]).to_frame()
    )


def test_an_array_of_python_objects_is_refused_at_the_assignment() -> None:
    """An object array becomes an object column, and that is what is refused.

    The dtype is the reason, not the container it arrived in, so the array
    is turned back at the same line and for the same reason a series of
    Python objects is.
    """
    af = ActuarialFrame({"policy_id": [1, 2, 3]})

    with pytest.raises(TypeError, match="Object"):
        af.shock = np.array([object(), object(), object()], dtype=object)


def test_a_two_dimensional_array_is_stamped_as_the_column_it_becomes() -> None:
    """A shape the frame already accepts is a shape the stamp has to cover.

    An ``(n, k)`` array lands as one fixed-width column of k values per
    row -- a simulated path per policy -- which is a column a model can
    hold, so it is not refused for its shape. Two different sets of paths
    under one name are two different models, exactly as in one dimension.
    """
    two_by_two = ActuarialFrame({"policy_id": [1, 2]})
    two_by_two.shock = np.array([[1.0, 2.0], [3.0, 4.0]])
    one_path_moved = ActuarialFrame({"policy_id": [1, 2]})
    one_path_moved.shock = np.array([[1.0, 2.0], [3.0, 5.0]])

    assert dict(_injection_attrs(two_by_two))["origin"] == "array"
    assert _injection_local(two_by_two) != _injection_local(one_path_moved)


def test_a_refused_injection_names_the_column_the_author_wrote() -> None:
    """The placeholder the values are hashed under is not a name to refuse under.

    The series' own name is kept out of the stamp on purpose -- the
    column's name is the assignment key -- so the values are encoded under
    a fixed placeholder. A refusal taken on the way through must still
    reach the author naming the column they actually wrote: a message
    about a column nobody named sends them looking for a line that is not
    in the model.
    """
    af = ActuarialFrame({"policy_id": [1, 2, 3]})

    with pytest.raises(UnmappedDtypeError) as raised:
        af.shock = pl.Series(["preferred", "standard"], dtype=pl.Categorical)

    message = str(raised.value)
    assert "'shock'" in message
    assert "injected" not in message


def test_a_rank_zero_array_is_the_scalar_it_holds_not_a_column() -> None:
    """One number is one number, however it was spelt.

    Polars broadcasts a rank-0 array across every row exactly as it
    broadcasts a float, so what lands is a column of n copies. Recording
    it as an injection would stamp a count of one against that column and
    call a literal an input; it takes the same node the number itself
    takes.
    """
    from_array = ActuarialFrame({"policy_id": [1, 2, 3]})
    from_array.shock = np.array(3.0)
    from_scalar = ActuarialFrame({"policy_id": [1, 2, 3]})
    from_scalar.shock = 3.0

    assert from_array.collect()["shock"].to_list() == [3.0, 3.0, 3.0]
    assert _node_for(from_array, "shock") == Lit(3.0)
    assert _node_for(from_array, "shock") == _node_for(from_scalar, "shock")


# --- an Object anywhere in the dtype is refused -----------------------------


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_a_column_of_lists_of_python_objects_is_refused_at_the_assignment() -> None:
    """The dtype is walked, not just read at the top.

    ``List(Object)`` clears a top-level Object test. Without the walk it
    would reach the injection stamp, which does refuse it -- an
    ``UnmappedDtypeError`` naming the column -- but refuses it as a type
    the calculation graph has no name for, which answers about the
    artifact's own vocabulary rather than about what the author did. The
    walk is what makes one refusal, at the line that wrote the column,
    cover both nested shapes and say the thing that is actually wrong: a
    column of Python objects is not a column of a model. Its sibling below
    needs the walk for a harder reason.

    Polars cannot free such a column cleanly -- releasing it panics in a
    Rust destructor, which Python reports as an unraisable exception -- so
    this test is one of the few in the suite that has to build one, and it
    silences that panic rather than leaving every green run carrying a
    warning about someone else's drop.
    """
    af = ActuarialFrame({"policy_id": [1]})
    objects = pl.Series("", [object(), object()], dtype=pl.Object)

    with pytest.raises(TypeError, match=r"List\(Object\)"):
        af.shock = objects.implode()


def test_a_fixed_width_column_of_python_objects_is_refused_at_the_assignment() -> None:
    """``Array(Object, n)`` is the other nesting a Series can actually hold.

    A fixed-width column of Float64 is a simulated path per policy and is
    stamped rather than refused; the same shape holding Python objects is
    refused, because it is the dtype that cannot be a column of a model,
    never the width.
    """
    af = ActuarialFrame({"policy_id": [1]})
    objects = pl.Series("", [object(), object()], dtype=pl.Object)

    with pytest.raises(TypeError, match=r"Array\(Object"):
        af.shock = objects.reshape((1, 2))


def test_a_two_dimensional_array_of_objects_is_refused_at_the_assignment() -> None:
    """The other door onto the same dtype: an ``(n, k)`` array of objects.

    A one-dimensional object array lands as a plain ``Object`` column; add
    a dimension and Polars nests it as ``Array(Object, k)`` instead. Both
    are the same mistake, so both are turned back at the same line.
    """
    af = ActuarialFrame({"policy_id": [1, 2]})

    with pytest.raises(TypeError, match=r"Array\(Object"):
        af.shock = np.array([[object(), object()], [object(), object()]], dtype=object)


def test_an_object_inside_a_struct_is_refused_by_the_dtype_walk() -> None:
    """A struct field is walked too, checked on the dtype because Polars refuses one.

    Polars will not build a Series over ``Struct({...: Object})`` by any
    route -- the constructor panics with "nested objects are not allowed" --
    so there is no assignment to make here. The walk still covers the
    shape: what Polars refuses to construct today it may construct
    tomorrow, and a check that quietly stopped at struct fields would be
    the kind of hole nobody finds until a run dies.
    """
    assert _holds_python_objects(pl.Struct({"paths": pl.Object}))
    assert _holds_python_objects(pl.List(pl.Struct({"paths": pl.List(pl.Object)})))


def test_a_nested_dtype_with_no_object_in_it_is_left_alone() -> None:
    """The walk refuses an Object, not nesting: the projection's own shape is nested.

    Every list column a projection produces is ``List(Float64)``, and a
    fixed-width simulated path is ``Array(Float64, k)``. A check that read
    "nested" as "suspect" would refuse the framework's ordinary output.
    """
    assert not _holds_python_objects(pl.List(pl.Float64))
    assert not _holds_python_objects(pl.Array(pl.Float64, 12))
    assert not _holds_python_objects(pl.Struct({"balance": pl.Float64}))

    af = ActuarialFrame({"policy_id": [1]})
    af.shock = pl.Series("", [[1.0, 2.0, 3.0]])

    assert dict(_injection_attrs(af))["origin"] == "series"


# --- stamping ---------------------------------------------------------------


def test_a_folded_graph_carries_no_fingerprints_until_it_is_asked() -> None:
    """Folding is the cheap structural pass; hashing is a separate decision.

    The fold runs on paths that will never want a fingerprint -- reporting
    a model's unaccounted-for columns, formatting an error -- and hashing
    every op-tree there would be work nobody asked for.
    """
    graph = fold(_tidy_frame())

    assert all(node.data.fingerprint is None for node in graph.nodes.values())
    assert all(node.data.local_fingerprint is None for node in graph.nodes.values())


def test_stamping_writes_the_sha256_prefixed_stamp_on_every_node() -> None:
    """Storage is the framework's own scheme; only display is abbreviated."""
    graph = fold(_tidy_frame())
    stamp_fingerprints(graph)

    for node in graph.nodes.values():
        assert node.data.fingerprint is not None
        assert node.data.local_fingerprint is not None
        assert len(node.data.fingerprint) == len(SHA256_PREFIX) + HEX_WIDTH
        assert len(node.data.local_fingerprint) == len(SHA256_PREFIX) + HEX_WIDTH
        assert node.data.fingerprint.startswith(SHA256_PREFIX)
        assert node.data.local_fingerprint.startswith(SHA256_PREFIX)


def test_a_stamped_fingerprint_matches_the_frameworks_sha256_convention() -> None:
    """The stamp is the same shape as every other identity hash in the framework.

    Compared to ``source_sha_of``'s own shape, not to a literal "sha256:"
    written a second time here -- the two agree because they share one
    constant, not because this test repeats it.
    """
    graph = fold(_tidy_frame())
    stamp_fingerprints(graph)

    reference_scheme, _, reference_hex = source_sha_of({"probe": "shape"}).partition(
        ":"
    )

    for node in graph.nodes.values():
        for stamped in (node.data.local_fingerprint, node.data.fingerprint):
            assert stamped is not None
            scheme, _, hex_part = stamped.partition(":")
            assert scheme == reference_scheme
            assert len(hex_part) == len(reference_hex)
            assert hex_part == hex_part.lower()
            assert all(char in "0123456789abcdef" for char in hex_part)


def test_a_stamped_fingerprint_is_the_one_the_computation_produced() -> None:
    """Stamping copies, it does not re-derive."""
    graph = fold(_tidy_frame())
    computed = fingerprints_for(graph)
    stamp_fingerprints(graph)

    for node_id, node in graph.nodes.items():
        assert (
            node.data.local_fingerprint
            == f"{SHA256_PREFIX}{computed[node_id].local.hex()}"
        )
        assert (
            node.data.fingerprint == f"{SHA256_PREFIX}{computed[node_id].merkle.hex()}"
        )


def test_a_display_fingerprint_is_the_first_twelve_characters() -> None:
    """Twelve hex is what a reviewer reads; it accepts either storage form."""
    digest = local_fingerprint(Col("a"))

    assert short_fingerprint(digest) == digest.hex()[:DISPLAY_WIDTH]
    assert short_fingerprint(digest.hex()) == digest.hex()[:DISPLAY_WIDTH]
    assert len(short_fingerprint(digest)) == DISPLAY_WIDTH


def test_a_display_fingerprint_strips_the_scheme_prefix_when_stamped() -> None:
    """A stamped ``sha256:<hex>`` value displays as bare hex, git-style."""
    graph = fold(_tidy_frame())
    stamp_fingerprints(graph)
    stamped = next(iter(graph.nodes.values())).data.fingerprint
    assert stamped is not None

    displayed = short_fingerprint(stamped)

    assert displayed == stamped.split(":", 1)[1][:DISPLAY_WIDTH]
    assert len(displayed) == DISPLAY_WIDTH
    assert ":" not in displayed


# --- what a change reaches, and what it must not ----------------------------


def test_the_columns_a_horizon_change_cannot_reach_do_not_move() -> None:
    """A horizon of 99 becomes 100, and no digest moves that has no business to.

    Both digests are checked on each of the three columns that sit above the
    timeline: neither their formulas nor anything they read was touched, so a
    fingerprint that moved here would be a false alarm in the one report whose
    value is its silence.
    """
    before, after = fold(_horizon_frame(99)), fold(_horizon_frame(100))
    unchanged = ("policy_id", "issue_age", "sum_assured")

    for node_id in unchanged:
        assert _locals(before)[node_id] == _locals(after)[node_id]
        assert _merkles(before)[node_id] == _merkles(after)[node_id]


# --- refusing to answer wrongly ---------------------------------------------


def test_a_graph_whose_nodes_are_held_out_of_order_is_refused() -> None:
    """A Merkle fingerprint needs its dependencies computed first.

    The fold hands its nodes over in log order, which is already
    topological. A graph rearranged afterwards cannot be fingerprinted
    truthfully, so it is refused by name rather than answered with a hash
    that silently dropped an upstream dependency.
    """
    graph = fold(_tidy_frame())
    graph.nodes = dict(reversed(list(graph.nodes.items())))

    with pytest.raises(ValueError, match="reserve@1"):
        fingerprints_for(graph)


def test_a_node_that_computes_and_lost_its_tree_is_not_hashed_as_a_leaf() -> None:
    """Three kinds are identified by a name and a type; nothing else may be.

    A column the data arrived with, a column nothing accounts for and a
    running rollforward state have no formula, so their bytes are the name
    and the neutral type. Every other node was folded from an operation tree
    and is identified by what it computes. One arriving here without a tree
    is a fold that lost it, and taking a leaf's bytes over it would identify
    a calculation by the column it happens to be called -- which gives two
    columns computed differently one digest, silently, in the field whose
    whole job is to say whether a number can still be what it was.
    """
    graph = fold(_tidy_frame())
    del graph.op_trees["reserve@1"]

    with pytest.raises(ValueError, match="no operation tree behind it"):
        fingerprints_for(graph)


def test_a_digest_from_fingerprints_that_are_not_this_graphs_is_refused() -> None:
    """Hashes that do not cover this graph's nodes answer for a model that is gone.

    A digest taken over a mapping that has drifted is still sixty-four hex
    digits and still compares equal to itself, so it is refused by name
    rather than returned. Here the mapping is short of a node the graph
    holds.

    Both sides of the comparison are named in the message, whichever one
    the caller actually tripped: which nodes are missing and which are
    surplus is what says whether they are holding a stale mapping or
    another model's, and a message naming only the side that happened to
    be non-empty leaves the reader to work out which question was
    answered.
    """
    graph = fold(_tidy_frame())
    prints = stamp_fingerprints(graph)
    stale = {
        node_id: taken for node_id, taken in prints.items() if node_id != "reserve@1"
    }

    with pytest.raises(ValueError, match="reserve@1") as refusal:
        graph_fingerprint(graph, prints=stale)

    message = str(refusal.value)
    assert "Nodes in the graph with no fingerprint offered" in message
    assert "Fingerprints offered for nodes the graph does not hold" in message


def test_a_digest_from_fingerprints_for_a_node_the_graph_lacks_is_refused() -> None:
    """The other direction: a mapping carrying a node this graph never held.

    Covering the graph's nodes is not the same as being the graph's
    mapping. A mapping holding every node the graph holds *and one more*
    was taken over something else, and a digest folded from it would be a
    number for a model nobody ran.
    """
    graph = fold(_tidy_frame())
    prints = stamp_fingerprints(graph)
    surplus = {**prints, "surrender_value@1": prints["reserve@1"]}

    with pytest.raises(ValueError, match="surrender_value@1"):
        graph_fingerprint(graph, prints=surplus)


# --- the date tag ------------------------------------------------------------


def test_the_flagships_own_date_encodes_as_the_five_bytes_the_grammar_states() -> None:
    """The worked example section 12.1 prints, reproduced from the encoder.

    ``2024-01-01`` is 19 723 days after the epoch; zigzagged that is 39 446,
    and as a varint, low group first, ``96 b4 02``. The literal tag, the date
    tag, three bytes of count. A second implementation reading only the words
    of that section has to reach this and nothing else.
    """
    assert canonical_bytes(Lit(datetime.date(2024, 1, 1))) == bytes.fromhex(
        "021696b402"
    )


@pytest.mark.parametrize(
    ("day", "encoded"),
    [
        pytest.param(datetime.date(1970, 1, 1), "1600", id="the epoch is nought"),
        pytest.param(datetime.date(1970, 1, 2), "1602", id="one day after"),
        pytest.param(datetime.date(1969, 12, 31), "1601", id="one day before"),
    ],
)
def test_a_date_encodes_as_a_zigzag_varint_of_days_from_the_epoch(
    day: datetime.date, encoded: str
) -> None:
    """The three boundary cases the grammar spells out by name.

    A count of days and never of seconds, forward from 1970-01-01, on the
    proleptic Gregorian calendar with no time zone and no offset applied.
    """
    assert canonical_bytes(Lit(day)) == b"\x02" + bytes.fromhex(encoded)


def test_a_date_and_the_text_that_spells_it_are_two_literals() -> None:
    """The whole reason the wire form is a key and not a spelling.

    A producer that wrote the date under ``value`` would have written the
    text, which encodes as the string tag and its eleven bytes and reaches a
    well-formed digest matching nothing.
    """
    assert canonical_bytes(Lit(datetime.date(2024, 1, 1))) != canonical_bytes(
        Lit("2024-01-01")
    )


def test_an_instant_is_refused_before_it_can_encode_as_its_own_day() -> None:
    """The trap the ordering of the two branches exists against.

    ``datetime.datetime`` is a subclass of ``datetime.date`` in Python, so a
    producer testing for the date first would encode an instant as its
    calendar day and lose the time in silence -- the same shape of mistake as
    encoding a flag as the whole number 1. All three doors refuse it: the
    literal's own, the encoder's, and the wire's.
    """
    with pytest.raises(TypeError, match="instant"):
        Lit(datetime.datetime(2024, 1, 1, 9, 30, tzinfo=datetime.UTC))

    with pytest.raises(TypeError, match="time of day"):
        _scalar(datetime.datetime(2024, 1, 1, 9, 30, tzinfo=datetime.UTC))


def test_a_date_is_a_literals_whole_payload_and_never_a_member_of_a_band() -> None:
    """The boundary the type states and the constructor enforces.

    The moment the scalar encoder learns the date tag, a tuple of dates
    becomes hashable as a sequence of them -- while the wire has no way to
    spell one, since a date arrives under its own key and a sequence has no
    key to give a member. Left open, the tree would accept a shape the wire
    cannot write.
    """
    with pytest.raises(TypeError, match="not a valid member of a sequence"):
        Lit((datetime.date(2018, 1, 1), datetime.date(2021, 6, 1)))


def test_a_date_membership_set_is_still_an_engine_fragment() -> None:
    """The remainder this change deliberately leaves, named as one.

    ``is_in`` is a core identifier whose membership set is an operand, and a
    set of dates is the one operand form the tree cannot hold. The line stays
    an engine fragment and the node says so, which is what this format says
    about every calculation it cannot yet spell.
    """
    frame = ActuarialFrame(pl.DataFrame({"entry_date": [datetime.date(2018, 1, 1)]}))
    frame.reformed = frame.entry_date.polars_native().is_in(
        [datetime.date(2018, 1, 1), datetime.date(2021, 6, 1)]
    )
    artifact = json.loads(GraphExporter(frame).export(profile="executable"))
    (node,) = [n for n in artifact["nodes"] if n["id"] == "reformed@1"]

    assert node["tier"] == "engine_native"


def test_the_producer_writes_a_date_literal_now_that_the_token_has_moved() -> None:
    """The emission was built behind a switch and turned on with the token.

    A date literal encodes under a tag the grammar did not have, and a new
    tag moves ``fingerprint_algorithm`` -- for any grammar change at all.
    Emitting one while that token still read ``gspv0-preview-1`` would have
    put bytes of the new grammar inside a document announcing the old one,
    which is the single thing the token exists to make impossible. Both moved
    in one commit, and this is the producer's half of it.
    """
    from gaspatchio.frame.lowering.ingress import DATE_LITERALS_BY_DEFAULT, to_node

    assert DATE_LITERALS_BY_DEFAULT is True

    written = to_node(datetime.date(2024, 1, 1))

    assert written == Lit(datetime.date(2024, 1, 1))
    assert not isinstance(written, EngineNative)


def test_the_wire_carries_a_date_under_its_own_key() -> None:
    """JSON has a number token and no date token, so the key carries it."""
    assert op_node_to_json(Lit(datetime.date(2024, 1, 1))) == {
        "op": "lit",
        "date": "2024-01-01",
    }
    assert op_node_from_json({"op": "lit", "date": "2024-01-01"}) == Lit(
        datetime.date(2024, 1, 1)
    )


@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param("2024-01-01T00:00:00", id="an instant"),
        pytest.param("20240101", id="the compact form"),
        pytest.param("2024-1-1", id="unpadded"),
        pytest.param("2024-01-01Z", id="a zone"),
        pytest.param("+002024-01-01", id="an expanded year"),
    ],
)
def test_only_one_spelling_of_a_day_is_read(spelling: str) -> None:
    """Wider forms are refused rather than accommodated.

    The value hashed is the day count, so two spellings of one day would be
    one digest under two documents, and a consumer checking one against the
    other could not say which spelling the producer wrote.
    """
    with pytest.raises(ValueError, match="ISO 8601"):
        op_node_from_json({"op": "lit", "date": spelling})
