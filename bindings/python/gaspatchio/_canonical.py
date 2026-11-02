# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Neutral recipe JSON and SHA-256 identity, independent of frames and engines.

The values/content grammar remains in ``_identity``. Keeping the recipe helpers
here lets engine protocols share the identity scheme without importing that
Polars-specific encoder or the graph dtype vocabulary it uses.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, NoReturn

# The one place the framework's content-identity scheme is spelled out.
# Every stamp in the audit chain -- recipe and content hashes, and the
# calculation graph's node fingerprints -- is this
# prefix followed by sixty-four lowercase hex digits. One definition so a
# second one can never drift from it.
SHA256_PREFIX: Final[str] = "sha256:"


def _raise_on_unknown(val: object) -> NoReturn:
    msg = f"canonical_bytes: cannot encode {type(val).__name__} ({val!r})"
    raise TypeError(msg)


def canonical_bytes(form: dict[str, Any]) -> bytes:
    """Deterministic JSON encoding for canonical_form dicts.

    Rules:
        - ``sort_keys=True`` at every level
        - ``separators=(',', ':')`` — no insignificant whitespace
        - ``ensure_ascii=True`` — stable bytes across platforms
        - ``allow_nan=False`` — explicit NaN raises (caller responsibility)
        - unknown types raise ``TypeError`` (no silent ``str()`` fallback)

    See also :func:`gaspatchio.frame.graph.fingerprint.canonical_bytes`, the
    calculation graph's byte grammar over op-trees, which takes the
    opposite position on NaN and normalizes it rather than raising.
    """
    return json.dumps(
        form,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_raise_on_unknown,
    ).encode("utf-8")


def source_sha_of(form: dict[str, Any]) -> str:
    """Return ``sha256:<hex>`` over ``canonical_bytes(form)``."""
    digest = hashlib.sha256(canonical_bytes(form)).hexdigest()
    return f"{SHA256_PREFIX}{digest}"


DISPLAY_WIDTH: Final[int] = 12


def short_fingerprint(digest: bytes | str) -> str:
    """Return the first twelve hex digits of a fingerprint, for display.

    Accepts any form a caller has to hand: the raw digest, a bare hex
    string, or a stamped ``"sha256:<hex>"`` string. A scheme prefix, if
    present, is stripped before truncating, so the result is always hex
    digits -- a git-style short id, never the scheme name. This is the
    framework's first short-display helper for a content hash; a later one
    should follow the same shape.
    """
    hex_form = digest.hex() if isinstance(digest, bytes) else digest.rsplit(":", 1)[-1]
    return hex_form[:DISPLAY_WIDTH]
