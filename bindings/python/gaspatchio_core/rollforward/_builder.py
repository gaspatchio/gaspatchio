"""RollforwardBuilder: immutable fluent builder for rollforward step sequences."""

from __future__ import annotations

from typing import Any

from gaspatchio_core.rollforward._step import StepDef, _col_name


class RollforwardStateProxy:
    """Proxy for extracting a single state from a multi-state rollforward.

    Created by indexing a multi-state ``RollforwardBuilder`` with a state name,
    e.g. ``rf["av"]``.  Assigning this proxy to an ``ActuarialFrame`` column
    triggers compilation of the entire multi-state rollforward and extraction
    of the named state field.
    """

    __slots__ = ("_builder", "_state_name")

    def __init__(self, builder: RollforwardBuilder, state_name: str) -> None:
        self._builder = builder
        self._state_name = state_name

    def __repr__(self) -> str:
        return f"RollforwardStateProxy(state={self._state_name!r})"


class RollforwardBuilder:
    """Immutable builder for rollforward step sequences.

    Every method returns a new ``RollforwardBuilder`` instance. The internal
    step list is stored as a ``tuple[StepDef, ...]`` to enforce immutability.
    Labels must be unique across all steps; duplicates raise ``ValueError``
    immediately.

    Parameters
    ----------
    frame : object
        The ActuarialFrame (or template reference) this rollforward targets.
    initial : str | None
        Column name for the single account value (single-state mode).
    states : dict[str, Any] | None
        Mapping of state name to column reference (multi-state mode).
    track_increments : bool
        Whether to capture per-step increments for diagnostics.

    Examples
    --------
    Single-state usage::

        b = (
            RollforwardBuilder(frame=af, initial="av")
            .add("premium", "Premium")
            .charge("admin_rate", "Admin Fee")
            .grow("interest_rate", "Interest Credit")
        )

    Multi-state usage::

        b = (
            RollforwardBuilder(frame=af, states={"av": "av_col", "guar": "guar_col"})
            .on("av")
            .add("premium", "Premium AV")
            .on("guar")
            .add("guar_prem", "Premium Guar")
            .lapse_when(all_non_positive=["av", "guar"])
        )

    """

    __slots__ = (
        "_current_target",
        "_frame",
        "_initial",
        "_lapse_condition",
        "_states",
        "_steps",
        "_track_increments",
    )

    def __init__(
        self,
        frame: Any,  # noqa: ANN401
        initial: str | None = None,
        states: dict[str, Any] | None = None,
        track_increments: bool = False,
        *,
        _steps: tuple[StepDef, ...] = (),
        _current_target: str | None = None,
        _lapse_condition: dict[str, Any] | None = None,
    ) -> None:
        if initial is not None and states is not None:
            msg = (
                "Provide either 'initial' (single-state) or 'states'"
                " (multi-state), not both."
            )
            raise ValueError(msg)
        if initial is None and states is None:
            msg = (
                "Either 'initial' (single-state) or 'states'"
                " (multi-state) must be provided."
            )
            raise ValueError(msg)

        self._frame = frame
        self._initial = initial
        self._states: dict[str, Any] | None = states
        self._track_increments = track_increments
        self._steps = _steps
        self._current_target = _current_target
        self._lapse_condition = _lapse_condition

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_multi_state(self) -> bool:
        """Return True if this is a multi-state builder."""
        return self._states is not None

    @property
    def steps(self) -> tuple[StepDef, ...]:
        """Return the immutable tuple of step definitions."""
        return self._steps

    @property
    def labels(self) -> tuple[str, ...]:
        """Return a tuple of step labels in order."""
        return tuple(s.label for s in self._steps)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new(self, **overrides: Any) -> RollforwardBuilder:  # noqa: ANN401
        """Create a new builder preserving all fields except those in overrides."""
        return RollforwardBuilder(
            frame=overrides.get("_frame", self._frame),
            initial=overrides.get("_initial", self._initial),
            states=overrides.get("_states", self._states),
            track_increments=overrides.get("_track_increments", self._track_increments),
            _steps=overrides.get("_steps", self._steps),
            _current_target=overrides.get("_current_target", self._current_target),
            _lapse_condition=overrides.get("_lapse_condition", self._lapse_condition),
        )

    def _check_unique_label(self, label: str) -> None:
        """Raise ValueError if label already exists in the step list."""
        if label in self.labels:
            existing = ", ".join(repr(lbl) for lbl in self.labels)
            msg = f"Duplicate label {label!r}. Existing labels: {existing}"
            raise ValueError(msg)

    def _find_label(self, label: str) -> int:
        """Return the index of the step with the given label.

        Raises
        ------
        KeyError
            If no step with *label* exists. The message includes available labels.

        """
        for i, step in enumerate(self._steps):
            if step.label == label:
                return i
        available = ", ".join(repr(lbl) for lbl in self.labels)
        msg = f"{label!r} not found. Available labels: {available}"
        raise KeyError(msg)

    def _append_step(self, step: StepDef) -> RollforwardBuilder:
        """Return a new builder with *step* appended, after label uniqueness check."""
        self._check_unique_label(step.label)
        return self._new(_steps=self._steps + (step,))

    def _make_step(
        self,
        operation: str,
        label: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any] | None = None,
    ) -> StepDef:
        """Build a StepDef, injecting ``_target`` into kwargs for multi-state mode."""
        merged: dict[str, Any] = dict(kwargs) if kwargs else {}
        if self.is_multi_state and self._current_target is not None:
            merged["_target"] = self._current_target
        return StepDef(operation=operation, label=label, args=args, kwargs=merged)

    # ------------------------------------------------------------------
    # State targeting
    # ------------------------------------------------------------------

    def on(self, state_name: str) -> RollforwardBuilder:
        """Switch the sticky state target for subsequent steps.

        Only valid in multi-state mode.

        Parameters
        ----------
        state_name : str
            Must be a key in the ``states`` dict supplied at construction.

        Raises
        ------
        ValueError
            If called on a single-state builder, or if *state_name* is not a
            known state.

        """
        if not self.is_multi_state:
            msg = "on() is only valid in multi-state mode."
            raise ValueError(msg)
        assert self._states is not None  # noqa: S101  (narrowing for type checker)
        if state_name not in self._states:
            available = ", ".join(repr(k) for k in self._states)
            msg = f"Unknown state {state_name!r}. Available states: {available}"
            raise ValueError(msg)
        return self._new(_current_target=state_name)

    # ------------------------------------------------------------------
    # Cross-state lapse condition
    # ------------------------------------------------------------------

    def lapse_when(self, *, all_non_positive: list[str]) -> RollforwardBuilder:
        """Store a cross-state lapse condition (not added to the step list).

        Only valid in multi-state mode. Only one ``lapse_when`` per builder.

        Parameters
        ----------
        all_non_positive : list[str]
            State names that must all be non-positive (≤ 0) to trigger lapse.

        Raises
        ------
        ValueError
            If called on a single-state builder, or if ``lapse_when`` has
            already been set.

        """
        if not self.is_multi_state:
            msg = "lapse_when() is only valid in multi-state mode."
            raise ValueError(msg)
        if self._lapse_condition is not None:
            msg = (
                "lapse_when() has already been set on this builder. "
                "Only one is allowed."
            )
            raise ValueError(msg)
        condition: dict[str, Any] = {"all_non_positive": all_non_positive}
        return self._new(_lapse_condition=condition)

    # ------------------------------------------------------------------
    # Step methods (14 total)
    # ------------------------------------------------------------------

    def add(self, amount: Any, label: str | None = None) -> RollforwardBuilder:  # noqa: ANN401
        """Append an Add step: av += amount[t].

        Parameters
        ----------
        amount :
            Column reference or template string for the amount.
        label : str | None
            Step label. Auto-generated as ``Add(<col>)`` if omitted.

        """
        resolved_label = label or f"Add({_col_name(amount)})"
        step = self._make_step("add", resolved_label, (amount,))
        return self._append_step(step)

    def subtract(self, amount: Any, label: str | None = None) -> RollforwardBuilder:  # noqa: ANN401
        """Append a Subtract step: av -= amount[t].

        Parameters
        ----------
        amount :
            Column reference or template string.
        label : str | None
            Step label. Auto-generated as ``Subtract(<col>)`` if omitted.

        """
        resolved_label = label or f"Subtract({_col_name(amount)})"
        step = self._make_step("subtract", resolved_label, (amount,))
        return self._append_step(step)

    def charge(self, rate: Any, label: str | None = None) -> RollforwardBuilder:  # noqa: ANN401
        """Append a Charge step: av *= (1 - rate[t]).

        Parameters
        ----------
        rate :
            Column reference or template string for the charge rate.
        label : str | None
            Step label. Auto-generated as ``Charge(<col>)`` if omitted.

        """
        resolved_label = label or f"Charge({_col_name(rate)})"
        step = self._make_step("charge", resolved_label, (rate,))
        return self._append_step(step)

    def grow(self, rate: Any, label: str | None = None) -> RollforwardBuilder:  # noqa: ANN401
        """Append a Grow step: av *= (1 + rate[t]).

        Parameters
        ----------
        rate :
            Column reference or template string.
        label : str | None
            Step label. Auto-generated as ``Grow(<col>)`` if omitted.

        """
        resolved_label = label or f"Grow({_col_name(rate)})"
        step = self._make_step("grow", resolved_label, (rate,))
        return self._append_step(step)

    def grow_capped(
        self,
        rate: Any,  # noqa: ANN401
        *,
        floor: float,
        cap: float,
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Append a GrowCapped step: av *= (1 + clamp(rate[t], floor, cap)).

        Parameters
        ----------
        rate :
            Column reference or template string.
        floor : float
            Minimum growth rate (inclusive).
        cap : float
            Maximum growth rate (inclusive).
        label : str | None
            Step label. Auto-generated as ``GrowCapped(<col>)`` if omitted.

        """
        resolved_label = label or f"GrowCapped({_col_name(rate)})"
        step = self._make_step(
            "grow_capped", resolved_label, (rate,), {"floor": floor, "cap": cap}
        )
        return self._append_step(step)

    def deduct_nar(
        self,
        rate: Any,  # noqa: ANN401
        *,
        death_benefit: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Append a DeductNAR step: av -= rate[t] * max(0, db[t] - av).

        Parameters
        ----------
        rate :
            COI rate column reference.
        death_benefit :
            Death benefit column reference.
        label : str | None
            Step label. Auto-generated as ``DeductNAR(<col>)`` if omitted.

        """
        resolved_label = label or f"DeductNAR({_col_name(rate)})"
        step = self._make_step(
            "deduct_nar", resolved_label, (rate,), {"death_benefit": death_benefit}
        )
        return self._append_step(step)

    def floor(self, value: float, label: str | None = None) -> RollforwardBuilder:
        """Append a Floor step: av = max(av, value).

        Parameters
        ----------
        value : float
            Minimum allowable account value.
        label : str | None
            Step label. Auto-generated as ``Floor(<value>)`` if omitted.

        """
        resolved_label = label or f"Floor({value})"
        step = self._make_step("floor", resolved_label, (value,))
        return self._append_step(step)

    def cap(self, value: float, label: str | None = None) -> RollforwardBuilder:
        """Append a Cap step: av = min(av, value).

        Parameters
        ----------
        value : float
            Maximum allowable account value.
        label : str | None
            Step label. Auto-generated as ``Cap(<value>)`` if omitted.

        """
        resolved_label = label or f"Cap({value})"
        step = self._make_step("cap", resolved_label, (value,))
        return self._append_step(step)

    def lapse_if_zero(self, label: str | None = None) -> RollforwardBuilder:
        """Append a LapseIfZero step: lapse the policy if av ≤ 0.

        Parameters
        ----------
        label : str | None
            Step label. Defaults to ``LapseIfZero``.

        """
        resolved_label = label or "LapseIfZero"
        step = self._make_step("lapse_if_zero", resolved_label, ())
        return self._append_step(step)

    def add_if(
        self,
        condition: Any,  # noqa: ANN401
        amount: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Append a conditional Add step: if condition[t]: av += amount[t].

        Parameters
        ----------
        condition :
            Boolean column reference.
        amount :
            Amount column reference.
        label : str | None
            Step label. Auto-generated as ``AddIf(<col>)`` if omitted.

        """
        resolved_label = label or f"AddIf({_col_name(amount)})"
        step = self._make_step("add_if", resolved_label, (condition, amount))
        return self._append_step(step)

    def charge_if(
        self,
        condition: Any,  # noqa: ANN401
        rate: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Append a conditional Charge step: if condition[t]: av *= (1 - rate[t]).

        Parameters
        ----------
        condition :
            Boolean column reference.
        rate :
            Rate column reference.
        label : str | None
            Step label. Auto-generated as ``ChargeIf(<col>)`` if omitted.

        """
        resolved_label = label or f"ChargeIf({_col_name(rate)})"
        step = self._make_step("charge_if", resolved_label, (condition, rate))
        return self._append_step(step)

    def capture(self, label: str | None = None) -> RollforwardBuilder:
        """Append a Capture step: snapshot the current av value.

        Parameters
        ----------
        label : str | None
            Step label. Defaults to ``Capture``.

        """
        resolved_label = label or "Capture"
        step = self._make_step("capture", resolved_label, ())
        return self._append_step(step)

    def ratchet_to(
        self, other_state: str, label: str | None = None
    ) -> RollforwardBuilder:
        """Append a RatchetTo step: av = max(av, other_state).

        Only valid in multi-state mode.

        Parameters
        ----------
        other_state : str
            Name of the state to ratchet up to.
        label : str | None
            Step label. Auto-generated as ``RatchetTo(<state>)`` if omitted.

        Raises
        ------
        ValueError
            If called on a single-state builder.

        """
        if not self.is_multi_state:
            msg = "ratchet_to() is only valid in multi-state mode."
            raise ValueError(msg)
        resolved_label = label or f"RatchetTo({other_state})"
        step = self._make_step("ratchet_to", resolved_label, (other_state,))
        return self._append_step(step)

    def pro_rata_with(
        self,
        capture_name: str,
        amount: Any,  # noqa: ANN401
        label: str | None = None,
    ) -> RollforwardBuilder:
        """Append a ProRataWith step: scale av pro-rata using a captured snapshot.

        The pro-rata formula is::

            state *= 1 - amount[t] / captured_value

        Only valid in multi-state mode.

        Parameters
        ----------
        capture_name : str
            Label of the ``capture()`` step whose snapshot to use as denominator.
        amount :
            Column reference for the withdrawal/deduction amount.
        label : str | None
            Step label. Auto-generated as ``ProRataWith(<capture_name>)`` if omitted.

        Raises
        ------
        ValueError
            If called on a single-state builder.

        """
        if not self.is_multi_state:
            msg = "pro_rata_with() is only valid in multi-state mode."
            raise ValueError(msg)
        resolved_label = label or f"ProRataWith({capture_name})"
        step = self._make_step("pro_rata_with", resolved_label, (capture_name, amount))
        return self._append_step(step)

    # ------------------------------------------------------------------
    # Composition methods (6 total)
    # ------------------------------------------------------------------

    def insert_before(self, label: str, step: StepDef) -> RollforwardBuilder:
        """Return a new builder with *step* inserted before the step labelled *label*.

        Parameters
        ----------
        label : str
            Label of the existing step to insert before.
        step : StepDef
            The new step to insert.

        Raises
        ------
        KeyError
            If *label* is not found.
        ValueError
            If ``step.label`` already exists in the step list.

        """
        self._check_unique_label(step.label)
        idx = self._find_label(label)
        new_steps = self._steps[:idx] + (step,) + self._steps[idx:]
        return self._new(_steps=new_steps)

    def insert_after(self, label: str, step: StepDef) -> RollforwardBuilder:
        """Return a new builder with *step* inserted after the step labelled *label*.

        Parameters
        ----------
        label : str
            Label of the existing step to insert after.
        step : StepDef
            The new step to insert.

        Raises
        ------
        KeyError
            If *label* is not found.
        ValueError
            If ``step.label`` already exists in the step list.

        """
        self._check_unique_label(step.label)
        idx = self._find_label(label)
        new_steps = self._steps[: idx + 1] + (step,) + self._steps[idx + 1 :]
        return self._new(_steps=new_steps)

    def remove(self, label: str) -> RollforwardBuilder:
        """Return a new builder with the step labelled *label* removed.

        Parameters
        ----------
        label : str
            Label of the step to remove.

        Raises
        ------
        KeyError
            If *label* is not found.

        """
        idx = self._find_label(label)
        new_steps = self._steps[:idx] + self._steps[idx + 1 :]
        return self._new(_steps=new_steps)

    def replace(self, label: str, step: StepDef) -> RollforwardBuilder:
        """Return a new builder with the step labelled *label* replaced by *step*.

        Parameters
        ----------
        label : str
            Label of the step to replace.
        step : StepDef
            The replacement step.

        Raises
        ------
        KeyError
            If *label* is not found.
        ValueError
            If ``step.label`` already exists (and differs from the one being replaced).

        """
        idx = self._find_label(label)
        # Allow replacing a label with the same label name
        if step.label != label:
            self._check_unique_label(step.label)
        new_steps = self._steps[:idx] + (step,) + self._steps[idx + 1 :]
        return self._new(_steps=new_steps)

    def prepend(self, step: StepDef) -> RollforwardBuilder:
        """Return a new builder with *step* inserted at position 0.

        Parameters
        ----------
        step : StepDef
            The step to prepend.

        Raises
        ------
        ValueError
            If ``step.label`` already exists.

        """
        self._check_unique_label(step.label)
        return self._new(_steps=(step,) + self._steps)

    def append(self, step: StepDef) -> RollforwardBuilder:
        """Return a new builder with *step* appended at the end.

        Parameters
        ----------
        step : StepDef
            The step to append.

        Raises
        ------
        ValueError
            If ``step.label`` already exists.

        """
        return self._append_step(step)

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __getitem__(self, state_name: str) -> RollforwardStateProxy:
        """Extract a single state from a multi-state rollforward.

        Returns a ``RollforwardStateProxy`` that, when assigned to an
        ``ActuarialFrame`` column, triggers compilation and extraction.

        Parameters
        ----------
        state_name : str
            Must be a key in the ``states`` dict supplied at construction.

        Raises
        ------
        TypeError
            If this is a single-state builder.
        KeyError
            If *state_name* is not a known state.

        """
        if not self.is_multi_state:
            msg = "Indexing with [] is only for multi-state rollforwards."
            raise TypeError(msg)
        assert self._states is not None  # noqa: S101  (narrowing for type checker)
        if state_name not in self._states:
            msg = f"Unknown state {state_name!r}. Available: {list(self._states)}"
            raise KeyError(msg)
        return RollforwardStateProxy(self, state_name)

    # ------------------------------------------------------------------
    # Inspection methods
    # ------------------------------------------------------------------

    def explain(self) -> str:
        """Return a formatted table describing all steps in this builder.

        Returns
        -------
        str
            Multi-line string with a header and one row per step showing
            step number, operation, label, and formula.

        """
        from gaspatchio_core.rollforward._explain import explain as _explain

        return _explain(self)

    def canonical(self) -> dict[str, Any]:
        """Return a structural dict describing this builder.

        Excludes column names and labels. Only includes operation types
        and structural parameters (floor/cap values, etc.). Suitable for
        change detection and model governance.

        Returns
        -------
        dict[str, Any]
            JSON-serialisable dict with keys ``"num_states"``, ``"steps"``,
            and ``"track_increments"``.

        """
        from gaspatchio_core.rollforward._explain import canonical as _canonical

        return _canonical(self)

    def fingerprint(self) -> str:
        """Return a SHA-256 fingerprint of this builder's canonical form.

        Two builders with identical structure but different column names or
        labels produce the same fingerprint. Useful for detecting structural
        changes between model versions.

        Returns
        -------
        str
            A string of the form ``"sha256:<64 hex chars>"``.

        """
        from gaspatchio_core.rollforward._explain import fingerprint as _fingerprint

        return _fingerprint(self)

    def __repr__(self) -> str:
        mode = "multi-state" if self.is_multi_state else "single-state"
        n = len(self._steps)
        return f"RollforwardBuilder({mode}, steps={n})"
