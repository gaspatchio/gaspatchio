# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The rollforward kernel — declarative state-machine projections.

Public surface:

  - :class:`RollforwardBuilder` — mutable builder that accumulates Ops
  - :class:`RollforwardCollector` — emits per-state and per-increment exprs
  - :func:`compile_rollforward` — turns a builder into a :class:`CompiledRollforward`
  - :class:`CompiledRollforward` — frozen artefact with ``explain()``,
    ``fingerprint()``, and ``canonical_form()`` for inspection

These are also re-exported at the top level (``from gaspatchio_core import ...``).
"""

from __future__ import annotations

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.rollforward._compiled import CompiledRollforward

__all__ = [
    "CompiledRollforward",
    "RollforwardBuilder",
    "RollforwardCollector",
    "compile_rollforward",
]
