# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A workbook's rollback runs on this engine, and gives Polars' own doubles.

Section 11.1.20's ``reverse`` and section 11.1.41's ``list.reverse`` exist so a
rollback converts without an escape hatch, and the point of that is this file:
the VM-20 NPR shape -- ``V[t] = v[t] * V[t+1] + cf[t]`` over a book whose
policies do not share one length -- reads as portable to ``jax`` and runs here.
Handed the same operands, both spellings are Polars' answer bit for bit: the
recurrence is one IEEE product and one IEEE sum per period in either engine,
and a reversal moves values without touching them. The whole NPR model is held
to section 11.1.12's agreement rule instead, because the ordinary arithmetic
in front of the rollback -- ``benefit * q - premium`` -- may be contracted into
one fused multiply-add by XLA and so is not the same double, which is exactly
what that rule is for.
"""

from __future__ import annotations

from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from tests.test_lowerings_projection import _call, _column, answered

# Three policies of four, two and three periods: the jagged book is the whole
# difficulty for a backward run, because a policy short of the bucket meets
# its padding first.
_BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "q": [[0.01, 0.02, 0.03, 0.04], [0.05, 0.06], [0.02, 0.02, 0.02]],
        "benefit": [1000.0, 500.0, 2000.0],
        "premium": [12.0, 30.0, 40.0],
    }
)


def _bits(rows: list[Any]) -> list[Any]:
    """Return every double as its exact bits, so equality is to the bit."""
    return [[float(x).hex() for x in row] for row in rows]


def _npr(*, three_step: bool) -> ActuarialFrame:
    """Return the NPR rollback, as one named recurrence or as three steps."""
    af = ActuarialFrame(_BOOK)
    af.v = af.q * 0.0 + 1.0 / 1.04
    af.net_cf = af.benefit * af.q - af.premium
    if three_step:
        af.cf_r = af.net_cf.list.reverse()
        af.v_r = af.v.list.reverse()
        af.acc = af.cf_r.projection.accumulate(
            initial=0.0, multiplier=af.v_r, addend=af.cf_r
        )
        af.npr = af.acc.list.reverse()
    else:
        af.npr = af.net_cf.projection.accumulate(
            initial=0.0, multiplier=af.v, addend=af.net_cf, reverse=True
        )
    return af


@pytest.mark.parametrize("three_step", [False, True], ids=["named", "three-step"])
def test_the_npr_rollback_reads_as_portable_to_this_engine(*, three_step: bool) -> None:
    """Every node core, nothing engine text, and the jax reading has no error."""
    document = GraphExporter(_npr(three_step=three_step)).export(profile="executable")
    report = validate_artifact(document, engine="jax", deep=True)
    assert report.ok, report.findings


# The rollback's own operands, arriving with the book rather than computed, so
# both engines hand the recurrence and the reversal the same doubles.
_OPERANDS = pl.DataFrame(
    {
        "v": [[0.9615384615384615] * 4, [0.97, 0.95], [0.9, 0.9, 0.9]],
        "cf": [[-2.0, 8.0, 18.0, 28.0], [-5.0, 0.0], [0.1, 0.2, 0.30000000000000004]],
    }
)

# Section 11.1.12: two finite results agree within 1e-12 of the line's scale.
_AGREEMENT = 1e-12


def _rolled_back(*, three_step: bool) -> ActuarialFrame:
    """Return the rollback over operands that arrived, in one spelling."""
    af = ActuarialFrame(_OPERANDS)
    if three_step:
        af.cf_r = af.cf.list.reverse()
        af.v_r = af.v.list.reverse()
        af.acc = af.cf_r.projection.accumulate(
            initial=0.0, multiplier=af.v_r, addend=af.cf_r
        )
        af.npr = af.acc.list.reverse()
    else:
        af.npr = af.cf.projection.accumulate(
            initial=0.0, multiplier=af.v, addend=af.cf, reverse=True
        )
    return af


@pytest.mark.parametrize("three_step", [False, True], ids=["named", "three-step"])
def test_the_rollback_is_polars_own_answer_to_the_bit(*, three_step: bool) -> None:
    on_polars = _rolled_back(three_step=three_step).collect()["npr"].to_list()
    on_jax = _rolled_back(three_step=three_step).collect(engine="jax")["npr"].to_list()
    assert [len(row) for row in on_jax] == [4, 2, 3]
    assert _bits(on_jax) == _bits(on_polars)


def test_the_two_spellings_are_one_reserve_on_this_engine() -> None:
    named = _rolled_back(three_step=False).collect(engine="jax")["npr"].to_list()
    three = _rolled_back(three_step=True).collect(engine="jax")["npr"].to_list()
    assert _bits(named) == _bits(three)


@pytest.mark.parametrize("three_step", [False, True], ids=["named", "three-step"])
def test_the_npr_model_agrees_with_polars_under_the_agreement_rule(
    *, three_step: bool
) -> None:
    """The whole model, its arithmetic included, within 1e-12 of each policy's scale."""
    on_polars = _npr(three_step=three_step).collect()
    on_jax = _npr(three_step=three_step).collect(engine="jax")
    for policy in range(_BOOK.height):
        reserve_p = on_polars["npr"][policy].to_list()
        reserve_j = on_jax["npr"][policy].to_list()
        flows = on_polars["net_cf"][policy].to_list()
        scale = max(abs(x) for x in [*reserve_p, *flows, 1.0])
        assert len(reserve_j) == len(reserve_p)
        assert all(
            abs(a - b) <= _AGREEMENT * scale
            for a, b in zip(reserve_j, reserve_p, strict=True)
        ), policy


