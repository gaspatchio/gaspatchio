# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period Categorical or Enum condition is decided on its codes.

``af.plan == "A"`` over a per-period Categorical column took about 5 s over
100,000 policies x 360 months streaming, where the same comparison over
numbers takes 0.13 s. The kernel was handed the labels, and Polars re-entered
every label into the category map for each block of rows it passed across
the plugin boundary. ``==`` and ``!=`` now hand the kernel the column's codes
and the right side's code in the column's own categories, so it compares
numbers.

The answers are the labels' answers, which is what these tests hold: every
case is compared with the kernel run on the labels directly -- the path
W2-H's oracle pins against the per-row walk -- for a Categorical and an Enum
column, a right side written as text, as a Categorical, and as an Enum whose
categories are ordered differently, each as one value, a value per policy
and a list per policy, with nulls on either side, a null and an empty
policy, and a label the column's categories do not hold.
"""

from __future__ import annotations

import re

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.lowering._polars.plugins import list_conditional

_PLANS = pl.Enum(["A", "B", "C"])
# The same labels in another order, and one more: a right-hand Enum whose
# codes are not the column's codes, so only the cast to the column's own
# dtype can answer correctly.
_OTHER_ORDER = pl.Enum(["Z", "C", "B", "A"])

_DATA = {
    "plan": [["A", "B", None, "C"], [], None, ["B", "B"], ["C", "A"], ["A"]],
    "target": ["A", None, "B", "Z", "C", "A"],
    "targets": [["A", None, "Z", "C"], [], ["A"], None, ["Z", "A"], ["B"]],
    "sa": [[1.0, 2.0, 3.0, 4.0], [], None, [5.0, 6.0], [7.0, 8.0], [9.0]],
}

_ENGINES = ("streaming", "in-memory")


def _book(labels: pl.DataType, text: pl.DataType) -> pl.DataFrame:
    return pl.DataFrame(
        _DATA,
        schema={
            "plan": pl.List(labels),
            "target": text,
            "targets": pl.List(text),
            "sa": pl.List(pl.Float64),
        },
    )


# What the model writes on the right, and the same operand for the kernel.
_RIGHT = {
    "a label": ("A", pl.lit("A")),
    "a label the categories lack": ("Z", pl.lit("Z")),
    "a value per policy": ("target", pl.col("target")),
    "a list per policy": ("targets", pl.col("targets")),
}

# What the condition selects, written both ways.
_BRANCHES = ("indicator", "number", "text", "commuted")


def _written(af: ActuarialFrame, right: object, op: str, branches: str) -> None:
    if branches == "commuted":
        af.out = (right == af.plan) if op == "eq" else (right != af.plan)
        return
    condition = (af.plan == right) if op == "eq" else (af.plan != right)
    if branches == "indicator":
        af.out = condition
    elif branches == "number":
        af.out = when(condition).then(af.sa).otherwise(0.0)
    else:
        af.out = when(condition).then("hit").otherwise("miss")


def _on_the_labels(
    book: pl.DataFrame, right: pl.Expr, op: str, branches: str, engine: str
) -> list[object]:
    then, otherwise = {
        "indicator": (pl.lit(1.0), pl.lit(0.0)),
        "commuted": (pl.lit(1.0), pl.lit(0.0)),
        "number": (pl.col("sa"), pl.lit(0.0)),
        "text": (pl.lit("hit"), pl.lit("miss")),
    }[branches]
    kernel = list_conditional(pl.col("plan"), right, then, otherwise, op)
    if right.meta.output_name() == "targets":
        # A policy with no right-hand run is null, as one with no left-hand
        # run is inside the kernel (11.1.25, 11.1.26).
        kernel = pl.when(right.is_null()).then(None).otherwise(kernel)
    out: list[object] = (
        book.lazy().select(out=kernel).collect(engine=engine)["out"].to_list()  # type: ignore[call-overload]
    )
    return out


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize("branches", _BRANCHES)
@pytest.mark.parametrize("op", ["eq", "ne"])
@pytest.mark.parametrize("right", list(_RIGHT), ids=list(_RIGHT))
@pytest.mark.parametrize(
    "text", [pl.String, pl.Categorical, _OTHER_ORDER], ids=["str", "cat", "enum"]
)
@pytest.mark.parametrize("labels", [pl.Categorical, _PLANS], ids=["cat", "enum"])
def test_the_codes_answer_what_the_labels_answer(  # noqa: PLR0913, PLR0917 - one oracle, six axes
    labels: pl.DataType,
    text: pl.DataType,
    right: str,
    op: str,
    branches: str,
    engine: str,
) -> None:
    """Every period, every null and every miss is the labels' answer."""
    if branches == "commuted" and right not in {
        "a label",
        "a label the categories lack",
    }:
        pytest.skip("the commuted form is written against one value")
    book = _book(labels, text)
    written, kernel_right = _RIGHT[right]
    af = ActuarialFrame(book)
    operand = af[written] if written in {"target", "targets"} else written

    _written(af, operand, op, branches)

    got = af.collect(engine=engine)["out"].to_list()
    assert got == _on_the_labels(book, kernel_right, op, branches, engine)


def _plan_of(af: ActuarialFrame, column: str) -> str:
    return str(af._df.select(column).explain())  # noqa: SLF001 - what the engine is handed is the case under test


