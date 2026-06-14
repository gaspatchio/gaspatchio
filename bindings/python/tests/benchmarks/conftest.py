# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Put repo root on sys.path so evals.benchmarks.* resolves under pytest."""

import sys
from pathlib import Path

# tests/benchmarks -> tests -> python -> bindings -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
