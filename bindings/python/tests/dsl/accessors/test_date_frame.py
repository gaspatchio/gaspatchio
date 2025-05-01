import datetime

import polars as pl
import pytest
from gaspatchio_core.dsl.accessors.date import DateFrameAccessor

# Assuming ActuarialFrame and its accessors are importable
from gaspatchio_core.dsl.core import ActuarialFrame


@pytest.fixture
def sample_af() -> ActuarialFrame:
    """Provides a sample ActuarialFrame with date columns."""
    data = {
        "start_date": [datetime.date(2023, 1, 1), datetime.date(2023, 2, 15)],
        "end_date": [datetime.date(2024, 1, 1), datetime.date(2024, 2, 15)],
        "other_col": [1, 2],
    }
    return ActuarialFrame(pl.DataFrame(data))


def test_date_frame_accessor_exists(sample_af: ActuarialFrame):
    """Test that the .date accessor exists on ActuarialFrame and is the correct type."""
    # TODO: Add .date property to ActuarialFrame itself later
    # For now, instantiate directly
    accessor = DateFrameAccessor(sample_af)
    assert isinstance(accessor, DateFrameAccessor)
    assert accessor._frame is sample_af


def test_create_timeline_returns_new_actuarial_frame(sample_af: ActuarialFrame):
    """Test that create_timeline returns a new ActuarialFrame instance."""
    # Instantiate accessor directly for now
    accessor = DateFrameAccessor(sample_af)

    # Call the method
    new_af = accessor.create_timeline("start_date", "end_date")

    # Check return type
    assert isinstance(new_af, ActuarialFrame)

    # Check it's a *new* wrapper instance
    assert id(new_af) != id(sample_af)

    # This might change when actual logic is added
    # assert id(new_af._df) == id(sample_af._df)
    assert id(new_af._df) != id(sample_af._df)  # Expect a *new* LazyFrame

    # REMOVED: Check that the data is identical - this is wrong as timeline modifies it.
    # assert_frame_equal(new_af.collect(), sample_af.collect())


def test_create_timeline_requires_valid_columns(sample_af: ActuarialFrame):
    """Test that create_timeline raises an error if columns don't exist."""
    accessor = DateFrameAccessor(sample_af)

    # Error occurs during collect(), not necessarily during create_timeline()
    # The error handler formats the ColumnNotFoundError nicely.
    with pytest.raises(
        pl.ColumnNotFoundError, match="Column 'invalid_start' not found"
    ):
        new_af_invalid_start = accessor.create_timeline("invalid_start", "end_date")
        new_af_invalid_start.collect()  # Error happens here

    with pytest.raises(pl.ColumnNotFoundError, match="Column 'invalid_end' not found"):
        new_af_invalid_end = accessor.create_timeline("start_date", "invalid_end")
        new_af_invalid_end.collect()  # Error happens here
