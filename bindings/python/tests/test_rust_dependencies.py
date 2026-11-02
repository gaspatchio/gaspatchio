# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""No crate is built into the extension for a dependency no code uses.

A dependency that one of this repository's two crates declares and never
names is still resolved, compiled and handed to the linker, with everything
it depends on in turn. The linker drops the code nothing calls, so nothing
fails. What shows is a longer build and a longer
``bindings/python/third-party-notices.txt``, which lists every crate the
extension is built from and which every wheel ships.

This test reads ``Cargo.lock``, each crate's manifest and each crate's own
Rust sources, and needs no cargo. A normal dependency is used when a Rust file
under the crate's ``src/`` names it outside comments and string literals: as a
path (``name::``), in ``use name`` or in ``extern crate name``. Code in
``tests/``, ``benches/`` and ``examples/`` does not count: it may use a
dev-dependency, and none of it is linked into the extension. A build script
sees only build-dependencies, so it cannot use a normal one. The test fails on
every crate the lockfile holds only through dependencies nothing names. It
passes a declaration that brings in nothing of its own, such as a crate the
build reaches anyway, or one declared only to choose its version or features.
Removing such a declaration would tidy the manifest without taking a crate out
of the build.

The lockfile records which crate depends on which, but not the features that
caused an edge. So the test sees a lower bound of what an unused dependency
brings in: a crate it reaches only by switching a feature on in another crate
is missed. ``scripts/rust_notices.py check`` in CI is what holds the notices to
the build.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# A string literal, raw or not, and a character literal. A lifetime ('a) is
# neither: it has no closing quote after one character.
RAW_STRING = re.compile(r'(?<![A-Za-z0-9_])[bc]?r(#*)"')
STRING = re.compile(r'(?<![A-Za-z0-9_])[bc]?"')
CHARACTER = re.compile(
    r"(?<![A-Za-z0-9_])b?'(?:[^'\\\n]|\\(?:[nrt\\0'\"]|x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]{1,6}\}))'"
)

# Keyed on the checkout, as tests/test_distributions.py's guard is: a run from
# an unpacked sdist stands down, and inside a checkout a missing Cargo.lock or
# manifest is the fault, not a reason to skip.
pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / ".git").exists(),
    reason="not a repository checkout; this reads the workspace's Cargo.lock",
)

Node = tuple[str, str]  # a locked package: name and version


def _toml(path: Path) -> dict[str, Any]:
    """Return a TOML document, parsed."""
    document: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    return document


