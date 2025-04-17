"""
Gaspatchio Core - Actuarial computation framework
"""

# Import key components for easier access
from gaspatchio_core.telemetry import (
    PerformanceViolationError,
    configure_telemetry,
)

# Enable telemetry by default
configure_telemetry(enable=True)
