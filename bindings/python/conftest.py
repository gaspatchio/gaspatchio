# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Session-level pytest guard against unresolved git-lfs pointer files.

Fixtures matching `*.parquet` and `*.csv` are LFS-tracked (see `.gitattributes`).
When a clone happens without git-lfs installed, those files land as ~140-byte
pointer blobs starting with `version https://git-lfs.github.com/spec/v1`.
Tests that load them then fail with cryptic parquet/csv read errors that look
like real bugs.

This guard scans the project at collection time. If pointer files are present:
  - emits a clear session-start warning naming the affected directories
  - skips tests whose containing directory tree includes pointer files

Resolution: `git lfs install && git lfs pull`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
_TRACKED_SUFFIXES = (".parquet", ".csv")
_POINTER_DIRS_KEY: pytest.StashKey[frozenset[Path]] = pytest.StashKey()


def _is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(len(_LFS_POINTER_PREFIX)) == _LFS_POINTER_PREFIX
    except OSError:
        return False


def _scan_pointer_dirs(root: Path) -> frozenset[Path]:
    """Return directories containing at least one unresolved LFS pointer file."""
    skip_parts = {".venv", "node_modules", "target", ".git", "__pycache__"}
    pointer_dirs: set[Path] = set()
    for path in root.rglob("*"):
        if any(part in skip_parts for part in path.parts):
            continue
        if path.suffix not in _TRACKED_SUFFIXES or not path.is_file():
            continue
        if _is_lfs_pointer(path):
            pointer_dirs.add(path.parent)
    return frozenset(pointer_dirs)


def pytest_configure(config: pytest.Config) -> None:
    pointer_dirs = _scan_pointer_dirs(Path(config.rootpath))
    config.stash[_POINTER_DIRS_KEY] = pointer_dirs
    if pointer_dirs:
        listing = "\n  ".join(sorted(str(d) for d in pointer_dirs))
        config.issue_config_time_warning(
            pytest.PytestConfigWarning(
                f"Detected {len(pointer_dirs)} director"
                f"{'y' if len(pointer_dirs) == 1 else 'ies'} with unresolved "
                f"git-lfs pointer files. Resolve with "
                f"`git lfs install && git lfs pull`. "
                f"Tests in these directories will be skipped:\n  {listing}",
            ),
            stacklevel=2,
        )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    pointer_dirs: frozenset[Path] = config.stash.get(_POINTER_DIRS_KEY, frozenset())
    if not pointer_dirs:
        return
    skip_marker = pytest.mark.skip(
        reason="git-lfs pointer files in this test's directory tree; "
        "run `git lfs install && git lfs pull`",
    )
    for item in items:
        test_dir = Path(item.fspath).parent.resolve()
        for pdir in pointer_dirs:
            try:
                pdir.resolve().relative_to(test_dir)
            except ValueError:
                continue
            item.add_marker(skip_marker)
            break
