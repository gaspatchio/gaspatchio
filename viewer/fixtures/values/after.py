# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A fee, what it is charged over three years, and a reserve: the later version.

The earlier version, ``before.py``, charges 0.02; this one charges 0.025 and
changes nothing else. See ``before.py`` for what the pair is for.
"""

import datetime

from gaspatchio import ActuarialFrame

FEE_RATE = 0.025


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
