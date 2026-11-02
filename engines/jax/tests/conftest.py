# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What this suite is measured on, asserted before the first test runs.

Every figure this engine reports is a figure about one interpreter, one jax,
one core wheel and one compiled extension. A suite that ran against a
different one of any of those would still print numbers, and the numbers
would be about something else -- which is the failure this repository's rule
against a swapped build exists to stop. So the stamp is a session fixture
that *refuses*, not a note in a report: the extension has to be the one inside
this project's own venv, never the one under ``bindings/python``, and its
sha256 is printed so a reader of the log can place the run without being told.

The two jax rows are deliberate. The lock resolves ``0.4.38`` for darwin
x86_64 -- this laptop, and the last jax with an Intel-Mac wheel -- and
``0.11.2`` for linux, which is the lane. Both are the floor or above it, and
the assertion below is the floor rather than an equality, because pinning the
laptop's row here would fail the lane for being newer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import polars as pl
import pytest

from gaspatchio_jax.vectors import Invocation, normalise

# The project root -- ``engines/jax`` -- found from this file rather than from
# the working directory, so the suite says the same thing wherever it is run
# from.
PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "src/gaspatchio_jax"

# What a fresh interpreter launched with a stripped environment still needs
# from this one. LD_LIBRARY_PATH is where the dynamic loader finds the
# interpreter's own libpython: setup-python's builds are found through it, and
# an image carrying a system Python of the same minor version (GitHub's GPU
# image does) otherwise hands the child that one, which fails at the first C
# extension. XLA_PYTHON_CLIENT_PREALLOCATE is whether JAX takes most of a GPU's
# memory at start-up; a child that does so while its parent holds the rest
# cannot start at all. Empty where this process was given neither, as on macOS.
LOADER_ENVIRONMENT: dict[str, str] = {
    name: os.environ[name]
    for name in ("LD_LIBRARY_PATH", "XLA_PYTHON_CLIENT_PREALLOCATE")
    if name in os.environ
}

# The oldest jax this engine supports: the last with a macOS x86_64 wheel.
JAX_FLOOR = (0, 4, 38)

# The core this engine is measured against: the release its pyproject.toml pins
# exactly. Asserted and not merely printed: a wheel of another version would
# carry another vocabulary, another validator and another set of published
# vectors, and every figure taken here would be a figure about that one. Read
# from the pin rather than written a second time, so the suite always measures
# the core the engine declares, and a version bump has one place to land;
# bindings/python/tests/test_distributions.py holds the pin to the core's own
# version.
_CORE_PIN = re.compile(r"gaspatchio==(\d[\w.!+-]*)")


def _pinned_core_version() -> str:
    """Return the core version this engine's own metadata requires, exactly."""
    project = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    pins = [
        found.group(1)
        for requirement in project["project"]["dependencies"]
        if (found := _CORE_PIN.fullmatch(requirement))
    ]
    if len(pins) != 1:
        message = (
            "engines/jax/pyproject.toml must require the core exactly once, as "
            f"gaspatchio==<version>; found {pins!r}"
        )
        raise RuntimeError(message)
    return pins[0]


CORE_VERSION = _pinned_core_version()

# Polars ships its engine as a separate wheel at one of two index widths, and
# the two are different builds of the same version. The core's own environment
# runs the 64-bit one; an engine agreeing with a 32-bit Polars would be
# agreeing with something the reference side never runs.
POLARS_RUNTIME = "_polars_runtime_64"

_LEADING_NUMBERS = re.compile(r"\A(\d+(?:\.\d+)*)")


def numeric_version(stated: str) -> tuple[int, ...]:
    """Return the leading dotted numbers of a version, for comparing a floor."""
    found = _LEADING_NUMBERS.match(stated)
    return tuple(int(group) for group in found.group(1).split(".")) if found else ()


