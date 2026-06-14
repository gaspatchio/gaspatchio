# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Typed term-structure primitive — Curve.

A frozen discount curve built from zero rates or par rates, with
spot / discount-factor / forward-rate readouts and parallel + key-rate
sensitivity stresses. Coexists with the existing column-of-rates
surface; nothing is forced to migrate.
"""

from __future__ import annotations

from gaspatchio_core.curves._curve import Curve

__all__ = ["Curve"]
