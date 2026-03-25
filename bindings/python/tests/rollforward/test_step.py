from __future__ import annotations

import pytest

from gaspatchio_core.rollforward._step import Step, StepDef


class TestStepDef:
    def test_creation(self) -> None:
        step = StepDef(operation="add", label="Premium", args=("premium",))
        assert step.operation == "add"
        assert step.label == "Premium"
        assert step.args == ("premium",)
        assert step.kwargs == {}

    def test_frozen(self) -> None:
        step = StepDef(operation="add", label="Premium", args=("premium",))
        with pytest.raises(AttributeError):
            step.operation = "charge"  # type: ignore[misc]

    def test_with_kwargs(self) -> None:
        step = StepDef(
            operation="deduct_nar",
            label="COI",
            args=("coi_rate",),
            kwargs={"death_benefit": "sum_assured"},
        )
        assert step.kwargs["death_benefit"] == "sum_assured"

    def test_equality(self) -> None:
        s1 = StepDef(operation="add", label="Premium", args=("premium",))
        s2 = StepDef(operation="add", label="Premium", args=("premium",))
        assert s1 == s2


class TestStepFactory:
    def test_add(self) -> None:
        step = Step.add("premium", "Premium")
        assert step.operation == "add"
        assert step.label == "Premium"
        assert step.args == ("premium",)

    def test_add_auto_label(self) -> None:
        step = Step.add("premium")
        assert step.label == "Add(premium)"

    def test_charge(self) -> None:
        step = Step.charge("admin_rate", "Admin")
        assert step.operation == "charge"
        assert step.label == "Admin"

    def test_grow(self) -> None:
        step = Step.grow("interest_rate", "Interest")
        assert step.operation == "grow"
        assert step.label == "Interest"

    def test_subtract(self) -> None:
        step = Step.subtract("expense", "Expense")
        assert step.operation == "subtract"
        assert step.label == "Expense"

    def test_grow_capped(self) -> None:
        step = Step.grow_capped("index_return", floor=0.0, cap=0.12, label="Index Credit")
        assert step.operation == "grow_capped"
        assert step.kwargs["floor"] == 0.0
        assert step.kwargs["cap"] == 0.12

    def test_deduct_nar(self) -> None:
        step = Step.deduct_nar("coi_rate", death_benefit="sum_assured", label="COI")
        assert step.operation == "deduct_nar"
        assert step.kwargs["death_benefit"] == "sum_assured"

    def test_floor(self) -> None:
        step = Step.floor(0.0)
        assert step.operation == "floor"
        assert step.label == "Floor(0.0)"
        assert step.args == (0.0,)

    def test_cap(self) -> None:
        step = Step.cap(1000000.0, "Max AV")
        assert step.operation == "cap"
        assert step.label == "Max AV"

    def test_add_if(self) -> None:
        step = Step.add_if("is_premium_month", "premium", "Conditional Premium")
        assert step.operation == "add_if"
        assert step.args == ("is_premium_month", "premium")

    def test_charge_if(self) -> None:
        step = Step.charge_if("is_vul", "me_rate", "M&E Fee")
        assert step.operation == "charge_if"
        assert step.args == ("is_vul", "me_rate")
