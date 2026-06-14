# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Resolves the gaspatchio-benchmarks sister-repo directory.

The lifelib reference data and modelx project used to live inside this
repository at evals/benchmarks/lifelib_ref/. They are MIT-licensed
(derivative of lifelib) and now ship as a separate sister repository so
gaspatchio-core can publish under Apache-2.0 with no MIT-attribution
obligations of its own.

Resolution order:
    1. The ``GASPATCHIO_BENCHMARKS_DIR`` environment variable, if set.
    2. Sister-checkout: ``<gaspatchio-core-repo>/../gaspatchio-benchmarks/``.

If neither resolves to an existing directory, ``_resolve_benchmarks_dir``
raises ``FileNotFoundError`` with instructions for how to obtain the
reference data.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path


@functools.lru_cache(maxsize=1)
def _resolve_benchmarks_dir() -> Path:
    """Locate the gaspatchio-benchmarks repository on disk.

    Returns:
        Absolute path to the gaspatchio-benchmarks repository root.

    Raises:
        FileNotFoundError: If neither the environment variable nor the
            sister-checkout default resolves to an existing directory.
    """
    env_dir = os.environ.get("GASPATCHIO_BENCHMARKS_DIR")
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
        if path.is_dir():
            return path
        msg = (
            f"GASPATCHIO_BENCHMARKS_DIR={env_dir!r} does not exist or is "
            f"not a directory."
        )
        raise FileNotFoundError(msg)

    # Sister-checkout fallback: gaspatchio-core/evals/benchmarks/<file>.py
    # → repo root is parents[2]; sibling is repo_root.parent / name.
    repo_root = Path(__file__).resolve().parents[2]
    sister = repo_root.parent / "gaspatchio-benchmarks"
    if sister.is_dir():
        return sister.resolve()

    msg = (
        "Cannot locate gaspatchio-benchmarks. Either:\n"
        f"  - set GASPATCHIO_BENCHMARKS_DIR=/path/to/gaspatchio-benchmarks, or\n"
        f"  - clone gaspatchio-benchmarks alongside this repo at "
        f"{sister}\n"
        "See https://github.com/opioinc/gaspatchio-benchmarks for the "
        "reference modelx project and assumption tables."
    )
    raise FileNotFoundError(msg)
