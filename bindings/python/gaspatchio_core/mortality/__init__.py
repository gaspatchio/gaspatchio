# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Typed mortality wrapper — MortalityTable.

A thin actuarial-convention wrapper over
:class:`gaspatchio_core.assumptions.Table` that records age-basis,
structure (aggregate / select-ultimate / joint), and (where
applicable) the select period. The underlying Table continues to work
for non-mortality assumptions (lapse, expense, surrender charges).
"""

from __future__ import annotations

from gaspatchio_core.mortality._conventions import AgeBasis, Structure
from gaspatchio_core.mortality._mortality_table import MortalityTable

__all__ = ["AgeBasis", "MortalityTable", "Structure"]
