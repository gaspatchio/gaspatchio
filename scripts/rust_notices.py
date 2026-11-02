# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The notices of the Rust crates compiled into gaspatchio's extension.

``gaspatchio._internal`` is compiled from this repository's two crates, a few
hundred others and the Rust standard library, most of them MIT, which asks
that every copy carry the crate's copyright notice.
``bindings/python/third-party-notices.txt`` carries them, in every wheel and
in the sdist: ``license-files`` in ``bindings/python/pyproject.toml`` names
it. This script writes that file and holds it to what the extension is built
from::

    python3 scripts/rust_notices.py write   # rewrite it from Cargo.lock
    python3 scripts/rust_notices.py check   # hold it to what the build uses

Both run on any Python from 3.11, for ``tomllib``: CI's ``python3``, or
``bindings/python/.venv/bin/python`` at a keyboard.

**What the extension is built from** is cargo's own answer, not a list kept
here: ``cargo tree --edges normal,no-proc-macro --target T`` from
``gaspatchio_core_python``, for each platform ``about.toml`` names: the four
the wheels are built for, and the two arm64 platforms pip builds the sdist
on. That is the resolver ``cargo build`` uses,
features and platform conditions included, and a build compiles exactly those
crates for the target. Normal dependencies only: a build script, a procedural
macro and what either depends on runs while the extension compiles and is not
linked into it, and dev-dependencies are tests'. The linker then leaves out
the few crates no code calls -- a dependency declared and never used -- and
those are listed anyway, so the list covers what is linked with a little to
spare. This repository's own two crates are not third parties and are not
listed. The Rust standard library is linked too, and is the toolchain's, not
Cargo.lock's: the file gives it a section of its own, ``STANDARD_LIBRARY``.

**The licence texts** come from cargo-about, at exactly the version
``CARGO_ABOUT`` names, configured by ``about.toml``: which licence a crate is
taken under when it offers a choice, and, crate by crate, where a crate's
texts are when cargo-about cannot find them itself. Each crate's texts are
carried as it ships them; a crate that ships none for its licence cites the
licence's standard text, from ``LICENSES/``, and the file ends with that text
for every licence it names. A crate taken under Apache-2.0 has its NOTICE
file carried too, as section 4(d) of that licence asks. A notice written out
at the head of a compiled source file, under a copyright the crate's own
licence files do not name, is carried by a clarification in ``about.toml``
too. cargo-about reads the crates a procedural macro reaches as well; what it
says about them is not written.

``write`` needs cargo, cargo-about ``CARGO_ABOUT`` on ``PATH``, and the
network: crates.io, and GitHub for the three texts ``about.toml`` reads from
the Polars repository. It refuses to write while cargo-about warns about
anything -- a clarification whose file no longer matches its checksum, say --
so a notice cannot quietly fall back to a standard text.

``check`` needs cargo and not cargo-about, and nothing from the network once
cargo has the crates (``CARGO_NET_OFFLINE=true``). It reads the file as
committed and fails, naming each, on:

* a crate the extension is built from that the file does not list, a crate
  it lists that the extension is not built from, a platform note that is
  wrong, or a reference to a text that is not there;
* a licence file below one of those crates' roots that the file neither
  carries nor explains in ``VENDORED``. cargo-about reads a crate's root and
  nothing below it (``max-depth`` in ``about.toml``), and a crate that
  compiles someone else's C library, as ``zstd-sys`` does, usually keeps
  that library's licence below its root and does not declare it;
* a notice written out in a file below a crate's root -- a licence's
  permission text after a copyright line -- whose holder and year the
  carried texts do not name, unless the holder is the crate's own, named in
  its root licence files, or ``EMBEDDED_WAIVED`` says why;
* a licence-named file at a crate's root that is not carried, is not the
  text of a licence the crate offers and is not taken under, and holds a
  dated copyright line: a notice cargo-about did not read as a licence,
  unless ``ROOT_WAIVED`` says why;
* a crate that cites a licence's standard text while it ships a
  licence-named file at its root, unless ``STANDARD_TEXT`` says why. That is
  what a licence file cargo-about can no longer read looks like: it falls
  back to the standard text without a word, and the crate's own copyright
  line goes missing;
* an entry in any of those tables that no longer matches anything.

CI runs both (``CI.yml``, the Rust Crate Notices job): ``check``, then
``write`` and a comparison with the committed file.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "bindings" / "python" / "Cargo.toml"
PACKAGE = "gaspatchio_core_python"
CONFIG = REPO_ROOT / "about.toml"
LICENSES = REPO_ROOT / "LICENSES"
NOTICES = REPO_ROOT / "bindings" / "python" / "third-party-notices.txt"

# The one version of cargo-about this file is written by. CI.yml installs it
# from the crate archive, checked against the SHA-256 it records beside the
# same number; moving one moves both.
CARGO_ABOUT = "0.9.2"

# The platforms the wheels are built for, which about.toml must name; the
# others it names are where pip builds the sdist.
WHEELS = (
    "x86_64-unknown-linux-gnu",
    "x86_64-apple-darwin",
    "aarch64-apple-darwin",
    "x86_64-pc-windows-msvc",
)

WIDTH = 78
RULE = "=" * WIDTH
THIN = "-" * WIDTH
INDEX_HEADING = "The crates"
STANDARD_HEADING = "The Rust standard library"
SEPARATOR = " -- "
# An index line: name and version, what it declares, what it is taken under
# with the texts that carry it, and, where not every platform uses it, which do.
INDEX_FIELDS = (3, 4)