@pytest.mark.parametrize("labels", [pl.Categorical, _PLANS], ids=["cat", "enum"])
def test_equality_is_handed_over_as_codes_and_an_ordering_as_labels(
    labels: pl.DataType,
) -> None:
    """``==`` and ``!=`` reach the kernel as codes; ``<`` keeps the labels.

    A label's code is its position in the column's categories, not its
    place in the alphabet, so an ordering on codes would answer a different
    question. The orderings stay where they were.
    """
    af = ActuarialFrame(_book(labels, pl.String))
    af.is_a = af.plan == "A"
    af.not_on_target = af.plan != af.target
    af.on_the_list = when(af.plan == af.targets).then(af.sa).otherwise(0.0)

    for column in ("is_a", "not_on_target", "on_the_list"):
        assert "to_physical" in _plan_of(af, column), column
    if labels is pl.Categorical:
        af.early = af.plan < "B"
        assert "to_physical" not in _plan_of(af, "early")
        return
    # An ordered category ordered against text has two meanings, its
    # categories' order and its letters', and is refused by name (11.1.26).
    with pytest.raises(TypeError, match=r"a band -- an ordered category"):
        af.early = af.plan < "B"


def test_text_and_a_number_keep_the_path_they_had() -> None:
    """A text column is not touched, and a category set against a number is refused.

    Text is already compared directly; a number against a category has no
    true answer, and the line is refused when it is written, naming both
    kinds -- earlier than the kernel's own refusal at collect().
    """
    af = ActuarialFrame(_book(pl.String, pl.String))
    af.is_a = af.plan == "A"
    assert "to_physical" not in _plan_of(af, "is_a")

    categories = ActuarialFrame(_book(pl.Categorical, pl.String))
    with pytest.raises(TypeError, match="sets text against a whole number"):
        categories.is_one = categories.plan == 1


def test_a_null_value_answers_null_as_the_labels_do() -> None:
    """``af.plan == None`` keeps the labels' answer: null in every period."""
    book = _book(_PLANS, pl.String)
    af = ActuarialFrame(book)
    af.out = af.plan == None  # noqa: E711 - a null right side is the case under test

    want = (
        book.lazy()
        .select(
            out=list_conditional(
                pl.col("plan"), pl.lit(None), pl.lit(1.0), pl.lit(0.0), "eq"
            )
        )
        .collect()["out"]
        .to_list()
    )
    assert af.collect()["out"].to_list() == want


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_one_row_list_literal_is_read_for_every_policy(engine: str) -> None:
    """A right-hand list written once covers every policy, on codes too."""
    book = pl.DataFrame(
        {"plan": [["A", "B"], ["B", "B"], ["C", "A"]]},
        schema={"plan": pl.List(_PLANS)},
    )
    once = pl.lit(pl.Series([["A", "Z"]]))
    af = ActuarialFrame(book)
    af.out = af.plan == ("A", "Z")
    assert "to_physical" in _plan_of(af, "out")

    want = (
        book.lazy()
        .select(
            out=list_conditional(pl.col("plan"), once, pl.lit(1.0), pl.lit(0.0), "eq")
        )
        .collect(engine=engine)["out"]  # type: ignore[call-overload]
        .to_list()
    )
    assert want == [[1.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
    assert af.collect(engine=engine)["out"].to_list() == want


# The refusal for a per-period right side of the wrong length: the operand,
# and both lengths "in one policy". No row: the row a kernel can count is the
# row within the block of rows the engine hands it, which under streaming is
# not the frame's, so the sentence is the same in both engines (the error
# report names the policy from the frame). Nothing follows the right-hand
# length but the sentence's end, so a message naming a third list is not
# this one.
_WRONG_LENGTH = re.escape(
    "mismatched inner list lengths in one policy: right against left\n"
    "left=1, right=3 in that policy."
)


@pytest.mark.parametrize(
    ("values", "dtype"),
    [
        ((["A", "B"], ["A"], ["A", "B", "C"]), pl.String),
        ((["A", "B"], ["A"], ["A", "B", "C"]), pl.Categorical),
        ((["A", "B"], ["A"], ["A", "B", "C"]), _PLANS),
        (([1.0, 2.0], [1.0], [1.0, 2.0, 3.0]), pl.Float64),
    ],
    ids=["text", "categorical", "enum", "number"],
)
@pytest.mark.parametrize("engine", _ENGINES)
def test_a_list_of_another_length_is_refused_by_its_lengths(
    values: tuple[list[object], list[object], list[object]],
    dtype: pl.DataType,
    engine: str,
) -> None:
    """A per-period right side shorter or longer than the policy is refused.

    Every path names the operand and both lengths, and no batch row: the
    numeric kernel -- which a Categorical or Enum condition now reaches as
    codes, and which every numeric list comparison reaches -- and the text
    path say it in one sentence.
    """
    two, one, three = values
    right = pl.String if dtype in {pl.Categorical, _PLANS} else dtype
    book = pl.DataFrame(
        {"plan": [two, one], "targets": [two, three]},
        schema={"plan": pl.List(dtype), "targets": pl.List(right)},
    )
    af = ActuarialFrame(book)
    af.out = af.plan == af.targets

    with pytest.raises(pl.exceptions.ComputeError, match=_WRONG_LENGTH) as refused:
        af.collect(engine=engine)
    assert re.search(r"\brow \d", str(refused.value).split("Failing column")[0]) is None
