# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What is reused between batches and between runs, and which reuse it was.

Four cases, and they are four because a reader who is told "cached" cannot
act on it. A **different book of the same shape** must be the same executable
over different numbers -- that is what makes a million policies a compilation
rather than a thousand of them. A **different width** or **a different
constant in the model** must not be: they are different programs and reusing
one would be answering the wrong question quickly. A **second process** must
find the executable on disk, because that is the reuse an actuary feels --
the second run of the morning.

And the two reuses are reported apart. A process-local one says nothing about
whether anything was written down; a persistent one is the one that survives
closing the laptop.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from gaspatchio_jax import cache
from gaspatchio_jax.plan import ExecutionPlan
from gaspatchio_jax.vectors import _sealed
from tests.conftest import LOADER_ENVIRONMENT, PROJECT, invocation
from tests.helpers import a_running_sum, cells

if TYPE_CHECKING:
    from pathlib import Path

    from gaspatchio_jax.plan import Prepared, Program
    from gaspatchio_jax.vectors import Invocation

POLICIES = 24
PERIODS = 8


def _prepared(one: Invocation) -> tuple[ExecutionPlan, Prepared]:
    plan = ExecutionPlan.stage_inspect(one.document)
    return plan, plan.stage_prepare(plan.stage_validate_inputs(one.inputs))


def _program(plan: ExecutionPlan, prepared: Prepared, rows: int = POLICIES) -> Program:
    return plan.compile_for(plan.stage_settle(prepared, np.arange(rows)))[0]


def _report_key(one: Invocation) -> str:
    """Return the key a run of this document would name its compilation by."""
    return cache.report_key(one.document, (12,), POLICIES)


def _with_the_literal(one: Invocation, multiplier: float) -> Invocation:
    """Return the same model with a literal multiplier written into the formula."""
    document = copy.deepcopy(one.document)
    answer = document["nodes"][-1]
    answer["expr"] = {
        "op": "call",
        "name": "cum_sum",
        "args": [
            {
                "op": "binop",
                "kind": "mul",
                "left": {"op": "col", "name": "flow"},
                "right": {"op": "lit", "value": multiplier},
            }
        ],
        "attrs": {},
    }
    return replace(one, document=_sealed(document))


def _answer(one: Invocation, program: Program) -> list[float]:
    """Return the first policy's own answer cells under one program."""
    plan, prepared = _prepared(one)
    batched = plan.stage_finish(
        plan.stage_dispatch(plan.stage_settle(prepared, np.arange(POLICIES)), program)
    )
    return list(np.asarray(batched.values[_answer_of(program)].array)[1])


def _a_read(sealed: dict[str, object]) -> Invocation:
    """Return a lookup over one basis, keyed on a column that arrived."""
    return invocation(
        {
            "op": "call",
            "name": "lookup",
            "args": [{"op": "col", "name": "key"}],
            "attrs": {
                "table": "rates",
                "table_fingerprint": str(sealed["fingerprint"]),
                "on_missing": "raise",
                "fill_value": None,
            },
        },
        {"key": {"dtype": "f64", "values": [0.0, 1.0, 2.0]}},
        "f64",
        [sealed],
    )


def test_a_different_book_of_one_shape_reuses_the_executable_and_answers_it() -> None:
    """The numbers are arguments; only the shape is in the program.

    The same program is handed a second book outright, and what comes back is
    that book's answers -- which is the assertion that matters. A program that
    had baked its first book in would answer the first book's numbers, fast
    and wrong.
    """
    plan, prepared = _prepared(a_running_sum(POLICIES, PERIODS))
    program = _program(plan, prepared)
    other = a_running_sum(POLICIES, PERIODS)
    doubled = other.inputs.with_columns(
        (other.inputs["flow"].list.eval(pl_element() * 2.0)).alias("flow")
    )
    plan_two = ExecutionPlan.stage_inspect(other.document)
    settled = plan_two.stage_settle(
        plan_two.stage_prepare(plan_two.stage_validate_inputs(doubled)),
        np.arange(POLICIES),
    )
    batched = plan_two.stage_finish(plan_two.stage_dispatch(settled, program))
    answered = batched.values[_answer_of(program)]
    # The bucket, not the periods: a rectangle is padded up to a width on the
    # grid and cut back to each policy's own count on the way out.
    assert answered.array.shape == (POLICIES, program.buckets[0])
    first = np.asarray(answered.array)[1, :PERIODS]
    assert first[1] == pytest.approx(2 * (cells(1, 2)[0] + cells(1, 2)[1]))


def test_a_changed_width_is_a_different_program() -> None:
    """A rectangle of another width is another program, not the same one wider."""
    plan, prepared = _prepared(a_running_sum(POLICIES, PERIODS))
    wide_plan, wide = _prepared(a_running_sum(POLICIES, 200))
    narrow = plan.compile_for(plan.stage_settle(prepared, np.arange(POLICIES)))[0]
    widened = wide_plan.compile_for(wide_plan.stage_settle(wide, np.arange(POLICIES)))[
        0
    ]
    assert narrow.buckets != widened.buckets
    assert narrow.compiled is not widened.compiled


