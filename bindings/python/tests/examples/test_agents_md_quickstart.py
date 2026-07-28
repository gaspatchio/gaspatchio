# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The AGENTS.md quickstart must actually run.

AGENTS.md is auto-loaded by every agent session, so a rotted example makes
every downstream session start from a false premise. #35 was exactly that: the
quickstart called ``af.date.create_projection_timeline(...)``, removed some
releases ago, and its parameter names (``projection_end_type``,
``projection_end_value``, ``projection_frequency``) had drifted too.

Correcting the prose fixes today and drifts again next release, so the
documented shape is executed here end to end.
"""

import datetime

import polars as pl

from gaspatchio_core import ActuarialFrame


def _model_points() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "policy_id": [1, 2],
            "issue_age": [40, 55],
            "policy_inception": [
                datetime.date(2020, 1, 1),
                datetime.date(2021, 6, 1),
            ],
        }
    )


def test_quickstart_projection_setup_runs() -> None:
    af = ActuarialFrame(_model_points())

    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="maximum_age",
        until_value=100,
        frequency="monthly",
    )

    out = af.collect()
    assert out.height == 2


def test_removed_api_is_really_gone() -> None:
    """Pins the reason #35 existed: the old entry point must not resurface."""
    af = ActuarialFrame(_model_points())
    assert not hasattr(af.date, "create_projection_timeline")
