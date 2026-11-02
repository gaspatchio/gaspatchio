# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path


def _has_pyright() -> bool:
    exe = shutil.which("pyright")
    return exe is not None


def test_pyright_sees_columnproxy_on_attribute(tmp_path):
    if not _has_pyright():
        # Skip gracefully if pyright not installed in env
        return

    code = textwrap.dedent(
        """
        from gaspatchio import ActuarialFrame
        
        af = ActuarialFrame({"age": [1, 2, 3]})
        _x = af.age.ceil()  # should be valid if __getattr__ -> ColumnProxy
        """
    )
    sample = tmp_path / "sample.py"
    sample.write_text(code)

    env = os.environ.copy()
    # prefer project's pyright if available via uv/pdm/poetry
    result = subprocess.run(
        ["pyright", str(sample)], check=False, capture_output=True, text=True, env=env
    )

    # pyright exits nonzero when errors found
    assert result.returncode == 0, (
        f"pyright failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_pyright_rollforward_chain_types(tmp_path):
    """The gh#104 contract: the model-building chain resolves to real types.

    Every link that was Unknown (or a false error) on the 0.8.1 stubs is
    pinned here: the top-level imports resolve, ``af.projection`` is the
    frame accessor rather than a ColumnProxy, ``rollforward()`` returns the
    builder with signature help, the handle chain stays typed through
    ``between``/``add``, and ``compile_rollforward`` returns
    ``CompiledRollforward``. Editor hovers are this contract — CI-tested,
    not hand-checked.
    """
    if not _has_pyright():
        return

    code = textwrap.dedent(
        """
        import datetime

        import polars as pl

        from gaspatchio import (
            ActuarialFrame,
            Curve,
            MortalityTable,
            Schedule,
            compile_rollforward,
        )

        af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "av_init": [100.0]}))
        reveal_type(af.projection)
        af = af.projection.set(
            start_date=datetime.date(2025, 1, 1), n_periods=3, frequency="1Y"
        )
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, points=("bop", "av_star", "eop")
        )
        reveal_type(b)
        h = b["av"].between("bop", "av_star").add(af["av_init"], label="Premium")
        reveal_type(h)
        reveal_type(compile_rollforward(b))

        _ = (Curve, MortalityTable, Schedule)
        """
    )
    sample = tmp_path / "sample.py"
    sample.write_text(code)

    result = subprocess.run(
        ["pyright", "--outputjson", str(sample)],
        check=False,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    diags = report["generalDiagnostics"]

    errors = [d for d in diags if d["severity"] == "error"]
    assert not errors, f"pyright errors on the canonical chain:\n{errors}"

    revealed = "\n".join(d["message"] for d in diags if d["severity"] == "information")
    for expected in (
        '"ProjectionFrameAccessor"',
        '"RollforwardBuilder"',
        '"_StateHandle"',
        '"CompiledRollforward"',
    ):
        assert expected in revealed, f"{expected} not revealed:\n{revealed}"


def _beside_the_interpreter(tool: str) -> str | None:
    """Return a type checker from this interpreter's environment, or from PATH."""
    beside = Path(sys.executable).parent / tool
    if beside.is_file():
        return str(beside)
    return shutil.which(tool)


# The package these tests run against, so a checker reads its stubs rather
# than whichever copy another environment holds.
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_pyright_accepts_a_states_increments_and_captures(tmp_path):
    """``af["av"].increments[...]`` and ``.captures[...]`` type-check in a model.

    Both were missing from the stub, so pyright and mypy refused a model
    that used them, while the runtime answered. pyright reads the same stub
    mypy does, in seconds rather than the minute mypy takes over the
    package, so it is the one asked here.
    """
    code = textwrap.dedent(
        """
        import datetime

        import polars as pl

        from gaspatchio import ActuarialFrame, compile_rollforward

        af = ActuarialFrame(pl.DataFrame({"av_init": [100.0], "fee": [[1.0, 1.0]]}))
        af = af.projection.set(
            start_date=datetime.date(2025, 1, 31), n_periods=2, frequency="1M"
        )
        b = af.projection.rollforward(
            states={"av": af["av_init"]}, track_increments=True
        )
        b["av"].subtract(af["fee"], label="fee")
        af["av"] = compile_rollforward(b).expr_for("av")
        af["fee_taken"] = af["av"].increments["fee"]
        af["closing"] = af["av"].captures["eop"]
        reveal_type(af["av"].increments)
        reveal_type(af["av"].captures["eop"])
        """
    )
    sample = tmp_path / "sample.py"
    sample.write_text(code)
    env = {**os.environ, "PYTHONPATH": str(_PACKAGE_ROOT)}

    pyright = _beside_the_interpreter("pyright")
    assert pyright is not None, "pyright is not installed beside this interpreter"
    checked = subprocess.run(  # noqa: S603 -- fixed argv, no shell, paths are ours
        [pyright, "--outputjson", "--pythonpath", sys.executable, str(sample)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    report = json.loads(checked.stdout)
    errors = [d for d in report["generalDiagnostics"] if d["severity"] == "error"]
    assert not errors, f"pyright refused the model:\n{errors}"
    revealed = "\n".join(
        d["message"]
        for d in report["generalDiagnostics"]
        if d["severity"] == "information"
    )
    assert '"_RollforwardFieldAccessor"' in revealed, revealed
    assert '"ExpressionProxy"' in revealed, revealed
