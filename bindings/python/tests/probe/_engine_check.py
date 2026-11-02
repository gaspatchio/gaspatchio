# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Standalone worker: check whether the model's final plan runs on the streaming engine.

Runs as a plain script — not a `tests.probe` import — so it can be executed
with any target environment's own interpreter, including a
``--baseline-worktree`` whose checkout predates this harness entirely:

    <env>/bin/python _engine_check.py --model PATH --data PATH

Prints one JSON object to stdout: ``explain_text`` (the streaming-engine
plan) and ``explain_fallback_marker_hit`` (whether that text contains one of
`FALLBACK_MARKERS`). The caller is expected to additionally run this with
``POLARS_VERBOSE=1`` set and check its *stderr* for the same markers — a
silent in-memory fallback does not always show up in `explain()` text alone.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable

# Substrings (checked case-insensitively) indicating the streaming engine
# could not run the plan as-is and silently dropped to in-memory execution.
# Polars does not (as of 1.42) document one single stable marker for this,
# so the list is deliberately broad — a false negative (a real fallback none
# of these catch) is the failure mode that matters, not a false positive.
FALLBACK_MARKERS: tuple[str, ...] = (
    "falling back",
    "fall back",
    "fallback",
    "in-memory engine",
    "not supported by the streaming engine",
    "not support streaming",
    "unable to run in streaming mode",
)


def _load_model_main(model_path: Path) -> Callable[..., Any]:
    """Import `model_path` as a module and return its `main` callable."""
    spec = importlib.util.spec_from_file_location(model_path.stem, model_path)
    if spec is None or spec.loader is None:
        msg = f"could not load a module spec from {model_path}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    main_callable: Callable[..., Any] = module.main
    return main_callable


def build_final_plan(model_path: Path, data_path: Path) -> pl.LazyFrame:
    """Import `model_path`, run its `main()` over `data_path`, return the lazy plan.

    Mirrors what `gspio run-model` does before it collects: wrap the data
    file in an `ActuarialFrame` and call the model's `main()`. The returned
    frame is never collected here — only its plan is inspected.
    """
    from gaspatchio import ActuarialFrame  # local import: only this script needs it

    model_main = _load_model_main(model_path)
    frame = ActuarialFrame(pl.read_parquet(data_path))
    result = model_main(frame)
    # `_df` is the only way to reach the underlying LazyFrame (see the many
    # precedents under tests/frame and tests/rollforward) — inspecting the
    # compiled plan is exactly what this worker exists to do.
    plan: pl.LazyFrame = result._df  # noqa: SLF001
    return plan


def check_fallback(explain_text: str) -> bool:
    """Return True if `explain_text` contains any known fallback marker."""
    lowered = explain_text.lower()
    return any(marker in lowered for marker in FALLBACK_MARKERS)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    return parser.parse_args(argv)


def _configure_result_channel() -> None:
    """Route this worker's JSON result to stdout via loguru, and nothing else there.

    ``logger.remove()`` drops loguru's default (stderr) sink — loguru is a
    process-wide singleton, and gaspatchio's own library code logs through
    this same `logger`, so without removing the default first, its ordinary
    DEBUG/INFO chatter could end up interleaved with the result. Two sinks
    replace it, partitioned by the same filter in opposite directions: stderr
    gets everything *except* the result record (so ordinary logging keeps
    working), stdout gets *only* the one record this script explicitly binds
    with ``result_channel=True``, formatted as the bare message. The caller
    (`probe_emission.py`) also scans this script's stderr for streaming-engine
    fallback markers — the JSON payload includes the full `explain()` text,
    so it must never be echoed to stderr too, or that scan would be checking
    its own duplicate rather than independent evidence.

    Called from `main()`, not at module import time: `probe_emission.py`
    imports this module for `FALLBACK_MARKERS`, and reconfiguring the
    process-wide logger as a side effect of that import would silently break
    its own logging in the *orchestrator's* process.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        filter=lambda record: not record["extra"].get("result_channel", False),
    )
    logger.add(
        sys.stdout,
        format="{message}",
        colorize=False,
        filter=lambda record: record["extra"].get("result_channel", False),
    )


def main(argv: list[str] | None = None) -> None:
    """Build the plan, explain it under the streaming engine, print JSON."""
    _configure_result_channel()
    args = _parse_args(argv)
    plan = build_final_plan(args.model, args.data)
    explain_text = plan.explain(engine="streaming")
    payload = {
        "explain_text": explain_text,
        "explain_fallback_marker_hit": check_fallback(explain_text),
    }
    # stdout is this worker's result channel (subprocess-JSON contract with
    # the orchestrator in probe_emission.py); the filtered sink above is what
    # keeps it JSON-only despite sharing loguru with gaspatchio's own logging.
    logger.bind(result_channel=True).info(json.dumps(payload))


if __name__ == "__main__":
    main()
