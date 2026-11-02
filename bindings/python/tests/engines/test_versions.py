# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The versions name the extension this process loaded, or say it changed.

A notebook runs for days, and a rebuild or an upgrade can land under it. The
values it computed came off the extension it loaded, so a statement of what
produced them has to be about that file: its digest where the file on disk is
still the one loaded, and a plain statement that it changed where it is not.
A digest of whatever now sits at the path would name a binary that computed
nothing here.
"""

from __future__ import annotations

import hashlib
import os
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, _internal
from gaspatchio.engines import _versions
from gaspatchio.engines._versions import (
    _LOADED,
    _as_loaded,
    _extension_sha256,
    _taken_once,
    versions_in_this_process,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

CHANGED = "unavailable: the extension file changed after this process loaded it"


@pytest.fixture
def read_afresh() -> Iterator[None]:
    """Let a test read the versions from scratch, and leave them to be read again."""
    _taken_once.cache_clear()
    yield
    _taken_once.cache_clear()


def _loaded(tmp_path: Path, content: bytes = b"compiled once") -> Path:
    binary = tmp_path / "extension.so"
    binary.write_bytes(content)
    return binary


def test_the_package_and_the_extension_each_state_their_own_version() -> None:
    stated = versions_in_this_process()

    assert stated["core_version"] == version("gaspatchio")
    assert stated["extension_version"] == _internal.__version__


def test_a_package_and_an_extension_that_differ_are_each_stated_as_they_are(
    read_afresh: None,  # noqa: ARG001 -- the fixture's effect is the point
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python code at one version over an extension compiled at another.

    An editable install over an extension built before the last bump is the
    ordinary case: the package's metadata says one thing and the binary the
    other, and a result has to say both rather than let either stand in.
    """
    monkeypatch.setattr(_versions, "version", lambda _: "1.0.0")
    monkeypatch.setattr(
        _versions, "_LOADED", _as_loaded(Path(_internal.__file__), "0.9.0")
    )

    stated = versions_in_this_process()

    assert stated["core_version"] == "1.0.0"
    assert stated["extension_version"] == "0.9.0"
    assert stated["extension_sha256"].startswith("sha256:")


def test_the_extension_is_placed_as_this_module_is_imported() -> None:
    now = Path(_internal.__file__).stat()
    assert _LOADED.placed == (
        now.st_dev,
        now.st_ino,
        now.st_size,
        now.st_mtime_ns,
    )


def test_the_extension_this_process_loaded_is_digested(tmp_path: Path) -> None:
    loaded = _as_loaded(_loaded(tmp_path), "1.2.3")

    digest = _extension_sha256(loaded)

    assert digest == f"sha256:{hashlib.sha256(b'compiled once').hexdigest()}"


def test_an_extension_written_over_after_load_is_not_digested(tmp_path: Path) -> None:
    binary = _loaded(tmp_path)
    loaded = _as_loaded(binary, "1.2.3")
    binary.write_bytes(b"rebuilt later")
    later = loaded.placed[3] + 1_000_000_000 if loaded.placed else 0
    os.utime(binary, ns=(later, later))

    assert _extension_sha256(loaded) == CHANGED


def test_an_extension_replaced_after_load_is_not_digested_even_with_one_content(
    tmp_path: Path,
) -> None:
    binary = _loaded(tmp_path)
    loaded = _as_loaded(binary, "1.2.3")
    replacement = tmp_path / "staged.so"
    replacement.write_bytes(b"compiled once")
    replacement.replace(binary)

    assert _extension_sha256(loaded) == CHANGED


def test_an_extension_gone_after_load_is_not_digested(tmp_path: Path) -> None:
    binary = _loaded(tmp_path)
    loaded = _as_loaded(binary, "1.2.3")
    binary.unlink()

    assert _extension_sha256(loaded) == CHANGED


def test_the_process_states_the_digest_of_the_extension_it_loaded(
    read_afresh: None,  # noqa: ARG001 -- the fixture's effect is the point
) -> None:
    on_disk = Path(_internal.__file__).read_bytes()

    stated = versions_in_this_process()["extension_sha256"]

    assert stated == f"sha256:{hashlib.sha256(on_disk).hexdigest()}"


def test_a_run_whose_extension_changed_since_load_says_so(
    tmp_path: Path,
    read_afresh: None,  # noqa: ARG001 -- the fixture's effect is the point
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = _loaded(tmp_path)
    monkeypatch.setattr(_versions, "_LOADED", _as_loaded(binary, "1.2.3"))
    af = ActuarialFrame(pl.DataFrame({"premium": [1200.0, 900.0]}))
    af.commission = af.premium * 0.05
    af.collect()
    replacement = tmp_path / "staged.so"
    replacement.write_bytes(b"rebuilt mid-session")
    replacement.replace(binary)

    summary = af.graph.last_run

    assert summary is not None
    assert summary.versions["extension_sha256"] == CHANGED
    assert summary.versions["extension_version"] == "1.2.3"
