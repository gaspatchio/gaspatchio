# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Expected claims on a twelve-month timeline, with a calculation at each tier.

Most lines are written in the framework's own terms, which the format's own
vocabulary accounts for: core. Two reach into Polars' own expression
language, one through the named escape and one as a batch of Polars
expressions: engine_native. One applies an operation registered the way an
extension registers one, which nothing has classified: opaque.

The arithmetic is the four operations and nothing else, so the values it
samples are the same bytes on every platform that runs it.
"""

import datetime

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio._authoring import emit
from gaspatchio.frame.lowering.polars import lower_polars, register_lowering


@register_lowering("acme.smoothing")
def _smoothing(node, ctx):
    """Halve the claims, as an extension's own operation would."""
    return lower_polars(node.args[0], ctx) * 0.5


def main(af: ActuarialFrame) -> ActuarialFrame:
    """Project each policy's expected claims over a year."""
    af = af.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=12, frequency="monthly"
    )
    af.claims = af.sum_assured * af.mortality_rate
    af.survival = 1 - af.mortality_rate / 12 * af.month
    af.expected_claims = af.claims / 12 * af.survival
    af.discounted_claims = af.expected_claims * af.discount_factor
    af.largest_claim_so_far = af.claims.polars_native().cum_max()
    af = af.with_columns((pl.col("claims") * 1.02).alias("loaded_claims"))
    af.smoothed_claims = emit.call("acme.smoothing", (af.claims,), af)
    return af
