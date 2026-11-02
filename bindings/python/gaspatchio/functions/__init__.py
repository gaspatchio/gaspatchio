# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The ``when`` conditional, re-exported by the top-level ``gaspatchio`` namespace."""

# functions/__init__.py

# The package holds ``conditional.when``, which the top-level ``gaspatchio``
# namespace re-exports; model code reaches it from there. The plugin wrappers
# are not a modelling door and live with the Polars lowerings, in
# ``gaspatchio.frame.lowering._polars.plugins``.

__all__: list[str] = []
