#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""ABOUTME: CLI tool to check standalone Python files with Gaspatchio style rules.
ABOUTME: Validates code against GP rules and executes to show output.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from gaspatchio_core.examples.docstrings.style import StyleChecker


def check_and_run_file(file_path: Path) -> int:
    """Check a Python file for style violations and run it.

    Parameters
    ----------
    file_path : Path
        Path to the Python file to check and run

    Returns
    -------
    int
        Exit code (0 for success, 1 for style violations or execution errors)

    """
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        return 1

    if not file_path.is_file():
        print(f"Error: Not a file: {file_path}")
        return 1

    # Read the file content
    try:
        code = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading file: {e}")
        return 1

    # Run style checker with all available rules
    checker = StyleChecker()  # All rules enabled by default
    violations = checker.check(code)

    # Report violations
    has_violations = len(violations) > 0
    if has_violations:
        print(f"\n{'='*60}")
        print(f"Style Violations in {file_path.name}")
        print(f"{'='*60}")
        for v in violations:
            print(f"  {checker.format_violation(v)}")
        print(f"{'='*60}\n")
    else:
        print(f"✓ No style violations in {file_path.name}\n")

    # Run the file
    print(f"{'='*60}")
    print(f"Running {file_path.name}")
    print(f"{'='*60}\n")

    try:
        result = subprocess.run(
            [sys.executable, str(file_path)],
            capture_output=True,
            text=True,
            check=False,
        )

        # Print stdout
        if result.stdout:
            print(result.stdout)

        # Print stderr if present
        if result.stderr:
            print(f"\n{'='*60}")
            print("STDERR:")
            print(f"{'='*60}")
            print(result.stderr)

        # Check exit code
        if result.returncode != 0:
            print(f"\nScript exited with code: {result.returncode}")
            return 1

    except Exception as e:
        print(f"Error executing file: {e}")
        return 1

    # Return non-zero if there were style violations
    return 1 if has_violations else 0


def main() -> int:
    """Main entry point for the CLI."""
    if len(sys.argv) != 2:
        print("Usage: uv run python scripts/examples/check_python_file.py <file.py>")
        print("\nChecks a Python file for Gaspatchio style violations and executes it.")
        print("\nStyle Rules:")
        print("  GP001: Prefer attribute notation (af.column) over bracket notation (af['column'])")
        return 1

    file_path = Path(sys.argv[1])
    return check_and_run_file(file_path)


if __name__ == "__main__":
    sys.exit(main())
