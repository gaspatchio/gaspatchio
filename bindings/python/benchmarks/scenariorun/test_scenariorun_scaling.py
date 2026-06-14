# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Memory-scaling benchmark mirroring ref/41-backend-portability/41-scenario-scaling-empirical.md."""

from __future__ import annotations

import json
import resource
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).parent / "_runner.py"


def _run_subprocess(spec: dict) -> tuple[float, float, dict]:
    """Run the inner runner; return (wall_s, peak_rss_mb, result_dict)."""
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(RUNNER), json.dumps(spec)],
        capture_output=True,
        text=True,
        check=True,
    )
    rusage = resource.getrusage(resource.RUSAGE_CHILDREN)
    if sys.platform == "darwin":
        # macOS reports ru_maxrss in bytes
        peak_rss_mb = rusage.ru_maxrss / (1024 * 1024)
    else:
        # Linux reports ru_maxrss in kilobytes
        peak_rss_mb = rusage.ru_maxrss / 1024
    result = json.loads(proc.stdout)
    return result["wall_time_s"], peak_rss_mb, result


@pytest.mark.benchmark
@pytest.mark.parametrize("batch_size", [1, 8])
def test_rss_bounded_within_batch_at_1k_policies(batch_size: int) -> None:
    """Peak RSS at 1k x 100 scenarios should not exceed a generous within-batch ceiling.

    The bound is loose - we're testing that the loop does NOT exhibit
    cross-product-scale RSS (which would be ~12 GB at 1k x 100 x per-row footprint).
    A working batched run should stay well under 4 GB.
    """
    _, peak_rss_mb, _ = _run_subprocess(
        {
            "n_policies": 1000,
            "n_scenarios": 100,
            "batch_size": batch_size,
        },
    )
    assert peak_rss_mb < 4096, (
        f"peak_rss_mb={peak_rss_mb:.0f} suggests cross-product behaviour"
    )