# A licence file below a crate's root that the notices do not carry, and why
# it need not be. Keyed by crate name and the file's path under the crate's
# root. `check` fails on any such file that is not here, and on an entry here
# that names a file no crate the extension is built from ships.
VENDORED: dict[tuple[str, str], str] = {
    ("chrono-tz", "tz/LICENSE"): (
        "the time zone database's statement that it is in the public domain, "
        "which chrono-tz's own LICENSE, carried, repeats"
    ),
    ("lz4-sys", "liblz4/LICENSE"): (
        "says which of LZ4's directories is under which licence: liblz4/lib, "
        "which the build script compiles, is BSD-2-Clause and its LICENSE is "
        "carried; the rest is not compiled"
    ),
    ("lz4-sys", "liblz4/contrib/debian/copyright"): (
        "Debian packaging for LZ4's programs, which are not compiled"
    ),
    ("lz4-sys", "liblz4/contrib/djgpp/LICENSE"): (
        "a DJGPP build for LZ4's programs, which is not compiled"
    ),
    ("lz4-sys", "liblz4/examples/COPYING"): "LZ4's examples, which are not compiled",
    ("lz4-sys", "liblz4/programs/COPYING"): (
        "LZ4's command-line programs, which are not compiled"
    ),
    ("lz4-sys", "liblz4/tests/COPYING"): "LZ4's tests, which are not compiled",
    ("pyo3", "pyo3-runtime/LICENSE-APACHE"): (
        "the source of the pyo3-runtime Python package, which is not compiled "
        "into the extension"
    ),
    ("ring", "src/polyfill/once_cell/LICENSE-APACHE"): (
        "once_cell's code in ring is MIT OR Apache-2.0 and ring is taken under "
        "Apache-2.0, whose text is carried"
    ),
    ("ring", "src/polyfill/once_cell/LICENSE-MIT"): (
        "once_cell's code in ring is MIT OR Apache-2.0 and ring is taken under "
        "Apache-2.0, whose text is carried"
    ),
    ("zstd-sys", "zstd/COPYING"): (
        "Zstandard is BSD-3-Clause or GPL-2.0-only and is taken under "
        "BSD-3-Clause, whose text is carried"
    ),
}

# Crates that may cite a licence's standard text although they ship a
# licence-named file at their root, because that file holds no text for the
# licence the standard one stands in for.
STANDARD_TEXT: dict[str, str] = {
    "brotli": (
        "BSD-3-Clause AND MIT: it ships LICENSE.MIT, which is carried, and no "
        "BSD-3-Clause text, so the standard one stands for that half"
    ),
}

# A licence-named file at a crate's root that is not carried, although it holds
# a dated copyright line and is not the text of a licence the crate offers and
# is not taken under, and why it need not be carried.
ROOT_WAIVED: dict[tuple[str, str], str] = {
    ("crossbeam-channel", "LICENSE-THIRD-PARTY"): (
        "the licences of the code in examples/matching.rs, tests/golang.rs and "
        "tests/mpsc.rs, none of which the library compiles"
    ),
    ("streaming-decompression", "LICENSE-MIT"): (
        "the crate declares Apache-2.0 and is taken under it; this is the MIT "
        "text its README offers beside it"
    ),
}

# A licence written out in a file below a crate's root, under a copyright the
# crate's own licence files do not name, that the notices do not carry, and
# why they need not.
EMBEDDED_WAIVED: dict[tuple[str, str], str] = {
    ("lz4-sys", "liblz4/contrib/gen_manual/Makefile"): (
        "LZ4's manual generator, which is not compiled"
    ),
    ("lz4-sys", "liblz4/contrib/gen_manual/gen_manual.cpp"): (
        "LZ4's manual generator, which is not compiled"
    ),
    ("lz4-sys", "liblz4/lib/lz4file.c"): (
        "not compiled: the build script compiles lz4.c, lz4frame.c, lz4hc.c and "
        "xxhash.c from liblz4/lib"
    ),
    ("lz4-sys", "liblz4/lib/lz4file.h"): (
        "not compiled: the build script compiles lz4.c, lz4frame.c, lz4hc.c and "
        "xxhash.c from liblz4/lib"
    ),
    ("lz4-sys", "src/wasm_shim.rs"): "compiled for wasm32 only",
    ("ndarray", "src/doc/ndarray_for_numpy_users/rk_step.rs"): (
        "part of ndarray's documentation pages, compiled only under docsrs"
    ),
    ("uuid", "src/rng.rs"): (
        "the notice is getrandom's, over the code in mod webcrypto, which is "
        "compiled for wasm32 with the js feature only"
    ),
}

# Directories below a crate's root that hold nothing the library compiles.
NOT_COMPILED = {
    "tests",
    "test",
    "benches",
    "bench",
    "examples",
    "fuzz",
    ".github",
    "ci",
    "testdata",
    "test-data",
}

# The sentences a licence grants and conditions with: a notice in a source
# file is one of these after its copyright line.
GRANT = re.compile(
    r"permission is hereby granted,? free of charge"
    r"|permission to use, copy, modify,? (?:and/or|and) distribute"
    r"|redistribution and use in source and binary forms"
    r"|altered source versions must be plainly marked"
    r"|unicode,? inc\.? license agreement",
    re.IGNORECASE,
)
COPYRIGHT_LINE = re.compile(r"(?:\bcopyright\b|©)[^\n]*", re.IGNORECASE)
NOT_A_NOTICE = re.compile(
    r"copyright (?:owner|holder|notice|and|license|law|convention|statement)"
    r"|\[yyyy\]|<year>",
    re.IGNORECASE,
)
# A year, or a range of them, as a copyright line gives it. The range's dash
# may be a hyphen or an en dash (U+2013).
YEARS = re.compile(
    r"\b((?:19|20)\d{2})(?:\s*[-\u2013]\s*((?:19|20)\d{2}|present))?",
    re.IGNORECASE,
)
NOT_A_HOLDER = {
    "the",
    "inc",
    "ltd",
    "llc",
    "co",
    "corp",
    "affiliates",
    "all",
    "rights",
    "reserved",
    "portions",
    "et",
    "al",
    "by",
    "of",
    "present",
    "copyright",
}
# How a root file's name says which licence's text it is. A name with LLVM in
# it is the Apache-2.0 text with the LLVM exception, which an expression names
# as LLVM-exception.
NAMED_LICENCE = {
    "apache": "Apache-2.0",
    "a2": "Apache-2.0",
    "a2llvm": "LLVM-exception",
    "llvm": "LLVM-exception",
    "mit": "MIT",
    "mit0": "MIT-0",
    "boost": "BSL-1.0",
    "bsl": "BSL-1.0",
    "cc0": "CC0-1.0",
    "unlicense": "Unlicense",
    "zlib": "Zlib",
    "0bsd": "0BSD",
    "isc": "ISC",
    "bsd": "BSD",
}

