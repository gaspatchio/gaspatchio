# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Curve canonical-form + source_sha tests."""

from __future__ import annotations

from gaspatchio_core.curves._curve import Curve
from gaspatchio_core.schedule._day_count import (
    Actual360,
    Actual365Fixed,
    ActualActualISDA,
)


class TestCanonicalForm:
    """JSON-encodable canonical form: kind, tenors, rates, day_count, interpolation."""

    def test_canonical_shape(self) -> None:
        """Canonical form is a flat dict with the five expected keys."""
        c = Curve.from_zero_rates(
            tenors=[1.0, 5.0, 10.0],
            rates=[0.03, 0.04, 0.05],
            day_count=ActualActualISDA(),
        )
        cf = c.canonical_form()
        assert cf == {
            "kind": "Curve",
            "tenors": [1.0, 5.0, 10.0],
            "rates": [0.03, 0.04, 0.05],
            "day_count": "ActualActualISDA",
            "interpolation": "linear",
        }

    def test_lists_not_tuples_in_canonical(self) -> None:
        """Tuples become lists so the form is JSON-serialisable."""
        c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        cf = c.canonical_form()
        assert isinstance(cf["tenors"], list)
        assert isinstance(cf["rates"], list)


class TestSourceSha:
    """sha256:<hex> over canonical_bytes — fingerprint for kernel integration."""

    def test_identical_curves_have_identical_sha(self) -> None:
        """Two identically-constructed curves hash equal."""
        a = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        b = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        assert a.source_sha() == b.source_sha()

    def test_different_rate_changes_sha(self) -> None:
        """Changing one rate changes the SHA."""
        a = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        b = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.041])
        assert a.source_sha() != b.source_sha()

    def test_different_day_count_changes_sha(self) -> None:
        """Two curves differing only in day_count have different SHAs."""
        a = Curve.from_zero_rates(
            tenors=[1.0, 5.0],
            rates=[0.03, 0.04],
            day_count=Actual365Fixed(),
        )
        b = Curve.from_zero_rates(
            tenors=[1.0, 5.0],
            rates=[0.03, 0.04],
            day_count=Actual360(),
        )
        assert a.source_sha() != b.source_sha()

    def test_shifted_curve_has_different_sha(self) -> None:
        """A shifted Curve has a different SHA from the original."""
        a = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        b = a.shift_parallel(bps=100)
        assert a.source_sha() != b.source_sha()

    def test_sha_format_is_sha256_hex(self) -> None:
        """source_sha format is `sha256:<64-hex>`."""
        c = Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])
        sha = c.source_sha()
        assert sha.startswith("sha256:")
        assert len(sha) == len("sha256:") + 64
