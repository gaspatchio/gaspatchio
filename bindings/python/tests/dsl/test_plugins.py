import importlib
import importlib.metadata
import logging
from unittest import mock

import polars as pl
import pytest

# Import the registration decorator *after* core components are defined
# Also import the module itself to allow reloading
from gaspatchio_core.dsl import plugins

# Import core components *before* defining and registering accessors
from gaspatchio_core.dsl.core import ActuarialFrame, ExpressionProxy
from gaspatchio_core.dsl.plugins import ENTRY_POINT_GROUP, register_accessor

# --- Define Dummy Accessors ---


class BaseAccessor:
    def __init__(self, obj):
        self._obj = obj


@register_accessor("risk", kind="column")
class RiskColumnAccessor(BaseAccessor):
    def calculate_var(self, percentile: float) -> ExpressionProxy:
        # Dummy implementation, just adds a literal
        return self._obj + pl.lit(percentile)

    def describe(self) -> str:
        return f"Risk accessor for {type(self._obj).__name__}"


@register_accessor("risk", kind="frame")
class RiskFrameAccessor(BaseAccessor):
    def overall_exposure(self) -> float:
        # Dummy implementation
        return 1_000_000.0

    def get_frame(self) -> ActuarialFrame:
        return self._obj


# --- ADDED: Dummy accessors for entry point testing (NOT decorated) ---
class DiscoveredFrameAccessor(BaseAccessor):
    def frame_plugin_method(self):
        return "Discovered Frame OK"


class DiscoveredColumnAccessor(BaseAccessor):
    def column_plugin_method(self):
        return "Discovered Column OK"


# --- Test Cases ---


@pytest.fixture
def sample_af() -> ActuarialFrame:
    "Provides a sample ActuarialFrame for testing."
    data = pl.DataFrame({"colA": [1, 2, 3], "colB": [4.0, 5.5, 6.0]})
    return ActuarialFrame(data)


def test_frame_accessor_registration(sample_af):
    "Test that frame accessors are registered and usable."
    assert hasattr(sample_af, "risk")
    accessor = sample_af.risk
    assert isinstance(accessor, RiskFrameAccessor)
    assert accessor.overall_exposure() == 1_000_000.0
    assert accessor.get_frame() is sample_af
    assert "risk" in dir(sample_af)


def test_column_accessor_registration_on_column_proxy(sample_af):
    "Test that column accessors are registered and usable via ColumnProxy."
    col_proxy = sample_af["colA"]
    assert hasattr(col_proxy, "risk")
    accessor = col_proxy.risk
    assert isinstance(accessor, RiskColumnAccessor)
    assert accessor.describe() == "Risk accessor for ColumnProxy"
    assert "risk" in dir(col_proxy)

    # Test calling a method that returns an ExpressionProxy
    expr_proxy = accessor.calculate_var(0.95)
    assert isinstance(expr_proxy, ExpressionProxy)

    # Check the resulting expression (optional, depends on dummy logic)
    result_df = sample_af.collect()
    result_df = result_df.with_columns(expr_proxy._expr.alias("var_result"))
    expected = result_df["colA"] + 0.95
    assert result_df["var_result"].equals(expected)


def test_column_accessor_registration_on_expression_proxy(sample_af):
    "Test that column accessors are registered and usable via ExpressionProxy."
    expr_proxy = sample_af["colB"] * 2
    assert hasattr(expr_proxy, "risk")
    accessor = expr_proxy.risk
    assert isinstance(accessor, RiskColumnAccessor)
    assert accessor.describe() == "Risk accessor for ExpressionProxy"
    assert "risk" in dir(expr_proxy)

    # Test calling a method that returns another ExpressionProxy
    new_expr_proxy = accessor.calculate_var(0.99)
    assert isinstance(new_expr_proxy, ExpressionProxy)

    # Check the resulting expression (optional, depends on dummy logic)
    result_df = sample_af.collect()
    result_df = result_df.with_columns(new_expr_proxy._expr.alias("expr_var_result"))
    expected = (result_df["colB"] * 2) + 0.99
    assert result_df["expr_var_result"].equals(expected)


