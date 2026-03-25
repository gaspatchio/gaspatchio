"""StepDef dataclass and Step factory namespace for rollforward operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _col_name(ref: Any) -> str:  # noqa: ANN401
    """Extract a display name from a column reference."""
    if isinstance(ref, str):
        return ref
    if hasattr(ref, "name"):
        return ref.name
    return str(ref)


@dataclass(slots=True, frozen=True)
class StepDef:
    """Internal representation of a single rollforward step.

    Immutable. Used by RollforwardBuilder for storage and composition
    operations. Not part of the public API — users interact through
    builder methods or the Step factory.
    """

    operation: str
    label: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any] = field(default_factory=dict)


class Step:
    """Factory namespace for creating StepDef objects.

    Used with composition methods (insert_before, insert_after, replace,
    prepend, append). Column arguments accept ColumnProxy, ExpressionProxy,
    or str (for templates).

    Examples
    --------
    ```python
    from gaspatchio_core.rollforward import Step

    step = Step.charge(af.rider_rate, "Rider Fee")
    builder = base.insert_before("Interest", step)
    ```

    """

    def __init__(self) -> None:
        msg = "Step is a namespace class and cannot be instantiated."
        raise TypeError(msg)

    @staticmethod
    def add(amount: Any, label: str | None = None) -> StepDef:  # noqa: ANN401
        """Create an Add step: av += amount[t]."""
        label = label or f"Add({_col_name(amount)})"
        return StepDef(operation="add", label=label, args=(amount,))

    @staticmethod
    def subtract(amount: Any, label: str | None = None) -> StepDef:  # noqa: ANN401
        """Create a Subtract step: av -= amount[t]."""
        label = label or f"Subtract({_col_name(amount)})"
        return StepDef(operation="subtract", label=label, args=(amount,))

    @staticmethod
    def charge(rate: Any, label: str | None = None) -> StepDef:  # noqa: ANN401
        """Create a Charge step: av *= (1 - rate[t])."""
        label = label or f"Charge({_col_name(rate)})"
        return StepDef(operation="charge", label=label, args=(rate,))

    @staticmethod
    def grow(rate: Any, label: str | None = None) -> StepDef:  # noqa: ANN401
        """Create a Grow step: av *= (1 + rate[t])."""
        label = label or f"Grow({_col_name(rate)})"
        return StepDef(operation="grow", label=label, args=(rate,))

    @staticmethod
    def grow_capped(
        rate: Any, *, floor: float, cap: float, label: str | None = None
    ) -> StepDef:  # noqa: ANN401
        """Create a GrowCapped step: av *= (1 + clamp(rate[t], floor, cap))."""
        label = label or f"GrowCapped({_col_name(rate)})"
        return StepDef(
            operation="grow_capped",
            label=label,
            args=(rate,),
            kwargs={"floor": floor, "cap": cap},
        )

    @staticmethod
    def deduct_nar(
        rate: Any, *, death_benefit: Any, label: str | None = None
    ) -> StepDef:  # noqa: ANN401
        """Create a DeductNAR step: av -= rate[t] * max(0, db[t] - av)."""
        label = label or f"DeductNAR({_col_name(rate)})"
        return StepDef(
            operation="deduct_nar",
            label=label,
            args=(rate,),
            kwargs={"death_benefit": death_benefit},
        )

    @staticmethod
    def floor(value: float, label: str | None = None) -> StepDef:
        """Create a Floor step: av = max(av, value)."""
        label = label or f"Floor({value})"
        return StepDef(operation="floor", label=label, args=(value,))

    @staticmethod
    def cap(value: float, label: str | None = None) -> StepDef:
        """Create a Cap step: av = min(av, value)."""
        label = label or f"Cap({value})"
        return StepDef(operation="cap", label=label, args=(value,))

    @staticmethod
    def add_if(condition: Any, amount: Any, label: str | None = None) -> StepDef:  # noqa: ANN401
        """Create a conditional Add step: if condition[t]: av += amount[t]."""
        label = label or f"AddIf({_col_name(amount)})"
        return StepDef(operation="add_if", label=label, args=(condition, amount))

    @staticmethod
    def charge_if(condition: Any, rate: Any, label: str | None = None) -> StepDef:  # noqa: ANN401
        """Create a conditional Charge step: if condition[t]: av *= (1 - rate[t])."""
        label = label or f"ChargeIf({_col_name(rate)})"
        return StepDef(operation="charge_if", label=label, args=(condition, rate))
