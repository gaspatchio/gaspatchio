# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The common batch boundary preserves bounded state and attributes collect errors."""

from __future__ import annotations

from typing import NoReturn

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import _batch


def test_batch_collection_never_enters_ordinary_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    af = ActuarialFrame({"amount": [2.0, 3.0]})
    af.value = af.amount * 2
    af.value = af.value + 1

    def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        pytest.fail("bounded collection retained an ordinary completion")

    monkeypatch.setattr(ActuarialFrame, "_complete_collection", forbidden)
    result, peak = _batch._collect_batch(af, engine="streaming")  # noqa: SLF001
    assert result.columns == ["amount", "value"]
    assert result["value"].to_list() == [5.0, 7.0]
    assert peak >= 0
    assert af.graph.last_run is None
    assert af._collected_values is None  # noqa: SLF001 -- bounded lifetime
    assert af._retained_values is None  # noqa: SLF001 -- bounded lifetime


def test_batch_failure_reaches_attribution_with_its_own_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    af = ActuarialFrame({"amount": [2.0]})
    # Construct a real invalid lazy plan; resolving it belongs to the boundary.
    af._df = af._df.select(pl.col("absent"))  # noqa: SLF001 -- failure witness
    seen: list[tuple[ActuarialFrame, Exception]] = []

    def attribute(frame: ActuarialFrame, error: Exception) -> NoReturn:
        seen.append((frame, error))
        raise error

    monkeypatch.setattr(_batch, "_handle_execution_error", attribute)
    with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
        _batch._collect_batch(af, engine="in-memory")  # noqa: SLF001
    assert seen == [(af, caught.value)]
    assert af.graph.last_run is None
