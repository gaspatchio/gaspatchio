# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Select-ultimate dispatch with select_period clamping.

The clamp takes two forms because a duration comes in two shapes. A
projection's duration is a per-period list column and clips inside each
row, through ``list.eval(element().clip(...))``; a pricing-at-issue
duration -- one point in time, no projection at all -- is an ordinary
per-policy column and clips through Polars' own ``clip`` directly. Both
are that same ``clip``, which is why they agree on a NaN duration where
the ``list_clip`` kernel this path used to take did not. That kernel is
retired from *this path*, not from the framework: it still backs
``ColumnProxy.clip()`` on a list column whose bounds are themselves
columns, and on what the alignment reached -- a NaN and a crossed pair
of bounds -- it no longer disagrees there either. On what the alignment
did not reach it still does: a null bound, a null list row, and an
Int64 column handed back as ``List(Float64)``.
Which form is used is decided on the column's actual dtype, in the
lowering, where the frame's schema is in reach. Both shapes are held
here, and the values they answer with are the same rates.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.mortality._mortality_table import MortalityTable


class TestSelectUltimateAt:
    """select_ultimate: clamps duration at select_period and looks up the table."""

    def test_duration_within_select_period_uses_select_rate(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """For duration <= select_period the lookup uses the actual duration."""
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        frame = pl.DataFrame({"age": [30, 40], "duration": [1, 3]})
        result = frame.with_columns(
            qx=m.at(age=pl.col("age"), duration=pl.col("duration")),
        )
        # Fixture rates: 0.001 * age * (1 + 0.1 * duration)
        # Age 30, duration 1 -> 0.001 * 30 * 1.1 = 0.033
        # Age 40, duration 3 -> 0.001 * 40 * 1.3 = 0.052
        assert result.get_column("qx").to_list() == pytest.approx([0.033, 0.052])

    def test_duration_above_select_period_clamps_to_select_period(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """Durations beyond select_period clamp to select_period."""
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        frame = pl.DataFrame({"age": [30, 40], "duration": [10, 25]})
        result = frame.with_columns(
            qx=m.at(age=pl.col("age"), duration=pl.col("duration")),
        )
        # Both clamped to duration=4 (the select_period):
        # 0.001 * age * (1 + 0.1 * 4) = 0.0014 * age
        # Age 30 -> 0.001 * 30 * 1.4 = 0.042
        # Age 40 -> 0.001 * 40 * 1.4 = 0.056
        assert result.get_column("qx").to_list() == pytest.approx([0.042, 0.056])

    def test_select_ultimate_requires_age_and_duration(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """select_ultimate requires both age and duration."""
        m = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        pattern = "select_ultimate.*requires.*age.*duration"
        with pytest.raises(ValueError, match=pattern):
            m.at(age=pl.col("age"))
        with pytest.raises(ValueError, match=pattern):
            m.at(duration=pl.col("duration"))


class TestTheTwoShapesADurationComesIn:
    """One convention, two column shapes, one set of answers."""

    def test_a_pricing_at_issue_read_clamps_instead_of_crashing(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """Scalar age and scalar duration, no projection: a rate, not an engine error.

        Pricing at issue is one point in time, so the model points carry a
        duration per policy rather than one per period. The clamp used to be
        chosen by asking whether the caller had passed a column proxy, and a
        per-policy column is a proxy too -- so this read took the list form
        and came back as ``ComputeError: values must be List dtype for
        list_clip``.
        """
        basis = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        frame = ActuarialFrame(
            pl.DataFrame({"age": [30, 40, 50], "duration": [1, 3, 25]})
        )
        frame.qx = basis.at(age=frame.age, duration=frame.duration)

        # Fixture rates: 0.001 * age * (1 + 0.1 * duration); 25 clamps to 4.
        assert frame.collect()["qx"].to_list() == pytest.approx([0.033, 0.052, 0.070])

    def test_a_projection_clamps_every_period_s_own_duration(
        self,
        select_ultimate_table: Table,
    ) -> None:
        """The per-period path: one clamp and one rate per projection period."""
        basis = MortalityTable(
            table=select_ultimate_table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=4,
        )
        frame = ActuarialFrame(pl.DataFrame({"policy_id": [1], "issue_age": [30]}))
        frame = frame.projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="term_months",
            until_value=60,
            frequency="annual",
        )
        frame.duration = frame.month // 12 + 1
        frame.qx = basis.at(age=frame.issue_age, duration=frame.duration)

        # Durations 1..6 against a select period of 4: the last two read the
        # select period's own row, which is what an ultimate rate is.
        assert frame.collect()["qx"].to_list()[0] == pytest.approx(
            [0.033, 0.036, 0.039, 0.042, 0.042, 0.042]
        )


class TestTheClampLandsOnTheDurationAndOnNothingElse:
    """The shape a shipped model actually reads a select basis in.

    A production basis is keyed by more than age and duration -- a table
    identifier for sex or smoker status is the usual third key -- and in a
    projection those keys do not share a shape: the duration is one value
    per period, the table identifier one value per policy. The read pairs
    each argument with the dimension it answers for and clamps only the
    duration, so the mixed shapes have to survive the pairing and the
    per-policy key has to reach every period.
    """

    @staticmethod
    def _basis(select_period: int = 2) -> MortalityTable:
        """Return a basis keyed by table_id, age and duration.

        Durations run from 0, so a read also shows that the clamp bounds
        above only: nothing raises a duration that has not reached the
        select period yet.
        """
        table = Table(
            name="select_by_sex_per_period",
            source=pl.DataFrame(
                [
                    {
                        "table_id": table_id,
                        "age": 30,
                        "duration": duration,
                        "qx": factor * (1 + duration),
                    }
                    for table_id, factor in (("M", 0.001), ("F", 0.002))
                    for duration in range(4)
                ]
            ),
            dimensions={
                "age": "age",
                "duration": "duration",
                "table_id": "table_id",
            },
            value="qx",
        )
        return MortalityTable(
            table=table,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=select_period,
        )

    def test_a_per_policy_key_reaches_every_period_of_a_clamped_read(self) -> None:
        """Two policies, two identifiers, one clamped duration per period."""
        frame = ActuarialFrame(
            pl.DataFrame({"policy_id": [1, 2], "age": [30, 30], "sex": ["M", "F"]})
        )
        frame = frame.projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="term_months",
            until_value=48,
            frequency="annual",
        )
        frame.duration = frame.month // 12
        frame.qx = self._basis().at(
            age=frame.age, duration=frame.duration, table_id=frame.sex
        )

        # Durations 0,1,2,3,4 against a select period of 2 read rows
        # 0,1,2,2,2. Rates are factor * (1 + duration), the factor coming
        # from each policy's own table_id.
        rates = frame.collect()["qx"].to_list()
        assert rates[0] == pytest.approx([0.001, 0.002, 0.003, 0.003, 0.003])
        assert rates[1] == pytest.approx([0.002, 0.004, 0.006, 0.006, 0.006])

    def test_the_unclamped_keys_are_read_exactly_as_written(self) -> None:
        """A per-period age is not held at anything; only the duration is.

        The clamp is named by the dimension it applies to rather than by
        position, so an age that climbs past the select period climbs. The
        basis holds age 30 only, so an attained age walking off the grid
        misses -- and the refusal prints both keys as the read sent them,
        which is where the two behaviours are legible side by side.
        """
        frame = ActuarialFrame(pl.DataFrame({"policy_id": [1], "issue_age": [30]}))
        frame = frame.projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="term_months",
            until_value=24,
            frequency="annual",
        )
        frame.attained_age = frame.issue_age + frame.month // 12
        frame.duration = frame.month // 12
        frame.qx = self._basis(select_period=1).at(
            age=frame.attained_age, duration=frame.duration, table_id="M"
        )

        with pytest.raises(pl.exceptions.ComputeError) as raised:
            frame.collect()

        # Three periods, both keys printed as the read sent them: the age
        # walked 30, 31, 32 and the duration was held at 1.
        assert "attained_age=[30, 31, 32]" in str(raised.value)
        assert "duration=[0, 1, 1]" in str(raised.value)