def _polars_runtime() -> str:
    """Return the polars engine module this process loaded, by name."""
    import polars as pl  # noqa: F401 -- importing it is what loads the runtime

    return next(
        (name for name in sorted(sys.modules) if name.startswith("_polars_runtime")),
        "",
    ).split(".")[0]


def vectors_directory() -> Path:
    """Return the published vector bundles, as the installed core ships them."""
    import gaspatchio

    return Path(gaspatchio.__file__).resolve().parent / "schemas/vectors"


@pytest.fixture(scope="session", autouse=True)
def stamp() -> dict[str, str]:
    """Refuse the session unless it is the environment this engine is measured on."""
    import jax
    import jaxlib

    from gaspatchio import _internal

    # ``sys.prefix`` and not ``sys.executable``: a uv venv's interpreter is a
    # symlink into the downloaded toolchain, so resolving the executable finds
    # the toolchain rather than the environment. The prefix is the environment.
    inside = PROJECT / ".venv"
    interpreter = Path(sys.prefix).resolve()
    assert interpreter == inside.resolve(), (
        f"this suite runs on {inside}/bin/python and found a prefix of "
        f"{interpreter}: run it as .venv/bin/python -m pytest from engines/jax"
    )

    assert numeric_version(jax.__version__) >= JAX_FLOOR, jax.__version__
    assert numeric_version(jaxlib.__version__) >= JAX_FLOOR, jaxlib.__version__

    assert version("gaspatchio") == CORE_VERSION, version("gaspatchio")
    assert _polars_runtime() == POLARS_RUNTIME, _polars_runtime()

    # Resolved on both sides, as the prefix is above: ``is_relative_to`` is a
    # comparison of spellings, and a venv reached through a symlink -- a
    # worktree borrowing another checkout's environment -- would otherwise
    # read as "outside" the very venv the interpreter was just proved to be.
    extension = Path(_internal.__file__).resolve()
    assert extension.is_relative_to(inside.resolve()), (
        f"the core extension in use is {extension}, which is outside this "
        "project's venv: the core arrives here as a wheel and never as an "
        "editable install into bindings/python"
    )

    read = {
        "interpreter": f"{sys.executable} {sys.version.split()[0]}",
        "jax": jax.__version__,
        "jaxlib": jaxlib.__version__,
        "polars_runtime": _polars_runtime(),
        "gaspatchio": version("gaspatchio"),
        "extension": str(extension),
        "extension_sha256": (
            f"sha256:{hashlib.sha256(extension.read_bytes()).hexdigest()}"
        ),
    }
    for name, value in read.items():
        print(f"{name} {value}")  # noqa: T201 -- the stamp is the point of this fixture
    return read


# A term book small enough to export and run inside the suite, and jagged the
# way a real one is: level 4 over seven terms, whose timelines round up to
# four widths -- four groups and four compiled programs.
JAGGED_POLICIES = 350


