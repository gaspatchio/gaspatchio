# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The AGENTS.md quickstart must actually run.

AGENTS.md is auto-loaded by every agent session, so a rotted example makes
every downstream session start from a false premise. #35 was exactly that: the
quickstart called ``af.date.create_projection_timeline(...)``, removed some
releases ago, and its parameter names (``projection_end_type``,
``projection_end_value``, ``projection_frequency``) had drifted too.

An earlier version of this test executed only the ``projection.set`` call —
the one line that had been reported — while claiming to cover the example end
to end. It therefore still passed with a Phase 3 that referenced ``af.age``,
a column the documented Phase 1 never creates. The whole three-phase shape is
executed here, because a guard that stops short of the rot is not a guard.
"""

import datetime
import itertools

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table


def _model_points() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "policy_id": [1, 2],
            "Issue Age": [40, 55],
            "policy_inception": [
                datetime.date(2020, 1, 1),
                datetime.date(2021, 6, 1),
            ],
        }
    )


def _mortality_table() -> Table:
    return Table(
        name="quickstart_mortality",
        source=pl.DataFrame(
            {
                # Wide enough for every attained age the projection reaches.
                # `until="maximum_age"` sizes one grid from the youngest life,
                # so the 55-year-old runs to attained age 115.
                "age": list(range(18, 131)),
                "rate": [min(0.001 + 0.0005 * (a - 18), 1.0) for a in range(18, 131)],
            }
        ),
        dimensions={"age": "age"},
        value="rate",
    )


def test_quickstart_three_phase_shape_runs_end_to_end() -> None:
    """Execute the documented Phase 1 -> 2 -> 3 shape exactly as written."""
    tables = {"mortality": _mortality_table()}
    af = ActuarialFrame(_model_points())

    # --- PHASE 1: Setup (scalar ops, .collect() OK here) ---
    mp = af.collect()
    mp = mp.with_columns(pl.col("Issue Age").alias("issue_age"))
    af = ActuarialFrame(mp)

    # --- PHASE 2: Projection timeline ---
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="maximum_age",
        until_value=100,
        frequency="monthly",
    )

    # --- PHASE 3: Calculations (lazy -- NO .collect() from here) ---
    af.attained_age = af.issue_age + af.proj_year
    af.mort_rate = tables["mortality"].lookup(age=af.attained_age)
    af.survival = af.mort_rate.projection.cumulative_survival()

    out = af.collect()
    assert out.height == 2
    assert "survival" in out.columns
    # A projection, not a single number: one survival value per period.
    assert out.schema["survival"] == pl.List(pl.Float64)
    # Survival is a probability and must be non-increasing over the projection.
    first_policy = out["survival"].to_list()[0]
    assert len(first_policy) > 1
    assert first_policy[0] <= 1.0
    assert all(
        later <= earlier + 1e-12 for earlier, later in itertools.pairwise(first_policy)
    )


def test_removed_api_is_really_gone() -> None:
    """Pins the reason #35 existed: the old entry point must not resurface."""
    af = ActuarialFrame(_model_points())
    assert not hasattr(af.date, "create_projection_timeline")
