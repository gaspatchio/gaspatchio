# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An accumulation states the convention it ran under.

"Is this survival beginning-of-period or end-of-period?" is the first
question a reviewing actuary puts to a survival curve. The figures alone do
not answer it, and a flat-rate test can pass a model converted wrongly
between the two conventions -- so a model struck under the wrong one can
pass every test it has. The record is where that is caught, and only if the
convention is printed on it.

So a node whose whole calculation is one of the two accumulations that name
a convention carries ``settings``: the section 11 attributes of that call,
quoted with the names and the values the operation tree writes. The tests
below are that claim from both ends -- the four shapes stating theirs, every
other node stating none, the four validator refusals, and the digest
unmoved, because the values restate attributes the canonical bytes already
carry and the member itself sits outside them.
"""

from __future__ import annotations

import copy
import datetime
import json
from typing import Any, Final

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact

# The digest of the model below, measured on the producer that had never
# heard of ``settings``. It is pinned here rather than recomputed because
# that is the whole claim: the member restates attributes already inside the
# canonical bytes and sits outside them itself, so a node that gained a
# stated convention is the same calculation it was before.
#
# Re-pinned once, by W3-D9b(a): the linear recurrence's tree now carries
# ``reverse: false`` (section 11.1.20), an attribute inside the canonical
# bytes. With that one attribute left out the producer still gives the
# digest taken before ``settings`` existed,
# sha256:97495fcb70a4c3d338597f5042636ac79be2afae722dc53ad7c2757663ebf9a7.
_GRAPH_FINGERPRINT: Final[str] = (
    "sha256:3c27a5805a1ea5842c732f983d9e98aece7f29ff0a674300fe63db36967b3e26"
)


def _the_model() -> ActuarialFrame:
    """Return a six-month run holding one of each shape a convention comes in.

    A survival fold under its default and the same fold recorded
    end-of-period; a prospective value struck on a rate and another struck
    on a factor at the opening of each period; the same survival fold
    nested inside a multiplication, where the node is the multiplication;
    and a linear recurrence, which accumulates and states no convention.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["A"],
                "sum_assured": [100_000.0],
                "annual_decrement": [0.012],
                "annual_discount": [0.03],
            }
        )
    )
    af = frame.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=6, frequency="monthly"
    )
    af.monthly_decrement = (af.annual_decrement / 12).projection.broadcast_to_periods(
        like=af.month
    )
    af.survival = af.monthly_decrement.projection.cumulative_survival()
    af.survival_to_the_period_end = af.monthly_decrement.projection.cumulative_survival(
        rate_timing="end_of_period"
    )
    af.claims = af.sum_assured * af.monthly_decrement * af.survival
    af.reserve_on_a_rate = af.claims.projection.prospective_value(discount_rate=0.0025)
    af.discount_factor = (
        1.0 / (1.0 + af.annual_discount / 12)
    ).projection.broadcast_to_periods(like=af.month)
    af.reserve_on_a_factor = af.claims.projection.prospective_value(
        discount_factor=af.discount_factor, timing="beginning_of_period"
    )
    af.scaled_survival = (
        af.sum_assured * af.monthly_decrement.projection.cumulative_survival()
    )
    af.fund = af.claims.projection.accumulate(
        initial=1_000.0, multiplier=1.0, addend=af.claims
    )
    return af