@pytest.fixture(scope="session")
def jagged_book(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, object], pl.DataFrame]:
    """Return a miniature jagged term book and its artifact, exported fresh.

    Through the **core** venv's own ``gspio`` on the **tree's** tutorial, the
    same path the every-node references take. Not committed: it is one
    command's output, and a committed copy would agree with a tutorial that
    had moved out from under it. Exported once for the session, because more
    than one module reads it.
    """
    core = PROJECT.parents[1] / "bindings/python"
    where = tmp_path_factory.mktemp("jagged")
    finished = subprocess.run(  # noqa: S603 -- the core's own venv and tutorials
        [
            str(core / ".venv/bin/python"),
            "-c",
            (
                f"import sys; sys.path.insert(0, {str(PROJECT)!r})\n"
                "from pathlib import Path\n"
                "from tests.models.export import jagged\n"
                f"jagged(Path({str(where)!r}), {JAGGED_POLICIES})"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
        cwd=core,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    artifact: dict[str, object] = json.loads(
        (where / "jagged.artifact.json").read_text(encoding="utf-8")
    )
    return artifact, pl.read_parquet(where / "book.parquet")


@dataclass(frozen=True, slots=True)
class ScalarOutcome:
    """What one scalar invocation did: a value, or a check that refused it."""

    value: object | None
    refused_with: str | None
    report: str


def invocation(
    expr: dict[str, object],
    inputs: dict[str, dict[str, object]],
    dtype: str,
    assumptions: list[dict[str, object]] | None = None,
    output_column: str = "answer",
) -> Invocation:
    """Return one tiny executable document, built the way a vector case is.

    The runner's own adapter, reused: a test that built documents a second way
    would be testing a second adapter, and the one the vectors go through is
    the one that has to be right.
    """
    rows = len(next(iter(inputs.values()))["values"])  # type: ignore[arg-type]
    return normalise(
        {
            "id": "a-test",
            "covers": [],
            "inputs": inputs,
            "expr": expr,
            "producer_check": False,
            "case_kind": "value",
            "expected": {"dtype": dtype, "values": [None] * rows},
            "comparison": {"atol": 0.0, "rtol": 0.0},
            "assumptions": assumptions or [],
            "output_column": output_column,
        },
        "tests",
    )


def entry(
    kind: str, payload: dict[str, object], name: str | None = None
) -> dict[str, object]:
    """Return one assumptions entry, sealed with the digest its kind is hashed under.

    Through the core's own payload digest rather than a second reading of the
    content grammar: the engine's first stage re-hashes every declared
    payload, so an entry sealed any other way would be refused for its seal
    rather than read for what it carries.
    """
    from gaspatchio.frame.graph.validate import _payload_digest

    fingerprint, reason = _payload_digest(kind, payload)
    assert reason is None, reason
    return {
        "kind": kind,
        "name": name if name is not None else f"{kind}:{fingerprint[7:15]}",
        "fingerprint": fingerprint,
        "payload": payload,
    }


def answered(one: Invocation) -> ScalarOutcome:
    """Run one invocation and return its first value, or what refused it."""
    from gaspatchio.engines.protocol import FrameSink
    from gaspatchio.engines.report import EngineRefusal
    from gaspatchio_jax.checks import CHECKS
    from gaspatchio_jax.engine import JaxEngine

    try:
        result = JaxEngine().run(one.document, one.inputs, FrameSink())
    except EngineRefusal as refused:
        rendered = refused.report.render()
        named = next((name for name in CHECKS if name in rendered), None)
        return ScalarOutcome(None, named, rendered)
    return ScalarOutcome(result.columns["answer"].to_list()[0], None, "")


def run_scalar(op: str, a: int, b: int, *, dtype: str = "i64") -> ScalarOutcome:
    """Return what this engine does with one binary operation on one policy."""
    return answered(
        invocation(
            {
                "op": "binop",
                "kind": op,
                "left": {"op": "col", "name": "a"},
                "right": {"op": "col", "name": "b"},
            },
            {
                "a": {"dtype": "i64", "values": [a]},
                "b": {"dtype": "i64", "values": [b]},
            },
            dtype,
        )
    )


def run_unary(name: str, a: int, *, dtype: str = "i64") -> ScalarOutcome:
    """Return what this engine does with one named call on one policy."""
    return answered(
        invocation(
            {
                "op": "call",
                "name": name,
                "args": [{"op": "col", "name": "a"}],
                "attrs": {},
            },
            {"a": {"dtype": "i64", "values": [a]}},
            dtype,
        )
    )


@pytest.fixture
def tiny_document() -> Invocation:
    """Return a two-column scalar model: one sum over two arriving columns."""
    return invocation(
        {
            "op": "binop",
            "kind": "add",
            "left": {"op": "col", "name": "a"},
            "right": {"op": "col", "name": "b"},
        },
        {
            "a": {"dtype": "i64", "values": [1, 2]},
            "b": {"dtype": "i64", "values": [10, 20]},
        },
        "i64",
    )
