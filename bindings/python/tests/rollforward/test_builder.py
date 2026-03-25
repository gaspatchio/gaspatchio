"""Tests for RollforwardBuilder fluent interface."""

from __future__ import annotations

import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._step import StepDef


class TestBuilderConstruction:
    """Test RollforwardBuilder initialization."""

    def test_single_state_init(self) -> None:
        """Single-state builder uses 'initial' param, no states dict."""
        b = RollforwardBuilder(frame="af", initial="av")
        assert not b.is_multi_state
        assert b.steps == ()
        assert b.labels == ()

    def test_multi_state_init(self) -> None:
        """Multi-state builder uses 'states' dict."""
        b = RollforwardBuilder(
            frame="af",
            states={"av": "av_col", "guar": "guar_col"},
        )
        assert b.is_multi_state
        assert b.steps == ()

    def test_track_increments_default_false(self) -> None:
        """track_increments defaults to False."""
        b = RollforwardBuilder(frame="af", initial="av")
        assert b._track_increments is False  # noqa: SLF001

    def test_track_increments_true(self) -> None:
        """track_increments can be set to True."""
        b = RollforwardBuilder(frame="af", initial="av", track_increments=True)
        assert b._track_increments is True  # noqa: SLF001

    def test_raises_if_neither_initial_nor_states(self) -> None:
        """Raises ValueError if neither initial nor states supplied."""
        with pytest.raises(ValueError, match="initial"):
            RollforwardBuilder(frame="af")

    def test_raises_if_both_initial_and_states(self) -> None:
        """Raises ValueError if both initial and states supplied."""
        with pytest.raises(ValueError, match="initial"):
            RollforwardBuilder(frame="af", initial="av", states={"av": "av_col"})


