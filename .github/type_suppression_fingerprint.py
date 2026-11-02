# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Digest the settings a type-checker count was measured under.

`MYPY_MAX` and `PYRIGHT_MAX` are counts, and `MYPY_MIN_FILES` and
`PYRIGHT_MIN_FILES` say how much of the package each count was taken over. Both
pairs are blind to the third thing that moves a count without touching a line
of source: the settings that decide whether a diagnostic is raised at all.
Four lines of TOML take mypy to `Success: no issues found in 192 source files`
-- zero errors, the denominator still exactly on its floor -- and the step then
invites the next commit to lower the ceiling to nothing:

    [[tool.mypy.overrides]]
    module = "gaspatchio.*"
    ignore_errors = true

This module prints a SHA-256 over those settings, one tool at a time, so the
workflow can refuse a run whose configuration is not the configuration the
ceilings were measured under. It is the shape `.github/jscpd-baseline.json`
already uses for duplication: what gets enforced is content identity, not a
number.

Run it from `bindings/python`, which is the directory both type checkers are
run from and therefore the directory each resolves its configuration relative
to:

    .venv/bin/python ../../.github/type_suppression_fingerprint.py mypy
    .venv/bin/python ../../.github/type_suppression_fingerprint.py pyright

Add `--document` to print the JSON that was hashed instead of the hash. That is
what to read when a digest has moved and you want to know which setting did it.

**Two sources, because only one of the two tools will report on itself.**

mypy's settings come from mypy: `mypy.main.process_options` is the function
`mypy` itself calls, so what comes back is the configuration mypy resolved,
from whichever file mypy chose to read it out of. That matters, because mypy
prefers `mypy.ini` and `.mypy.ini` to `pyproject.toml` -- a digest taken over
`[tool.mypy]` in `pyproject.toml` would not see a `mypy.ini` dropped in beside
it, and this one does.

pyright has no equivalent. `--verbose` prints its search paths and its language
level and stops there; no flag makes it report its diagnostic rule set, and
`--outputjson` carries only the summary and the diagnostics. So pyright's
settings are read from `pyproject.toml` -- and, to buy back the part of the
mypy story that loses, the document also records whether a `pyrightconfig.json`
exists in the project root, because pyright would read that INSTEAD of
`pyproject.toml`.

**Deny-lists, not allow-lists.** Both documents are "every setting except the
named exclusions" rather than "the named suppression settings". An allow-list
is the more precise instrument and it is the wrong one here: it silently stops
covering a setting the day a release adds or renames one, and a guard that
quietly narrows is the failure this whole apparatus exists to catch. The cost
of a deny-list is a digest that also moves on a setting nobody would call a
suppression -- and that cost is one line in `.github/ratchets.env` with the
reason beside it, which is what every other figure there already asks for.

