# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Synthesize the 100k-policy workload fixture used by the probe.

The probe's workload is a machine-local model that is not part of this
repository, named by the ``GASPATCHIO_PROBE_WORKLOAD_DIR`` environment
variable; there is no default. That directory holds ``model_ifrs17.py`` and
``model_points.parquet``, and the workload's ``model_points.parquet``
carries one row per workbook tab (``Base``, ``Lapse Shock``, ``Expense
Shock``, ``Expense Shock no Assn Change``); this script replicates the
``Base`` row to a `policy_count`-row frame so the model runs at a realistic
scale.

Two things vary per synthesized row, and only two: the policy identifier
(otherwise every row would collide) and ``sum_insured`` (the one numeric
input jittered with a fixed-seed RNG, so the file is not just one value
copied everywhere). Every other column — the assumption list columns, the
switch-year sentinels — is replicated verbatim from the source row, because
this fixture exists to exercise *scale*, not to exercise the model's other
scenario branches.

The output is deterministic given `seed` and is written to one shared path
(`FIXTURE_PATH`) so a `--baseline-worktree` comparison reads the exact same
bytes as the candidate run rather than regenerating its own copy — see
``probe_emission.py``. The output parquet is git-ignored; only this script
is checked in.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl
from loguru import logger

PROBE_WORKLOAD_DIR_ENV_VAR: Final[str] = "GASPATCHIO_PROBE_WORKLOAD_DIR"
_probe_workload_dir_setting = os.environ.get(PROBE_WORKLOAD_DIR_ENV_VAR)
# There is deliberately no default. A fallback path would be a directory only
# one machine has: everywhere else it would resolve, fail to exist, and read
# as "the workload is missing" rather than "you never said where it is".
PROBE_WORKLOAD_DIRECTORY: Final[Path | None] = (
    Path(_probe_workload_dir_setting).expanduser().resolve()
    if _probe_workload_dir_setting
    else None
)
#: The two files the probe reads out of the workload directory. Named once,
#: so the messages below and the paths built from them cannot drift apart.
MODEL_FILE_NAME: Final[str] = "model_ifrs17.py"
MODEL_POINTS_FILE_NAME: Final[str] = "model_points.parquet"

BASE_MODEL_POINTS_PATH: Final[Path | None] = (
    None
    if PROBE_WORKLOAD_DIRECTORY is None
    else PROBE_WORKLOAD_DIRECTORY / MODEL_POINTS_FILE_NAME
)

#: The sentence for the one case where there is nothing to point at: the
#: variable was never set. It names the variable and what the directory must
#: hold, and no path, because there is no path to suggest.
WORKLOAD_NOT_CONFIGURED_MESSAGE: Final[str] = (
    "the probe's workload is a machine-local model that is not part of this "
    f"repository — set {PROBE_WORKLOAD_DIR_ENV_VAR} to a directory holding "
    f"{MODEL_FILE_NAME} and {MODEL_POINTS_FILE_NAME}; there is no default"
)

FIXTURE_DIRECTORY: Final[Path] = Path(__file__).resolve().parent / "fixtures"
FIXTURE_PATH: Final[Path] = FIXTURE_DIRECTORY / "ifrs17_100k.parquet"

POLICY_COUNT: Final[int] = 100_000
RANDOM_SEED: Final[int] = 42
SUM_INSURED_JITTER_LOW: Final[float] = 0.8
SUM_INSURED_JITTER_HIGH: Final[float] = 1.2
BASE_RUN_NAME: Final[str] = "Base"
POLICY_ID_COLUMN: Final[str] = "policy_id"
JITTERED_COLUMN: Final[str] = "sum_insured"


@dataclass(slots=True, frozen=True)
class WorkloadPaths:
    """The two files the probe reads out of the machine-local workload."""

    model: Path
    model_points: Path


def resolve_workload() -> WorkloadPaths | str:
    """Return the workload's two files, or one sentence saying why not.

    Two failures, two diagnoses, because they need two different next moves.
    "There is no default" is the right answer only for someone who never
    named a directory; said to someone who did, it sends them to fix the
    wrong thing. So a directory that is named but incomplete is reported as
    itself, with the files it lacks — that path came from the caller's own
    environment, which makes naming it back runtime data rather than a
    location checked into this repository.
    """
    directory = PROBE_WORKLOAD_DIRECTORY
    if directory is None:
        return WORKLOAD_NOT_CONFIGURED_MESSAGE
    missing = [
        name
        for name in (MODEL_FILE_NAME, MODEL_POINTS_FILE_NAME)
        if not (directory / name).exists()
    ]
    if missing:
        return (
            f"{PROBE_WORKLOAD_DIR_ENV_VAR} names {directory}, which is missing "
            f"{' and '.join(missing)}"
        )
    return WorkloadPaths(
        model=directory / MODEL_FILE_NAME,
        model_points=directory / MODEL_POINTS_FILE_NAME,
    )