class TestStepMethods:
    """One test per step method (14 total)."""

    def setup_method(self) -> None:
        """Create base single-state builder."""
        self.b = RollforwardBuilder(frame="af", initial="av")

    def test_add(self) -> None:
        b2 = self.b.add("premium", "Premium")
        assert len(b2.steps) == 1
        step = b2.steps[0]
        assert step.operation == "add"
        assert step.label == "Premium"
        assert step.args == ("premium",)

    def test_add_auto_label(self) -> None:
        b2 = self.b.add("premium")
        assert b2.steps[0].label == "Add(premium)"

    def test_subtract(self) -> None:
        b2 = self.b.subtract("expense", "Expense")
        step = b2.steps[0]
        assert step.operation == "subtract"
        assert step.label == "Expense"

    def test_subtract_auto_label(self) -> None:
        b2 = self.b.subtract("expense")
        assert b2.steps[0].label == "Subtract(expense)"

    def test_charge(self) -> None:
        b2 = self.b.charge("admin_rate", "Admin Fee")
        step = b2.steps[0]
        assert step.operation == "charge"
        assert step.label == "Admin Fee"

    def test_charge_auto_label(self) -> None:
        b2 = self.b.charge("admin_rate")
        assert b2.steps[0].label == "Charge(admin_rate)"

    def test_grow(self) -> None:
        b2 = self.b.grow("interest_rate", "Interest")
        step = b2.steps[0]
        assert step.operation == "grow"
        assert step.label == "Interest"

    def test_grow_auto_label(self) -> None:
        b2 = self.b.grow("rate")
        assert b2.steps[0].label == "Grow(rate)"

    def test_grow_capped(self) -> None:
        b2 = self.b.grow_capped("index_return", floor=0.0, cap=0.12, label="Index Credit")
        step = b2.steps[0]
        assert step.operation == "grow_capped"
        assert step.label == "Index Credit"
        assert step.kwargs["floor"] == 0.0
        assert step.kwargs["cap"] == 0.12

    def test_grow_capped_auto_label(self) -> None:
        b2 = self.b.grow_capped("idx", floor=-0.1, cap=0.15)
        assert b2.steps[0].label == "GrowCapped(idx)"

    def test_deduct_nar(self) -> None:
        b2 = self.b.deduct_nar("coi_rate", death_benefit="sum_assured", label="COI")
        step = b2.steps[0]
        assert step.operation == "deduct_nar"
        assert step.kwargs["death_benefit"] == "sum_assured"
        assert step.label == "COI"

    def test_deduct_nar_auto_label(self) -> None:
        b2 = self.b.deduct_nar("coi_rate", death_benefit="db")
        assert b2.steps[0].label == "DeductNAR(coi_rate)"

    def test_floor(self) -> None:
        b2 = self.b.floor(0.0, "Floor Zero")
        step = b2.steps[0]
        assert step.operation == "floor"
        assert step.label == "Floor Zero"
        assert step.args == (0.0,)

    def test_floor_auto_label(self) -> None:
        b2 = self.b.floor(0.0)
        assert b2.steps[0].label == "Floor(0.0)"

    def test_cap(self) -> None:
        b2 = self.b.cap(1_000_000.0, "Cap AV")
        step = b2.steps[0]
        assert step.operation == "cap"
        assert step.label == "Cap AV"

    def test_cap_auto_label(self) -> None:
        b2 = self.b.cap(1000.0)
        assert b2.steps[0].label == "Cap(1000.0)"

    def test_lapse_if_zero(self) -> None:
        b2 = self.b.lapse_if_zero("Lapse Zero AV")
        step = b2.steps[0]
        assert step.operation == "lapse_if_zero"
        assert step.label == "Lapse Zero AV"

    def test_lapse_if_zero_auto_label(self) -> None:
        b2 = self.b.lapse_if_zero()
        assert b2.steps[0].label == "LapseIfZero"

    def test_add_if(self) -> None:
        b2 = self.b.add_if("is_premium_month", "premium", "Conditional Premium")
        step = b2.steps[0]
        assert step.operation == "add_if"
        assert step.args == ("is_premium_month", "premium")
        assert step.label == "Conditional Premium"

    def test_add_if_auto_label(self) -> None:
        b2 = self.b.add_if("cond", "amount")
        assert b2.steps[0].label == "AddIf(amount)"

    def test_charge_if(self) -> None:
        b2 = self.b.charge_if("is_vul", "me_rate", "M&E Fee")
        step = b2.steps[0]
        assert step.operation == "charge_if"
        assert step.args == ("is_vul", "me_rate")
        assert step.label == "M&E Fee"

    def test_charge_if_auto_label(self) -> None:
        b2 = self.b.charge_if("cond", "rate")
        assert b2.steps[0].label == "ChargeIf(rate)"

    def test_capture(self) -> None:
        b2 = self.b.add("premium").capture("BOP AV")
        steps = b2.steps
        assert len(steps) == 2
        assert steps[1].operation == "capture"
        assert steps[1].label == "BOP AV"

    def test_capture_auto_label(self) -> None:
        b2 = self.b.capture()
        assert b2.steps[0].label == "Capture"

    def test_ratchet_to_multi_state(self) -> None:
        b = RollforwardBuilder(
            frame="af",
            states={"av": "av_col", "floor": "floor_col"},
        )
        b2 = b.on("av").ratchet_to("floor", label="Ratchet")
        step = b2.steps[0]
        assert step.operation == "ratchet_to"
        assert step.label == "Ratchet"
        assert step.args == ("floor",)

    def test_ratchet_to_single_state_raises(self) -> None:
        with pytest.raises(ValueError, match="multi-state"):
            self.b.ratchet_to("floor")

    def test_pro_rata_with_multi_state(self) -> None:
        b = RollforwardBuilder(
            frame="af",
            states={"av": "av_col", "reserve": "res_col"},
        )
        b2 = b.on("av").pro_rata_with("AV Snapshot", "withdrawal", label="Pro Rata")
        step = b2.steps[0]
        assert step.operation == "pro_rata_with"
        assert step.label == "Pro Rata"
        assert step.args == ("AV Snapshot", "withdrawal")

    def test_pro_rata_with_single_state_raises(self) -> None:
        with pytest.raises(ValueError, match="multi-state"):
            self.b.pro_rata_with("AV Snapshot", "withdrawal")


