# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What the frame says to a Polars method that chooses rows and is not a model step.

Which policies a model values is part of its record (graph-artifact spec
section 7.6): ``af.filter`` records its condition, a semi or anti join its key
list, and a replay of the document makes the same choice again over the book.
A choice the record can state is one made on what a policy holds. Polars'
other ways of choosing rows are not that:

- ``head``, ``tail``, ``limit`` and ``slice`` keep rows by their position, and
  a policy is found again by its identity, never by counting to it (section
  7.4);
- ``unique`` keeps one row of each set of duplicates, a choice that depends on
  the other rows rather than on what one policy holds;
- ``drop_nulls`` and ``drop_nans`` ask whether a value is missing, which on a
  frame holding per-period columns is two questions -- a policy without the
  value, or a period without one -- and the frame does not pick one for the
  author;
- ``gather_every`` keeps every n-th row, which is a position too;
- ``sample`` chooses rows at random, a choice no replay makes again;
- ``top_k`` and ``bottom_k`` keep the rows that rank highest or lowest by a
  column, a choice that rests on the other rows, as ``unique``'s does;
- ``remove`` drops the rows a condition holds for and keeps those where it is
  null, which is not the complement ``af.filter(~condition)`` states, so the
  sentence names the condition for the policies kept, with its null test
  where nulls are to stay.

So none of them is a frame method, and reaching for one says why and what to
write instead -- a condition ``af.filter`` records, or the cut made on the
model points before the frame is built, which the record does not need to
state because the book is then the rows kept -- rather than reading the
method's name as a column the frame does not hold. A column that is called
``head`` is still a column, and ``af.head`` still reaches it.
"""

from __future__ import annotations

from typing import Final

__all__ = ["per_period_condition_refusal", "row_choosing_refusal"]

_POSITIONAL: Final = frozenset({"head", "tail", "limit", "slice", "gather_every"})
_DUPLICATES: Final = frozenset({"unique"})
_MISSING: Final = frozenset({"drop_nulls", "drop_nans"})
_RANKED: Final = frozenset({"top_k", "bottom_k"})

_WHY_A_CONDITION: Final = (
    "a model chooses which policies it values by what they hold, so that its "
    "record can state the choice and a replay can make it again."
)

_PHASE_ONE: Final = (
    "or make the cut on the model points before the frame is built -- "
    "ActuarialFrame(model_points.{call}) -- where the book is then the rows "
    "kept and the record needs no step for them."
)


def row_choosing_refusal(name: str) -> str | None:
    """Return the sentence refusing ``af.<name>``, or None where it is no such method.

    Args:
        name: The attribute the author reached for on a frame.

    Returns:
        Why the method is not a step a model takes and what to write
        instead, or ``None`` for any other name.

    """
    other = _other_row_choosing_refusal(name)
    if other is not None:
        return other
    if name in _POSITIONAL:
        call = "slice(offset, length)" if name == "slice" else f"{name}(n)"
        return (
            f"af.{name}() is not a step a model takes: it keeps rows by their "
            f"position, and {_WHY_A_CONDITION} "
            "Write the condition and af.filter records it -- "
            'af.filter(af.policy_id.is_in(["P1", "P2"])) -- '
            + _PHASE_ONE.format(call=call)
            + f" To look at rows, collect first: af.collect().{call}."
        )
    if name in _DUPLICATES:
        return (
            "af.unique() is not a step a model takes: it keeps one row of each "
            "set of duplicates, a choice that rests on the other rows rather than "
            "on what one policy holds, and a model's record states which policies "
            "it values only as a condition (af.filter) or a key list (a semi or "
            "anti join). De-duplicate the model points before the frame is "
            'built -- ActuarialFrame(model_points.unique(subset=["policy_id"])) '
            "-- where the book is then the rows kept and the record needs no "
            "step for them."
        )
    if name in _MISSING:
        test = "is_not_null" if name == "drop_nulls" else "is_not_nan"
        return (
            f"af.{name}() is not a step a model takes: on a frame holding "
            "per-period columns a missing value is either a policy without the "
            "value or a period without one, and the frame will not pick which "
            "you meant. Write the condition on the per-policy column you mean "
            f"and af.filter records it -- af.filter(af.sum_assured.{test}()) -- "
            + _PHASE_ONE.format(call=f'{name}(subset=["sum_assured"])')
        )
    return None


def _other_row_choosing_refusal(name: str) -> str | None:
    """Return the sentence for ``sample``, ``top_k``, ``bottom_k`` or ``remove``."""
    if name == "sample":
        return (
            "af.sample() is not a step a model takes: it chooses rows at random, "
            f"and {_WHY_A_CONDITION} Write the condition and af.filter records "
            'it -- af.filter(af.policy_id.is_in(["P1", "P2"])) -- '
            + _PHASE_ONE.format(call="sample(n, seed=1)")
            + " To look at rows, collect first: af.collect().sample(n)."
        )
    if name in _RANKED:
        call = f'{name}(k, by="sum_assured")'
        direction = "highest" if name == "top_k" else "lowest"
        return (
            f"af.{name}() is not a step a model takes: it keeps the k rows that "
            f"rank {direction} by a column, a choice that rests on the other rows "
            "rather than on what one policy holds, and a model's record states "
            "which policies it values only as a condition (af.filter) or a key "
            "list (a semi or anti join). Write the threshold you mean and "
            "af.filter records it -- af.filter(af.sum_assured >= 250_000) -- "
            + _PHASE_ONE.format(call=call)
            + f" To look at rows, collect first: af.collect().{call}."
        )
    if name == "remove":
        return (
            "af.remove() is not a frame method: a model chooses which policies it "
            "values with af.filter, which records the condition for the policies "
            'kept. Write that condition -- af.filter(~(af.status == "LAPSED")) -- '
            "and, where a policy whose condition is null is to stay, as Polars' "
            "remove keeps it, add its null test: "
            'af.filter(~(af.status == "LAPSED") | af.status.is_null()).'
        )
    return None


def per_period_condition_refusal(read: tuple[str, str] | None) -> str:
    """Return the sentence refusing a filter condition that answers once a period.

    A selection chooses which policies a model values, so a policy is kept
    or dropped in every period at once and the condition that decides it is
    one value per policy. The frame's declared list reductions turn a
    per-period value into one: ``list.get`` for the value at one period,
    ``list.min`` and ``list.max`` for every period and any period.

    Args:
        read: What the condition reads that holds a value per period, as
            ``("column", name)`` or ``("state", name)`` for a compiled
            rollforward's state, where the frame can name one.

    Returns:
        Why the condition is not a selection and the per-policy forms to
        write instead.

    """
    because, written = "", "af.value"
    if read is not None:
        kind, name = read
        if kind == "state":
            because = (
                f", because the rollforward state {name!r} holds one value per period"
            )
            written = f'compiled.expr_for("{name}")'
        else:
            because = f", because {name!r} holds one value per period"
            written = f"af.{name}" if name.isidentifier() else f"af[{name!r}]"
    return (
        "af.filter() keeps or drops whole policies, so its condition must be "
        f"one value per policy, and this one answers once a period{because}. "
        "A selection chooses which policies the model values, and a policy is "
        "kept or dropped in every period at once. Reduce the condition to one "
        f"answer per policy -- {written}.list.get(0) > 0 for the value at the "
        f"first period, {written}.list.min() > 0 for every period, "
        f"{written}.list.max() > 0 for any period -- or make the cut on the "
        "model points before the frame is built. To leave periods out rather "
        "than policies, keep the policy and mask its cash flows with when(...)."
    )
