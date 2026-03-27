"""Bundled tutorial models for gaspatchio.

Provides tutorial files that ship with the package, so
`gspio tutorial init level-1` works regardless of install method.
"""

from pathlib import Path


def get_tutorials_dir() -> Path:
    """Return the path to the bundled tutorials directory."""
    return Path(__file__).parent
