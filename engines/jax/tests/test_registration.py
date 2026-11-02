# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Importing the package is what puts the engine within reach, and enables x64."""

from __future__ import annotations

import pytest


def test_importing_the_package_registers_the_engine_under_its_name() -> None:
    import gaspatchio_jax  # noqa: F401 -- the import is what registers it
    from gaspatchio.engines import REGISTERED_ENGINES

    assert "jax" in REGISTERED_ENGINES


def test_the_core_finds_the_engine_by_name() -> None:
    from gaspatchio.engines import engine_named

    engine = engine_named("jax")
    assert engine.name == "jax"
    assert engine.version


def test_sixty_four_bit_values_are_on_after_the_import() -> None:
    import jax

    import gaspatchio_jax  # noqa: F401 -- as above

    assert jax.config.read("jax_enable_x64") is True


def test_an_x64_that_will_not_turn_on_refuses_the_package_by_name(monkeypatch) -> None:
    import jax

    from gaspatchio.engines.report import EngineRefusal
    from gaspatchio_jax import _enable_x64

    monkeypatch.setattr(jax.config, "update", lambda *_a, **_k: None)
    monkeypatch.setattr(jax.config, "read", lambda _name: False)
    with pytest.raises(EngineRefusal) as refused:
        _enable_x64()
    assert "jax_enable_x64" in str(refused.value)
    # Section 10's typing table is what carries an i64 and an f64 at 64 bits.
    assert refused.value.report.refusals[0].clause == "10"
    assert refused.value.report.closing_sentence() == "Nothing was computed."


def test_one_name_carries_one_engine() -> None:
    from gaspatchio.engines import register_engine

    with pytest.raises(ValueError, match="already registered"):
        register_engine("jax", object)  # type: ignore[arg-type]


def test_every_axis_sizing_registration_has_a_sizing_and_the_other_way() -> None:
    """The two tables are one claim, and a claim kept in two places drifts.

    A registration that declares ``sizes_its_own_axis`` is a registration the
    plan will ask for a cell count before it builds anything; a ``SIZINGS``
    entry with no declaration behind it is a count nobody asks for. Either
    way round the engine would be wrong quietly -- the first by raising a
    ``KeyError`` deep inside the stage that settles widths, the second by
    leaving an operation to size its own axis inside a program, where a width
    is not a number that can be handed in.
    """
    from gaspatchio_jax.lowerings import LOWERINGS, SIZINGS, load

    load()
    declared = {
        identifier
        for identifier, (_lowering, capability) in LOWERINGS.items()
        if capability.sizes_its_own_axis
    }
    assert declared == set(SIZINGS), declared ^ set(SIZINGS)
    # And the set is not empty, which a symmetric emptiness would satisfy.
    assert {"projection_set", "date.date_ranges"} <= declared
    assert len(declared) == 13


def test_a_registration_that_sizes_its_own_axis_says_so_in_its_coverage_row() -> None:
    """The claim a reader reads is the claim the runtime applies.

    ``coverage.json`` is the engine's published account of what it does with
    each identifier, and *when* an operation is answered is part of that: a
    reader porting a model wants to know that the schedule family is settled
    on the host before anything is compiled, because it is the one thing
    about them a compiled engine cannot hide.
    """
    from gaspatchio_jax import coverage
    from gaspatchio_jax.lowerings import LOWERINGS, load

    load()
    rows = {row["identifier"]: row for row in coverage.manifest()["operations"]}
    for identifier, (_lowering, capability) in LOWERINGS.items():
        # ``when_then`` is a tree form rather than an identifier (11.1.28), so
        # the vocabulary names no row for it.
        if identifier not in rows:
            continue
        condition = rows[identifier]["condition"] or ""
        assert ("width of its answer is read" in condition) is (
            capability.sizes_its_own_axis
        ), identifier
