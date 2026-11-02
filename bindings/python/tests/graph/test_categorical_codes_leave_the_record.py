# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A categorical condition run on codes is recorded in the model's words.

``plan == "A"`` over a per-period Categorical or Enum operand now reaches the
conditional kernel as the operand's codes against the code ``"A"`` has in its
categories. That is how it runs, not what the model says. The op-tree, the
graph fingerprint, the as-written formula, the ``gaspatchio_lowered`` facet
and the walk-through are each what they were before: ``plan == "A"``, never
``to_physical``.

A Categorical *column* refuses at export -- the record has no dtype name for
one -- so the categorical operand here is written inline, through
``polars_native()``, the one way a categorical comparison reaches a record.
"""

from __future__ import annotations

import json
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph.calc_graph import GraphExporter
from gaspatchio.frame.graph.validate import validate_artifact
from gaspatchio.frame.lowering._polars.rendering import labels_for_codes

_PLANS = pl.Enum(["A", "B", "C"])


def _export() -> dict[str, Any]:
    """Export a model writing every categorical equality form once."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "opt": [["A", "A", "B"], ["B", None, "C"], ["C", "A", "A"]],
                "target": ["A", None, "Z"],
                "targets": [["A", "Z", None], None, ["C", "C", "A"]],
                "sa": [100.0, 200.0, 300.0],
            },
            schema={
                "policy_id": pl.Int64,
                "opt": pl.List(pl.String),
                "target": pl.String,
                "targets": pl.List(pl.String),
                "sa": pl.Float64,
            },
        )
    )
    category = af.opt.polars_native().cast(pl.List(pl.Categorical))
    plan = af.opt.polars_native().cast(pl.List(_PLANS))
    af.is_a = category == "A"
    af.not_a = plan != "A"
    af.unknown = plan == "Z"
    af.on_target = category == af.target
    af.off_the_list = plan != af.targets
    af.benefit = when(category == "A").then(af.sa).otherwise(0.0)
    af.label = when(plan == af.target).then("hit").otherwise("miss")
    af.either = (category == "A") | (plan == "C")
    frame = af.collect()
    document: dict[str, Any] = json.loads(
        GraphExporter(af).export(frame, include_lowered=True)
    )
    return document


def _without_the_clock(document: dict[str, Any]) -> dict[str, Any]:
    """Drop the two fields that move with the time of the export."""
    return {
        key: value
        for key, value in document.items()
        if key not in {"created_at", "document_digest"}
    }


def test_the_record_is_the_one_the_labels_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codes on or off, the export is the same document.

    The second export runs with the codes lowering switched off, which is
    the label path this release replaced. Fingerprints, formulas, facets,
    walk-throughs and values all agree.
    """
    on_codes = _export()

    def on_labels(left: pl.Expr, right: pl.Expr, *_: object) -> tuple[pl.Expr, pl.Expr]:
        return left, right

    monkeypatch.setattr(
        "gaspatchio.frame.lowering.polars.on_codes_where_labelled", on_labels
    )
    on_labels_only = _export()

    assert on_codes["graph_fingerprint"] == on_labels_only["graph_fingerprint"]
    assert _without_the_clock(on_codes) == _without_the_clock(on_labels_only)


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """Return the export, once for the module."""
    return _export()


def _node(document: dict[str, Any], node_id: str) -> dict[str, Any]:
    node: dict[str, Any] = next(
        one for one in document["nodes"] if one["id"] == node_id
    )
    return node


def test_no_node_says_to_physical(document: dict[str, Any]) -> None:
    """The conversion to codes is how it ran; no node a reader opens says so.

    The nodes are read rather than the whole document, which carries this
    file's own source -- and that says ``to_physical`` in its docstring.
    """
    nodes = json.dumps(document["nodes"])

    assert "to_physical" not in nodes
    assert "fill_null" not in nodes


_CATEGORY = "(opt.strict_cast(List(Categorical)))"
_ENUM = "(opt.strict_cast(List(Enum(...))))"


@pytest.mark.parametrize(
    ("node_id", "opening"),
    [
        ("is_a@1", f'.when({_CATEGORY} == ("A")).then(1).otherwise(0)'),
        ("on_target@1", f".when({_CATEGORY} == (target)).then(1).otherwise(0)"),
        ("off_the_list@1", f".when({_ENUM} != (targets)).then(1).otherwise(0)"),
        ("benefit@1", f'.when({_CATEGORY} == ("A")).then(sa).otherwise(0)'),
    ],
)
def test_the_walk_through_opens_on_the_comparison_the_model_wrote(
    document: dict[str, Any], node_id: str, opening: str
) -> None:
    """The column and the value, compared as written."""
    assert _node(document, node_id)["trace"][0]["expr"] == opening


def test_the_validator_reads_one_story(document: dict[str, Any]) -> None:
    """The walk-through and the rendering beside it still agree."""
    verdict = validate_artifact(document)

    assert verdict.ok
    assert not [one for one in verdict.findings if "opens on" in one.message]


_CODE = ".cast(Categorical).to_physical().fill_null([dyn int: -1])"
_CODES = 'col("plan").to_physical()'
_PER_POLICY = f'.when(col("t").is_null()).then(null).otherwise(col("t"){_CODE})'
_PER_PERIOD = (
    'col("r").list.eval(.when(element().is_null()).then(null)'
    f".otherwise(element(){_CODE}))"
)


@pytest.mark.parametrize(
    ("receiver", "right", "written"),
    [
        (_CODES, f'"A"{_CODE}', ('col("plan")', '"A"')),
        (_CODES, _PER_POLICY, ('col("plan")', 'col("t")')),
        (_CODES, _PER_PERIOD, ('col("plan")', 'col("r")')),
        (
            _CODES,
            '"A".cast(Enum([...])).to_physical().fill_null([dyn int: -1])',
            ('col("plan")', '"A"'),
        ),
    ],
    ids=["one value", "a value per policy", "a list per policy", "an enum"],
)
def test_each_codes_form_reads_back_as_the_operands_written(
    receiver: str, right: str, written: tuple[str, str]
) -> None:
    """Every form the lowering writes reads back to the model's operands."""
    assert labels_for_codes(receiver, right) == written


@pytest.mark.parametrize(
    ("receiver", "right"),
    [
        # The null check names another operand than the code: not ours.
        (
            _CODES,
            f'.when(col("u").is_null()).then(null).otherwise(col("t"){_CODE})',
        ),
        # A code with no conversion of the column beside it.
        ('col("plan")', f'"A"{_CODE}'),
        # A column read as codes beside an ordinary value.
        (_CODES, '"A"'),
    ],
    ids=["another operand", "no codes on the left", "no code on the right"],
)
def test_anything_else_keeps_the_text_it_had(receiver: str, right: str) -> None:
    """A near miss is left as it was: more than it means, never less."""
    assert labels_for_codes(receiver, right) == (receiver, right)
