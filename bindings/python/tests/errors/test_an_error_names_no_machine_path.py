# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A failed lookup names the lookup, not the directory the extension sits in.

Polars names a plugin call by the library it was loaded from, so a lookup
miss read ``col("age")./home/<name>/.../_internal.cpython-313-darwin.so:
lookup_by_table_and_hash()`` -- the reader's home directory, in every log the
error reached. The message now carries the record's own stand-in,
``<plugin>:lookup_by_table_and_hash()``, whichever error mode enhances it and
whether the frame or ``run_aggregated`` collected it; ``AF_ERROR_MODE=off``
still hands the engine's exception over untouched.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, _internal
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import Sum, run_aggregated

_EXTENSION_DIRECTORY = str(Path(_internal.__file__).parent)
_NAMED_LOOKUP = 'col("age").<plugin>:lookup_by_table_and_hash()'

_RATES = Table(
    name="machine_path_mortality",
    source=pl.DataFrame({"age": [40, 41], "rate": [0.01, 0.02]}),
    dimensions={"age": "age"},
    value="rate",
)
_BOOK = pl.DataFrame({"policy_id": ["A", "B"], "age": [40, 99]})


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af.rate = _RATES.lookup(age=af.age)
    return af


@pytest.mark.parametrize("mode", ["enhanced", "basic", "debug"])
def test_a_lookup_miss_names_the_lookup_and_no_path(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("AF_ERROR_MODE", mode)
    af = _model(ActuarialFrame(_BOOK))

    with pytest.raises(pl.exceptions.ComputeError) as raised:
        af.collect()

    message = str(raised.value)
    assert "(age=99)" in message
    assert _NAMED_LOOKUP in message
    assert _EXTENSION_DIRECTORY not in message


def test_a_lookup_miss_in_a_batched_fold_names_no_path() -> None:
    with pytest.raises(pl.exceptions.ComputeError) as raised:
        run_aggregated(_model, _BOOK, [Sum("rate").alias("rate")], batch_size=1)

    message = str(raised.value)
    assert _NAMED_LOOKUP in message
    assert _EXTENSION_DIRECTORY not in message


def test_off_still_hands_the_engine_s_message_over_as_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AF_ERROR_MODE", "off")
    af = _model(ActuarialFrame(_BOOK))

    with pytest.raises(pl.exceptions.ComputeError) as raised:
        af.collect()

    assert _EXTENSION_DIRECTORY in str(raised.value)
