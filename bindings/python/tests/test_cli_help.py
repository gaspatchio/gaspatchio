# ABOUTME: Tests for gspio --help output.
# ABOUTME: Validates command groups and LLM guidance text.
"""Tests for gspio --help output."""

from typer.testing import CliRunner

from gaspatchio_core.cli import app

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
