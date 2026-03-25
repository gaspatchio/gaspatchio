"""Tests for explain(), canonical(), and fingerprint() on RollforwardBuilder."""

from __future__ import annotations

import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder


class TestExplain:
    """Tests for RollforwardBuilder.explain()."""

    def test_explain_basic(self) -> None:
        """explain() output contains label and formula tokens."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add("premium", "Premium")
            .grow("interest_rate", "Interest")
        )
        output = b.explain()
        assert "Premium" in output
        assert "Interest" in output
        assert "av_init[t]" in output

    def test_explain_contains_header(self) -> None:
        """explain() starts with a Rollforward header line."""
        b = RollforwardBuilder(frame=None, initial="av").add("p", "P")
        output = b.explain()
        assert output.startswith("Rollforward:")
        assert "initial=av" in output

    def test_explain_step_count_in_header(self) -> None:
        """Header shows correct step count."""
        b = (
            RollforwardBuilder(frame=None, initial="av")
            .add("a", "A")
            .grow("r", "R")
            .floor(0.0)
        )
        output = b.explain()
        assert "3 steps" in output

    def test_explain_singular_step(self) -> None:
        """Header uses 'step' (not 'steps') for a single step."""
        b = RollforwardBuilder(frame=None, initial="av").add("a", "A")
        output = b.explain()
        assert "1 step" in output
        assert "1 steps" not in output

    def test_explain_all_operations(self) -> None:
        """explain() renders formulas for a variety of operations."""
        b = (
            RollforwardBuilder(frame=None, initial="av")
            .add("prem", "Premium")
            .subtract("fee", "Fee")
            .charge("admin_rate", "Admin")
            .grow("int_rate", "Interest")
            .grow_capped("rate", floor=0.0, cap=0.12, label="GrowCapped")
            .floor(0.0, "Floor0")
            .cap(1000.0, "Cap1000")
            .lapse_if_zero("LapseIfZero")
            .add_if("has_prem", "bonus", "AddIf")
            .charge_if("is_alive", "mort_rate", "ChargeIf")
        )
        output = b.explain()
        assert "av[t] = av[t] + prem[t]" in output
        assert "av[t] = av[t] - fee[t]" in output
        assert "av[t] = av[t] * (1 - admin_rate[t])" in output
        assert "av[t] = av[t] * (1 + int_rate[t])" in output
        assert "clamp(rate[t], 0.0, 0.12)" in output
        assert "max(av[t], 0.0)" in output
        assert "min(av[t], 1000.0)" in output
        assert "if av[t] <= 0: zero remaining" in output
        assert "if has_prem[t]: av[t] += bonus[t]" in output
        assert "if is_alive[t]: av[t] *= (1 - mort_rate[t])" in output

    def test_explain_deduct_nar(self) -> None:
        """explain() renders deduct_nar formula with death benefit column."""
        b = RollforwardBuilder(frame=None, initial="av").deduct_nar(
            "coi_rate", death_benefit="sa", label="COI"
        )
        output = b.explain()
        assert "av[t] = av[t] - coi_rate[t] * max(0, sa[t] - av[t])" in output

    def test_explain_empty_builder(self) -> None:
        """explain() on an empty builder still shows header and column headers."""
        b = RollforwardBuilder(frame=None, initial="av")
        output = b.explain()
        assert "0 steps" in output
        assert "Step" in output

    def test_explain_multi_state(self) -> None:
        """State names appear in multi-state formulas."""
        b = (
            RollforwardBuilder(frame=None, states={"av": "av_col", "guar": "guar_col"})
            .on("av")
            .add("prem", "Premium AV")
            .on("guar")
            .add("guar_prem", "Premium Guar")
        )
        output = b.explain()
        assert "av[t]" in output
        assert "guar[t]" in output
        assert "states=[av, guar]" in output

    def test_explain_multi_state_ratchet(self) -> None:
        """ratchet_to formula uses correct av variable."""
        b = (
            RollforwardBuilder(frame=None, states={"av": "av_col", "guar": "guar_col"})
            .on("av")
            .ratchet_to("guar", "RatchetAV")
        )
        output = b.explain()
        assert "max(av[t], guar[t])" in output


class TestCanonical:
    """Tests for RollforwardBuilder.canonical()."""

    def test_canonical_returns_dict(self) -> None:
        """canonical() returns a dict."""
        b = RollforwardBuilder(frame=None, initial="av").add("prem", "P")
        assert isinstance(b.canonical(), dict)

    def test_canonical_dict(self) -> None:
        """canonical() has correct step entries for add and grow."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add("premium", "Premium")
            .grow("rate", "Interest")
        )
        canon = b.canonical()
        assert len(canon["steps"]) == 2
        assert canon["steps"][0] == {"operation": "add"}
        assert canon["steps"][1] == {"operation": "grow"}

    def test_canonical_excludes_labels_and_columns(self) -> None:
        """Two builders with same structure but different names/labels are equal."""
        b1 = RollforwardBuilder(frame=None, initial="x").add("a", "Label1")
        b2 = RollforwardBuilder(frame=None, initial="y").add("b", "Label2")
        assert b1.canonical() == b2.canonical()

    def test_canonical_includes_structural_params_floor(self) -> None:
        """canonical() includes 'value' for floor steps."""
        b = RollforwardBuilder(frame=None, initial="x").floor(0.0)
        steps = b.canonical()["steps"]
        assert steps[0] == {"operation": "floor", "value": 0.0}

    def test_canonical_includes_structural_params_cap(self) -> None:
        """canonical() includes 'value' for cap steps."""
        b = RollforwardBuilder(frame=None, initial="x").cap(1000.0)
        steps = b.canonical()["steps"]
        assert steps[0] == {"operation": "cap", "value": 1000.0}

    def test_canonical_includes_structural_params_grow_capped(self) -> None:
        """canonical() includes floor and cap for grow_capped steps."""
        b = RollforwardBuilder(frame=None, initial="x").grow_capped(
            "r", floor=0.0, cap=0.12, label="GC"
        )
        steps = b.canonical()["steps"]
        assert steps[0] == {"operation": "grow_capped", "floor": 0.0, "cap": 0.12}

    def test_canonical_floor_and_grow_capped_together(self) -> None:
        """canonical() handles mixed step types with structural params."""
        b = (
            RollforwardBuilder(frame=None, initial="x")
            .floor(0.0)
            .grow_capped("r", floor=0.0, cap=0.12, label="GC")
        )
        steps = b.canonical()["steps"]
        assert steps[0] == {"operation": "floor", "value": 0.0}
        assert steps[1] == {"operation": "grow_capped", "floor": 0.0, "cap": 0.12}

    def test_canonical_num_states_single(self) -> None:
        """canonical() reports num_states=1 for single-state builders."""
        b = RollforwardBuilder(frame=None, initial="av").add("p", "P")
        assert b.canonical()["num_states"] == 1

    def test_canonical_num_states_multi(self) -> None:
        """canonical() reports correct num_states for multi-state builders."""
        b = RollforwardBuilder(
            frame=None, states={"av": "av_col", "guar": "guar_col"}
        )
        assert b.canonical()["num_states"] == 2

    def test_canonical_track_increments(self) -> None:
        """canonical() includes track_increments flag."""
        b1 = RollforwardBuilder(frame=None, initial="av", track_increments=False).add("p", "P")
        b2 = RollforwardBuilder(frame=None, initial="av", track_increments=True).add("p", "P")
        assert b1.canonical()["track_increments"] is False
        assert b2.canonical()["track_increments"] is True

    def test_canonical_empty_builder(self) -> None:
        """canonical() on empty builder has empty steps list."""
        b = RollforwardBuilder(frame=None, initial="av")
        canon = b.canonical()
        assert canon["steps"] == []

    def test_canonical_deduct_nar_no_structural_params(self) -> None:
        """deduct_nar has no structural params in canonical form."""
        b = RollforwardBuilder(frame=None, initial="av").deduct_nar(
            "coi", death_benefit="sa", label="COI"
        )
        steps = b.canonical()["steps"]
        assert steps[0] == {"operation": "deduct_nar"}


