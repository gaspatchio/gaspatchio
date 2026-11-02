# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Calculation graph functionality for ActuarialFrame operations.

This package provides tools for building, analyzing, and exporting
directed acyclic graphs (DAGs) folded from the calculation record an
ActuarialFrame keeps as the model is written.
"""

from .artifact import (
    ARTIFACT_FILE_NAME,
    DOCUMENT_DIGEST_FIELD,
    FINGERPRINT_ALGORITHM,
    PAYLOAD_DIRECTORY,
    PROFILE_AUDIT,
    PROFILE_EXECUTABLE,
    SCHEMA_ID,
    SEAL_BY_DEFAULT,
    SOURCE_DIRECTORY,
    build_artifact,
    document_digest_of,
    payload_bytes,
    payload_file_name,
    source_payload_of,
)
from .assumptions import (
    ArtefactKind,
    ArtefactReference,
    artefacts_read,
    assumptions_read_by_node,
)
from .calc_graph import GraphExporter, GraphFrameAccessor, node_accounting
from .diff import (
    DIFF_REPORT_VERSION,
    Change,
    ChangeKind,
    ChangeOrigin,
    ComparedDocument,
    DataChange,
    DataKind,
    DiffReport,
    ModuleMoved,
    SourceChange,
    diff_artifacts,
)
from .diff_results import diff_with_results
from .edges import (
    AGGREGATING_CALLS,
    AGGREGATING_METHODS,
    EdgeClass,
    EdgeSubtype,
    EdgeType,
    classify_reads,
)
from .execution import (
    ExecutionFinding,
    ExecutionInspection,
    InputRequirement,
    inspect_execution,
)
from .expr_analyzer import analyze_expression_tree, extract_dependencies
from .facets import PRODUCER_URI, SCHEMA_URL_TEMPLATE, FacetLedger, facet
from .fingerprint import (
    NodeFingerprints,
    canonical_bytes,
    fingerprint,
    fingerprints_for,
    formulas_fingerprint,
    graph_fingerprint,
    local_fingerprint,
    short_fingerprint,
    stamp_fingerprints,
)
from .graph_builder import CalcGraph, fold
from .graph_models import (
    GraphEdge,
    GraphExportConfig,
    GraphNode,
    HoleReason,
    ModelIdentity,
    NodeData,
    NodeId,
    NodeType,
    Provenance,
)
from .holes import Hole, find_holes, holes_in
from .lineage import Unused
from .op_json import op_node_from_json, op_node_to_json
from .tiers import TIERS, OpTier, TierCensus, tier_of
from .validate import (
    KNOWN_FACETS,
    REPORT_VERSION,
    Finding,
    Section,
    Severity,
    ValidationReport,
    validate_artifact,
)
from .values_moved import LineValues, ValuesReport
from .verify import (
    VERIFICATION_REPORT_VERSION,
    Check,
    CheckOutcome,
    VerificationReport,
    verify_artifact,
)
from .xlsx_export import render_xlsx

__all__ = [
    "AGGREGATING_CALLS",
    "AGGREGATING_METHODS",
    "ARTIFACT_FILE_NAME",
    "DIFF_REPORT_VERSION",
    "DOCUMENT_DIGEST_FIELD",
    "FINGERPRINT_ALGORITHM",
    "KNOWN_FACETS",
    "PAYLOAD_DIRECTORY",
    "PRODUCER_URI",
    "PROFILE_AUDIT",
    "PROFILE_EXECUTABLE",
    "REPORT_VERSION",
    "SCHEMA_ID",
    "SCHEMA_URL_TEMPLATE",
    "SEAL_BY_DEFAULT",
    "SOURCE_DIRECTORY",
    "TIERS",
    "VERIFICATION_REPORT_VERSION",
    "ArtefactKind",
    "ArtefactReference",
    "CalcGraph",
    "Change",
    "ChangeKind",
    "ChangeOrigin",
    "Check",
    "CheckOutcome",
    "ComparedDocument",
    "DataChange",
    "DataKind",
    "DiffReport",
    "EdgeClass",
    "EdgeSubtype",
    "EdgeType",
    "ExecutionFinding",
    "ExecutionInspection",
    "FacetLedger",
    "Finding",
    "GraphEdge",
    "GraphExportConfig",
    "GraphExporter",
    "GraphFrameAccessor",
    "GraphNode",
    "Hole",
    "HoleReason",
    "InputRequirement",
    "LineValues",
    "ModelIdentity",
    "ModuleMoved",
    "NodeData",
    "NodeFingerprints",
    "NodeId",
    "NodeType",
    "OpTier",
    "Provenance",
    "Section",
    "Severity",
    "SourceChange",
    "TierCensus",
    "Unused",
    "ValidationReport",
    "ValuesReport",
    "VerificationReport",
    "analyze_expression_tree",
    "artefacts_read",
    "assumptions_read_by_node",
    "build_artifact",
    "canonical_bytes",
    "classify_reads",
    "diff_artifacts",
    "diff_with_results",
    "document_digest_of",
    "extract_dependencies",
    "facet",
    "find_holes",
    "fingerprint",
    "fingerprints_for",
    "fold",
    "formulas_fingerprint",
    "graph_fingerprint",
    "holes_in",
    "inspect_execution",
    "local_fingerprint",
    "node_accounting",
    "op_node_from_json",
    "op_node_to_json",
    "payload_bytes",
    "payload_file_name",
    "render_xlsx",
    "short_fingerprint",
    "source_payload_of",
    "stamp_fingerprints",
    "tier_of",
    "validate_artifact",
    "verify_artifact",
]