class TestImmutability:
    """Builder methods return new builder instances."""

    def test_add_returns_new_builder(self) -> None:
        b1 = RollforwardBuilder(frame="af", initial="av")
        b2 = b1.add("premium")
        assert b1 is not b2

    def test_original_unchanged_after_add(self) -> None:
        b1 = RollforwardBuilder(frame="af", initial="av")
        b1.add("premium")
        assert b1.steps == ()

    def test_chain_builds_correctly(self) -> None:
        b = (
            RollforwardBuilder(frame="af", initial="av")
            .add("premium", "Premium")
            .charge("admin_rate", "Admin")
            .grow("interest_rate", "Interest")
        )
        assert len(b.steps) == 3
        labels = b.labels
        assert labels == ("Premium", "Admin", "Interest")

    def test_on_returns_new_builder(self) -> None:
        b = RollforwardBuilder(
            frame="af", states={"av": "av_col", "guar": "guar_col"}
        )
        b2 = b.on("av")
        assert b is not b2

    def test_on_same_target_returns_new_builder(self) -> None:
        """on() returns new builder even when targeting the same state."""
        b = RollforwardBuilder(
            frame="af",
            states={"av": "av_col"},
            _current_target="av",
        )
        b2 = b.on("av")
        assert b is not b2


class TestLabelValidation:
    """Duplicate labels raise ValueError immediately."""

    def test_duplicate_label_raises(self) -> None:
        b = RollforwardBuilder(frame="af", initial="av").add("premium", "Premium")
        with pytest.raises(ValueError, match="Premium"):
            b.add("other_premium", "Premium")

    def test_auto_labels_are_unique_across_steps(self) -> None:
        """Two identical auto-labels should raise ValueError."""
        b = RollforwardBuilder(frame="af", initial="av").add("premium")
        with pytest.raises(ValueError, match="Add\\(premium\\)"):
            b.add("premium")

    def test_different_labels_allowed(self) -> None:
        b = (
            RollforwardBuilder(frame="af", initial="av")
            .add("premium", "Premium")
            .add("other", "Other Premium")
        )
        assert len(b.steps) == 2

    def test_find_label_raises_key_error_with_available(self) -> None:
        b = (
            RollforwardBuilder(frame="af", initial="av")
            .add("premium", "Premium")
            .charge("rate", "Admin")
        )
        with pytest.raises(KeyError, match="NotExist"):
            b.insert_before("NotExist", StepDef(operation="add", label="X", args=()))


class TestMultiStateOn:
    """Test .on() sticky state targeting."""

    def setup_method(self) -> None:
        self.b = RollforwardBuilder(
            frame="af",
            states={"av": "av_col", "guar": "guar_col"},
        )

    def test_on_sets_current_target(self) -> None:
        b2 = self.b.on("av")
        assert b2._current_target == "av"  # noqa: SLF001

    def test_on_is_sticky(self) -> None:
        """After .on('av'), subsequent steps target av."""
        b2 = self.b.on("av").add("premium", "Prem").add("bonus", "Bonus")
        for step in b2.steps:
            assert step.kwargs.get("_target") == "av"

    def test_on_switches_target(self) -> None:
        b2 = self.b.on("av").add("premium", "Prem AV").on("guar").add("guar_prem", "Prem Guar")
        av_step = b2.steps[0]
        guar_step = b2.steps[1]
        assert av_step.kwargs["_target"] == "av"
        assert guar_step.kwargs["_target"] == "guar"

    def test_on_invalid_state_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid_state"):
            self.b.on("invalid_state")

    def test_on_noop_when_same_state(self) -> None:
        """on() targeting current state produces equivalent builder."""
        b1 = self.b.on("av")
        b2 = b1.on("av")
        assert b2._current_target == "av"  # noqa: SLF001

    def test_single_state_on_raises(self) -> None:
        b = RollforwardBuilder(frame="af", initial="av")
        with pytest.raises(ValueError, match="multi-state"):
            b.on("av")


