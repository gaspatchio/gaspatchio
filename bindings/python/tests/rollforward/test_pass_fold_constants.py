# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""FoldConstants pass — pass-through stub."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio_core.rollforward._passes import FoldConstants

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._ir import IR


class TestFoldConstants:
    def test_pass_name(self) -> None:
        assert FoldConstants().name() == "fold_constants"

    def test_phase_1_is_pass_through(self, single_state_ir: IR) -> None:
        out = FoldConstants().apply(single_state_ir)
        assert out is single_state_ir
