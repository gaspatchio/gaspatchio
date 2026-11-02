# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Regression tests for the row order with_scenarios() guarantees.
# ABOUTME: Model points major, scenarios minor -- under the streaming engine too.
# ruff: noqa: S603
"""Row-order regression tests for scenario expansion.

``with_scenarios`` guarantees model-point-major, scenario-minor row order: policy 0
paired with every scenario, then policy 1, and so on. That is the order every tutorial
and worked example already implies, so it needs to hold whichever engine ran the plan.

Before the cross join carried ``maintain_order="left_right"`` it did not. The in-memory
engine emitted model-point-major and the streaming engine -- which is what
``ActuarialFrame.collect()`` uses by default -- emitted scenario-major, so the same
frame read differently depending on an execution detail the modeller never chose.

The stressor is ``POLARS_STREAMING_CHUNK_SIZE=1000``, which forces the streaming engine
to cut the frame into many small morsels. It has to be set in the environment of a
*fresh* interpreter: polars reads the variable once, so setting it part-way through a
running process (``monkeypatch.setenv``) changes nothing. Hence the subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import with_scenarios

if TYPE_CHECKING:
    from pathlib import Path

# Large enough that the forced 1000-row chunk size actually splits the frame into
# hundreds of morsels: 50_000 x 5 = 250_000 rows.
_N_POLICIES = 50_000
_SCENARIOS = ["BASE", "UP", "DOWN", "MASS_LAPSE", "PANDEMIC"]
_N_COLLECTS = 4

_SUBPROCESS_SCRIPT = '''
"""Collect a with_scenarios frame repeatedly and record the row order each time."""

import json
import sys

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import with_scenarios

n_policies = int(sys.argv[1])
n_collects = int(sys.argv[2])
out_path = sys.argv[3]
scenarios = json.loads(sys.argv[4])

af = ActuarialFrame(
    {
        "policy_id": list(range(n_policies)),
        "premium": [100.0 + i for i in range(n_policies)],
    }
)
expanded = with_scenarios(af, scenarios)

want_policy = [p for p in range(n_policies) for _ in scenarios]
want_scenario = scenarios * n_policies

results = []
for _ in range(n_collects):
    df = expanded.collect()
    got_policy = df["policy_id"].to_list()
    got_scenario = df["scenario_id"].to_list()
    first_bad = next(
        (i for i in range(len(want_policy)) if got_policy[i] != want_policy[i]),
        None,
    )
    results.append(
        {
            "n_rows": len(df),
            "n_chunks": df.n_chunks(),
            "policy_major": got_policy == want_policy,
            "scenario_minor": got_scenario == want_scenario,
            "first_divergence": first_bad,
            "head_policy": got_policy[:10],
            "head_scenario": got_scenario[:10],
        }
    )

with open(out_path, "w") as fh:
    json.dump(results, fh)
'''


def test_streaming_row_order_is_model_point_major(tmp_path: Path) -> None:
    """Forced small chunks must not reorder the scenario axis.

    Runs in a fresh interpreter so ``POLARS_STREAMING_CHUNK_SIZE`` is read at startup.
    Every collect must come back model-point-major, scenario-minor.
    """
    # Arrange
    script_path = tmp_path / "collect_order_runner.py"
    script_path.write_text(_SUBPROCESS_SCRIPT)
    out_path = tmp_path / "order_results.json"

    # Act
    proc = subprocess.run(
        [
            sys.executable,
            str(script_path),
            str(_N_POLICIES),
            str(_N_COLLECTS),
            str(out_path),
            json.dumps(_SCENARIOS),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "POLARS_STREAMING_CHUNK_SIZE": "1000"},
    )
    if proc.returncode != 0:
        pytest.fail(
            "Order-check subprocess failed:"
            f"\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    results = json.loads(out_path.read_text())

    # Assert
    assert len(results) == _N_COLLECTS
    expected_rows = _N_POLICIES * len(_SCENARIOS)

    # The stressor has to be live, or the test passes for the wrong reason. The
    # floor separates the two states rather than merely excluding a single chunk:
    # forced 1000-row chunks put this 250K-row frame in 256, while the default
    # chunking gives one per core (16 here). Anything at or below 100 means the
    # forced size never applied.
    assert results[0]["n_chunks"] > 100, (
        "POLARS_STREAMING_CHUNK_SIZE did not take effect -- the frame came back in "
        f"{results[0]['n_chunks']} chunk(s), too few for the forced 1000-row size, "
        "so this run proves nothing about order under chunked streaming."
    )

    for i, res in enumerate(results):
        assert res["n_rows"] == expected_rows
        assert res["policy_major"], (
            f"collect {i + 1} of {_N_COLLECTS} was not model-point-major: first "
            f"divergence at row {res['first_divergence']}, "
            f"head policy_id {res['head_policy']}, "
            f"head scenario_id {res['head_scenario']}"
        )
        assert res["scenario_minor"], (
            f"collect {i + 1} of {_N_COLLECTS} did not cycle scenarios within a "
            f"model point: head scenario_id {res['head_scenario']}"
        )


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
def test_both_engines_agree_on_row_order(engine: str) -> None:
    """The two engines must lay the scenario axis out the same way."""
    # Arrange
    af = ActuarialFrame({"policy_id": [1, 2, 3], "premium": [100.0, 200.0, 300.0]})

    # Act
    result = with_scenarios(af, ["BASE", "UP", "DOWN"]).collect(engine=engine)

    # Assert
    assert result["policy_id"].to_list() == [1, 1, 1, 2, 2, 2, 3, 3, 3]
    assert result["scenario_id"].to_list() == ["BASE", "UP", "DOWN"] * 3
