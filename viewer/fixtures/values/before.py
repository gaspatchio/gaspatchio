# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A fee, what it is charged over three years, and a reserve: the earlier version.

The later version, ``after.py``, raises the fee rate and nothing else, so the
two runs part in every way a change report has to tell apart: a line edited, a
line whose numbers moved because what it reads did, a line flagged by its
identity that moved no number, a line moved out of zero, and -- because the
later run is over a revised book with one policy gone and one arrived -- a line
whose definition held while the book under it moved.
"""

import datetime

from gaspatchio import ActuarialFrame

FEE_RATE = 0.02


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Project the fee and the reserve over three annual periods."""
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_years",
        until_value=3,
        frequency="annual",
    )
    af.fee = af.premium * FEE_RATE
    af.charge = af.fee * af.month
    af.fee_over_base = af.fee - af.base_fee
    af.waived = af.fee * af.waiver
    af.reserve = af.premium * af.month
    return af
