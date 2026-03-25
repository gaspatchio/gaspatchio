"""Tests for compile_rollforward: converting builder to plugin args/kwargs."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.rollforward._step import StepDef


class TestCompileSingleState:
    """Tests for single-state rollforward compilation."""

    def test_basic_structure(self) -> None:
        """Add + charge produces 3 args (av_init, premium, admin_rate) and correct kwargs."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add("premium", "Premium")
            .charge("admin_rate", "Admin Fee")
        )
        args, kwargs = compile_rollforward(b)

        # 3 unique columns: av_init, premium, admin_rate
        assert len(args) == 3
        assert all(isinstance(a, pl.Expr) for a in args)

        # States: single "__default__" state
        assert len(kwargs["states"]) == 1
        assert kwargs["states"][0]["name"] == "__default__"
        assert kwargs["states"][0]["initial_col_index"] == 0  # av_init is first

        # Steps: 2 steps
        assert len(kwargs["steps"]) == 2

        add_step = kwargs["steps"][0]
        assert "Add" in add_step
        assert add_step["Add"]["target_index"] == 0
        assert add_step["Add"]["input_index"] == 1  # premium
        assert add_step["Add"]["label"] == "Premium"
        assert add_step["Add"]["expected_input_index"] is None

        charge_step = kwargs["steps"][1]
        assert "Charge" in charge_step
        assert charge_step["Charge"]["target_index"] == 0
        assert charge_step["Charge"]["input_index"] == 2  # admin_rate
        assert charge_step["Charge"]["label"] == "Admin Fee"

        assert kwargs["track_increments"] is False
        assert kwargs["assertion_mode"] is None
        assert kwargs["num_captures"] == 0
        assert kwargs["lapse_condition"] is None

    def test_column_deduplication(self) -> None:
        """Same column used twice should share the same index in args."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add("premium", "Add Premium")
            .subtract("premium", "Sub Premium")
        )
        args, kwargs = compile_rollforward(b)

        # Only 2 unique columns: av_init, premium (reused)
        assert len(args) == 2

        add_step = kwargs["steps"][0]
        sub_step = kwargs["steps"][1]
        # Both reference the same index for "premium"
        assert add_step["Add"]["input_index"] == sub_step["Subtract"]["input_index"]
        assert add_step["Add"]["input_index"] == 1

    def test_deduct_nar_kwargs(self) -> None:
        """DeductNar produces distinct rate_index and db_index."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .deduct_nar("coi_rate", death_benefit="death_benefit", label="COI")
        )
        args, kwargs = compile_rollforward(b)

        # 3 columns: av_init, coi_rate, death_benefit
        assert len(args) == 3

        step = kwargs["steps"][0]
        assert "DeductNar" in step
        nar = step["DeductNar"]
        assert nar["rate_index"] == 1
        assert nar["db_index"] == 2
        assert nar["label"] == "COI"
        # rate and db must be different indices
        assert nar["rate_index"] != nar["db_index"]

    def test_grow_capped_kwargs(self) -> None:
        """GrowCapped includes rate_floor and rate_cap in output."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .grow_capped("interest_rate", floor=-0.05, cap=0.15, label="Capped Growth")
        )
        args, kwargs = compile_rollforward(b)

        step = kwargs["steps"][0]
        assert "GrowCapped" in step
        gc = step["GrowCapped"]
        assert gc["input_index"] == 1
        assert gc["rate_floor"] == -0.05
        assert gc["rate_cap"] == 0.15
        assert gc["label"] == "Capped Growth"

    def test_floor_and_cap_steps(self) -> None:
        """Floor and Cap store literal float values, no column registration."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .floor(0.0, "Zero Floor")
            .cap(1000000.0, "Max Cap")
        )
        args, kwargs = compile_rollforward(b)

        # Only 1 column: av_init (floor/cap don't register columns)
        assert len(args) == 1

        floor_step = kwargs["steps"][0]
        assert "Floor" in floor_step
        assert floor_step["Floor"]["value"] == 0.0
        assert floor_step["Floor"]["target_index"] == 0

        cap_step = kwargs["steps"][1]
        assert "Cap" in cap_step
        assert cap_step["Cap"]["value"] == 1000000.0

    def test_lapse_if_zero(self) -> None:
        """LapseIfZero only has target_index."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .lapse_if_zero("Lapse Check")
        )
        args, kwargs = compile_rollforward(b)

        step = kwargs["steps"][0]
        assert "LapseIfZero" in step
        assert step["LapseIfZero"]["target_index"] == 0
        assert len(step["LapseIfZero"]) == 1

    def test_add_if_step(self) -> None:
        """AddIf registers both condition and amount columns."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add_if("is_alive", "bonus", "Bonus If Alive")
        )
        args, kwargs = compile_rollforward(b)

        # 3 columns: av_init, is_alive, bonus
        assert len(args) == 3

        step = kwargs["steps"][0]
        assert "AddIf" in step
        assert step["AddIf"]["condition_index"] == 1
        assert step["AddIf"]["amount_index"] == 2
        assert step["AddIf"]["label"] == "Bonus If Alive"

    def test_charge_if_step(self) -> None:
        """ChargeIf registers both condition and rate columns."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .charge_if("has_rider", "rider_rate", "Rider Fee")
        )
        args, kwargs = compile_rollforward(b)

        step = kwargs["steps"][0]
        assert "ChargeIf" in step
        assert step["ChargeIf"]["condition_index"] == 1
        assert step["ChargeIf"]["rate_index"] == 2

    def test_track_increments_flag(self) -> None:
        """track_increments is propagated to kwargs."""
        b = RollforwardBuilder(
            frame=None, initial="av_init", track_increments=True,
        ).add("premium", "Premium")
        _, kwargs = compile_rollforward(b)

        assert kwargs["track_increments"] is True

    def test_grow_and_subtract_steps(self) -> None:
        """Grow and Subtract produce correct step tags."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .grow("interest_rate", "Interest")
            .subtract("fees", "Fees")
        )
        _, kwargs = compile_rollforward(b)

        assert "Grow" in kwargs["steps"][0]
        assert "Subtract" in kwargs["steps"][1]

    def test_unknown_operation_raises(self) -> None:
        """An unknown operation in a StepDef raises ValueError."""
        step = StepDef(operation="explode", label="Boom", args=("x",))
        b = RollforwardBuilder(
            frame=None,
            initial="av_init",
            _steps=(step,),
        )
        with pytest.raises(ValueError, match="Unknown rollforward operation"):
            compile_rollforward(b)


