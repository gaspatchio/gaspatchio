# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test that .pyi stub files stay in sync with the runtime implementation."""

import re
import subprocess
import sys
from pathlib import Path

# stubtest always closes with one summary line reporting the module count,
# whichever way the comparison went -- something like `Success: no issues
# found in 284 modules` when clean, or `Found 61 errors (checked 284
# modules)` when not. Parsing that count (rather than trusting a zero exit
# code, or merely the absence of `error:` lines) is what lets the test tell
# a clean comparison apart from one that silently checked nothing -- an
# aborted build prints neither line.
_SUCCESS_RE = re.compile(r"^Success: no issues found in (\d+) modules?$")
_FAILURE_RE = re.compile(r"^Found \d+ errors? \(checked (\d+) modules?\)$")

# The comparison currently walks 284 modules (see AGENTS.md's type-checking
# baseline table). This bound sits well under that so ordinary module
# additions or removals don't flap the test -- it exists only to catch a run
# that checked (near) nothing.
_MIN_MODULES_CHECKED = 200


def parse_modules_checked(stdout: str) -> int | None:
    """Extract the module count from stubtest's closing summary line.

    Returns ``None`` when no summary line is present, which happens when
    stubtest aborts before it reaches a comparison (for example, a build
    failure in the package under test).
    """
    for line in stdout.splitlines():
        match = _SUCCESS_RE.match(line) or _FAILURE_RE.match(line)
        if match:
            return int(match.group(1))
    return None


def test_parse_modules_checked_reads_the_success_line() -> None:
    stdout = "Success: no issues found in 284 modules"
    assert parse_modules_checked(stdout) == 284


def test_parse_modules_checked_reads_the_failure_line() -> None:
    stdout = (
        "note: unused allowlist entry gaspatchio.cli\n"
        "Found 1 error (checked 284 modules)\n"
    )
    assert parse_modules_checked(stdout) == 284


def test_parse_modules_checked_returns_none_without_a_summary_line() -> None:
    """A stdout with no summary line -- the shape of an aborted run.

    The fixture line has neither an ``error:`` prefix (which the older,
    weaker check in ``test_stubs_match_runtime`` already caught) nor a
    closing summary line -- it stands in for a run that failed before
    reaching a comparison at all, which used to pass silently. Must not be
    mistaken for a comparison that ran: this is what makes the module-count
    assertion fail loudly on that shape of run instead.
    """
    stdout = "Skipping gaspatchio: cannot import\n"
    assert parse_modules_checked(stdout) is None


def test_stubs_match_runtime() -> None:
    """Ensure .pyi stubs match the actual runtime signatures.

    Uses mypy.stubtest to verify that all type stubs (.pyi files) accurately
    reflect the runtime implementation. This catches:
    - Missing or extra methods/attributes
    - Signature mismatches (args, return types)
    - Incorrect type annotations
    - Allowlist entries that no longer match anything (stale exceptions)
    - A comparison that silently checked nothing at all
    """
    # Get the directory containing this test file
    test_dir = Path(__file__).parent.parent
    allowlist = test_dir / "stubtest-allowlist.txt"
    mypy_config = test_dir / "mypy-stubtest.ini"

    cmd = [
        sys.executable,
        "-m",
        "mypy.stubtest",
        "gaspatchio",
    ]

    # Add allowlist if it exists
    if allowlist.exists():
        cmd.extend(["--allowlist", str(allowlist)])

    # Add mypy config if it exists
    if mypy_config.exists():
        cmd.extend(["--mypy-config-file", str(mypy_config)])

    result = subprocess.run(  # noqa: S603 — fixed argv, no shell, all paths are ours
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(test_dir),  # Run from package directory
    )

    stdout = result.stdout or ""
    lines = stdout.splitlines()

    # Check if there are actual errors (not just unused allowlist entries)
    # Stubtest exits with 1 even for just unused allowlist entries
    has_actual_errors = any(line.startswith("error:") for line in lines)

    if has_actual_errors:
        # Format output for readable pytest failure
        failure_msg = "stubtest found stub/runtime mismatches:\n"
        if result.stdout:
            failure_msg += f"\n{result.stdout}"
        if result.stderr:
            failure_msg += f"\nSTDERR:\n{result.stderr}"
        raise AssertionError(failure_msg)

    # An allowlist entry that no longer matches anything is exception debt:
    # it hides the fact that the thing it once excused is gone. Fail on it
    # so the allowlist can only grow when it is still true.
    unused_entries = [
        line for line in lines if line.startswith("note: unused allowlist entry")
    ]
    if unused_entries:
        raise AssertionError(
            "stubtest-allowlist.txt has entries that no longer match "
            "anything -- remove them (see AGENTS.md's stubtest command):\n\n"
            + "\n".join(unused_entries)
        )

    # A comparison that never ran (package failed to build, stubtest crashed
    # before printing its summary) has no "error:" lines and no unused-entry
    # notes either -- it would otherwise pass this test by omission. Require
    # the closing summary line and a plausible module count instead.
    modules_checked = parse_modules_checked(stdout)
    assert modules_checked is not None, (
        "stubtest printed no closing summary line -- the comparison may "
        f"not have run at all:\n\n{stdout}"
    )
    assert modules_checked >= _MIN_MODULES_CHECKED, (
        f"stubtest only checked {modules_checked} modules, fewer than the "
        f"{_MIN_MODULES_CHECKED} expected -- the comparison may have run "
        f"against an incomplete package:\n\n{stdout}"
    )