def _tables(manifest: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """Return every ``kind`` table a manifest holds, platform-specific ones too."""
    tables = [manifest.get(kind, {})]
    tables += [target.get(kind, {}) for target in manifest.get("target", {}).values()]
    return tables


def _package(key: str, spec: object) -> str:
    """Return the package a dependency entry names, renamed or not."""
    if isinstance(spec, dict) and "package" in spec:
        return str(spec["package"])
    return key


def _comment_end(source: str, at: int) -> int | None:
    """Return where a comment that starts at ``at`` ends, or None for no comment."""
    if source.startswith("//", at):
        end = source.find("\n", at)
        return len(source) if end == -1 else end
    if not source.startswith("/*", at):
        return None
    depth, at = 1, at + 2
    while at < len(source) and depth:
        if source.startswith("/*", at):
            depth, at = depth + 1, at + 2
        elif source.startswith("*/", at):
            depth, at = depth - 1, at + 2
        else:
            at += 1
    return at


def _literal_end(source: str, at: int) -> int | None:
    """Return where a literal that starts at ``at`` ends, or None for no literal."""
    if raw := RAW_STRING.match(source, at):
        end = source.find('"' + raw.group(1), raw.end())
        return len(source) if end == -1 else end + 1 + len(raw.group(1))
    if text := STRING.match(source, at):
        at = text.end()
        while at < len(source) and source[at] != '"':
            at += 2 if source[at] == "\\" else 1
        return at + 1
    if character := CHARACTER.match(source, at):
        return character.end()
    return None


def _code(source: str) -> str:
    """Return Rust source with its comments and literals blanked out.

    Line and block comments, doc comments among them, and nested block
    comments go; so do string, raw string, byte string and character literals.
    What is left is what the compiler reads as code.
    """
    code = []
    at = 0
    while at < len(source):
        end = _comment_end(source, at)
        if end is None:
            end = _literal_end(source, at)
        if end is None:
            code.append(source[at])
            at += 1
        else:
            code.append(" ")
            at = end
    return "".join(code)


def _unnamed_dependencies(crate: Path) -> set[str]:
    """Return the normal dependencies of ``crate`` that no code under src/ names.

    A dependency also declared for tests or build scripts is left out: the
    lockfile gives its edges no kind, so cutting one would cut the other.
    """
    manifest = _toml(crate / "Cargo.toml")
    other_kinds = {
        _package(key, spec)
        for kind in ("dev-dependencies", "build-dependencies")
        for table in _tables(manifest, kind)
        for key, spec in table.items()
    }
    sources = [
        _code(path.read_text(encoding="utf-8"))
        for path in sorted((crate / "src").rglob("*.rs"))
    ]
    unnamed = set()
    for table in _tables(manifest, "dependencies"):
        for key, spec in table.items():
            package = _package(key, spec)
            if package in other_kinds:
                continue
            name = re.escape(key.replace("-", "_"))
            named = re.compile(
                rf"\b{name}\s*::|\buse\s+(?:::)?{name}\b|\bextern\s+crate\s+{name}\b"
            )
            if not any(named.search(text) for text in sources):
                unnamed.add(package)
    return unnamed


def _lock() -> tuple[dict[Node, list[Node]], dict[str, Node]]:
    """Return the lockfile's dependency graph, and its first-party packages.

    A dependency is written ``name`` where the lockfile holds one version of
    it and ``name version`` where it holds several.
    """
    packages = _toml(REPO_ROOT / "Cargo.lock")["package"]
    versions: dict[str, list[str]] = {}
    for package in packages:
        versions.setdefault(package["name"], []).append(package["version"])

    def node(entry: str) -> Node:
        name, _, version = entry.partition(" ")
        return (name, version.split(" ")[0] if version else versions[name][0])

    graph = {
        (p["name"], p["version"]): [node(d) for d in p.get("dependencies", [])]
        for p in packages
    }
    # Workspace members are the packages with no source: no registry, no git.
    members = {
        p["name"]: (p["name"], p["version"]) for p in packages if "source" not in p
    }
    return graph, members


def _reached(
    graph: dict[Node, list[Node]], start: list[Node], cut: set[tuple[Node, str]]
) -> set[Node]:
    """Return every package reachable from ``start``, not crossing an edge in ``cut``.

    An edge in ``cut`` is a package and the name of a dependency it declares.
    """
    seen: set[Node] = set()
    stack = list(start)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack += [d for d in graph[current] if (current, d[0]) not in cut]
    return seen


def test_no_locked_crate_is_there_only_for_a_dependency_no_code_names() -> None:
    """Every crate in Cargo.lock is reached through a dependency some code uses."""
    members = [
        REPO_ROOT / member
        for member in _toml(REPO_ROOT / "Cargo.toml")["workspace"]["members"]
    ]
    graph, locked = _lock()
    unnamed = {
        (locked[_toml(crate / "Cargo.toml")["package"]["name"]], dependency): crate
        for crate in members
        for dependency in _unnamed_dependencies(crate)
    }
    roots = list(locked.values())
    stranded = _reached(graph, roots, set()) - _reached(graph, roots, set(unnamed))

    causes = []
    for (member, dependency), crate in sorted(unnamed.items()):
        targets = [d for d in graph[member] if d[0] == dependency]
        brought = sorted(_reached(graph, targets, set()) & stranded)
        if brought:
            names = ", ".join(f"{name} {version}" for name, version in brought)
            causes.append(
                f"{(crate / 'Cargo.toml').relative_to(REPO_ROOT)} declares "
                f"{dependency}, which no code under "
                f"{crate.relative_to(REPO_ROOT)}/src/ names, and Cargo.lock holds "
                f"{names} only for it"
            )
    assert not stranded, (
        "; ".join(causes) + ". The extension's build resolves each of them, and "
        "bindings/python/third-party-notices.txt lists each one it compiles. "
        "Remove the declaration, let cargo prune Cargo.lock (cargo update "
        "--workspace), then rewrite the notices: python3 scripts/rust_notices.py "
        "write."
    )


MANIFEST = """[package]
name = "demo"
version = "0.1.0"
edition = "2021"

[dependencies]
alpha = "1"
beta = "1"

[dev-dependencies]
gamma = "1"
"""


@pytest.mark.parametrize(
    ("files", "unnamed"),
    [
        # A comment naming both, which is all a once-tried dependency leaves.
        (
            {"src/lib.rs": "// alpha::Thing and beta::fmt were tried here once.\n"},
            {"alpha", "beta"},
        ),
        # Nested block comments and doc comments.
        (
            {"src/lib.rs": "/* alpha::A /* beta::B */ alpha::C */\n/// beta::D\n"},
            {"alpha", "beta"},
        ),
        # String literals, raw ones among them.
        (
            {
                "src/lib.rs": (
                    'const A: &str = "alpha::Thing";\n'
                    'const B: &str = r#"use beta::x; "quoted" "#;\n'
                )
            },
            {"alpha", "beta"},
        ),
        # Used only by a benchmark, a test and an example: none is linked.
        (
            {
                "src/lib.rs": "pub fn f() {}\n",
                "benches/b.rs": "use alpha::Thing;\n",
                "tests/t.rs": "use beta::Other;\n",
                "examples/e.rs": "fn main() { alpha::run(); }\n",
            },
            {"alpha", "beta"},
        ),
        # Used by the library, past a lifetime and a character literal; the
        # dev-dependency is used where it may be.
        (
            {
                "src/lib.rs": (
                    "use alpha::Thing;\n"
                    "fn f<'a>(x: &'a str) -> char { beta::y(x); 'a' }\n"
                ),
                "benches/b.rs": "use gamma::Bench;\n",
            },
            set(),
        ),
    ],
)
def test_only_code_under_src_names_a_normal_dependency(
    tmp_path: Path, files: dict[str, str], unnamed: set[str]
) -> None:
    """A comment, a string, a test or a benchmark does not count as a use."""
    (tmp_path / "Cargo.toml").write_text(MANIFEST, encoding="utf-8")
    for relative, text in files.items():
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(text, encoding="utf-8")
    assert _unnamed_dependencies(tmp_path) == unnamed
