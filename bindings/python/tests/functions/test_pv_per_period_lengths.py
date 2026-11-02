# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period PV whose lists differ in length within a policy is refused.

``af.rate.excel.pv(af.nper, af.pmt)`` with two or three per-period operands
paired them period by period by zipping, so a policy with three periods of
rate and two of pmt answered two present values and said nothing. On the
base, for policy P002 (three periods of rate, two of the short operand):

- rate and pmt per period:  ``[-7.7217..., -7.7217...]``, two values;
- rate and nper per period: ``[-0.9523..., -0.9523...]``, two values.

Two lists must have equal lengths within each policy (graph-artifact spec,
section 11.1.18), and every other list kernel already refused a misfit; PV
now refuses it the same way, naming the operands and both lengths, and the
error report names the policy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

_ENGINES = ("streaming", "in-memory")


def _book() -> pl.DataFrame:
    """Two policies; P002 has three periods of rate and two of ``short``."""
    return pl.DataFrame(
        {
            "policy_id": ["P001", "P002"],
            "flat_rate": [0.05, 0.05],
            "rate": [[0.05, 0.05], [0.05, 0.05, 0.05]],
            "nper": [[10.0, 10.0], [10.0, 10.0, 10.0]],
            "short": [[1.0, 1.0], [1.0, 1.0]],
        }
    )


_CASES: dict[str, tuple[Callable[[ActuarialFrame], object], str]] = {
    "rate and pmt per period": (
        lambda af: af.rate.excel.pv(10.0, af.short),
        "pmt against rate",
    ),
    "rate and nper per period": (
        lambda af: af.rate.excel.pv(af.short, 1.0),
        "nper against rate",
    ),
    "nper and pmt per period": (
        lambda af: af.flat_rate.excel.pv(af.nper, af.short),
        "pmt against nper",
    ),
    "all three per period": (
        lambda af: af.rate.excel.pv(af.nper, af.short),
        "pmt against rate",
    ),
}


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize("case", list(_CASES), ids=list(_CASES))
def test_a_per_period_operand_of_another_length_is_refused(
    case: str, engine: str
) -> None:
    """Refused by both lengths, and the policy named -- never two values."""
    formula, sentence = _CASES[case]
    af = ActuarialFrame(_book())
    af.out = formula(af)

    with pytest.raises(pl.exceptions.ComputeError) as refused:
        af.collect(engine=engine)

    message = str(refused.value)
    assert f"mismatched inner list lengths in one policy: {sentence}" in message
    assert "  Policy:         policy_id=P002 (row 1)" in message


@pytest.mark.parametrize("engine", _ENGINES)
def test_lists_that_fit_answer_one_value_per_period(engine: str) -> None:
    """Every operand with its policy's periods answers as before."""
    af = ActuarialFrame(_book())
    af.out = af.rate.excel.pv(af.nper, af.rate)

    out = af.collect(engine=engine)["out"].to_list()
    assert [len(row) for row in out] == [2, 3]
