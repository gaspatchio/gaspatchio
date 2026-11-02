# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""How ``scripts/rust_notices.py check`` reads a notice it did not write.

CI runs the check itself, against the crates cargo resolves, and it needs
cargo and the crates' sources, which a test run has neither of. What is held
here is the reading the check's audits rest on, which is heuristic: a
copyright line taken apart into the holders and years it names, a root file's
name taken for the licence whose text it holds, and the committed notices
read back, standard texts told apart from the texts crates ship. A change to
any of them changes what the check can see, and these say what it saw when
it was written.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "rust_notices.py"

# The script sits at the repository root, outside the core's sdist, which
# ships this directory; inside a checkout its absence is the fault.
pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / ".git").exists(),
    reason="not a repository checkout; the core's sdist ships no scripts/",
)


@pytest.fixture(scope="module")
def notices() -> ModuleType:
    """scripts/rust_notices.py, imported."""
    spec = importlib.util.spec_from_file_location("rust_notices", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "Copyright (c) 2020 Gilad Naaman, Ralf Jung",
            {(("gilad", "naaman"), 2020), (("ralf", "jung"), 2020)},
        ),
        ("// Portions Copyright (c) 2016, Google Inc.", {(("google",), 2016)}),
        (
            "Copyright (C) 2014-2016, Yann Collet.",
            {(("yann", "collet"), year) for year in (2014, 2015, 2016)},
        ),
        (
            "Copyright © 2005-2020 Rich Felker, et al.",
            {(("rich", "felker"), year) for year in range(2005, 2021)},
        ),
        (
            "Copyright (c) 2003-2008 Yuta Mori All Rights Reserved.",
            {(("yuta", "mori"), year) for year in range(2003, 2009)},
        ),
        # A notice that names no year still names its holders.
        (
            "Copyright (c) Yann Collet, Meta Platforms, Inc. and affiliates.",
            {(("yann", "collet"), None), (("meta", "platforms"), None)},
        ),
        # The Apache licence's own template, and prose about copyright, are
        # not notices.
        ("Copyright [yyyy] [name of copyright owner]", set()),
        ("the copyright owner or entity authorized by", set()),
    ],
)
def test_a_copyright_line_names_its_holders_and_years(
    notices: ModuleType, line: str, expected: set[tuple[tuple[str, ...], int | None]]
) -> None:
    assert notices.holders_and_years(line) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("LICENSE-APACHE", {"Apache-2.0"}),
        ("license-apache-2.0", {"Apache-2.0"}),
        ("LICENSE_A2LLVM", {"LLVM-exception"}),
        ("license-apache-2.0_with_llvm-exception", {"Apache-2.0", "LLVM-exception"}),
        ("LICENSE-MIT", {"MIT"}),
        ("LICENSE-MIT0", {"MIT-0"}),
        ("LICENSE-BOOST", {"BSL-1.0"}),
        ("UNLICENSE", {"Unlicense"}),
        ("LICENSE-ZLIB.md", {"Zlib"}),
        # A name that says no licence, as a notice or a pointer file's does.
        ("LICENSE", set()),
        ("COPYING", set()),
        ("LICENSE-THIRD-PARTY", set()),
    ],
)
def test_a_root_file_is_named_for_the_licence_it_holds(
    notices: ModuleType, name: str, expected: set[str]
) -> None:
    assert notices.named_for(name) == expected


def test_the_committed_notices_tell_standard_texts_from_shipped_ones(
    notices: ModuleType,
) -> None:
    """Every crate cites a text the file holds, and some texts are standard."""
    committed = (
        REPO_ROOT / "bindings" / "python" / "third-party-notices.txt"
    ).read_text(encoding="utf-8")
    listed, numbered = notices.read(committed)
    assert listed
    assert {n for entry in listed.values() for n in entry.refs} <= set(numbered)
    standard = {licence for licence, is_standard in numbered.values() if is_standard}
    shipped = {licence for licence, is_standard in numbered.values() if not is_standard}
    assert "MIT" in standard
    assert "MIT" in shipped


def test_the_standard_library_section_cites_the_rust_projects_mit_text(
    notices: ModuleType,
) -> None:
    """The number the section cites is a text in the Rust project's own words."""
    committed = (
        REPO_ROOT / "bindings" / "python" / "third-party-notices.txt"
    ).read_text(encoding="utf-8")
    section = committed.split(notices.STANDARD_HEADING, 1)[1].split(notices.RULE, 1)[0]
    cited = re.search(r"in the words of \[(\d+)\]", " ".join(section.split()))
    assert cited is not None, "the section cites no text"
    block = committed.split(f"{notices.RULE}\n[{cited.group(1)}] MIT\n", 1)[1]
    body = block.split(f"{notices.THIN}\n", 1)[1].split(f"\n{notices.RULE}\n", 1)[0]
    words = hashlib.sha256(" ".join(body.split()).encode()).hexdigest()
    assert words == notices.RUST_MIT_WORDS