class TestCompileMultiState:
    """Tests for multi-state rollforward compilation."""

    def test_multi_state_structure(self) -> None:
        """Two states produce correct states list and target indices."""
        b = (
            RollforwardBuilder(
                frame=None,
                states={"av": "av_init", "guarantee": "g_init"},
            )
            .on("av")
            .add("premium", "Premium AV")
            .on("guarantee")
            .grow("fund_return", "Fund Return Guar")
        )
        args, kwargs = compile_rollforward(b)

        # 4 unique columns: av_init, g_init, premium, fund_return
        assert len(args) == 4

        # States
        assert len(kwargs["states"]) == 2
        assert kwargs["states"][0]["name"] == "av"
        assert kwargs["states"][0]["initial_col_index"] == 0
        assert kwargs["states"][1]["name"] == "guarantee"
        assert kwargs["states"][1]["initial_col_index"] == 1

        # Premium targets av (index 0)
        add_step = kwargs["steps"][0]
        assert add_step["Add"]["target_index"] == 0

        # Grow targets guarantee (index 1)
        grow_step = kwargs["steps"][1]
        assert grow_step["Grow"]["target_index"] == 1

    def test_ratchet_to_resolves_state(self) -> None:
        """RatchetTo resolves other_state_index from state_name_to_index."""
        b = (
            RollforwardBuilder(
                frame=None,
                states={"av": "av_init", "guarantee": "g_init"},
            )
            .on("guarantee")
            .ratchet_to("av", "Ratchet DB")
        )
        _, kwargs = compile_rollforward(b)

        step = kwargs["steps"][0]
        assert "RatchetTo" in step
        # target is guarantee (index 1), other_state is av (index 0)
        assert step["RatchetTo"]["target_index"] == 1
        assert step["RatchetTo"]["other_state_index"] == 0

    def test_capture_and_pro_rata(self) -> None:
        """Capture indices are resolved and ProRataWith references them.

        Uses raw StepDef objects since the builder's pro_rata_with()
        currently only stores the state name. The Rust ProRataWith expects
        capture_index and amount_index.
        """
        # Build step sequence manually:
        # 1. Capture AV (capture index 0)
        # 2. Subtract withdrawal from AV
        # 3. Pro-rata benefit_base using captured AV and withdrawal amount
        capture_step = StepDef(
            operation="capture",
            label="AV Snapshot",
            args=(),
            kwargs={"_target": "av"},
        )
        subtract_step = StepDef(
            operation="subtract",
            label="Withdraw",
            args=("withdrawal",),
            kwargs={"_target": "av"},
        )
        pro_rata_step = StepDef(
            operation="pro_rata_with",
            label="Pro Rata BB",
            args=("AV Snapshot", "withdrawal"),
            kwargs={"_target": "benefit_base"},
        )

        b = RollforwardBuilder(
            frame=None,
            states={"av": "av_init", "benefit_base": "bb_init"},
            _steps=(capture_step, subtract_step, pro_rata_step),
        )
        args, kwargs = compile_rollforward(b)

        # Columns: av_init, bb_init, withdrawal
        assert len(args) == 3

        # Capture step
        cap = kwargs["steps"][0]
        assert "Capture" in cap
        assert cap["Capture"]["target_index"] == 0  # av
        assert cap["Capture"]["capture_index"] == 0

        # ProRataWith step
        prt = kwargs["steps"][2]
        assert "ProRataWith" in prt
        assert prt["ProRataWith"]["target_index"] == 1  # benefit_base
        assert prt["ProRataWith"]["capture_index"] == 0  # AV Snapshot
        assert prt["ProRataWith"]["amount_index"] == 2  # withdrawal

        assert kwargs["num_captures"] == 1

    def test_lapse_condition(self) -> None:
        """AllNonPositive lapse condition resolves state names to indices."""
        b = (
            RollforwardBuilder(
                frame=None,
                states={"av": "av_init", "guarantee": "g_init"},
            )
            .on("av")
            .add("premium", "Premium")
            .lapse_when(all_non_positive=["av", "guarantee"])
        )
        _, kwargs = compile_rollforward(b)

        assert kwargs["lapse_condition"] is not None
        assert "AllNonPositive" in kwargs["lapse_condition"]
        indices = kwargs["lapse_condition"]["AllNonPositive"]["state_indices"]
        assert indices == [0, 1]

    def test_lapse_condition_none_when_not_set(self) -> None:
        """No lapse_when call means lapse_condition is None."""
        b = (
            RollforwardBuilder(
                frame=None,
                states={"av": "av_init", "guarantee": "g_init"},
            )
            .on("av")
            .add("premium", "Premium")
        )
        _, kwargs = compile_rollforward(b)

        assert kwargs["lapse_condition"] is None

    def test_multiple_captures(self) -> None:
        """Multiple capture steps get sequential indices."""
        cap1 = StepDef(operation="capture", label="Snap1", args=(), kwargs={"_target": "av"})
        cap2 = StepDef(operation="capture", label="Snap2", args=(), kwargs={"_target": "av"})

        b = RollforwardBuilder(
            frame=None,
            states={"av": "av_init"},
            _steps=(cap1, cap2),
        )
        _, kwargs = compile_rollforward(b)

        assert kwargs["num_captures"] == 2
        assert kwargs["steps"][0]["Capture"]["capture_index"] == 0
        assert kwargs["steps"][1]["Capture"]["capture_index"] == 1


