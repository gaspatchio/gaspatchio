from pathlib import Path

import pytest

# Ensure reset_global_registry is imported if needed
# Import ActuarialFrame via the facade

# CORRECTED: Import init_logging from _internal temporarily
try:
    from gaspatchio_core._internal import init_logging
except ImportError:
    print("Warning: Could not import init_logging from Rust bindings.")

    def init_logging(*args, **kwargs):
        pass  # Dummy implementation

# Import Assumption related classes directly for testing

# Define test directory relative to this file
TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"


@pytest.fixture(autouse=True)
def setup_logging():
    """Ensure logging is configured for tests."""
    # init_logging(level=logging.DEBUG) # Or configure as needed
    pass  # Temporarily disable explicit init during refactor if causing issues
