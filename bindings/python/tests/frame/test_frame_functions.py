# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


@pytest.fixture
def sample_eager_frame() -> pl.DataFrame:
    df = pl.DataFrame(
        {
            "foo": [1, 2, 3],
            "bar": [6, 7, 8],
            "ham": ["b", "a", "c"],
        },
    )
    return df


def test_max(sample_eager_frame):
    af = ActuarialFrame(sample_eager_frame)
    assert af.max()["bar"] == 8
    assert af.max()["foo"] == 3
    assert af.max()["ham"] == "c"


def test_min(sample_eager_frame):
    af = ActuarialFrame(sample_eager_frame)
    assert af.min()["bar"] == 6
    assert af.min()["foo"] == 1
    assert af.min()["ham"] == "a"


def test_mean(sample_eager_frame):
    af = ActuarialFrame(sample_eager_frame)
    assert af.mean()["bar"] == 7.0
    assert af.mean()["foo"] == 2.0
    # Note: mean() on string columns returns None in Polars
    assert af.mean()["ham"] is None


def test_std(sample_eager_frame):
    af = ActuarialFrame(sample_eager_frame)
    assert af.std()["bar"] == 1.0
    assert af.std()["foo"] == 1.0
    assert af.std()["ham"] is None


def test_var(sample_eager_frame):
    af = ActuarialFrame(sample_eager_frame)
    assert af.var()["bar"] == 1.0
    assert af.var()["foo"] == 1.0
    assert af.var()["ham"] is None


def test_median(sample_eager_frame):
    af = ActuarialFrame(sample_eager_frame)
    assert af.median()["bar"] == 7.0
    assert af.median()["foo"] == 2.0
    assert af.median()["ham"] is None


def test_sum(sample_eager_frame):
    af = ActuarialFrame(sample_eager_frame)
    assert af.sum()["bar"] == 21
    assert af.sum()["foo"] == 6
    assert af.sum()["ham"] is None


def test_count(sample_eager_frame):
    af = ActuarialFrame(sample_eager_frame)
    assert af.count()["bar"] == 3
    assert af.count()["foo"] == 3
    assert af.count()["ham"] == 3


def test_product(sample_eager_frame):
    af = ActuarialFrame(sample_eager_frame)
    assert af.product()["bar"] == 336  # 6 * 7 * 8
    assert af.product()["foo"] == 6    # 1 * 2 * 3
    assert af.product()["ham"] is None


def test_quantile():
    # Create a frame with more data points for quantile testing
    data = {
        "values": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "scores": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    }
    af = ActuarialFrame(data)
    
    # Test 25th percentile (with nearest interpolation)
    q25 = af.quantile(0.25)
    assert q25["values"] == 3.0
    assert q25["scores"] == 30.0
    
    # Test 75th percentile (with nearest interpolation)
    q75 = af.quantile(0.75)
    assert q75["values"] == 8.0
    assert q75["scores"] == 80.0
    
    # Test median (50th percentile with nearest interpolation)
    q50 = af.quantile(0.5)
    assert q50["values"] == 6.0  # With nearest, it picks the higher value for even count
    assert q50["scores"] == 60.0
