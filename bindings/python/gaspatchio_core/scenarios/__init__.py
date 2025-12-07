# ABOUTME: Scenario support module for multi-scenario actuarial model execution.
# ABOUTME: Provides scenario expansion, batching, and audit trail functions.

"""Scenario support module for multi-scenario actuarial model execution."""

from ._batching import batch_scenarios
from ._describe import describe_scenarios
from ._sensitivity import sensitivity_analysis
from ._with_scenarios import with_scenarios

__all__ = [
    "batch_scenarios",
    "describe_scenarios",
    "sensitivity_analysis",
    "with_scenarios",
]