class TestFingerprint:
    """Tests for RollforwardBuilder.fingerprint()."""

    def test_format(self) -> None:
        """fingerprint() returns 'sha256:' followed by 64 hex chars."""
        b = RollforwardBuilder(frame=None, initial="x").add("a", "P")
        fp = b.fingerprint()
        assert fp.startswith("sha256:")
        assert len(fp) == 7 + 64

    def test_only_hex_after_prefix(self) -> None:
        """Characters after 'sha256:' are valid hex."""
        b = RollforwardBuilder(frame=None, initial="x").add("a", "P")
        hex_part = b.fingerprint()[7:]
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_deterministic(self) -> None:
        """Same structure → same fingerprint regardless of column names or labels."""
        b1 = RollforwardBuilder(frame=None, initial="x").add("a", "A").grow("b", "B")
        b2 = RollforwardBuilder(frame=None, initial="y").add("c", "C").grow("d", "D")
        assert b1.fingerprint() == b2.fingerprint()

    def test_changes_with_different_operations(self) -> None:
        """Different operations → different fingerprints."""
        b1 = RollforwardBuilder(frame=None, initial="x").add("a", "A")
        b2 = RollforwardBuilder(frame=None, initial="x").grow("a", "A")
        assert b1.fingerprint() != b2.fingerprint()

    def test_changes_with_extra_step(self) -> None:
        """Adding a step changes the fingerprint."""
        b1 = RollforwardBuilder(frame=None, initial="x").add("a", "A")
        b2 = RollforwardBuilder(frame=None, initial="x").add("a", "A").grow("b", "B")
        assert b1.fingerprint() != b2.fingerprint()

    def test_changes_with_structural_param(self) -> None:
        """Different structural params (floor value) change fingerprint."""
        b1 = RollforwardBuilder(frame=None, initial="x").floor(0.0)
        b2 = RollforwardBuilder(frame=None, initial="x").floor(1.0)
        assert b1.fingerprint() != b2.fingerprint()

    def test_stable_across_calls(self) -> None:
        """fingerprint() is idempotent — same result on repeated calls."""
        b = RollforwardBuilder(frame=None, initial="x").add("a", "A")
        assert b.fingerprint() == b.fingerprint()

    def test_track_increments_changes_fingerprint(self) -> None:
        """Changing track_increments changes the fingerprint."""
        b1 = RollforwardBuilder(frame=None, initial="x", track_increments=False).add("a", "A")
        b2 = RollforwardBuilder(frame=None, initial="x", track_increments=True).add("a", "A")
        assert b1.fingerprint() != b2.fingerprint()