def _exported() -> dict[str, Any]:
    """Return the artifact that model exports, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(GraphExporter(_the_model()).export())
    return artifact


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    (found,) = [entry for entry in artifact["nodes"] if entry["id"] == node_id]
    return found


# --- the four shapes a stated convention comes in ----------------------------


def test_a_survival_fold_under_its_default_says_it_opens_at_the_boundary() -> None:
    """1.0 is beginning-of-period timing, in the format's own name for it.

    Not ``rate_timing``: the accessor's keyword is the actuary's word for
    the choice, and what the record keeps is the value the operation runs
    on, which 11.1.19 defines. A producer renaming it here would have the
    format naming one convention twice.
    """
    assert _node(_exported(), "survival@1")["settings"] == {
        "start_at": 1.0,
        "from_survival": False,
    }


def test_a_survival_fold_recorded_end_of_period_says_so_with_a_null() -> None:
    """The null is a claim rather than a gap, and 11.1.19 is what it says.

    This is the case that tells a quoted value from a guessed one. Written
    ``rate_timing="end_of_period"`` by the actuary, the operation records
    ``start_at`` null -- and a producer inferring a convention from the
    formula text would have had to invent the word back again.
    """
    assert _node(_exported(), "survival_to_the_period_end@1")["settings"] == {
        "start_at": None,
        "from_survival": False,
    }


def test_a_prospective_value_on_a_rate_states_its_timing_and_its_operand() -> None:
    """Which period the cashflow lands in, and what the second operand is."""
    assert _node(_exported(), "reserve_on_a_rate@1")["settings"] == {
        "timing": "end_of_period",
        "discount_kind": "rate",
    }


def test_a_prospective_value_on_a_factor_says_it_is_a_factor() -> None:
    """Nothing else in the record says which of the two the operand is.

    A factor read as a rate is a valuation error rather than a parse error:
    the arithmetic runs, the numbers come out, and they are wrong by
    roughly the discount itself.
    """
    assert _node(_exported(), "reserve_on_a_factor@1")["settings"] == {
        "timing": "beginning_of_period",
        "discount_kind": "factor",
    }


# --- and every other node states none -----------------------------------------


def test_an_accumulation_nested_in_a_larger_formula_states_nothing() -> None:
    """What this node computes is the multiplication, not the fold inside it.

    A reader of a node's settings must never have to ask which of two
    operations they describe. The convention travels where a nested call's
    configuration has always travelled: in the executable profile's tree.
    """
    assert "settings" not in _node(_exported(), "scaled_survival@1")


def test_an_ordinary_node_states_nothing_at_all() -> None:
    """Most nodes have no convention, and say so by saying nothing."""
    assert "settings" not in _node(_exported(), "claims@1")


def test_a_linear_recurrence_states_nothing_either() -> None:
    """``accumulate`` accumulates and names no convention to state.

    It is an accumulation, and it is not one of the two: its clause fixes
    the recurrence completely, so there is no choice of timing left for a
    reviewer to have to check. A field written on it would be settings
    quoted from attributes the call does not carry.
    """
    assert "settings" not in _node(_exported(), "fund@1")


def test_a_leaf_states_nothing_because_it_executes_nothing() -> None:
    """An arriving column ran no operation, so there is no convention."""
    assert "settings" not in _node(_exported(), "sum_assured")


def test_four_nodes_state_a_convention_and_the_rest_carry_no_member() -> None:
    """The absence is nearly everywhere, which is what makes the presence read."""
    artifact = _exported()

    stated = [node["id"] for node in artifact["nodes"] if "settings" in node]

    assert stated == [
        "survival@1",
        "survival_to_the_period_end@1",
        "reserve_on_a_rate@1",
        "reserve_on_a_factor@1",
    ]
    assert len(artifact["nodes"]) - len(stated) == 13


def test_the_member_is_written_in_the_audit_profile_a_reviewer_reads() -> None:
    """The profile that needs it most is the one carrying no operation tree.

    An audit artifact holds no ``expr`` at all, so a convention living only
    in the tree lives nowhere a supervisor looks -- which is the whole
    reason this member exists rather than being read off the executable
    profile.
    """
    exporter = GraphExporter(_the_model())
    audit = json.loads(exporter.export())
    executable = json.loads(exporter.export(profile="executable"))

    assert "expr" not in _node(audit, "survival@1")
    assert (
        _node(audit, "survival@1")["settings"]
        == (_node(executable, "survival@1")["settings"])
    )


def test_the_values_are_the_attributes_the_operation_tree_serialises() -> None:
    """Quoted, not re-derived: the same object under both spellings.

    If the two were built separately they could disagree, and the file
    would carry one convention said two ways with nothing to say which of
    them the model ran.
    """
    executable = json.loads(GraphExporter(_the_model()).export(profile="executable"))

    for node_id in ("survival@1", "reserve_on_a_factor@1"):
        node = _node(executable, node_id)
        assert node["settings"] == node["expr"]["attrs"]


# --- and no digest moves for any of it ---------------------------------------


def test_stating_the_convention_moves_no_fingerprint() -> None:
    """The attributes were always inside the canonical bytes; the member is not.

    The digest below was taken on the producer before ``settings`` existed.
    A field that moved it would be saying the model changed when what
    changed is what the file says about it, and every quarter-on-quarter
    comparison drawn on these digests would report a difference nobody
    made.
    """
    artifact = _exported()

    assert artifact["graph_fingerprint"] == _GRAPH_FINGERPRINT


# --- the four ways it can be mis-stated, and the four refusals ----------------


def _with_settings(node_id: str, stated: Any) -> dict[str, Any]:  # noqa: ANN401
    """Return the artifact with one node's ``settings`` replaced by ``stated``."""
    artifact = _exported()
    _node(artifact, node_id)["settings"] = stated
    return artifact


def _refusals(artifact: dict[str, Any]) -> list[str]:
    """Return the error-grade messages the semantic reading draws.

    Filtered to that reading on purpose. Every mis-statement below but the
    first is refused twice over -- the published schema constrains the
    member to the two shapes -- and what these tests are about is the
    reading that states the rule in the model's own terms.
    """
    return [
        finding.message
        for finding in validate_artifact(artifact).findings
        if finding.severity == "error" and finding.section == "semantic"
    ]


def _schema_refuses(artifact: dict[str, Any]) -> bool:
    """Return whether the published schema refuses the document as it stands."""
    return any(
        finding.section == "schema" and finding.severity == "error"
        for finding in validate_artifact(artifact).findings
    )


