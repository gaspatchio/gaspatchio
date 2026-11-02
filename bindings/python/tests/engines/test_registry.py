# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""How an engine is found by name, and what is said when it is not there.

Three outcomes have to stay apart: the package for a known engine is not
installed, the package is installed and its import failed, and the name is
one nothing here has ever heard of. Collapsing any two of them costs the
reader the one sentence that would have told them what to do next.
"""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING

import pytest

from gaspatchio.engines import (
    PROVIDERS,
    REGISTERED_ENGINES,
    EngineBrokenError,
    EngineNotInstalledError,
    engine_named,
    register_engine,
)

if TYPE_CHECKING:
    from pathlib import Path

# A provider module: importing it is what puts its engine within reach, which
# is the whole of the contract between the seam and a package outside it.
PROVIDER_SOURCE = '''
from gaspatchio.engines import register_engine


class LazyEngine:
    """An engine that exists to be found, and does nothing else."""

    name = "lazy"
    version = "0.0.0-test"

    def validate_tree(self, document):
        return ()

    def run(self, document, inputs, sink, *, every_node=False):
        raise NotImplementedError


register_engine("lazy", LazyEngine)
'''


def _stub_engine() -> object:
    """Return something engine-shaped enough to be handed back by a factory."""

    class Stub:
        name = "stub"
        version = "0.0.0-test"

    return Stub()


def test_an_absent_provider_is_refused_by_name() -> None:
    with pytest.raises(EngineNotInstalledError) as caught:
        engine_named("jax")  # gaspatchio_jax is not installed in the core venv
    assert 'pip install "gaspatchio[jax]"' in str(caught.value)
    assert "is not installed" in str(caught.value)


def test_a_broken_provider_is_a_different_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "broken_engine.py").write_text(
        "raise ImportError('a dependency the provider needs')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(PROVIDERS, "broken", "broken_engine")
    importlib.invalidate_caches()
    with pytest.raises(EngineBrokenError, match="broken_engine"):
        engine_named("broken")


def test_an_unknown_name_names_the_names_that_exist() -> None:
    with pytest.raises(EngineNotInstalledError) as caught:
        engine_named("duckdb")
    assert "duckdb" in str(caught.value)
    assert "jax" in str(caught.value)


def test_a_name_registers_once() -> None:
    register_engine("twice", _stub_engine)
    with pytest.raises(ValueError, match="already registered"):
        register_engine("twice", _stub_engine)


def test_a_provider_is_imported_only_when_asked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "lazy_engine.py").write_text(PROVIDER_SOURCE)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(PROVIDERS, "lazy", "lazy_engine")
    importlib.invalidate_caches()

    assert "lazy_engine" not in sys.modules

    engine = engine_named("lazy")

    assert "lazy_engine" in sys.modules
    assert engine.name == "lazy"
    assert "lazy" in REGISTERED_ENGINES


def test_a_provider_that_imports_without_registering_is_broken(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "silent_engine.py").write_text("# imports, registers nothing\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(PROVIDERS, "silent", "silent_engine")
    importlib.invalidate_caches()
    with pytest.raises(EngineBrokenError, match="silent_engine"):
        engine_named("silent")
