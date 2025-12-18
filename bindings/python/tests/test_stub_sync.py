"""Test that .pyi stub files stay in sync with the runtime implementation."""

import subprocess
import sys
from pathlib import Path


def test_stubs_match_runtime():
    """Ensure .pyi stubs match the actual runtime signatures.

    Uses mypy.stubtest to verify that all type stubs (.pyi files) accurately
    reflect the runtime implementation. This catches:
    - Missing or extra methods/attributes
    - Signature mismatches (args, return types)
    - Incorrect type annotations
    """
    # Get the directory containing this test file
    test_dir = Path(__file__).parent.parent
    allowlist = test_dir / "stubtest-allowlist.txt"
    mypy_config = test_dir / "mypy-stubtest.ini"

    cmd = [
        sys.executable,
        "-m",
        "mypy.stubtest",
        "gaspatchio_core",
        "--ignore-missing-stub",  # Don't fail on missing stubs for dependencies
    ]

    # Add allowlist if it exists
    if allowlist.exists():
        cmd.extend(["--allowlist", str(allowlist)])

    # Add mypy config if it exists
    if mypy_config.exists():
        cmd.extend(["--mypy-config-file", str(mypy_config)])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(test_dir),  # Run from package directory
    )
    
    # Check if there are actual errors (not just unused allowlist entries)
    # Stubtest exits with 1 even for just unused allowlist entries
    stdout = result.stdout or ""
    has_actual_errors = any(
        line.startswith("error:") for line in stdout.splitlines()
    )
    
    if has_actual_errors:
        # Format output for readable pytest failure
        failure_msg = "stubtest found stub/runtime mismatches:\n"
        if result.stdout:
            failure_msg += f"\n{result.stdout}"
        if result.stderr:
            failure_msg += f"\nSTDERR:\n{result.stderr}"
        raise AssertionError(failure_msg)
