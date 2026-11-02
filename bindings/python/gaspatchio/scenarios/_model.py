# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Explicit adaptation of ordinary frame models to the scenario calling contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from gaspatchio.frame.execution import run_model

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from gaspatchio.assumptions import Table
    from gaspatchio.frame import ActuarialFrame


class _ScenarioModel(Protocol):
    def __call__(
        self,
        af: ActuarialFrame,
        *,
        tables: Mapping[str, Table],
        drivers: Mapping[str, object],
    ) -> ActuarialFrame: ...


def as_scenario_model(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame | None],
) -> _ScenarioModel:
    """Adapt a frame-only model to ``for_each_scenario``'s ids and drivers shapes.

    A shocks plan -- ``ScenarioRun.run`` or a shocks-dict ``for_each_scenario``
    -- already takes the frame-only model as it is; pass ``model.main``, not
    this adapter, which such a plan refuses. The ids and drivers shapes call
    ``model(af, *, tables, drivers)``, and this adapts a frame-only model to
    them. The model receives the scenario-expanded frame, so it can read its
    scenario axis as data. None keeps the input frame, as in ordinary
    ``run_model``. The callable is invoked once, without signature guessing or
    TypeError retries.

    Nonempty ``tables`` or ``drivers`` are refused before calling the model: a
    frame-only function cannot consume plain tables or per-scenario drivers.
    For those inputs, write ``model(af, *, tables, drivers)`` explicitly instead.
    """

    def adapted(
        af: ActuarialFrame,
        *,
        tables: Mapping[str, Table],
        drivers: Mapping[str, object],
    ) -> ActuarialFrame:
        if tables or drivers:
            supplied = ", ".join(
                name
                for name, values in (("tables", tables), ("drivers", drivers))
                if values
            )
            msg = (
                f"as_scenario_model cannot ignore nonempty {supplied}. "
                "Write model(af, *, tables, drivers) to consume these scenario inputs."
            )
            raise ValueError(msg)
        return run_model(model_fn, af)

    return adapted
