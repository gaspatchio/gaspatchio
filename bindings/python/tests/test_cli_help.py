# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for gspio --help output.
# ABOUTME: Validates command groups and LLM guidance text.
"""Tests for gspio --help output."""

import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app

runner = CliRunner()


class TestMainHelp:
    """Tests for the main --help output."""

    def test_main_help_shows_knowledge_discovery_section(self):
        """Main --help shows Knowledge Discovery command group."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Knowledge Discovery" in result.output

    def test_main_help_shows_model_execution_section(self):
        """Main --help shows Model Execution command group."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Model Execution" in result.output

    def test_main_help_shows_data_inspection_section(self):
        """Main --help shows Data Inspection command group."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Data Inspection" in result.output

    def test_main_help_shows_prefer_search_guidance(self):
        """Main --help includes guidance to prefer search over --answer."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Check for the guidance text
        assert (
            "prefer search results" in result.output.lower()
            or "always prefer" in result.output.lower()
        )

    def test_main_help_shows_when_building_guidance(self):
        """Main --help includes 'When building a model' guidance."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert (
            "when building" in result.output.lower()
            or "when you need to find" in result.output.lower()
        )

    def test_main_help_shows_docs_and_knowledge_commands(self):
        """Main --help lists docs and knowledge commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "docs" in result.output
        assert "knowledge" in result.output

    def test_main_help_shows_usage_examples(self):
        """Main --help includes usage examples."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Should have some example commands
        assert "gspio" in result.output
        # Should have examples section
        assert "example" in result.output.lower()


class TestViewerExtraNamed:
    """The --html help names the extra it needs, brackets and all."""

    @pytest.mark.parametrize("command", ["calc-graph", "diff"])
    def test_html_help_names_the_viewer_extra(self, command: str):
        """``gaspatchio[viewer]`` survives rich markup in the help text.

        Rich reads ``[viewer]`` as a style tag, and the unescaped help printed
        "needs the gaspatchio extra" -- an install line that installs nothing
        the page needs. Whitespace and the panel's borders are dropped before
        the search, so a narrow terminal folding the name cannot hide it.
        """
        result = runner.invoke(app, [command, "--help"], env={"COLUMNS": "200"})
        assert result.exit_code == 0
        flattened = "".join(result.output.replace("\u2502", "").split())
        assert "needsthegaspatchio[viewer]extra" in flattened, result.output


class TestAuditPanel:
    """The commands that read or write an audit file are listed together."""

    _AUDIT = ("calc-graph", "validate", "diff", "sheet", "compare", "verify", "graph")

    def _panels(self) -> dict[str, list[str]]:
        result = runner.invoke(app, ["--help"], env={"COLUMNS": "200"})
        assert result.exit_code == 0
        panels: dict[str, list[str]] = {}
        current: str | None = None
        for line in result.output.splitlines():
            if line.startswith("╭─ "):
                current = line.split("─ ", 1)[1].split(" ─", 1)[0]
                panels[current] = []
            elif line.startswith("╰"):
                current = None
            elif current is not None:
                words = line.strip("│ ").split()
                if words:
                    panels[current].append(words[0])
        return panels

    def test_the_audit_commands_sit_under_one_panel(self):
        """calc-graph sat under Model Execution, the rest under Data Inspection."""
        panels = self._panels()
        assert set(self._AUDIT) <= set(panels["Audit"])
        assert "calc-graph" not in panels["Model Execution"]
        assert panels["Data Inspection"] == ["describe"]

    @pytest.mark.parametrize(
        "command", ["run-model", "run-single-policy", "calc-graph", "run-artifact"]
    )
    def test_the_policy_id_help_names_the_columns_it_looks_for(self, command: str):
        """'auto-detected if omitted' named nothing a reader could check."""
        result = runner.invoke(app, [command, "--help"], env={"COLUMNS": "200"})
        assert result.exit_code == 0
        flattened = " ".join(result.output.replace("│", " ").split())
        assert "auto-detected" not in flattened
        assert (
            "policy_id, policy_number, policy number, policyid, pol_id, point_id "
            "or id, the first the book carries, in any case"
        ) in flattened
