# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Par-to-zero bootstrap and zero-to-par derivation.

Bootstrap assumes annually compounded par bonds at integer-year tenors
starting at year 1, contiguous (1, 2, 3, ...). The bootstrap pattern:

    DF(t) = (1 - p_t * sum_{i<t} DF(i)) / (1 + p_t)

where ``p_t`` is the par coupon rate at maturity ``t`` and DF(0) = 1.
The zero rate at tenor ``t`` is then ``r_t = DF(t)^(-1/t) - 1``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def _validate_annual_tenors(tenors: Sequence[float]) -> None:
    """Reject non-annual / non-contiguous / non-1-start tenor lists."""
    if not tenors or tenors[0] != 1.0:
        msg = (
            f"par-rate tenors must be annual (1, 2, 3, ...) starting at 1; "
            f"got {list(tenors)}"
        )
        raise ValueError(msg)
    for i in range(1, len(tenors)):
        if tenors[i] - tenors[i - 1] != 1.0:
            msg = (
                f"par-rate tenors must be annual (1, 2, 3, ...) starting at 1; "
                f"got {list(tenors)}"
            )
            raise ValueError(msg)


def par_to_zero_rates(
    tenors: Sequence[float],
    par_rates: Sequence[float],
) -> list[float]:
    """Bootstrap zero rates from annual par rates.

    Args:
        tenors: Integer-year tenors starting at 1, contiguous (e.g. 1, 2, 3).
        par_rates: Par coupon rates corresponding to each tenor.

    Returns:
        List of annually compounded zero rates at each tenor.

    Raises:
        ValueError: If tenors are not contiguous annual integers starting at 1.

    Examples:
        >>> par_to_zero_rates([1.0, 2.0], [0.04, 0.04])  # doctest: +ELLIPSIS
        [0.04..., 0.04...]

    """
    _validate_annual_tenors(tenors)
    discount_factors: list[float] = []
    for i, (_t, p) in enumerate(zip(tenors, par_rates, strict=True)):
        discount_factor = (
            1.0 / (1.0 + p) if i == 0 else (1.0 - p * sum(discount_factors)) / (1.0 + p)
        )
        discount_factors.append(discount_factor)
    return [
        float(discount_factor ** (-1.0 / t) - 1.0)
        for t, discount_factor in zip(tenors, discount_factors, strict=True)
    ]


def zero_to_par_rates(
    tenors: Sequence[float],
    zero_rates: Sequence[float],
) -> list[float]:
    """Derive annual par coupon rates from a zero curve.

    Inverse of :func:`par_to_zero_rates`.
    ``p_t = (1 - DF(t)) / sum_{i<=t} DF(i)``.

    Args:
        tenors: Integer-year tenors starting at 1, contiguous (e.g. 1, 2, 3).
        zero_rates: Annually compounded zero rates at each tenor.

    Returns:
        List of par coupon rates at each tenor.

    Raises:
        ValueError: If tenors are not contiguous annual integers starting at 1.

    Examples:
        >>> zero_to_par_rates([1.0, 2.0], [0.04, 0.04])  # doctest: +ELLIPSIS
        [0.04..., 0.04...]

    """
    _validate_annual_tenors(tenors)
    discount_factors = [
        float((1.0 + r) ** (-t)) for t, r in zip(tenors, zero_rates, strict=True)
    ]
    par_rates: list[float] = []
    for i in range(len(tenors)):
        cumulative_df = sum(discount_factors[: i + 1])
        p = (1.0 - discount_factors[i]) / cumulative_df
        par_rates.append(p)
    return par_rates


__all__ = ["par_to_zero_rates", "zero_to_par_rates"]