# Test potential name collision warning (optional)
def test_accessor_re_registration_warning(caplog):
    # Set log level to capture warnings
    caplog.set_level(logging.WARNING)

    @register_accessor("risk", kind="frame")
    class AnotherRiskFrameAccessor(BaseAccessor):
        def new_method(self):
            return "new"

    # Verify the warning message was logged
    assert (
        "Accessor 'risk' of kind 'frame' is already registered. Overwriting."
        in caplog.text
    )
    # Verify the *new* accessor is now active
    af = ActuarialFrame()
    assert hasattr(af.risk, "new_method")


# Test invalid kind error
def test_invalid_kind_error():
    with pytest.raises(ValueError, match=r"Invalid accessor kind: 'invalid'"):

        @register_accessor("invalid_test", kind="invalid")  # type: ignore
        class InvalidAccessor:
            pass


# Test decorating non-class error
def test_decorating_non_class_error():
    with pytest.raises(TypeError, match="Accessor must be a class."):

        @register_accessor("non_class_test", kind="frame")
        def not_a_class_accessor():
            pass


# --- ADDED: Entry Point Discovery Test ---
def test_entry_point_discovery():
    "Test that accessors defined via entry points are discovered and registered."
    # Create mock EntryPoint objects
    mock_frame_ep = mock.Mock(spec=importlib.metadata.EntryPoint)
    mock_frame_ep.name = "frame.discovered_frame"
    mock_frame_ep.load.return_value = DiscoveredFrameAccessor

    mock_column_ep = mock.Mock(spec=importlib.metadata.EntryPoint)
    mock_column_ep.name = "column.discovered_column"
    mock_column_ep.load.return_value = DiscoveredColumnAccessor

    mock_invalid_name_ep = mock.Mock(spec=importlib.metadata.EntryPoint)
    mock_invalid_name_ep.name = "invalidkind.whatever"
    # .load shouldn't be called for this one

    mock_bad_load_ep = mock.Mock(spec=importlib.metadata.EntryPoint)
    mock_bad_load_ep.name = "frame.badload"
    mock_bad_load_ep.load.side_effect = ImportError("Test import error")

    # Patch importlib.metadata.entry_points to return our mocks for the specific group
    with mock.patch(
        "importlib.metadata.entry_points",
        return_value=[
            mock_frame_ep,
            mock_column_ep,
            mock_invalid_name_ep,
            mock_bad_load_ep,
        ],
    ) as mock_ep:
        # Reload the plugins module to trigger discovery with the mocked entry points
        # This is crucial because discovery runs on initial import.
        importlib.reload(plugins)

        # Verify importlib.metadata.entry_points was called correctly
        mock_ep.assert_called_once_with(group=ENTRY_POINT_GROUP)

    # Create a sample frame *after* discovery
    af = ActuarialFrame({"x": [1]})
    col_proxy = af["x"]
    expr_proxy = af["x"] + 1

    # --- Assertions ---
    # Check discovered frame accessor
    assert hasattr(af, "discovered_frame")
    assert isinstance(af.discovered_frame, DiscoveredFrameAccessor)
    assert af.discovered_frame.frame_plugin_method() == "Discovered Frame OK"
    assert "discovered_frame" in dir(af)

    # Check discovered column accessor on ColumnProxy
    assert hasattr(col_proxy, "discovered_column")
    assert isinstance(col_proxy.discovered_column, DiscoveredColumnAccessor)
    assert col_proxy.discovered_column.column_plugin_method() == "Discovered Column OK"
    assert "discovered_column" in dir(col_proxy)

    # Check discovered column accessor on ExpressionProxy
    assert hasattr(expr_proxy, "discovered_column")
    assert isinstance(expr_proxy.discovered_column, DiscoveredColumnAccessor)
    assert expr_proxy.discovered_column.column_plugin_method() == "Discovered Column OK"
    assert "discovered_column" in dir(expr_proxy)

    # Check that invalid/bad entry points didn't register anything unexpected
    assert not hasattr(af, "whatever")
    assert not hasattr(af, "badload")
    assert "whatever" not in dir(af)
    assert "badload" not in dir(af)