**What the digests do not cover** is written down in `.github/RATCHETS.md`
under each section, and the honest summary is: scope (each `exclude` list, left
to the floors), the host (mypy's `platform` is reduced to "was it overridden?"
and its `python_executable` is dropped, because CI and a keyboard disagree
about both), and the tool versions (`uv.lock` pins those, and a bump re-measures
the ceilings anyway).
"""

from __future__ import annotations

import hashlib
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

# Bumped when what gets hashed changes, so that a digest taken under an older
# rule cannot be mistaken for one taken under this one. Both recorded values
# move in the same commit as a bump.
SCHEMA = 1

#: Keys of ``mypy.options.Options.snapshot()`` kept OUT of the mypy document.
#: Everything not named here is in it, including any key a future mypy adds.
MYPY_NOT_HASHED: dict[str, str] = {
    # Scope. `exclude` is what the MYPY_MIN_FILES floor answers for, and a
    # denominator and a digest disagreeing about who guards scope is how a
    # narrowed run gets waved through twice.
    "exclude": "scope; MYPY_MIN_FILES is the guard",
    "exclude_gitignore": "scope; MYPY_MIN_FILES is the guard",
    # The invocation. These follow the command line, and the command line is
    # the workflow step's, not the configuration's.
    "files": "set by the command line",
    "modules": "set by the command line",
    "packages": "set by the command line",
    "config_file": "the path the settings came from, not a setting",
    # The host. Every one of these differs between CI and a keyboard, and a
    # digest CI and a keyboard disagree about is no better than a ceiling they
    # disagree about. `platform` is not simply dropped: the document carries
    # `platform_is_host_default` instead, which is False the moment anyone
    # pins it in configuration.
    "platform": "host-dependent; see platform_is_host_default",
    "python_executable": "host-dependent absolute path",
    "abs_custom_typeshed_dir": "host-dependent absolute path",
    "cache_dir": "host-dependent, and affects nothing a run reports",
    "color_output": "depends on whether stdout is a terminal",
    "num_workers": "may follow the machine's core count",
    "sqlite_num_shards": "may follow the machine's core count",
    "verbosity": "set by the command line",
}

#: Keys of ``[tool.pyright]`` kept OUT of the pyright document, for the reason
#: `exclude` is kept out of mypy's. Note that `ignore` is NOT here: it
#: suppresses diagnostics while leaving `filesAnalyzed` untouched, so the
#: PYRIGHT_MIN_FILES floor cannot see it and this digest must.
PYRIGHT_NOT_HASHED: dict[str, str] = {
    "include": "scope; PYRIGHT_MIN_FILES is the guard",
    "exclude": "scope; PYRIGHT_MIN_FILES is the guard",
}

#: Config files pyright reads in preference to ``pyproject.toml``. Their
#: presence is recorded so that adding one moves the digest rather than
#: silently taking the configuration somewhere this module does not look.
PYRIGHT_PREFERRED_FILES = ("pyrightconfig.json",)


def _plain(value: object) -> object:
    """Render one setting as JSON, deterministically.

    Sets come back from mypy unordered and tuples come back where JSON has
    only arrays, so both are normalised here rather than left to
    ``json.dumps`` -- an unordered set would give a different digest on
    different runs, which is the one thing a fingerprint may not do.
    """
    if isinstance(value, (set, frozenset)):
        return sorted(_plain(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in sorted(value.items())}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _mypy_document(root: Path) -> dict[str, Any]:
    """Return mypy's own resolved settings, minus the host and the scope.

    ``process_options`` is what ``mypy`` runs before it checks anything, so
    this reads the configuration mypy read, out of the file mypy chose.
    Argument list and working directory are the step's, so that the settings
    digested are the settings the counted run used.
    """
    from mypy.main import process_options  # noqa: PLC0415  (import cost, not API)

    if root != Path.cwd():  # pragma: no cover - the callers all chdir first
        message = (
            "mypy resolves its configuration from the working directory; "
            f"run this from {root}"
        )
        raise SystemExit(message)

    _, options = process_options(["gaspatchio"])
    snapshot = options.snapshot()
    settings = {
        name: _plain(value)
        for name, value in sorted(snapshot.items())
        if name not in MYPY_NOT_HASHED
    }
    # Reinstated in the one form that means the same thing on both hosts: not
    # WHICH platform, but whether the configuration named one at all.
    settings["platform_is_host_default"] = snapshot["platform"] == sys.platform
    return {"tool": "mypy", "schema": SCHEMA, "settings": settings}


def _pyright_document(root: Path) -> dict[str, Any]:
    """Return ``[tool.pyright]`` as pyright would read it, minus the scope.

    Read from the file rather than from the tool, because pyright will not
    say. The two ``sources`` entries are the compensation: a
    ``pyrightconfig.json`` appearing beside ``pyproject.toml`` takes the
    configuration somewhere this function does not read, and recording that it
    is not there is what turns that from a blind spot into a failure.
    """
    manifest = root / "pyproject.toml"
    if not manifest.is_file():
        message = f"no pyproject.toml in {root}; pyright's settings cannot be read"
        raise SystemExit(message)

    with manifest.open("rb") as handle:
        table = tomllib.load(handle).get("tool", {}).get("pyright", {})

    settings = {
        name: _plain(value)
        for name, value in sorted(table.items())
        if name not in PYRIGHT_NOT_HASHED
    }
    return {
        "tool": "pyright",
        "schema": SCHEMA,
        "sources": {name: (root / name).exists() for name in PYRIGHT_PREFERRED_FILES},
        "settings": settings,
    }


BUILDERS = {"mypy": _mypy_document, "pyright": _pyright_document}


def canonical(document: dict[str, Any]) -> str:
    """Serialise a document to the exact bytes that get hashed."""
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def main(argv: list[str]) -> int:
    """Print one tool's digest, or the document behind it under ``--document``."""
    wanted = [argument for argument in argv if not argument.startswith("-")]
    show_document = "--document" in argv
    unknown = [
        argument
        for argument in argv
        if argument.startswith("-") and argument != "--document"
    ]
    if len(wanted) != 1 or wanted[0] not in BUILDERS or unknown:
        sys.stderr.write(
            f"usage: {Path(sys.argv[0]).name} "
            f"{{{'|'.join(sorted(BUILDERS))}}} [--document]\n"
        )
        return 2

    document = BUILDERS[wanted[0]](Path.cwd())
    if show_document:
        sys.stdout.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
        return 0
    sys.stdout.write(hashlib.sha256(canonical(document).encode()).hexdigest() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
