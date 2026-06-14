# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Regression tests for ``ArrayStorage::lookup_vector_batch`` under the streaming engine.

These pin the homepage example's shape — multi-policy list-column lookups
with downstream consumers — which previously panicked at
``core/src/assumptions/array_storage.rs:247`` ("index out of bounds:
the len is N but the index is N") and silently returned garbage memory
before the safe-indexing change in PR #104.

The streaming engine slices the with-columns op into chunks where the
list column's offsets are absolute positions into the parent buffer
(e.g. ``[5, 10]`` for a 1-row chunk of a 3-row series, not ``[0, 5]``).
Three things had to be fixed together:

  1. ``total_len = offsets[last] - offsets[0]`` (relative length)
  2. ``rechunk()`` the first vector column so the encoded view matches
     the offset buffer view
  3. Normalise the output ListArray offsets to start at 0

The tests below would fail loudly on any regression to those guarantees.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table


@pytest.fixture
def mortality_table() -> Table:
    """Linear-rate mortality table keyed by age — easy to predict from age."""
    return Table(
        name="qx_demo",
        source=pl.DataFrame(
            {
                "age": list(range(20, 120)),
                "qx": [0.001 + (a - 30) * 0.0008 for a in range(20, 120)],
            },
        ),
        dimensions={"age": "age"},
        value="qx",
    )


def _expected_qx(age: int) -> float:
    """Closed-form for the fixture's linear-rate mortality."""
    return 0.001 + (age - 30) * 0.0008


@pytest.mark.parametrize(
    ("n_policies", "ages_per_policy"),
    [
        (1, 3),    # baseline — was the only case that worked pre-fix
        (2, 3),    # smallest multi-policy case
        (2, 5),
        (3, 5),    # exact homepage example shape
        (5, 10),   # wider
        (10, 12),  # monthly projection over a year
    ],
)
def test_lookup_vector_batch_multi_policy(
    mortality_table: Table,
    n_policies: int,
    ages_per_policy: int,
) -> None:
    """Multi-policy list-column lookup returns correct values for every (policy, t)."""
    # Each policy starts at issue_age = 30 + 5 * policy_idx, projects ``ages_per_policy`` years
    issue_ages = [30 + 5 * i for i in range(n_policies)]
    attained_age = [
        list(range(issue, issue + ages_per_policy)) for issue in issue_ages
    ]

    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [f"P{i:03d}" for i in range(n_policies)],
                "attained_age": attained_age,
            },
        ),
    )
    af.qx = mortality_table.lookup(age=af.attained_age)
    result = af.collect()

    qx_lists = result.get_column("qx").to_list()
    assert len(qx_lists) == n_policies, "row count mismatch"
    for policy_idx, qx_list in enumerate(qx_lists):
        assert len(qx_list) == ages_per_policy, (
            f"policy {policy_idx} list length mismatch"
        )
        for t, qx in enumerate(qx_list):
            expected = _expected_qx(attained_age[policy_idx][t])
            assert qx == pytest.approx(expected, rel=1e-9), (
                f"policy {policy_idx} t={t}: expected {expected}, got {qx}"
            )


def test_lookup_with_downstream_consumer_forces_streaming(
    mortality_table: Table,
) -> None:
    """
    Exact homepage shape — 3 policies, downstream chain (qx → survival →
    expected_claims). The downstream chain is what previously triggered
    the streaming engine's sliced-offset behaviour.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P001", "P002", "P003"],
                "sum_assured": [100_000.0, 250_000.0, 500_000.0],
                "attained_age": [
                    [35, 36, 37, 38, 39],
                    [42, 43, 44, 45, 46],
                    [55, 56, 57, 58, 59],
                ],
            },
        ),
    )
    af.qx = mortality_table.lookup(age=af.attained_age)
    af.survival = af.qx.projection.cumulative_survival()
    af.expected_claims = af.survival * af.qx * af.sum_assured
    result = af.collect()

    # Survival at t=0 must be 1.0 for every policy
    for survival in result.get_column("survival").to_list():
        assert survival[0] == pytest.approx(1.0, rel=1e-12)

    # P001 — first qx is _expected_qx(35) = 0.005 — pin the first claim
    p001 = result.filter(pl.col("policy_id") == "P001").row(0, named=True)
    assert p001["qx"][0] == pytest.approx(0.005, rel=1e-9)
    assert p001["expected_claims"][0] == pytest.approx(500.0, rel=1e-9)

    # P003 starts at age 55 — the highest qx
    p003 = result.filter(pl.col("policy_id") == "P003").row(0, named=True)
    expected_p003_qx_0 = _expected_qx(55)
    assert p003["qx"][0] == pytest.approx(expected_p003_qx_0, rel=1e-9)
    assert p003["expected_claims"][0] == pytest.approx(
        500_000.0 * expected_p003_qx_0,
        rel=1e-9,
    )


def test_lookup_with_explicit_streaming_engine(mortality_table: Table) -> None:
    """Pin the streaming engine path explicitly — this is the slicing trigger."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P001", "P002", "P003"],
                "attained_age": [
                    [40, 41, 42],
                    [50, 51, 52],
                    [60, 61, 62],
                ],
            },
        ),
    )
    af.qx = mortality_table.lookup(age=af.attained_age)
    af.qx_times_two = af.qx * 2.0  # downstream consumer forces sub-graph split
    result = af.collect(engine="streaming")

    qx_lists = result.get_column("qx").to_list()
    qx_x2_lists = result.get_column("qx_times_two").to_list()

    assert len(qx_lists) == 3
    for policy_idx, (qx_list, qx_x2_list) in enumerate(zip(qx_lists, qx_x2_lists, strict=True)):
        for t in range(3):
            age = 40 + 10 * policy_idx + t
            expected_qx = _expected_qx(age)
            assert qx_list[t] == pytest.approx(expected_qx, rel=1e-9)
            assert qx_x2_list[t] == pytest.approx(2.0 * expected_qx, rel=1e-9)
