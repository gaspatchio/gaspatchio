# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Traced-run entry point and query-plan logging for ActuarialFrame
# ABOUTME: Marks a debug-mode run and renders the calculation log as a plan
"""Traced-run entry point and query-plan logging for ActuarialFrame.

Two things live here.

``build_trace_decorator`` is where a **traced run** begins: ``--mode debug``
routes the model function through it, and it stamps ``_traced_run`` on the
frame so the error path knows the user asked for the verbose diagnosis
panel. That flag is the only run-scoped state the framework keeps —
calculations themselves are recorded on every frame in every mode, by the
durable log in ``frame/calculations.py``, not by anything here.

``log_query_plan`` renders that log as a numbered list of steps when
verbose logging is on.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Protocol

from loguru import logger

from gaspatchio._source import display_filename
from gaspatchio.util import get_default_verbose

if TYPE_CHECKING:
    from collections.abc import Callable

    import polars as pl

    from gaspatchio.frame.calculations import CalculationRecord, LogEntry


class _TraceSource(Protocol):
    """Only the diagnostic mode and calculation log used by tracing."""

    _mode: str
    _traced_run: bool
    _calculations: list[LogEntry]

    @property
    def _df(self) -> pl.LazyFrame | None: ...


def log_query_plan(records: list[CalculationRecord], frame_df: pl.LazyFrame) -> None:
    """Log the calculations and the resulting query plan, if verbose is on.

    One numbered step per calculation record, each followed by the line of
    the user's own source that asked for it. A record whose source could
    not be resolved (stdin, an ``exec``-compiled snippet, a bare REPL)
    prints its step without a source line rather than a placeholder.
    """
    if get_default_verbose():
        logger.trace("Computation Graph:")
        for i, record in enumerate(records):
            logger.trace(f"  Step {i + 1}: {record.column} = {record.expr}")
            if record.source is not None:
                logger.trace(
                    f"    Source: "
                    f"{display_filename(record.source.file)}:"
                    f"{record.source.line}",
                )
        logger.trace("Optimized Query Plan:")
        try:
            logger.debug(frame_df.explain(optimized=True))
        except Exception:  # noqa: BLE001
            logger.warning("Could not explain query plan")


def build_trace_decorator(frame_instance: _TraceSource) -> Callable:  # type: ignore[type-arg]
    """Create trace decorator for a specific ActuarialFrame instance."""

    def decorator(func: Callable) -> Callable:  # type: ignore[type-arg]
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> _TraceSource | None:  # noqa: ANN401
            from gaspatchio.frame.calculations import CalculationRecord  # noqa: PLC0415

            mode = frame_instance._mode  # noqa: SLF001 -- explicit frame mode wins

            if mode == "debug":
                func_name = getattr(func, "__name__", "<unknown>")
                logger.debug(
                    f"Tracing {func_name} in debug mode for enhanced error handling."
                )
                # A traced run begins HERE, and this is the only place the
                # flag is set. It says the user asked for `--mode debug`,
                # which is what selects the verbose diagnosis panel on the
                # error path — a question about the RUN, not about any one
                # calculation, so it is answered once at the run's door
                # rather than re-decided per record. It is deliberately
                # sticky: the model function has long returned by the time
                # collect() fails, so a flag that unwound here would be
                # False at exactly the moment the panel is chosen.
                frame_instance._traced_run = True  # noqa: SLF001
                first_step = len(frame_instance._calculations)  # noqa: SLF001

                result = func(*args, **kwargs)

                # Models may hand back a frame derived from the input (a
                # scenario axis cross-joins one in). That successor is what
                # the runner collects, so it is what has to carry the flag.
                # `_carry_calculation_log` already carries it to anything
                # derived while the run was in progress; this covers a
                # frame built some other way. A model that returns something
                # that is not a frame at all (a plain value) is left alone —
                # a calculation log is what makes it a frame here.
                frame = frame_instance if result is None else result
                calculations = getattr(frame, "_calculations", None)
                if calculations is not None:
                    frame._traced_run = True  # noqa: SLF001
                    steps = [
                        entry
                        for entry in calculations[first_step:]
                        if isinstance(entry, CalculationRecord)
                    ]
                    if steps:
                        logger.debug(f"{len(steps)} calculations recorded.")
                        if get_default_verbose() and frame._df is not None:  # noqa: SLF001
                            log_query_plan(steps, frame._df)  # noqa: SLF001
                    else:
                        logger.debug("No calculations recorded during the run.")

                return frame

            if mode == "optimize":
                func_name = getattr(func, "__name__", "<unknown>")
                logger.debug(f"Running {func_name} in optimize mode.")
                result = func(*args, **kwargs)
                return frame_instance if result is None else result

            msg = f"Unknown execution mode: {mode}"
            raise ValueError(msg)

        return wrapper

    return decorator


__all__ = ["build_trace_decorator", "log_query_plan"]