def test_a_changed_literal_in_the_model_compiles_a_different_program() -> None:
    """A literal is part of the program, and a program is what it computes.

    The document is mutated where the *model* is -- the number written into
    the formula -- and what is asserted is that the compiled module is a
    different module. A program that reused the first one would answer the
    old model's question quickly, which is the one thing a cache must never
    do.
    """
    one = a_running_sum(POLICIES, PERIODS)
    doubled = _with_the_literal(one, 2.0)
    first = _program(*_prepared(one))
    second = _program(*_prepared(doubled))
    # The module text is a real discriminator and not a value that always
    # differs: one document compiled twice is the same module, byte for byte.
    assert _program(*_prepared(one)).compiled.as_text() == first.compiled.as_text()
    assert first.compiled.as_text() != second.compiled.as_text()
    assert _report_key(one) != _report_key(doubled)
    # And the programs answer their own models: 1x the flow against 2x it.
    assert _answer(one, first)[1] * 2 == pytest.approx(_answer(doubled, second)[1])


def test_a_changed_table_payload_compiles_a_different_program() -> None:
    """A basis is host data the program carries, so a changed basis is a program.

    The rows of a table are baked into the module -- that is what makes a
    lookup an address computation rather than a search -- so moving one rate
    is a different module and a different key. The alternative, a program
    that took the table as an argument, would be a program that could not
    address it.
    """
    from tests.conftest import entry
    from tests.fixtures import make_tables

    keys = [0.0, 1.0, 2.0]
    one = _a_read(entry("table", make_tables.one_key(keys), "rates"))
    moved = make_tables.one_key(keys)
    moved["rows"][1][1] = moved["rows"][1][1] + 0.5
    other = _a_read(entry("table", moved, "rates"))
    first = _program(*_prepared(one), rows=len(keys))
    second = _program(*_prepared(other), rows=len(keys))
    assert first.compiled.as_text() != second.compiled.as_text()
    assert _report_key(one) != _report_key(other)