def test_settings_on_a_node_that_executes_nothing_is_refused() -> None:
    """A column that arrived ran no operation, so it configured none."""
    refused = _refusals(
        _with_settings("sum_assured", {"start_at": 1.0, "from_survival": False})
    )

    assert refused, "settings on a leaf drew no refusal"
    assert "its ``kind`` is 'input'" in refused[0]
    assert "only a 'computed' node has one to state" in refused[0]


def test_a_settings_object_stating_nothing_is_refused() -> None:
    """An empty object is an accumulation that ran under no convention."""
    refused = _refusals(_with_settings("survival@1", {}))

    assert refused, "an empty settings object drew no refusal"
    assert "states ``settings`` and states nothing in it" in refused[0]
    assert "carries no ``settings`` at all" in refused[0]
    assert _schema_refuses(_with_settings("survival@1", {}))


def test_a_settings_object_of_neither_shape_is_refused() -> None:
    """A key missing, a key too many and a key from elsewhere read alike.

    ``rate_timing`` is the case worth naming: it is the accessor's own
    keyword, so a producer that wrote what the actuary typed rather than
    what the operation recorded lands exactly here.
    """
    renamed = _refusals(
        _with_settings("survival@1", {"rate_timing": "beginning_of_period"})
    )
    a_key_short = _refusals(_with_settings("survival@1", {"start_at": 1.0}))
    a_key_over = _refusals(
        _with_settings(
            "survival@1", {"start_at": 1.0, "from_survival": False, "basis": "best"}
        )
    )

    assert renamed, "a renamed setting drew no refusal"
    assert "neither of the two shapes this revision defines" in renamed[0]
    assert "['from_survival', 'start_at']" in renamed[0]
    assert "['discount_kind', 'timing']" in renamed[0]
    assert a_key_short, "a missing key drew no refusal"
    assert a_key_over, "an unknown key drew no refusal"
    assert _schema_refuses(_with_settings("survival@1", {"start_at": 1.0}))


def test_a_setting_outside_what_it_admits_is_refused() -> None:
    """Four values, four conventions the format does not define.

    A null ``start_at`` is not among them: 11.1.19 records end-of-period
    timing that way, and a reading that refused it would refuse the
    convention this member exists to state.
    """
    start_at = _refusals(
        _with_settings("survival@1", {"start_at": "beginning", "from_survival": False})
    )
    from_survival = _refusals(
        _with_settings("survival@1", {"start_at": 1.0, "from_survival": "no"})
    )
    timing = _refusals(
        _with_settings(
            "reserve_on_a_rate@1", {"timing": "mid_period", "discount_kind": "rate"}
        )
    )
    discount_kind = _refusals(
        _with_settings(
            "reserve_on_a_rate@1", {"timing": "end_of_period", "discount_kind": "yield"}
        )
    )

    assert start_at, "a start_at that is not a decimal drew no refusal"
    assert "is a decimal or null" in start_at[0]
    assert from_survival, "a from_survival that is not a flag drew no refusal"
    assert "is true or false" in from_survival[0]
    assert timing, "a timing outside the two conventions drew no refusal"
    assert "'beginning_of_period' or 'end_of_period'" in timing[0]
    assert discount_kind, "a discount_kind outside the two drew no refusal"
    assert "a 'rate' or a 'factor'" in discount_kind[0]
    assert validate_artifact(
        _with_settings("survival@1", {"start_at": None, "from_survival": False})
    ).ok


def test_the_refusal_does_not_say_flat_rates_make_the_conventions_agree() -> None:
    """At flat rates the two conventions differ; the refusal said they agreed.

    A survival curve opened at the boundary is the end-of-period one shifted
    by a period's decrement, and a prospective value differs by a period's
    discount, at any rate: what flat rates hide is a wrong conversion
    between the two, which a refusal that told the reader otherwise sent them
    straight back into.
    """
    refused = _refusals(
        _with_settings(
            "reserve_on_a_rate@1", {"timing": "mid_period", "discount_kind": "rate"}
        )
    )

    assert refused, "a timing outside the two conventions drew no refusal"
    assert "identical numbers" not in refused[0]
    assert "do not give the same numbers, even at flat rates" in refused[0]
    assert "what flat rates hide is a wrong conversion" in refused[0]


def test_one_finding_per_node_however_many_ways_it_is_wrong() -> None:
    """Four readings of one object, and a reader fixes it once."""
    wrong = copy.deepcopy(_exported())
    _node(wrong, "survival@1")["settings"] = {"start_at": "x", "from_survival": "y"}

    assert len(_refusals(wrong)) == 1


def test_a_well_stated_convention_is_accepted() -> None:
    """The refusals bite on the mis-statement rather than on the member."""
    assert validate_artifact(_exported()).ok
