# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""StateRef + PointRef typed references."""

from __future__ import annotations

import pytest

from gaspatchio_core.rollforward._refs import PointRef, StateRef


class TestStateRef:
    def test_basic_construction(self) -> None:
        r = StateRef(state="av", point="post_coi")
        assert r.state == "av"
        assert r.point == "post_coi"

    def test_canonical_name(self) -> None:
        assert StateRef(state="av", point="post_coi").canonical_name() == "av@post_coi"

    def test_equal_refs_hash_equal(self) -> None:
        a = StateRef(state="av", point="bop")
        b = StateRef(state="av", point="bop")
        assert a == b
        assert hash(a) == hash(b)

    def test_is_frozen(self) -> None:
        r = StateRef(state="av", point="bop")
        with pytest.raises(Exception):
            r.state = "guarantee"  # type: ignore[misc]

    def test_state_required_nonempty(self) -> None:
        with pytest.raises(ValueError, match="state name"):
            StateRef(state="", point="bop")

    def test_point_required_nonempty(self) -> None:
        with pytest.raises(ValueError, match="point name"):
            StateRef(state="av", point="")


class TestPointRef:
    def test_construction_and_canonical_name(self) -> None:
        p = PointRef(name="post_coi")
        assert p.name == "post_coi"
        assert p.canonical_name() == "post_coi"

    def test_equality(self) -> None:
        assert PointRef(name="bop") == PointRef(name="bop")
        assert PointRef(name="bop") != PointRef(name="eop")

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="point name"):
            PointRef(name="")
