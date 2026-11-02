# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for query-plan logging, rendered from the calculation log
# ABOUTME: Covers step rendering, source lines, the verbose gate, and explain failures
# ruff: noqa: ARG002

"""Tests for ``log_query_plan``, the verbose rendering of a traced run.

A traced run under verbose logging prints what the model calculated, in
order, each step followed by the line of the user's own source that asked
for it. The steps come from the frame's durable calculation log -- the same
records error attribution and the calc-graph export read -- so there is one
account of what a model did, not a parallel one kept for logging.
"""

from unittest.mock import Mock, patch

import polars as pl

from gaspatchio._semantic.ir import Col
from gaspatchio.frame.calculations import CalculationRecord, SourceSpan
from gaspatchio.frame.tracing import log_query_plan


def _record(column: str, expr: pl.Expr, source: SourceSpan | None) -> CalculationRecord:
    """Build one calculation record, the way an assignment would."""
    return CalculationRecord(
        column=column,
        ordinal=1,
        operation_id=0,
        node=Col(name=column),
        expr=expr,
        dtype=None,
        source=source,
        origin="assignment",
    )


def _span(file: str, line: int, statement: str) -> SourceSpan:
    """Build one source span pointing at a model's own line."""
    return SourceSpan(
        file=file,
        line=line,
        end_line=line,
        function=None,
        statement=statement,
        rhs=None,
        target_literal=True,
    )


class TestLogQueryPlan:
    """The plan log is one numbered step per calculation, in order."""

    @patch("gaspatchio.frame.tracing.get_default_verbose", return_value=True)
    @patch("gaspatchio.frame.tracing.logger")
    def test_renders_one_numbered_step_per_record(self, mock_logger, mock_verbose):
        """Each record prints as ``Step n: <column> = <expression>``."""
        records = [
            _record(
                "death_claims", pl.col("sum_assured") * pl.col("mortality_rate"), None
            ),
            _record("expenses", pl.col("annual_premium") * 0.05, None),
        ]
        frame_df = pl.LazyFrame({"sum_assured": [100_000.0]})

        log_query_plan(records, frame_df)

        trace_calls = [call[0][0] for call in mock_logger.trace.call_args_list]
        assert any("Step 1: death_claims = " in call for call in trace_calls)
        assert any("Step 2: expenses = " in call for call in trace_calls)

    @patch("gaspatchio.frame.tracing.get_default_verbose", return_value=True)
    @patch("gaspatchio.frame.tracing.logger")
    def test_reports_the_source_line_of_each_record(self, mock_logger, mock_verbose):
        """A record's span names the model file and line that wrote it."""
        records = [
            _record(
                "death_claims",
                pl.col("sum_assured") * pl.col("mortality_rate"),
                _span("term_model.py", 10, "af.death_claims = ..."),
            ),
            _record(
                "expenses",
                pl.col("annual_premium") * 0.05,
                _span("term_model.py", 20, "af.expenses = ..."),
            ),
        ]
        frame_df = pl.LazyFrame({"sum_assured": [100_000.0]})

        log_query_plan(records, frame_df)

        trace_calls = [call[0][0] for call in mock_logger.trace.call_args_list]
        assert any("Source: term_model.py:10" in call for call in trace_calls)
        assert any("Source: term_model.py:20" in call for call in trace_calls)

    @patch("gaspatchio.frame.tracing.get_default_verbose", return_value=True)
    @patch("gaspatchio.frame.tracing.logger")
    def test_renders_a_notebook_cell_by_its_number(self, mock_logger, mock_verbose):
        """A cell's machine filename becomes the cell an actuary can look at."""
        records = [
            _record(
                "death_claims",
                pl.col("sum_assured") * pl.col("mortality_rate"),
                _span("<ipython-input-3-abc123>", 4, "af.death_claims = ..."),
            ),
        ]
        frame_df = pl.LazyFrame({"sum_assured": [100_000.0]})

        log_query_plan(records, frame_df)

        trace_calls = [call[0][0] for call in mock_logger.trace.call_args_list]
        assert any("Source: Jupyter Cell 3:4" in call for call in trace_calls)

    @patch("gaspatchio.frame.tracing.get_default_verbose", return_value=True)
    @patch("gaspatchio.frame.tracing.logger")
    def test_a_record_without_a_span_still_prints_its_step(
        self, mock_logger, mock_verbose
    ):
        """An unresolvable source is reported as absent, not as a placeholder."""
        records = [_record("death_claims", pl.col("sum_assured"), None)]
        frame_df = pl.LazyFrame({"sum_assured": [100_000.0]})

        log_query_plan(records, frame_df)

        trace_calls = [call[0][0] for call in mock_logger.trace.call_args_list]
        assert any("Step 1: death_claims = " in call for call in trace_calls)
        assert not any("Source:" in call for call in trace_calls)

    @patch("gaspatchio.frame.tracing.get_default_verbose", return_value=False)
    @patch("gaspatchio.frame.tracing.logger")
    def test_no_logging_when_verbose_disabled(self, mock_logger, mock_verbose):
        """Test that nothing is logged when verbose mode is disabled."""
        records = [_record("death_claims", pl.col("sum_assured"), None)]
        frame_df = pl.LazyFrame({"sum_assured": [100_000.0]})

        log_query_plan(records, frame_df)

        # Should not call logger.trace when verbose is disabled
        mock_logger.trace.assert_not_called()

    @patch("gaspatchio.frame.tracing.get_default_verbose", return_value=True)
    @patch("gaspatchio.frame.tracing.logger")
    def test_query_plan_explanation_error_handling(self, mock_logger, mock_verbose):
        """Test handling of errors during query plan explanation."""
        records = [_record("death_claims", pl.col("sum_assured"), None)]
        frame_df = Mock()
        frame_df.explain.side_effect = Exception("Explain failed")

        log_query_plan(records, frame_df)

        # Should log a warning when explain fails
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args[0][0]
        assert "Could not explain query plan" in warning_call