class TestCompileEdgeCases:
    """Edge cases and deduplication scenarios."""

    def test_empty_steps(self) -> None:
        """Builder with no steps produces empty steps list."""
        b = RollforwardBuilder(frame=None, initial="av_init")
        args, kwargs = compile_rollforward(b)

        assert len(args) == 1
        assert len(kwargs["steps"]) == 0
        assert len(kwargs["states"]) == 1

    def test_initial_column_shared_with_step(self) -> None:
        """If a step references the same column as initial, they share an index."""
        b = (
            RollforwardBuilder(frame=None, initial="av_init")
            .add("av_init", "Add Self")
        )
        args, kwargs = compile_rollforward(b)

        # Only 1 column: av_init is reused
        assert len(args) == 1
        assert kwargs["states"][0]["initial_col_index"] == 0
        assert kwargs["steps"][0]["Add"]["input_index"] == 0

    def test_multi_state_column_deduplication(self) -> None:
        """Multi-state: same column used by two states and a step."""
        b = (
            RollforwardBuilder(
                frame=None,
                states={"av": "shared_init", "guarantee": "shared_init"},
            )
            .on("av")
            .add("shared_init", "Add Shared")
        )
        args, kwargs = compile_rollforward(b)

        # Only 1 column: shared_init for everything
        assert len(args) == 1
        assert kwargs["states"][0]["initial_col_index"] == 0
        assert kwargs["states"][1]["initial_col_index"] == 0
        assert kwargs["steps"][0]["Add"]["input_index"] == 0