def test_a_reversal_of_every_element_type_is_polars_own() -> None:
    frame = pl.DataFrame(
        {
            "f": [[1.5, 2.5, 3.5], [4.5], []],
            "i": [[1, 2, 3], [4], []],
            "b": [[True, False, False], [True], []],
        }
    )
    af = ActuarialFrame(frame)
    af.f_r = af.f.list.reverse()
    af.i_r = af.i.list.reverse()
    af.b_r = af.b.list.reverse()
    on_jax = ActuarialFrame(frame)
    on_jax.f_r = on_jax.f.list.reverse()
    on_jax.i_r = on_jax.i.list.reverse()
    on_jax.b_r = on_jax.b.list.reverse()
    polars_answer = af.collect()
    jax_answer = on_jax.collect(engine="jax")
    for column in ("f_r", "i_r", "b_r"):
        assert jax_answer[column].to_list() == polars_answer[column].to_list(), column


def test_each_policy_opens_at_its_own_last_period_in_a_padded_bucket() -> None:
    """The clause's workbook rollback beside a one-period policy, in one bucket.

    The one-period policy stands in a bucket of twelve, eleven of them padding.
    Its run opens at its own period on 10.0 and answers 10 * 0.5 + 1 = 6.0; a
    run stepped through the padding first would reach that period carrying
    whatever the padded cells made of the opening.
    """
    tree = _call(
        "projection.accumulate",
        [_column("opening"), _column("v"), _column("cf")],
        {"reverse": True},
    )
    inputs = {
        "opening": {"dtype": "f64", "values": [0.0, 10.0]},
        "v": {"dtype": "list[f64]", "values": [[0.9, 0.9, 0.9], [0.5]]},
        "cf": {"dtype": "list[f64]", "values": [[1.0, 2.0, 3.0], [1.0]]},
    }
    assert answered(tree, inputs, "list[f64]") == [[5.23, 4.7, 3.0], [6.0]]


def test_a_negative_zero_opening_survives_the_padding() -> None:
    """The carry is held across a padded cell rather than stepped through it.

    ``-0.0 * 1 + 0`` is ``+0.0``, so a run stepped through padding before it
    reached the policy's last period would open on the wrong zero, and
    ``0.0 * 2 + -0.0`` would answer ``+0.0`` where Polars answers ``-0.0``.
    """
    tree = _call(
        "projection.accumulate",
        [_column("opening"), _column("v"), _column("cf")],
        {"reverse": True},
    )
    inputs = {
        "opening": {"dtype": "f64", "values": [-0.0]},
        "v": {"dtype": "list[f64]", "values": [[2.0]]},
        "cf": {"dtype": "list[f64]", "values": [[-0.0]]},
    }
    (row,) = answered(tree, inputs, "list[f64]")
    assert [float(x).hex() for x in row] == ["-0x0.0p+0"]


def test_a_tree_written_before_the_attribute_runs_forward() -> None:
    """No ``reverse`` meant the forward recurrence, the only one there was."""
    inputs = {
        "i": {"dtype": "f64", "values": [10.0]},
        "m": {"dtype": "list[f64]", "values": [[2.0, 3.0]]},
        "a": {"dtype": "list[f64]", "values": [[1.0, 1.0]]},
    }
    older = _call("projection.accumulate", [_column("i"), _column("m"), _column("a")])
    assert answered(older, inputs, "list[f64]") == [[21.0, 64.0]]
