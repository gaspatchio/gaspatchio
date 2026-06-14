# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Smoke test: a model with mixed scalar/list dispatch produces identical output in debug and optimize modes.

After Phase 2's shape SOT, mode parity is invariant by construction — the
single schema-based source of shape truth means debug and optimize cannot
disagree. This test pins that property end-to-end against a representative
mixed model.
"""

from __future__ import annotations

import pytest

from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.util import set_default_mode


def _build_model(af: ActuarialFrame) -> ActuarialFrame:
    af.is_active = af.month < af.premium_term
    af.premium_due = (
        when(af.is_active == False)  # noqa: E712 — list comparison via ==
        .then(0.0)
        .when(af.age > 60)
        .then(af.base_premium * 1.2)
        .otherwise(af.base_premium)
    )
    return af


def _fresh_frame() -> ActuarialFrame:
    return ActuarialFrame(
        {
            "policy_id": ["P001", "P002"],
            "age": [35, 65],
            "month": [list(range(12)), list(range(24))],
            "premium_term": [12, 24],
            "base_premium": [100.0, 200.0],
        }
    )


class TestModeParity:
    def test_mixed_scalar_list_dispatch_parity(self) -> None:
        set_default_mode("debug")
        debug_result = _build_model(_fresh_frame()).collect()

        set_default_mode("optimize")
        optimize_result = _build_model(_fresh_frame()).collect()

        # Same columns, same values, same schema
        assert debug_result.columns == optimize_result.columns
        for col in debug_result.columns:
            assert debug_result[col].to_list() == optimize_result[col].to_list(), (
                f"Column {col} differs between debug and optimize modes"
            )
        assert debug_result.schema == optimize_result.schema
