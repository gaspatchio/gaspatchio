# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A compiled rollforward reading a table a shock names runs each scenario's rates.

A rollforward's operand is a bare column of the frame, so a model reads a
table into a column -- ``af.coi = coi.lookup(age=af.attained)`` -- and hands
the rollforward that column. The plan binds that lookup like any other, so
each scenario's running balance is the one that scenario reaches alone over
the table shocked by hand, bit for bit, at every batch size. A lookup handed
to the rollforward directly is refused, naming the move; nothing reads BASE.
The JAX engine's half is ``engines/jax/tests/test_scenario_plan.py``.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import MultiplicativeShock, ScenarioRun, Sum

PERIODS = 24
BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "av_init": [1000.0, 2000.0, 1500.0],
        "attained": [[a + m // 12 for m in range(PERIODS)] for a in (40, 45, 50)],
        "growth": [[0.004] * PERIODS] * 3,
        "db": [[5000.0] * PERIODS] * 3,
    }
)
SHOCKS = {"BASE": [], "COI_UP": [MultiplicativeShock(1.5, table="rollforward_coi")]}
_AGG = (Sum("av_end").alias("av_end").over("scenario_id"),)


def _coi(scale: float = 1.0) -> Table:
    return Table(
        name="rollforward_coi",
        source=pl.DataFrame(
            {
                "age": list(range(40, 60)),
                "c": [scale * (0.01 + 0.001 * i) for i in range(20)],
            }
        ),
        dimensions={"age": "age"},
        value="c",
    )


def _model(scale: float = 1.0):  # noqa: ANN202 -- a model function
    def model(af: ActuarialFrame) -> ActuarialFrame:
        af = af.projection.set(
            start_date=date(2025, 1, 31), n_periods=PERIODS, frequency="monthly"
        )
        af.coi = _coi(scale).lookup(age=af.attained)
        b = af.projection.rollforward(states={"av": af["av_init"]})
        b["av"].grow(af["growth"], label="growth").charge(af["coi"], label="coi")
        b["av"].deduct_nar(af["coi"], death_benefit=af["db"], label="nar")
        af.av = compile_rollforward(b).expr_for("av")
        af.av_end = af.av.list.get(-1)
        return af

    return model


@pytest.mark.parametrize("batch_size", [1, 2, "auto"])
def test_each_scenario_rolls_forward_on_its_own_shocked_rates(
    batch_size: int | str,
) -> None:
    plan = ScenarioRun(shocks=SHOCKS, aggregations=_AGG)
    ran = dict(
        plan.run(ActuarialFrame(BOOK), _model(), batch_size=batch_size)  # type: ignore[arg-type]
        .aggregations["av_end"]
        .iter_rows()
    )
    for sid, scale in (("BASE", 1.0), ("COI_UP", 1.5)):
        alone = _model(scale)(ActuarialFrame(BOOK)).collect()
        assert ran[sid] == alone["av_end"].sum(), sid
    assert ran["COI_UP"] < ran["BASE"]


def test_a_lookup_handed_to_the_rollforward_directly_is_refused() -> None:
    def inline(af: ActuarialFrame) -> ActuarialFrame:
        af = af.projection.set(
            start_date=date(2025, 1, 31), n_periods=PERIODS, frequency="monthly"
        )
        b = af.projection.rollforward(states={"av": af["av_init"]})
        b["av"].charge(_coi().lookup(age=af.attained), label="coi")
        af.av = compile_rollforward(b).expr_for("av")
        af.av_end = af.av.list.get(-1)
        return af

    with pytest.raises(NotImplementedError, match="reads one named column"):
        ScenarioRun(shocks=SHOCKS, aggregations=_AGG).run(
            ActuarialFrame(BOOK), inline, batch_size=2
        )
