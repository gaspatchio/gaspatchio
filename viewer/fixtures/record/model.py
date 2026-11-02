# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Expected claims over a year, resting on a helper and three tables.

What the record says the model rests on beside its own file is the point of
this model, so it rests on one of each: a helper module beside it, a table
read from a file whose column the recipe renames, a table read from a file as
it stands, and a table built from a frame written in the code. The rates are
divided by twelve so the values the record carries run to every digit a
double holds, which is what the page is held to quote.
"""

import datetime
from pathlib import Path

import loadings
import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table

HERE = Path(__file__).resolve().parent


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Project each policy's expected claims and expenses over a year."""
    mortality = Table(
        name="record_mortality",
        source=HERE / "mortality.csv",
        dimensions={"age": "Age"},
        value="qx",
    )
    lapse = Table(
        name="record_lapse",
        source=HERE / "lapse.csv",
        dimensions={"age": "age"},
        value="rate",
    )
    expense = Table(
        name="record_expense",
        source=pl.DataFrame({"age": [30, 40], "cost": [10.0, 12.5]}),
        dimensions={"age": "age"},
        value="cost",
    )
    af = af.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=12, frequency="monthly"
    )
    af.qx_monthly = mortality.lookup(age=af.age) / 12
    af.lapse_monthly = lapse.lookup(age=af.age) / 12
    af.expense = expense.lookup(age=af.age) * loadings.inflation()
    af.in_force = 1 - (af.qx_monthly + af.lapse_monthly) * af.month
    af.expected_claims = (
        af.sum_assured * af.qx_monthly * af.in_force * loadings.margin()
    )
    return af
