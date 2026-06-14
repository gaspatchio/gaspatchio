# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test the shared canonical_bytes + source_sha_of helpers."""

from __future__ import annotations

import pytest

from gaspatchio_core._identity import canonical_bytes, source_sha_of


def test_canonical_bytes_sorts_keys():
    assert canonical_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_canonical_bytes_separators_compact():
    assert canonical_bytes({"a": 1}) == b'{"a":1}'


def test_canonical_bytes_rejects_nan():
    with pytest.raises(ValueError):
        canonical_bytes({"x": float("nan")})


def test_canonical_bytes_rejects_unknown_types():
    class Custom:
        pass

    with pytest.raises(TypeError):
        canonical_bytes({"x": Custom()})


def test_source_sha_of_format():
    sha = source_sha_of({"a": 1})
    assert sha.startswith("sha256:")
    assert len(sha) == len("sha256:") + 64


def test_source_sha_of_determinism():
    sha1 = source_sha_of({"a": 1, "b": 2})
    sha2 = source_sha_of({"b": 2, "a": 1})
    assert sha1 == sha2
