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

Keys are derived from one **run**: the compilation's
:meth:`CompiledRollforward.fingerprint` and the ``source_sha()`` of the
schedule it runs on. The fingerprint is the machine alone, so a
name minted from it alone would give one machine on two schedules -- this
quarter's model and last quarter's, compiled in one process -- one column and
one kernel between them, and the second would run on the first one's
periods. With the schedule in the key the same model compiled twice still
shares one entry (and one materialised column), while two runs that differ in
either the machine or its schedule can never collide. Entries are tiny (one
``pl.Expr`` each) and live for the process; scenario worker processes
repopulate naturally when the model function recompiles its rollforward.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from gaspatchio._identity import canonical_bytes

if TYPE_CHECKING:
    import polars as pl

HIDDEN_PREFIX = "__rollforward_"

# How many characters of the fingerprint's hex digest a minted name keeps.
_DIGEST_KEPT = 16
_HEX_DIGITS = frozenset("0123456789abcdef")

_PLUGIN_EXPRS: dict[str, pl.Expr] = {}


def hidden_column_name(fingerprint: str, schedule: str) -> str:
    """Return the hidden struct column name for one run of a compiled rollforward.

    Args:
        fingerprint: The compilation's published identity, the machine alone.
        schedule: The ``source_sha()`` of the schedule that machine runs on,
            as every rollforward call carries it.

    Returns:
        The prefix and sixteen hex characters of a digest over the pair --
        a pure function of the two attributes a call carries, so the name a
        record keeps is recomputable from the call it came from.

    """
    run = canonical_bytes({"fingerprint": fingerprint, "schedule": schedule})
    digest = hashlib.sha256(run).hexdigest()
    return f"{HIDDEN_PREFIX}{digest[:_DIGEST_KEPT]}"


def _is_minted_name(name: str) -> bool:
    """Return whether ``name`` is exactly the shape :func:`hidden_column_name` mints.

    The prefix and sixteen lower-case hex characters of a fingerprint, and
    nothing else. A name that only begins like one is not one: the shape is
    what tells the kernel's own column apart from anything else under the
    prefix, wherever that question is asked.
    """
    digest = name.removeprefix(HIDDEN_PREFIX)
    return digest != name and len(digest) == _DIGEST_KEPT and set(digest) <= _HEX_DIGITS


def register(name: str, plugin_expr: pl.Expr) -> None:
    """Record the plugin expr that materialises ``name`` (first writer wins).

    First-writer-wins is safe because the name embeds the run -- the machine's
    fingerprint and its schedule's: two registrations for one name are the
    same machine on the same schedule, so their plugin exprs are
    interchangeable.
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