def test_a_second_batch_of_one_shape_is_reused_inside_the_process() -> None:
    """Three batches of one size, one compilation, and the rest are the same object."""
    plan, prepared = _prepared(a_running_sum(POLICIES, PERIODS))
    assert len(list(plan.stage_batches(prepared, batch=POLICIES // 3))) == 3
    assert len(plan.programs) == 1
    # Two lines for three batches: the compilation, and the reuse -- said
    # once each, because a hundred batches of one shape are one reuse.
    written = [note for note in plan.notes if note.startswith("compile cache:")]
    assert len(written) == 2, written
    assert sum("reused in this process" in note for note in written) == 1
    assert (
        sum(
            ("compiled" in note) or ("loaded from the persistent cache" in note)
            for note in written
        )
        == 1
    )
    assert any("batching: 3 batches" in note for note in plan.notes)


def test_the_two_counter_names_are_the_ones_this_jax_records() -> None:
    """Read off the live library, because a rename here is a silent never-a-hit.

    ``persistent`` is decided by counting one of jax's own compilation-cache
    events. If jax renamed either counter, :func:`cache.watching` would simply
    stop seeing hits and every run would report itself cold -- no error, no
    failing test, just a number that is quietly always false. So the names are
    held against what this jax actually emits: a first compilation records a
    miss, and the same computation after the in-process caches are dropped
    records a hit.
    """
    import jax
    import jax.numpy as jnp
    from jax import monitoring

    # Registered and taken off again: a listener left behind would append
    # every compilation-cache event for the rest of the session to a closure
    # this test owns. Removed by identity rather than through
    # ``clear_event_listeners``, which would take the engine's own with it.
    seen: list[str] = []

    def watch(name: str, **_kw: object) -> None:
        seen.append(name)

    monitoring.register_event_listener(watch)
    try:
        # A constant no run has compiled before, so the first call is a
        # genuine miss however many times this file has been run and whatever
        # is already in the cache directory.
        salt = float(time.time_ns())
        fresh = jax.jit(lambda x: (x * 7.0).sum() + salt)
        fresh(jnp.arange(8.0))
        assert cache.CACHE_MISS in seen, seen
        seen.clear()
        jax.clear_caches()
        fresh(jnp.arange(8.0))
        assert cache.CACHE_HIT in seen, seen
    finally:
        # Public from the jax releases after the 0.4.38 floor
        # (jax.monitoring.unregister_event_listener); the floor has only the
        # private spelling. Either way the listener goes by identity.
        unregister = getattr(monitoring, "unregister_event_listener", None)
        if unregister is None:
            from jax._src import monitoring as internals

            unregister = internals._unregister_event_listener_by_callback  # noqa: SLF001
        unregister(watch)


def test_a_fresh_process_loads_the_executable_the_last_one_compiled(
    tmp_path: Path,
) -> None:
    """The reuse an actuary feels: the second run of the morning.

    Two fresh interpreters over one cache directory. The first compiles and
    writes; the second reports ``persistent`` and does not. A process-local
    cache cannot produce this, which is the whole reason the two are told
    apart.
    """
    where = tmp_path / "compilation"
    script = tmp_path / "once.py"
    script.write_text(_ONCE, encoding="utf-8")
    read = []
    for _run in range(2):
        finished = subprocess.run(  # noqa: S603 -- this project's own venv
            [str(PROJECT / ".venv/bin/python"), str(script)],
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(tmp_path),
                "JAX_COMPILATION_CACHE_DIR": str(where),
                # This tree's engine, ahead of wherever the venv's editable
                # install points: a worktree's venv can point at another tree.
                "PYTHONPATH": os.pathsep.join([str(PROJECT / "src"), str(PROJECT)]),
                **LOADER_ENVIRONMENT,
            },
        )
        assert finished.returncode == 0, finished.stdout + finished.stderr
        read.append(json.loads(finished.stdout.strip().splitlines()[-1]))
    assert read[0]["persistent"] is False
    assert read[1]["persistent"] is True
    assert read[0]["answers"] == read[1]["answers"]
    assert where.exists()
    assert any(where.iterdir())


def _answer_of(program: Program) -> str:
    """Return the node id the document's answer column stands under."""
    return next(node for node, column in program.columns.items() if column == "answer")


def pl_element():
    """Return polars' own element reference, imported where it is used."""
    import polars as pl

    return pl.element()


_ONCE = """
import json

import numpy as np

import gaspatchio_jax
from gaspatchio_jax import cache
from gaspatchio_jax.plan import ExecutionPlan
from tests.helpers import a_running_sum

cache.configure(min_compile_seconds=0.0)
one = a_running_sum(24, 8)
plan = ExecutionPlan.stage_inspect(one.document)
prepared = plan.stage_prepare(plan.stage_validate_inputs(one.inputs))
settled = plan.stage_settle(prepared, np.arange(24))
program, outcome = plan.compile_for(settled)
batched = plan.stage_finish(plan.stage_dispatch(settled, program))
answered = batched.values[
    next(node for node, column in program.columns.items() if column == "answer")
]
print(json.dumps({
    "persistent": outcome.persistent,
    "process_local": outcome.process_local,
    "answers": np.asarray(answered.array).sum().item(),
}))
"""


_WITHOUT_A_CACHE = """
import json
import warnings

import polars as pl

import gaspatchio_jax
from gaspatchio.engines.protocol import FrameSink
from gaspatchio_jax import cache
from gaspatchio_jax.engine import JaxEngine
from tests.helpers import a_running_sum

import jax

one = a_running_sum(24, 8)
with warnings.catch_warnings(record=True) as raised:
    warnings.simplefilter("always")
    answered = JaxEngine().run(one.document, one.inputs, FrameSink())
print(json.dumps({
    "rows": answered.columns.height,
    "unusable": cache.unusable(),
    "noted": [note for note in answered.report.notes if "cannot be used" in note],
    "cache_dir": jax.config.jax_compilation_cache_dir,
    "warned": [
        str(one.message) for one in raised
        if "cache" in str(one.message).lower()
    ],
}))
"""


def test_a_cache_location_that_cannot_be_written_costs_seconds_and_not_the_run(
    tmp_path: Path,
) -> None:
    """A read-only home is a slow morning, not an engine that will not start.

    Before this, the directory was made at import and the ``OSError`` came
    back out through provider discovery as *the jax engine's package is
    installed and importing it failed* -- an installation to repair, which is
    the wrong next move entirely. The cache is an optimisation; the engine is
    not.

    And it degrades *quietly*: jax reads the environment variable itself, so
    an engine that merely declined to configure the cache still had XLA trying
    the location and warning about it once per compiled program.
    """
    script = tmp_path / "without_a_cache.py"
    script.write_text(_WITHOUT_A_CACHE, encoding="utf-8")
    finished = subprocess.run(  # noqa: S603 -- this project's own venv
        [str(PROJECT / ".venv/bin/python"), str(script)],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            # A path whose parent is a character device: it cannot be made,
            # and it cannot be made writable either.
            "JAX_COMPILATION_CACHE_DIR": "/dev/null/no-such-place",
            # This tree's engine, as above.
            "PYTHONPATH": os.pathsep.join([str(PROJECT / "src"), str(PROJECT)]),
            **LOADER_ENVIRONMENT,
        },
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    read = json.loads(finished.stdout.strip().splitlines()[-1])
    assert read["rows"] == 24
    assert read["unusable"] is not None
    assert "JAX_COMPILATION_CACHE_DIR" in read["unusable"]
    assert len(read["noted"]) == 1
    # Quiet as well as survivable: jax is told to stop reading the location,
    # so XLA does not try it and warn once per compiled program about a thing
    # the report has already said in one sentence.
    assert read["cache_dir"] is None
    assert read["warned"] == []
