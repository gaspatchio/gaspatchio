# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Data models for calculation graph components.

This module provides Pydantic models for type-safe graph construction.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Types of nodes in the calculation graph."""

    INPUT = "input"
    COMPUTED = "computed"


class DataSource(str, Enum):
    """Sources of data for input nodes."""

    MODEL_POINTS = "model_points"
    ASSUMPTIONS = "assumptions"
    INFERRED = "inferred"


class ListBroadcastMetadata(BaseModel):
    """Metadata for list broadcasting operations using explode/re-aggregate pattern."""

    result_column: str = Field(description="Name of the result column being created")
    list_columns: list[str] = Field(description="List columns that were exploded")
    conditional_expr: str = Field(
        description="String representation of conditional expression"
    )
    pattern_steps: list[str] = Field(
        default_factory=list,
        description=(
            "Steps in the pattern: with_row_index, explode, "
            "with_columns, group_by, agg, drop"
        ),
    )


class NodeData(BaseModel):
    """Data associated with a graph node."""

    dtype: str = Field(default="unknown", description="Data type of the node")
    source: DataSource | None = Field(default=None, description="Source of input data")
    dependencies: list[str] = Field(
        default_factory=list, description="Node dependencies"
    )
    formula: str | None = Field(default=None, description="Computation formula")
    source_location: str | None = Field(
        default=None, description="Source code location"
    )
    value_sample: Any | None = Field(default=None, description="Sample value from data")
    trace: list[dict[str, Any]] | None = Field(
        default=None, description="Calculation trace"
    )
    list_broadcast: ListBroadcastMetadata | None = Field(
        default=None, description="Metadata for list broadcasting operations"
    )


class GraphNode(BaseModel):
    """Represents a node in the calculation graph."""

    id: str = Field(description="Unique identifier for the node")
    type: NodeType = Field(description="Type of the node")
    label: str = Field(description="Display label for the node")
    data: NodeData = Field(description="Additional node data")


class GraphEdge(BaseModel):
    """Represents an edge (dependency) in the calculation graph."""

    source: str = Field(description="Source node ID")
    target: str = Field(description="Target node ID")


class GraphExportConfig(BaseModel):
    """Configuration for graph export operations."""

    policy_id: str | None = Field(
        default=None, description="Policy ID for sample values"
    )
    policy_id_column: str = Field(
        default="Policy number", description="Name of policy ID column"
    )
    filter_expr: str | None = Field(
        default=None, description="Polars filter expression"
    )
    include_traces: bool = Field(default=True, description="Whether to generate traces")