def synthesize_fixture(
    *,
    base_model_points_path: Path | None = BASE_MODEL_POINTS_PATH,
    policy_count: int = POLICY_COUNT,
    seed: int = RANDOM_SEED,
) -> pl.DataFrame:
    """Replicate the workload's ``Base`` cohort row into a `policy_count`-row frame.

    Deterministic given `seed`: the same inputs always produce the same
    bytes, which is what lets a candidate run and a `--baseline-worktree`
    run share one fixture file instead of each regenerating their own.

    Raises:
        RuntimeError: `base_model_points_path` is None — the workload
            directory was never named, so there is nothing to replicate.
        FileNotFoundError: `base_model_points_path` does not exist — this
            fixture is machine-local, not part of the repository checkout.
        ValueError: the source file does not have exactly one ``Base`` row.

    """
    if base_model_points_path is None:
        raise RuntimeError(WORKLOAD_NOT_CONFIGURED_MESSAGE)
    if not base_model_points_path.exists():
        msg = (
            f"workload model-points file not found at {base_model_points_path} "
            f"— {PROBE_WORKLOAD_DIR_ENV_VAR} must name a directory holding "
            f"{MODEL_FILE_NAME} and {MODEL_POINTS_FILE_NAME}."
        )
        raise FileNotFoundError(msg)

    source_frame = pl.read_parquet(base_model_points_path)
    base_rows = source_frame.filter(pl.col("run") == BASE_RUN_NAME)
    if base_rows.height != 1:
        msg = (
            f"expected exactly one {BASE_RUN_NAME!r} row in "
            f"{base_model_points_path}, found {base_rows.height}"
        )
        raise ValueError(msg)

    base_values = base_rows.to_dicts()[0]
    base_sum_insured = base_values[JITTERED_COLUMN]

    rng = np.random.default_rng(seed)
    jitter = rng.uniform(
        SUM_INSURED_JITTER_LOW, SUM_INSURED_JITTER_HIGH, size=policy_count
    )
    sum_insured_values = (base_sum_insured * jitter).tolist()
    policy_ids = [f"COHORT_{i:06d}" for i in range(1, policy_count + 1)]

    columns: dict[str, object] = {}
    for name, value in base_values.items():
        if name == POLICY_ID_COLUMN:
            columns[name] = policy_ids
        elif name == JITTERED_COLUMN:
            columns[name] = sum_insured_values
        else:
            columns[name] = [value] * policy_count

    return pl.DataFrame(columns, schema=source_frame.schema)


def write_fixture(
    *,
    output_path: Path = FIXTURE_PATH,
    base_model_points_path: Path | None = BASE_MODEL_POINTS_PATH,
    policy_count: int = POLICY_COUNT,
    seed: int = RANDOM_SEED,
) -> Path:
    """Synthesize and write the fixture to `output_path`, creating parent dirs."""
    frame = synthesize_fixture(
        base_model_points_path=base_model_points_path,
        policy_count=policy_count,
        seed=seed,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(output_path)
    logger.info(
        "wrote {} rows x {} columns to {}", frame.height, frame.width, output_path
    )
    return output_path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        # Not `__doc__`: the module docstring is written for someone reading
        # the file, and `--help` would print its whole RST-marked body.
        description="Synthesize the 100k-policy workload fixture used by the probe."
    )
    parser.add_argument("--output", type=Path, default=FIXTURE_PATH)
    parser.add_argument("--policy-count", type=int, default=POLICY_COUNT)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Command-line entry: write the fixture, logging where it landed.

    Refuses with a logged sentence and a non-zero exit whenever the workload
    is unusable — never named, or named but missing a file — the same way
    the probe's own CLI does. `synthesize_fixture` keeps raising for
    programmatic callers; a traceback is a library's register, not a
    command line's.
    """
    args = _parse_args(argv)
    workload = resolve_workload()
    if isinstance(workload, str):
        logger.error(workload)
        raise SystemExit(1)
    write_fixture(
        output_path=args.output,
        base_model_points_path=workload.model_points,
        policy_count=args.policy_count,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