# The Rust project's MIT permission notice, the words after its copyright line
# at rust-lang/rust's LICENSE-MIT, which the standard library section cites.
# SHA-256 of the words, joined by single spaces.
RUST_MIT_WORDS = "fe2a9817987f862eaced948f0468c7f51d2fedfc48c5c505b246a49a3870e9a5"

# The standard library, as Rust 1.94.0 links it into the extension (its link
# line, on x86_64-apple-darwin), and each crate's copyright line from the MIT
# text it ships, at the version library/Cargo.lock pins. Every one offers MIT.
STANDARD_LIBRARY = (
    "The extension also links the standard library of the Rust toolchain that "
    "builds it, which Cargo.lock does not name. As Rust 1.94 links it, that is "
    "std, core and alloc, with std_detect, panic_unwind, unwind, "
    "compiler_builtins and two shims that re-export core and alloc, Copyright "
    "(c) The Rust Project Contributors; and the crates std is built from, each "
    "under its own copyright line: addr2line, Copyright (c) 2016-2018 The gimli "
    "Developers; adler2, which has none; cfg-if and rustc-demangle, Copyright "
    "(c) 2014 Alex Crichton; gimli, Copyright (c) 2015 The Rust Project "
    "Developers; hashbrown, Copyright (c) 2016 Amanieu d'Antras; libc, "
    "Copyright (c) 2014-2020 The Rust Project Developers; memchr, Copyright (c) "
    "2015 Andrew Gallant; miniz_oxide, Copyright 2013-2014 RAD Game Tools and "
    "Valve Software and Copyright 2010-2014 Rich Geldreich and Tenacious "
    "Software LLC; and object, Copyright (c) 2015 The Gimli Developers. Each "
    "offers MIT among its licences and is taken under it here; the permission "
    "notice after each copyright line is the MIT licence's, in the words of "
    "[{rust_mit}]. compiler_builtins also carries code from LLVM's compiler-rt "
    "under Apache-2.0 WITH LLVM-exception, whose exception asks nothing of code "
    "compiled into a program. A wheel built by another Rust release links that "
    "release's library, which can differ by a crate or a version."
)

# A file whose name says it is a licence or a notice: the pattern
# viewer/bundle.mjs reads a package's licence files by, widened to the names
# vendored C libraries use.
LICENCE_FILE = re.compile(
    r"^(licen[cs]e|copying|copyright|notice|unlicen[cs]e)([-._].*)?$", re.IGNORECASE
)
NOTICE_FILE = re.compile(r"^notice([-._].*)?$", re.IGNORECASE)
# cargo-about colours its log lines whatever --color says.
ANSI = re.compile(r"\x1b\[[0-9;]*m")
REF = re.compile(r"\[(\d+)\]")
TITLE = re.compile(r"^\[(\d+)\] (\S+?)(,.*)?$")


class NoticesError(RuntimeError):
    """The notices cannot be written, or do not hold."""


@dataclass(frozen=True, order=True)
class Crate:
    """One crate, by name and version."""

    name: str
    version: str

    def __str__(self) -> str:
        """Return the crate as the notices name it: ``name version``."""
        return f"{self.name} {self.version}"


@dataclass
class Text:
    """One text the notices carry, and the crates it is carried for."""

    licence: str  # an SPDX identifier, or "NOTICE"
    text: str
    source: str  # where it came from, in words
    crates: set[Crate] = field(default_factory=set)
    standard: bool = False


@dataclass
class Listed:
    """What the committed file says about one crate."""

    declared: str
    under: list[str]
    refs: list[int]
    platforms: list[str] | None  # None: every platform


# ---------------------------------------------------------------------------
# cargo


