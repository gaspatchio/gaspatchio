# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Finding a second engine by name, and saying so plainly when it is absent.

An engine is a package outside this one. It arrives under a name -- ``jax``
-- and importing the package it lives in is what puts it within reach: the
package calls :func:`register_engine` at import, and nothing here imports it
until somebody asks for that name. The core therefore ships knowing the
names of engines it has never loaded, and a core installation with no engine
installed loads no engine's dependencies, which is what the clean-process
test in this package's tests holds it to.

**Three outcomes, kept apart.** The package for a known name is not
installed; it is installed and its import failed; the name is one nothing
here has heard of. The first is an extra to install and the sentence names
it. The second is a broken installation and the sentence names the module
and carries the cause, because "install the extra" would send the reader
round a loop they have already been round. The third is a typo or an engine
that does not exist, and the sentence names what does.

**A test and integration hook.** ``GASPATCHIO_ENGINE_PROVIDERS``, read once
when this module is imported, adds providers to :data:`PROVIDERS` in the
form ``name=module,name=module``. That is how a test puts a stub provider on
``PYTHONPATH`` and has a *fresh* subprocess find it -- discovery that only a
running process could arrange would not be discovery. It is deliberately
additive and deliberately read once: an engine name whose provider changed
half way through a run would be two engines under one name.
"""

from __future__ import annotations

import importlib
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from .protocol import Engine

__all__ = [
    "PROVIDERS",
    "REGISTERED_ENGINES",
    "EngineBrokenError",
    "EngineNotInstalledError",
    "engine_named",
    "register_engine",
]

# The environment variable the hook above is spelled with, and the two
# characters it is written in. One place, so the docstring, the parser and
# any message naming it cannot drift apart.
PROVIDER_OVERRIDE = "GASPATCHIO_ENGINE_PROVIDERS"
_ENTRIES = ","
_BINDS = "="


class EngineNotInstalledError(RuntimeError):
    """No engine of that name can be reached from this installation.

    Either its package is not installed or nothing here knows the name. A
    distinct type rather than a bare ``ImportError`` because the commands
    treat it as a refusal with an exit code of its own, not as an unexpected
    failure to print a traceback for.
    """


class EngineBrokenError(RuntimeError):
    """The engine's package is installed and importing it failed.

    Separate from :class:`EngineNotInstalledError` because the next move is
    different: this reader has the package and something inside it -- a
    missing dependency of its own, a version that no longer matches -- did
    not come up. Telling them to install the extra would send them round a
    loop they are already past.
    """


def _providers_from_environment(declared: str | None) -> dict[str, str]:
    """Return the providers an environment variable adds, ignoring the empty.

    A malformed entry is skipped rather than raising: this is read at import
    of a core module, and a stray comma in somebody's shell profile must not
    make ``import gaspatchio`` fail.
    """
    if not declared:
        return {}
    found: dict[str, str] = {}
    for entry in declared.split(_ENTRIES):
        name, sep, module = entry.partition(_BINDS)
        if sep and name.strip() and module.strip():
            found[name.strip()] = module.strip()
    return found


# Engine name to the module whose import puts it within reach. The names here
# are the ones this installation knows how to ask for; whether any of them is
# installed is a different question, answered at the moment somebody asks.
PROVIDERS: dict[str, str] = {"jax": "gaspatchio_jax"}
PROVIDERS.update(_providers_from_environment(os.environ.get(PROVIDER_OVERRIDE)))

# Engine name to what makes one. Filled by :func:`register_engine`, either
# from a provider module's import or from a test that injects one directly.
REGISTERED_ENGINES: dict[str, Callable[[], Engine]] = {}


def register_engine(name: str, factory: Callable[[], Engine]) -> None:
    """Put one engine within reach under one name.

    A second registration of a name is refused rather than allowed to win.
    Two packages claiming ``jax`` is a situation where the honest answer is
    that nobody can say which engine a result came from, and a result nobody
    can place is worse than a run that did not start.
    """
    if name in REGISTERED_ENGINES:
        message = (
            f"An engine is already registered under {name!r}. Two packages "
            "claiming one name leaves no way to say which of them produced a "
            "result, so the second is refused rather than allowed to win. "
            "Uninstall whichever of the two you did not mean to have."
        )
        raise ValueError(message)
    REGISTERED_ENGINES[name] = factory


def _not_installed(name: str, module: str) -> str:
    """Return the sentence for a known engine whose package is absent.

    The double spaces are deliberate, as they are in the viewer's sentence:
    they set the commands off from the prose in a terminal that has no other
    way to show a command.
    """
    package = module.replace("_", "-")
    return (
        f"The {name} engine is not installed. Running on it needs the "
        f"{package} package: install the extra with  "
        f'pip install "gaspatchio[{name}]"  (or  uv add "gaspatchio[{name}]")  '
        "and run the command again."
    )


def _no_such_engine(name: str) -> str:
    """Return the sentence for a name nothing here has heard of."""
    known = ", ".join(sorted({*PROVIDERS, *REGISTERED_ENGINES}))
    return (
        f"No engine named {name!r} is known here. The names this "
        f"installation can ask for are: {known or 'none'}. Polars is not one "
        "of them -- it is the engine the frame already runs on, reached as "
        'collect(engine="streaming"), "in-memory" or "auto".'
    )


def _broken(name: str, module: str, cause: BaseException) -> str:
    """Return the sentence for a provider that is installed and did not import."""
    return (
        f"The {name} engine's package is installed and importing "
        f"{module} failed, so there is no engine to run on: {cause}. This is "
        "an installation to repair rather than an extra to add -- check that "
        f"{module}'s own dependencies are present and at versions it accepts."
    )


def engine_named(name: str) -> Engine:
    """Return the engine registered under ``name``, importing its package once.

    Args:
        name: The engine's name, as ``--engine`` and ``collect(engine=...)``
            spell it.

    Returns:
        The engine, from the factory registered under that name.

    Raises:
        EngineNotInstalledError: The name is known and its package is not
            installed, or the name is not known at all.
        EngineBrokenError: The package is installed and importing it failed,
            or it imported and registered nothing under the name it is
            declared for.

    """
    factory = REGISTERED_ENGINES.get(name)
    if factory is not None:
        return factory()

    module = PROVIDERS.get(name)
    if module is None:
        raise EngineNotInstalledError(_no_such_engine(name))

    try:
        importlib.import_module(module)
    except ModuleNotFoundError as missing:
        # The provider itself, or something the provider imports? The first
        # is an extra to install and the second is that extra's own
        # installation in trouble, and one sentence for both would send half
        # the readers to the wrong place.
        absent = missing.name or ""
        if absent == module or absent.startswith(f"{module}."):
            raise EngineNotInstalledError(_not_installed(name, module)) from missing
        raise EngineBrokenError(_broken(name, module, missing)) from missing
    except Exception as error:
        raise EngineBrokenError(_broken(name, module, error)) from error

    factory = REGISTERED_ENGINES.get(name)
    if factory is None:
        message = (
            f"{module} imported and registered no engine under {name!r}, so "
            f"there is nothing to run on. A provider module registers its "
            "engine at import; this one did not, which makes it a version "
            "that does not match this core rather than an extra to install."
        )
        raise EngineBrokenError(message)
    return factory()