class TestLapseWhen:
    """Test .lapse_when() stored separately from steps."""

    def test_lapse_when_stored_in_lapse_condition(self) -> None:
        b = RollforwardBuilder(
            frame="af",
            states={"av": "av_col", "guar": "guar_col"},
        )
        b2 = b.lapse_when(all_non_positive=["av", "guar"])
        assert b2._lapse_condition == {"all_non_positive": ["av", "guar"]}  # noqa: SLF001

    def test_lapse_when_not_a_step(self) -> None:
        b = RollforwardBuilder(
            frame="af",
            states={"av": "av_col", "guar": "guar_col"},
        )
        b2 = b.lapse_when(all_non_positive=["av"])
        assert b2.steps == ()

    def test_lapse_when_single_state_raises(self) -> None:
        b = RollforwardBuilder(frame="af", initial="av")
        with pytest.raises(ValueError, match="multi-state"):
            b.lapse_when(all_non_positive=["av"])

    def test_lapse_when_multiple_calls_raises(self) -> None:
        b = RollforwardBuilder(
            frame="af",
            states={"av": "av_col", "guar": "guar_col"},
        )
        b2 = b.lapse_when(all_non_positive=["av"])
        with pytest.raises(ValueError, match="lapse_when"):
            b2.lapse_when(all_non_positive=["guar"])

    def test_lapse_when_is_immutable(self) -> None:
        b = RollforwardBuilder(
            frame="af",
            states={"av": "av_col", "guar": "guar_col"},
        )
        b2 = b.lapse_when(all_non_positive=["av"])
        assert b._lapse_condition is None  # noqa: SLF001
        assert b2._lapse_condition is not None  # noqa: SLF001


class TestCompositionMethods:
    """Test insert_before, insert_after, remove, replace, prepend, append."""

    def setup_method(self) -> None:
        self.b = (
            RollforwardBuilder(frame="af", initial="av")
            .add("premium", "Premium")
            .charge("admin_rate", "Admin")
            .grow("interest_rate", "Interest")
        )

    def test_insert_before(self) -> None:
        new_step = StepDef(operation="subtract", label="Withdrawal", args=("wd",))
        b2 = self.b.insert_before("Admin", new_step)
        assert b2.labels == ("Premium", "Withdrawal", "Admin", "Interest")

    def test_insert_after(self) -> None:
        new_step = StepDef(operation="floor", label="Floor Zero", args=(0.0,))
        b2 = self.b.insert_after("Interest", new_step)
        assert b2.labels == ("Premium", "Admin", "Interest", "Floor Zero")

    def test_insert_before_first(self) -> None:
        new_step = StepDef(operation="capture", label="BOP", args=())
        b2 = self.b.insert_before("Premium", new_step)
        assert b2.labels[0] == "BOP"

    def test_remove(self) -> None:
        b2 = self.b.remove("Admin")
        assert b2.labels == ("Premium", "Interest")

    def test_replace(self) -> None:
        new_step = StepDef(operation="charge", label="Admin v2", args=("admin_rate_v2",))
        b2 = self.b.replace("Admin", new_step)
        assert "Admin" not in b2.labels
        assert "Admin v2" in b2.labels
        assert b2.labels == ("Premium", "Admin v2", "Interest")

    def test_prepend(self) -> None:
        new_step = StepDef(operation="capture", label="BOP", args=())
        b2 = self.b.prepend(new_step)
        assert b2.labels[0] == "BOP"
        assert len(b2.steps) == 4

    def test_append(self) -> None:
        new_step = StepDef(operation="floor", label="Final Floor", args=(0.0,))
        b2 = self.b.append(new_step)
        assert b2.labels[-1] == "Final Floor"
        assert len(b2.steps) == 4

    def test_insert_before_unknown_label_raises(self) -> None:
        new_step = StepDef(operation="add", label="X", args=())
        with pytest.raises(KeyError, match="NotFound"):
            self.b.insert_before("NotFound", new_step)

    def test_insert_after_unknown_label_raises(self) -> None:
        new_step = StepDef(operation="add", label="X", args=())
        with pytest.raises(KeyError, match="NotFound"):
            self.b.insert_after("NotFound", new_step)

    def test_remove_unknown_label_raises(self) -> None:
        with pytest.raises(KeyError, match="NotFound"):
            self.b.remove("NotFound")

    def test_replace_unknown_label_raises(self) -> None:
        new_step = StepDef(operation="add", label="X", args=())
        with pytest.raises(KeyError, match="NotFound"):
            self.b.replace("NotFound", new_step)

    def test_composition_returns_new_builder(self) -> None:
        new_step = StepDef(operation="add", label="X", args=())
        b2 = self.b.append(new_step)
        assert b2 is not self.b

    def test_insert_before_duplicate_label_raises(self) -> None:
        """Inserted step whose label already exists raises ValueError."""
        duplicate = StepDef(operation="add", label="Premium", args=())
        with pytest.raises(ValueError, match="Premium"):
            self.b.insert_before("Admin", duplicate)
