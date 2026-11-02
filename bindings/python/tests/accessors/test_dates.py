# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import datetime
from pathlib import Path

import polars as pl

from gaspatchio import ActuarialFrame

# ADDED: Define base path relative to this test file
TEST_DIR = Path(__file__).parent


def test_fixture_load():
    # Load fixture CSV and ensure it loads correctly
    # UPDATED: Use correct relative path and resolve
    fixture = (TEST_DIR.parent / "fixtures" / "age-dates-test.csv").resolve()
    df = pl.read_csv(fixture.as_posix(), infer_schema_length=10000)
    # Assert expected columns and row count
    assert "age" in df.columns
    assert df.height > 0
    assert len(df.columns) == 5


class TestToPeriod:
    """``date.to_period`` snaps a date back to the start of its period.

    This is the aggregation key an experience study groups on: which month
    did the claim fall in, which quarter was the policy issued in.
    """

    def _claims_frame(self) -> ActuarialFrame:
        """Three claims spanning two months, two quarters and one year."""
        return ActuarialFrame(
            {
                "claim_id": [1, 2, 3],
                "claim_date": [
                    datetime.datetime(2023, 1, 15, 10, 30, 0),  # noqa: DTZ001
                    datetime.datetime(2023, 2, 5, 8, 0, 0),  # noqa: DTZ001
                    datetime.datetime(2023, 7, 20, 14, 0, 0),  # noqa: DTZ001
                ],
            }
        )

    def test_month_start(self) -> None:
        """Claims in the same month share one aggregation key."""
        af = self._claims_frame()

        af.claim_month = af.claim_date.date.to_period("M")

        assert af.collect()["claim_month"].to_list() == [
            datetime.date(2023, 1, 1),
            datetime.date(2023, 2, 1),
            datetime.date(2023, 7, 1),
        ]

    def test_quarter_start(self) -> None:
        """January and February collapse to the same quarter, July does not."""
        af = self._claims_frame()

        af.claim_quarter = af.claim_date.date.to_period("1q")

        assert af.collect()["claim_quarter"].to_list() == [
            datetime.date(2023, 1, 1),
            datetime.date(2023, 1, 1),
            datetime.date(2023, 7, 1),
        ]

    def test_year_start(self) -> None:
        """Every claim in the same accident year shares one key."""
        af = self._claims_frame()

        af.claim_year = af.claim_date.date.to_period("Y")

        assert af.collect()["claim_year"].to_list() == [datetime.date(2023, 1, 1)] * 3

    def test_a_polars_interval_is_passed_through_as_written(self) -> None:
        """A caller who already speaks Polars intervals is not blocked."""
        af = self._claims_frame()

        af.claim_month = af.claim_date.date.to_period("1mo")

        assert af.collect()["claim_month"].to_list() == [
            datetime.date(2023, 1, 1),
            datetime.date(2023, 2, 1),
            datetime.date(2023, 7, 1),
        ]

    def test_the_result_is_a_date_not_a_datetime(self) -> None:
        """Truncating a timestamp gives a date, so it joins to a date key."""
        af = self._claims_frame()

        af.claim_month = af.claim_date.date.to_period("M")

        assert af.collect().schema["claim_month"] == pl.Date
