# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""§4.9 GSP-92 VA Illustration acceptance test — gated on gold-file landing.

Per spec §13.0, before this becomes a release-gate the gold values for
``policy_00000065.parquet`` must be sourced from an authority independent
of any prior in-tree implementation. Until the gold file lands in this
checkout, the test is skipped — the scaffold ships now so wiring it up
is one focused PR once the gold-file pathway is settled.

When unblocking:
  1. Drop the gold parquet at ``tests/fixtures/policy_00000065.parquet``.
  2. Build the §4.9 model: 1200-period VA with GMDB ratchet, COI deduction,
     fund growth, lapse stop-condition. See spec §4.9 for the construction.
  3. Reconcile each of the 25 list-typed output columns to the gold file
     at ``atol ≤ 1e-9`` per spec §4.9.
"""

from __future__ import annotations

from pathlib import Path

import pytest

GOLD_FILE = Path(__file__).parent.parent / "fixtures" / "policy_00000065.parquet"


@pytest.mark.skipif(
    not GOLD_FILE.exists(),
    reason="VA gold-file not yet provided (see module docstring)",
)
class TestVaAcceptance:
    def test_full_model_reconciles_to_gold_file(self) -> None:
        # When the gold file lands:
        #   - Construct the §4.9 model: call af.projection.set(...) to declare
        #     the projection axis, then af.projection.rollforward(...) to build
        #     the state-machine projection.
        #   - Collect the 25 output columns
        #   - Loop over columns and assert pl.testing.assert_series_equal
        #     with atol=1e-9 against gold[col]
        pytest.fail(
            "VA acceptance body not yet implemented — gold file present but"
            " test not wired (see module docstring for unblocking steps)"
        )
