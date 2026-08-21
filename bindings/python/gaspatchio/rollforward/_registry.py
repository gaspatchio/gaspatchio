# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Registry mapping hidden rollforward column names to their plugin exprs.

``CompiledRollforward.expr_for`` returns ``pl.col("__rollforward_<fp>")
.struct.field(...)`` — a reference to a struct column that does not exist
until something materialises it. This module is the lookup that lets
``ActuarialFrame`` do that materialisation: when an assigned expression
references a ``__rollforward_*`` column missing from the frame's schema, the
frame fetches the plugin expr here and adds the column once. Every later
extraction reuses it, which is what guarantees ONE kernel call per compiled
rollforward regardless of how many states or increments are read.

Keys are derived from :meth:`CompiledRollforward.fingerprint`, so the same
model compiled twice shares one entry (and one materialised column), while
structurally different models can never collide. Entries are tiny (one
``pl.Expr`` each) and live for the process; scenario worker processes
repopulate naturally when the model function recompiles its rollforward.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

HIDDEN_PREFIX = "__rollforward_"

_PLUGIN_EXPRS: dict[str, pl.Expr] = {}


def hidden_column_name(fingerprint: str) -> str:
    """Return the hidden struct column name for a compiled-rollforward fingerprint."""
    # Fingerprints render as "sha256:<hex>"; keep 16 hex chars of the digest.
    digest = fingerprint.split(":", 1)[-1]
    return f"{HIDDEN_PREFIX}{digest[:16]}"


def register(name: str, plugin_expr: pl.Expr) -> None:
    """Record the plugin expr that materialises ``name`` (first writer wins).

    First-writer-wins is safe because the name embeds the model fingerprint:
    two registrations for one name are the same model, so their plugin exprs
    are interchangeable.
    """
    _PLUGIN_EXPRS.setdefault(name, plugin_expr)


def has_entries() -> bool:
    """Return True when any rollforward has registered (cheap hot-path guard)."""
    return bool(_PLUGIN_EXPRS)


def plugin_expr_for(name: str) -> pl.Expr:
    """Return the plugin expr for a hidden column name.

    Raises:
        KeyError: If ``name`` was never registered — an expression referencing
            a hidden rollforward column reached a frame in a process where the
            rollforward was never compiled.

    """
    try:
        return _PLUGIN_EXPRS[name]
    except KeyError:
        msg = (
            f"unknown rollforward column {name!r}: the expression references a "
            "compiled rollforward that was never registered in this process. "
            "Build the expression from CompiledRollforward.expr_for(...) in "
            "the same process that runs the frame."
        )
        raise KeyError(msg) from None


__all__ = [
    "HIDDEN_PREFIX",
    "has_entries",
    "hidden_column_name",
    "plugin_expr_for",
    "register",
]
