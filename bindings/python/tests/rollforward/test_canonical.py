# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""IR canonical-form determinism."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio_core.rollforward._canonical import canonical_form

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._ir import IR


class TestCanonicalForm:
    def test_top_level_keys(self, single_state_ir: IR) -> None:
        cf = canonical_form(single_state_ir)
        # Per spec §9.1, batch_axes is OMITTED when it equals the engine
        # default ("policy",) — which the fixture uses. The default-omit
        # branch is exercised by test_default_batch_axes_omitted below.
        assert set(cf.keys()) == {
            "states",
            "points",
            "transitions",
            "schedule",
            "track_increments",
            "lapse_when_all_non_positive",
            "contract_boundary",
            "engine_binding",
        }

    def test_engine_binding_included(self, single_state_ir: IR) -> None:
        cf = canonical_form(single_state_ir)
        assert cf["engine_binding"] in ("portable", "polars")

    def test_default_batch_axes_omitted(self, single_state_ir: IR) -> None:
        # batch_axes=("policy",) is the default and is OMITTED from canonical form
        # (per spec §9.1: "hashed only when not the engine default")
        cf = canonical_form(single_state_ir)
        assert "batch_axes" not in cf

    def test_schedule_canonical_embedded(self, single_state_ir: IR) -> None:
        cf = canonical_form(single_state_ir)
        # Schedule's canonical form is embedded as a dict
        assert isinstance(cf["schedule"], dict)
        assert cf["schedule"]["kind"] == "from_calendar_grid"

    def test_two_identical_irs_have_identical_canonical(
        self,
        single_state_ir: IR,
    ) -> None:
        cf_a = canonical_form(single_state_ir)
        cf_b = canonical_form(single_state_ir)
        assert cf_a == cf_b

    def test_transitions_preserve_declared_order(self, single_state_ir: IR) -> None:
        cf = canonical_form(single_state_ir)
        # Transitions are ordered by declaration — NOT sorted
        # (order matters semantically).
        labels = [t.get("label") for t in cf["transitions"]]
        assert labels == ["Premium", "Interest", None]  # Floor has no label