def _run(command: list[str]) -> str:
    """Run ``command`` from the repository root and return what it printed."""
    result = subprocess.run(  # noqa: S603
        command, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        message = f"{' '.join(command)} exited {result.returncode}:\n{result.stderr}"
        raise NoticesError(message)
    return result.stdout


def _config() -> dict:
    """Return ``about.toml``."""
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def targets() -> list[str]:
    """Return the platforms the notices cover, as ``about.toml`` names them."""
    named = list(_config()["targets"])
    missing = [target for target in WHEELS if target not in named]
    if missing:
        message = (
            f"about.toml's targets leave out {missing}, which the wheels are built for"
        )
        raise NoticesError(message)
    return named


def metadata() -> dict:
    """Return ``cargo metadata`` for the workspace, every package resolved."""
    command = ["cargo", "metadata", "--locked", "--format-version", "1"]
    return json.loads(_run([*command, "--manifest-path", str(MANIFEST)]))


def built_from(workspace: set[str]) -> dict[Crate, set[str]]:
    """Return every third-party crate the extension is built from, and where."""
    found: dict[Crate, set[str]] = {}
    for target in targets():
        tree = _run(
            [
                "cargo",
                "tree",
                "--locked",
                "--manifest-path",
                str(MANIFEST),
                "--package",
                PACKAGE,
                "--target",
                target,
                "--edges",
                "normal,no-proc-macro",
                "--prefix",
                "none",
                "--format",
                "{p}",
            ]
        )
        for line in filter(str.strip, tree.splitlines()):
            name, version = line.split(" ")[:2]
            if name not in workspace:
                crate = Crate(name, version.removeprefix("v"))
                found.setdefault(crate, set()).add(target)
    if not found:
        message = "cargo tree listed no crate the extension is built from"
        raise NoticesError(message)
    return found


def _roots(meta: dict) -> dict[Crate, Path]:
    """Return each resolved package's root directory."""
    return {
        Crate(p["name"], p["version"]): Path(p["manifest_path"]).parent
        for p in meta["packages"]
    }


def _workspace(meta: dict) -> set[str]:
    """Return the names of this repository's own crates."""
    members = set(meta["workspace_members"])
    return {p["name"] for p in meta["packages"] if p["id"] in members}


# ---------------------------------------------------------------------------
# Texts


def _normal(text: str) -> str:
    """Return ``text`` as the notices carry it: LF line ends, nothing trailing."""
    return text.removeprefix("﻿").replace("\r\n", "\n").rstrip()


def _version_key(crate: Crate) -> tuple:
    """Sort by name, then by version as numbers where they are numbers."""
    parts = re.split(r"[.+-]", crate.version)
    numbered = [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in parts]
    return (crate.name, numbered)


def _order(licence: str, accepted: list[str]) -> tuple[int, str]:
    """Return where ``licence`` sorts: accepted order first, then by name."""
    if licence in accepted:
        return (accepted.index(licence), licence)
    return (len(accepted), licence)


def _cargo_about() -> dict:
    """Run cargo-about over the extension's crate and return what it found."""
    executable = shutil.which("cargo-about")
    if executable is None:
        message = (
            f"cargo-about is not on PATH. Install exactly {CARGO_ABOUT}, as CI.yml "
            "does: the notices are written by one version of it."
        )
        raise NoticesError(message)
    version = _run([executable, "--version"]).split()
    if version[-1:] != [CARGO_ABOUT]:
        message = f"cargo-about is {' '.join(version)}; the notices want {CARGO_ABOUT}"
        raise NoticesError(message)
    command = [
        executable,
        "--color",
        "never",
        "generate",
        "--locked",
        "--fail",
        "--config",
        str(CONFIG),
        "--manifest-path",
        str(MANIFEST),
        "--format",
        "json",
    ]
    result = subprocess.run(  # noqa: S603
        command, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    said = [ANSI.sub("", line) for line in result.stderr.splitlines() if line.strip()]
    if result.returncode != 0 or said:
        # Anything it says is a warning at least: a clarification whose file
        # stopped matching its checksum is one, and a notice written past it
        # would be a standard text standing in for the crate's own.
        message = "cargo-about did not finish cleanly:\n" + "\n".join(said)
        raise NoticesError(message)
    return json.loads(result.stdout)


def _source(path: str, body: str, first: Crate, roots: dict[Crate, Path]) -> str:
    """Say where one text came from, without a path on this machine.

    cargo-about gives a file it found by its absolute path, and a file a
    clarification names by the path the clarification gives, relative to the
    crate's root for a file the crate ships and to its repository's root for
    one read from the repository. The two relative kinds are told apart by
    whether the crate holds the text at that path.
    """
    root = roots[first]
    shipped = Path(path)
    if shipped.is_absolute():
        try:
            relative = shipped.relative_to(root).as_posix()
        except ValueError:
            relative = shipped.name
        return f"{first}'s {relative}"
    local = root / shipped
    if local.is_file():
        whole = _normal(local.read_text(encoding="utf-8"))
        if body == whole:
            return f"{first}'s {shipped.as_posix()}"
        if body in whole:
            return f"{first}'s {shipped.as_posix()}, the notice at its head"
    return (
        f"{first}'s repository, its {shipped.as_posix()} at the commit the crate "
        "was published from, which the crate points at and does not ship"
    )


def _shipped_texts(
    about: dict, found: dict[Crate, set[str]], roots: dict[Crate, Path]
) -> tuple[dict[tuple[str, str], Text], dict[str, set[Crate]]]:
    """Return the texts the crates ship, and who cites which standard text.

    One text for each licence and wording, however many crates ship it. Its
    source is said as the first of those crates ships it, whichever of
    cargo-about's entries that crate arrived in.
    """
    shipped: dict[tuple[str, str], dict[Crate, str]] = {}
    standard: dict[str, set[Crate]] = {}
    for entry in about["licenses"]:
        users = {
            Crate(used["crate"]["name"], used["crate"]["version"])
            for used in entry["used_by"]
        } & set(found)
        if not users:
            continue
        if entry["source_path"] is None:
            standard.setdefault(entry["id"], set()).update(users)
            continue
        paths = shipped.setdefault((entry["id"], _normal(entry["text"])), {})
        for crate in users:
            paths.setdefault(crate, entry["source_path"])
    texts = {}
    for (licence, body), paths in shipped.items():
        first = min(paths, key=_version_key)
        source = _source(paths[first], body, first, roots)
        texts[(licence, body)] = Text(licence, body, source, set(paths))
    return texts, standard


def _taken_under(
    texts: dict[tuple[str, str], Text], standard: dict[str, set[Crate]]
) -> dict[Crate, set[str]]:
    """Return the licences each crate is taken under."""
    under: dict[Crate, set[str]] = {}
    for text in texts.values():
        for crate in text.crates:
            under.setdefault(crate, set()).add(text.licence)
    for licence, crates in standard.items():
        for crate in crates:
            under.setdefault(crate, set()).add(licence)
    return under


def _notice_files(
    under: dict[Crate, set[str]], roots: dict[Crate, Path]
) -> dict[tuple[str, str], Text]:
    """Return the NOTICE files of the crates taken under Apache-2.0 (its 4(d))."""
    notices: dict[tuple[str, str], Text] = {}
    for crate in sorted(under, key=_version_key):
        if "Apache-2.0" not in under[crate]:
            continue
        for path in sorted(roots[crate].iterdir()):
            if path.is_file() and NOTICE_FILE.match(path.name):
                body = _normal(path.read_text(encoding="utf-8"))
                source = f"{crate}'s {path.name}"
                text = notices.setdefault(
                    ("NOTICE", body), Text("NOTICE", body, source)
                )
                text.crates.add(crate)
    return notices


def _standard_texts(
    under: dict[Crate, set[str]], standard: dict[str, set[Crate]], accepted: list[str]
) -> list[Text]:
    """Return each named licence's standard text, from ``LICENSES/``."""
    named = {licence for licences in under.values() for licence in licences}
    texts = []
    for licence in sorted(named, key=lambda lic: _order(lic, accepted)):
        path = LICENSES / f"{licence}.txt"
        if not path.is_file():
            message = (
                f"a crate is taken under {licence} and LICENSES/ holds no text for "
                f"it. Add LICENSES/{licence}.txt (reuse download {licence})."
            )
            raise NoticesError(message)
        body = _normal(path.read_text(encoding="utf-8"))
        source = (
            f"the licence's standard text, LICENSES/{licence}.txt in this repository"
        )
        cited = standard.get(licence, set())
        texts.append(Text(licence, body, source, cited, standard=True))
    return texts


def gather(
    meta: dict, found: dict[Crate, set[str]]
) -> tuple[list[Text], dict[Crate, str]]:
    """Return the texts the crates are carried under, and what each declares."""
    accepted = list(_config()["accepted"])
    roots = _roots(meta)
    about = _cargo_about()

    declared = {
        Crate(entry["package"]["name"], entry["package"]["version"]): (
            entry["package"].get("license") or "(none declared)"
        )
        for entry in about["crates"]
    }
    missing = sorted(set(found) - set(declared), key=_version_key)
    if missing:
        names = ", ".join(str(c) for c in missing)
        message = f"cargo-about read no licence for {names}, which the extension uses"
        raise NoticesError(message)

    texts, standard = _shipped_texts(about, found, roots)
    under = _taken_under(texts, standard)
    everything = [
        *texts.values(),
        *_notice_files(under, roots).values(),
        *_standard_texts(under, standard, accepted),
    ]
    ordered = sorted(
        everything,
        key=lambda t: (
            2 if t.standard else (1 if t.licence == "NOTICE" else 0),
            _order(t.licence, accepted),
            _version_key(min(t.crates, key=_version_key)) if t.crates else ("", []),
            t.text,
        ),
    )
    return ordered, {crate: declared[crate] for crate in found}


# ---------------------------------------------------------------------------
# The file


def _wrapped(label: str, pieces: list[str]) -> list[str]:
    """Return ``label`` and ``pieces``, space-separated, wrapped at WIDTH.

    A piece is never broken: one longer than a line has a line to itself.
    """
    indent = " " * len(label)
    lines: list[str] = []
    line = label
    started = False
    for piece in pieces:
        if started and len(line) + 1 + len(piece) > WIDTH:
            lines.append(line)
            line = indent
        line = f"{line} {piece}"
        started = True
    lines.append(line)
    return lines


def _listed(crates: list[str]) -> list[str]:
    """Return crate names as pieces of a comma-separated list."""
    return [c + ("," if i < len(crates) - 1 else "") for i, c in enumerate(crates)]


def _header(count: int, shipped: int, accepted: list[str]) -> str:
    """Return what the file says before its index: what it is, and how made."""
    every = targets()
    wheels = ", ".join(WHEELS[:-1]) + f" and {WHEELS[-1]}"
    others = [target for target in every if target not in WHEELS]
    sdist = (
        f", and on {' and '.join(others)}, where pip builds the sdist for want "
        "of a wheel"
        if others
        else ""
    )
    paragraphs = [
        "Third-party software in gaspatchio's compiled extension",
        (
            "gaspatchio._internal, the extension module every gaspatchio wheel "
            "carries, is compiled from this repository's two Rust crates, from "
            f"the {count} crates below and from the Rust standard library. The "
            "first are Opio Inc.'s work; this file carries the notices of the "
            "rest. The crates are every crate Cargo.lock resolves as "
            "a normal dependency of bindings/python on the platforms the wheels "
            f"are built for, {wheels}{sdist}. A crate that only some of those "
            "platforms use is listed once and says so. A few are compiled and "
            "then left out by the linker, because no code calls them; they are "
            "listed all the same. Crates used only while the extension is built "
            "are not in it and are not listed: build scripts, procedural macros "
            "and what either uses, and the dependencies of tests. The standard "
            "library, which the Rust toolchain supplies rather than Cargo.lock, "
            "has a section of its own after the crates."
        ),
        (
            "Each crate is listed with the licence it declares and the licence it "
            "is taken under here: where it offers a choice, the first of "
            f"{', '.join(accepted)} that it offers, unless about.toml says "
            f"otherwise and why. The numbers are the texts that follow: {shipped} "
            "as the crates ship them, each with the crates it is carried for, then "
            "each licence's standard text. A crate that ships no text of its own "
            "for its licence cites the standard one. Where a crate's sources "
            "carry a notice of their own, a licence written out at the head of a "
            "file under a copyright the crate's licence files do not name, that "
            "notice is carried beside the crate's."
        ),
        (
            "The Level 4 tutorial's data, which the wheel also carries, derives "
            "from lifelib, under MIT; its attribution is in NOTICE, beside this "
            "file."
        ),
        (
            "Written by scripts/rust_notices.py from Cargo.lock, with cargo-about "
            f"{CARGO_ABOUT} configured by about.toml; edits here are lost."
        ),
    ]
    return "\n\n".join(_fill(p) for p in paragraphs) + "\n"


def _fill(paragraph: str) -> str:
    """Return a paragraph wrapped at WIDTH, never inside a name or a triple."""
    return textwrap.fill(
        paragraph, WIDTH, break_on_hyphens=False, break_long_words=False
    )


def _words(text: str) -> str:
    """Return the SHA-256 of a text's words, joined by single spaces."""
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


def _standard_library(texts: list[Text]) -> str:
    """Return the section on the Rust standard library, which cites a text above."""
    cited = [
        n
        for n, text in enumerate(texts, start=1)
        if not text.standard and _words(text.text) == RUST_MIT_WORDS
    ]
    if not cited:
        message = (
            "no text the notices carry is the Rust project's MIT permission "
            "notice, which the standard library's section cites; carry it"
        )
        raise NoticesError(message)
    body = _fill(STANDARD_LIBRARY.format(rust_mit=cited[0]))
    return f"{RULE}\n{STANDARD_HEADING}\n{THIN}\n\n{body}\n\n"


def _index(
    texts: list[Text],
    declared: dict[Crate, str],
    found: dict[Crate, set[str]],
    accepted: list[str],
) -> list[str]:
    """Return one line for each crate, in name order."""
    every = targets()
    refs: dict[Crate, list[int]] = {}
    under: dict[Crate, set[str]] = {}
    for n, text in enumerate(texts, start=1):
        for crate in text.crates:
            refs.setdefault(crate, []).append(n)
            if text.licence != "NOTICE":
                under.setdefault(crate, set()).add(text.licence)
    lines = []
    for crate in sorted(found, key=_version_key):
        order = sorted(under[crate], key=lambda lic: _order(lic, accepted))
        cited = ", ".join(f"[{n}]" for n in sorted(refs[crate]))
        line = f"{crate}{SEPARATOR}{declared[crate]}{SEPARATOR}{' and '.join(order)}"
        line += f" {cited}"
        platforms = [t for t in every if t in found[crate]]
        if platforms != every:
            line += f"{SEPARATOR}{' and '.join(platforms)} only"
        lines.append(line)
    return lines


def _block(n: int, text: Text) -> str:
    """Return one text as the file carries it, under its number and its users."""
    if text.licence == "NOTICE":
        title = f"[{n}] NOTICE"
    else:
        title = f"[{n}] {text.licence}{', standard text' if text.standard else ''}"
    users = [str(c) for c in sorted(text.crates, key=_version_key)]
    head = [RULE, title]
    if not text.standard:
        head += _wrapped("Used by:", _listed(users))
    elif users:
        head += _wrapped("Cited by:", _listed(users))
    head += _wrapped("Text:", text.source.split(" "))
    return "\n".join([*head, THIN, "", text.text, ""])


def render(
    texts: list[Text],
    declared: dict[Crate, str],
    found: dict[Crate, set[str]],
    accepted: list[str],
) -> str:
    """Return the notices file."""
    shipped = sum(1 for text in texts if not text.standard)
    columns = (
        "name version -- the licence it declares -- the licence it is taken under,\n"
        "and the texts that carry it -- the platforms that use it, where not all do"
    )
    return (
        f"{_header(len(found), shipped, accepted)}\n"
        f"{RULE}\n{INDEX_HEADING}\n{THIN}\n{columns}\n{THIN}\n"
        + "\n".join(_index(texts, declared, found, accepted))
        + "\n\n"
        + _standard_library(texts)
        + "\n".join(_block(n, text) for n, text in enumerate(texts, start=1))
    )


# ---------------------------------------------------------------------------
# Reading the file back


def read(text: str) -> tuple[dict[Crate, Listed], dict[int, tuple[str, bool]]]:
    """Return the crates the notices list, and each text by number.

    A text is its licence, and whether it is that licence's standard text.
    """
    lines = text.split("\n")
    try:
        at = lines.index(INDEX_HEADING) + 1
    except ValueError as missing:
        message = f"the notices have no {INDEX_HEADING!r} section"
        raise NoticesError(message) from missing
    # The heading's rule, the column description, and the rule under it.
    at = lines.index(THIN, lines.index(THIN, at) + 1) + 1
    listed: dict[Crate, Listed] = {}
    while at < len(lines) and lines[at]:
        parts = lines[at].split(SEPARATOR)
        if len(parts) not in INDEX_FIELDS:
            message = f"cannot read the notices' line {at + 1}: {lines[at]!r}"
            raise NoticesError(message)
        name, _, version = parts[0].partition(" ")
        licences, _, cited = parts[2].partition(" [")
        platforms = parts[3].removesuffix(" only").split(" and ") if parts[3:] else None
        listed[Crate(name, version)] = Listed(
            declared=parts[1],
            under=licences.split(" and "),
            refs=[int(n) for n in REF.findall("[" + cited)],
            platforms=platforms,
        )
        at += 1
    numbered = {
        int(match.group(1)): (match.group(2), match.group(3) == ", standard text")
        for before, line in itertools.pairwise(lines)
        if before == RULE and (match := TITLE.match(line))
    }
    return listed, numbered


def licences_named(text: str) -> set[str]:
    """Return every licence the notices take a crate under."""
    listed, _ = read(text)
    return {licence for entry in listed.values() for licence in entry.under}


# ---------------------------------------------------------------------------
# The two commands


def write() -> int:
    """Rewrite the notices from Cargo.lock."""
    meta = metadata()
    found = built_from(_workspace(meta))
    texts, declared = gather(meta, found)
    accepted = list(_config()["accepted"])
    NOTICES.write_text(render(texts, declared, found, accepted), encoding="utf-8")
    print(  # noqa: T201
        f"{NOTICES.relative_to(REPO_ROOT)}: {len(found)} crates, {len(texts)} texts, "
        f"{NOTICES.stat().st_size} bytes"
    )
    return 0


def _listing_problems(
    found: dict[Crate, set[str]],
    listed: dict[Crate, Listed],
    numbered: dict[int, tuple[str, bool]],
) -> list[str]:
    """Return how the file's list differs from what the extension is built from."""
    every = targets()
    problems = [
        f"{crate} is built into the extension and the notices do not list it"
        for crate in sorted(set(found) - set(listed), key=_version_key)
    ]
    problems += [
        f"{crate} is listed and the extension is not built from it"
        for crate in sorted(set(listed) - set(found), key=_version_key)
    ]
    for crate in sorted(set(found) & set(listed), key=_version_key):
        entry = listed[crate]
        used_on = [t for t in every if t in found[crate]]
        said = entry.platforms or every
        if said != used_on:
            problems.append(
                f"{crate}: the notices say it is built for {', '.join(said)}; "
                f"cargo says {', '.join(used_on)}"
            )
        if not entry.refs:
            problems.append(f"{crate} cites no text")
        problems += [
            f"{crate} cites text [{n}], which the notices do not hold"
            for n in entry.refs
            if n not in numbered
        ]
    return problems


def _vendored_problems(
    found: dict[Crate, set[str]], roots: dict[Crate, Path], carried: str
) -> list[str]:
    """Return each licence file below a crate's root, not carried and not explained."""
    problems = []
    seen: set[tuple[str, str]] = set()
    for crate in sorted(found, key=_version_key):
        root = roots[crate]
        for folder, dirs, files in os.walk(root):
            dirs.sort()
            if Path(folder) == root:
                continue  # cargo-about's to read, at the root
            for name in sorted(filter(LICENCE_FILE.match, files)):
                relative = (Path(folder) / name).relative_to(root).as_posix()
                seen.add((crate.name, relative))
                if (crate.name, relative) in VENDORED:
                    continue
                try:
                    body = _normal((Path(folder) / name).read_text(encoding="utf-8"))
                except UnicodeDecodeError:
                    body = ""
                if body and body in carried:
                    continue
                problems.append(
                    f"{crate} ships {relative}, below its root, and the notices "
                    "neither carry it nor say why not. If the build compiles the "
                    "code it covers, clarify the crate in about.toml; if not, add "
                    "it to VENDORED in scripts/rust_notices.py with the reason."
                )
    problems += [
        f"VENDORED names {name}'s {path}, and no crate the extension is built from "
        "ships it; remove the entry"
        for name, path in sorted(set(VENDORED) - seen)
    ]
    return problems


def _holders(line: str) -> list[tuple[str, ...]]:
    """Return the holders one copyright line names, each by its first two words."""
    text = re.sub(r"(?i)\bcopyright\b|\(c\)|©|all rights reserved|et al\.?", " ", line)
    text = re.sub(r"<[^>]*>|https?://\S+", " ", YEARS.sub(" ", text))
    holders = []
    for part in re.split(r",|;|&|\band\b", text, flags=re.IGNORECASE):
        words = [
            word
            for word in re.findall(r"[a-z0-9']+", part.lower())
            if len(word) > 1 and word not in NOT_A_HOLDER
        ]
        if words and words[0][0].isalpha():
            holders.append(tuple(words[:2]))
    return holders


def holders_and_years(text: str) -> set[tuple[tuple[str, ...], int | None]]:
    """Return every holder and year the copyright lines in ``text`` name."""
    this_year = datetime.datetime.now(tz=datetime.UTC).year
    pairs: set[tuple[tuple[str, ...], int | None]] = set()
    for match in COPYRIGHT_LINE.finditer(text):
        line = match.group(0)
        if NOT_A_NOTICE.search(line):
            continue
        years: set[int] = set()
        for first, last in YEARS.findall(line):
            end = this_year if last.lower() == "present" else int(last or first)
            years.update(range(int(first), end + 1))
        for holder in _holders(line):
            pairs.update({(holder, year) for year in years} or {(holder, None)})
    return pairs


def _cited_by_crate(committed: str) -> dict[Crate, list[str]]:
    """Return, for each crate, the bodies of the texts the notices carry for it."""
    cited: dict[Crate, list[str]] = {}
    for block in committed.split(f"\n{RULE}\n"):
        head, _, body = block.partition(f"{THIN}\n")
        users = re.search(r"(?:Used by|Cited by):(.*?)\nText:", head, re.DOTALL)
        if users is None:
            continue
        for name in " ".join(users.group(1).split()).split(", "):
            crate, _, version = name.strip().partition(" ")
            cited.setdefault(Crate(crate, version), []).append(body)
    return cited


def _licence_files_at(root: Path) -> list[Path]:
    """Return the licence-named files at a crate's root."""
    return [
        p for p in sorted(root.iterdir()) if p.is_file() and LICENCE_FILE.match(p.name)
    ]


def _read(path: Path) -> str:
    """Return a file's text, or nothing for a file that is not text."""
    raw = path.read_bytes()
    if b"\0" in raw[:4096]:
        return ""
    return raw.decode("utf-8", errors="replace")


def _sources(root: Path) -> list[Path]:
    """Return every file of a crate that the library could compile, or read."""
    found = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in NOT_COMPILED)
        found += [
            Path(folder) / name
            for name in sorted(files)
            if not LICENCE_FILE.match(name)
        ]
    return found


def _embedded_problems(
    found: dict[Crate, set[str]], roots: dict[Crate, Path], committed: str
) -> list[str]:
    """Return each notice written out in a crate's files that is not carried.

    A notice is a licence's permission text and the copyright lines before it.
    Every holder and year those lines name has to be named by a text the
    notices carry for the crate, unless the holder is the crate's own, named
    in its root licence files, whatever the year.
    """
    cited = _cited_by_crate(committed)
    problems = []
    seen: set[tuple[str, str]] = set()
    for crate in sorted(found, key=_version_key):
        root = roots[crate]
        own = {
            holder
            for path in _licence_files_at(root)
            for holder, _ in holders_and_years(_read(path))
        }
        carried = {
            pair for body in cited.get(crate, []) for pair in holders_and_years(body)
        }
        carried_names = {holder for holder, _ in carried}
        for path in _sources(root):
            text = _read(path)
            missing = set()
            for grant in GRANT.finditer(text):
                window = text[max(0, grant.start() - 1200) : grant.start()]
                for holder, year in holders_and_years(window):
                    if holder in own or (holder, year) in carried:
                        continue
                    if year is None and holder in carried_names:
                        continue
                    missing.add((holder, year))
            if not missing:
                continue
            relative = path.relative_to(root).as_posix()
            seen.add((crate.name, relative))
            if (crate.name, relative) in EMBEDDED_WAIVED:
                continue
            spans: dict[str, list[int]] = {}
            for holder, year in missing:
                spans.setdefault(" ".join(holder), []).extend(
                    [] if year is None else [year]
                )
            named = "; ".join(
                holder + _span(years) for holder, years in sorted(spans.items())
            )
            problems.append(
                f"{crate}'s {relative} writes out a licence under a copyright the "
                f"notices do not carry ({named}). If the build compiles it, carry "
                "its notice with a clarification in about.toml; if not, add it to "
                "EMBEDDED_WAIVED in scripts/rust_notices.py with the reason."
            )
    problems += [
        f"EMBEDDED_WAIVED names {name}'s {path}, which holds no notice the "
        "notices lack in any crate the extension is built from; remove the entry"
        for name, path in sorted(set(EMBEDDED_WAIVED) - seen)
    ]
    return problems


def _span(years: list[int]) -> str:
    """Return a holder's years as a copyright line gives them: one, or a range."""
    if not years:
        return ""
    first, last = min(years), max(years)
    return f" {first}" if first == last else f" {first}-{last}"


def _licence_ids(expression: str) -> set[str]:
    """Return the licence identifiers an SPDX expression names."""
    return set(re.findall(r"[A-Za-z0-9.+-]+", expression)) - {"OR", "AND", "WITH"}


def named_for(name: str) -> set[str]:
    """Return the licences a root file's name says it holds the text of."""
    tokens = re.split(r"[^a-z0-9]+", name.lower())
    return {NAMED_LICENCE[token] for token in tokens if token in NAMED_LICENCE}


def _root_problems(
    found: dict[Crate, set[str]],
    roots: dict[Crate, Path],
    listed: dict[Crate, Listed],
    carried: str,
) -> list[str]:
    """Return each notice at a crate's root that is neither carried nor explained.

    A licence-named file at the root is accounted for if it is carried, if its
    name says it holds the text of a licence the crate offers and is not taken
    under, or if it holds no dated copyright line: a pointer to the licences,
    not a notice.
    """
    problems = []
    seen: set[tuple[str, str]] = set()
    for crate in sorted(set(found) & set(listed), key=_version_key):
        entry = listed[crate]
        passed_over = _licence_ids(entry.declared) - set(entry.under)
        for path in _licence_files_at(roots[crate]):
            body = _normal(_read(path))
            if not body or body in carried:
                continue
            if any(
                licence in passed_over
                or (licence == "BSD" and any(o.startswith("BSD") for o in passed_over))
                for licence in named_for(path.name)
            ):
                continue
            if not any(year is not None for _, year in holders_and_years(body)):
                continue
            seen.add((crate.name, path.name))
            if (crate.name, path.name) in ROOT_WAIVED:
                continue
            problems.append(
                f"{crate} ships {path.name} at its root, a notice the notices do not "
                "carry and cargo-about did not read as a licence. Carry it with a "
                "clarification in about.toml, or add it to ROOT_WAIVED in "
                "scripts/rust_notices.py with the reason."
            )
    problems += [
        f"ROOT_WAIVED names {name}'s {path}, which is carried, is not at the root "
        "of any crate the extension is built from, or is no notice; remove the entry"
        for name, path in sorted(set(ROOT_WAIVED) - seen)
    ]
    return problems


def _standard_text_problems(
    found: dict[Crate, set[str]],
    roots: dict[Crate, Path],
    listed: dict[Crate, Listed],
    numbered: dict[int, tuple[str, bool]],
) -> list[str]:
    """Return each crate that cites a standard text beside a licence file of its own.

    cargo-about falls back to a licence's standard text, without a word, when
    it cannot read the text a crate ships: renamed, reflowed, or joined to
    another licence's. The crate's own copyright line is lost when it does.
    """
    standard = {n for n, (_, is_standard) in numbered.items() if is_standard}
    problems = []
    allowed: set[str] = set()
    for crate in sorted(set(found) & set(listed), key=_version_key):
        if not set(listed[crate].refs) & standard:
            continue
        shipped = [path.name for path in _licence_files_at(roots[crate])]
        if not shipped:
            continue
        if crate.name in STANDARD_TEXT:
            allowed.add(crate.name)
            continue
        problems.append(
            f"{crate} cites a licence's standard text and ships {', '.join(shipped)} "
            "at its root: cargo-about found no text of its own there for that "
            "licence, so its notice is not carried. Clarify the crate in "
            "about.toml, or add it to STANDARD_TEXT in scripts/rust_notices.py "
            "with the reason."
        )
    problems += [
        f"STANDARD_TEXT names {name}, which cites no standard text beside a "
        "licence file of its own; remove the entry"
        for name in sorted(set(STANDARD_TEXT) - allowed)
    ]
    return problems


def check() -> int:
    """Hold the committed notices to what the extension is built from."""
    meta = metadata()
    found = built_from(_workspace(meta))
    roots = _roots(meta)
    committed = NOTICES.read_text(encoding="utf-8")
    listed, numbered = read(committed)
    problems = _listing_problems(found, listed, numbered)
    problems += _vendored_problems(found, roots, _normal(committed))
    problems += _embedded_problems(found, roots, committed)
    problems += _root_problems(found, roots, listed, _normal(committed))
    problems += _standard_text_problems(found, roots, listed, numbered)
    if problems:
        for problem in problems:
            print(f"::error::{problem}")  # noqa: T201
        print(  # noqa: T201
            f"{len(problems)} problem(s). Rewrite the notices with "
            "`python3 scripts/rust_notices.py write` once the cause is fixed."
        )
        return 1
    print(  # noqa: T201
        f"{NOTICES.relative_to(REPO_ROOT)} lists the {len(found)} crates the "
        f"extension is built from on {len(targets())} platforms, and carries or "
        "accounts for every notice in them: licence files below their roots, "
        "licences written out in their files, notices at their roots, and their "
        "own licence texts where a standard one stands in"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run ``write`` or ``check``."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("command", choices=("write", "check"))
    arguments = parser.parse_args(argv)
    try:
        return write() if arguments.command == "write" else check()
    except NoticesError as error:
        print(f"::error::{error}")  # noqa: T201
        return 1


if __name__ == "__main__":
    sys.exit(main())
