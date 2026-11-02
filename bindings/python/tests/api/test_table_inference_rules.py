# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What `gspio describe` infers about a file, pinned rule by rule.

`AGENTS.md` tells every agent and actuary to run `gspio describe` before
writing a line of model code, and names `--json` as the way to read a file's
shape — so what these rules answer is a contract, not an implementation
detail. Their docstrings in ``gaspatchio/_table_inference.py`` make specific
claims about where the rules fall back and where they guess; each one below is
that claim, driven.

Where a rule still guesses — the substring test a numeric key can win is the
one left — the test pins the guess rather than asking for a better answer, and
says so.
Where a rule now reports its runners-up instead of picking silently, the test
pins the runners-up: that is the contract an agent reads to decide whether to
ask the user which column holds the rate.
"""

import json
from pathlib import Path
from typing import Any

import polars as pl
from typer.testing import CliRunner

from gaspatchio._table_inference import (
    _VALUE_COLUMN_PATTERNS,
    CodeExamples,
    analyze_table_shape,
    build_describe_response,
    describe_table,
    detect_table_structure,
)
from gaspatchio.assumptions import analyze_table
from gaspatchio.assumptions._analysis import _SCAN_CELL_BUDGET
from gaspatchio.cli import app

runner = CliRunner()


class TestTheValueRuleReadsTheHeaderFirst:
    """Rule 1: the first NUMERIC header whose wording names a rate, normalised.

    The numeric filter is the half of the rule that arrived last, and it is
    what keeps a String id column from answering on its name: see
    `TestOneVerdictPrintedByBothSurfaces` for the shipped file it was measured
    on.
    """

    def test_a_rate_column_is_found_by_its_wording(self) -> None:
        guess = detect_table_structure(
            pl.DataFrame({"age": [30], "duration": [0], "rate": [0.01]}),
        )
        assert guess.name == "rate"
        assert guess.dimensions == {"age": "age", "duration": "duration"}

    def test_case_and_spaces_in_the_header_do_not_hide_it(self) -> None:
        guess = detect_table_structure(
            pl.DataFrame(
                {"Policy Number": [1], "Attained Age": [30], "Mortality Rate": [0.01]},
            ),
        )
        assert guess.name == "Mortality Rate"

    def test_wording_beats_position_even_when_the_rate_comes_first(self) -> None:
        guess = detect_table_structure(
            pl.DataFrame({"rate": [0.01], "age": [30], "duration": [0]}),
        )
        assert guess.name == "rate"
        assert guess.dimensions == {"age": "age", "duration": "duration"}

    def test_the_test_is_a_substring_so_a_key_can_win_it(self) -> None:
        """``premium_term`` is a term in years and is still taken as the rate.

        Pinned as a guess, not asked to be better, and now decided rather than
        left open: an ends-with rule answers this shape but moves 43 files of
        this repository's 136 tracked data files (46 with the numeric filter
        beside it), most of them no more right than before, against 11 for the
        numeric filter alone. The substring test stands; what the numeric
        filter takes out is a column that could not hold a rate at all.
        """
        guess = detect_table_structure(
            pl.DataFrame(
                {"premium_term": [10], "duration": [0], "annual_charge": [1.0]},
            ),
        )
        assert guess.name == "premium_term"


class TestTheValueRuleFallsBackToDtypeThenPosition:
    """Rules 2 and 3, for headers that name nothing the rule knows."""

    def test_the_last_numeric_column_wins_when_no_header_matches(self) -> None:
        guess = detect_table_structure(
            pl.DataFrame(
                {
                    "alpha": ["a"],
                    "beta": [1.0],
                    "gamma": [4.0],
                    "delta": ["p"],
                },
            ),
        )
        assert guess.name == "gamma"

    def test_the_last_column_wins_when_nothing_is_numeric_at_all(self) -> None:
        guess = detect_table_structure(
            pl.DataFrame({"alpha": ["a"], "beta": ["x"], "gamma": ["p"]}),
        )
        assert guess.name == "gamma"
        assert guess.dimensions == {"alpha": "alpha", "beta": "beta"}

    def test_a_single_column_file_names_that_column(self) -> None:
        guess = detect_table_structure(pl.DataFrame({"alpha": ["a"]}))
        assert guess.name == "alpha"
        assert guess.dimensions == {}


class TestTheShapeRuleCountsNumberLikeHeaders:
    """Wide or long, decided on the headers after the first."""

    def test_a_select_ultimate_grid_is_wide_on_its_durations(self) -> None:
        frame = pl.DataFrame(
            {
                "Age": [20],
                "0": [0.001],
                "1": [0.002],
                "2": [0.003],
                "3": [0.004],
                "4": [0.005],
                "Ult.": [0.006],
            },
        )
        assert analyze_table_shape(frame) == "wide"

    def test_two_numeric_headers_stay_long_and_three_tip_it(self) -> None:
        two = pl.DataFrame({"age": [1], "0": [0.1], "1": [0.2]})
        three = pl.DataFrame({"age": [1], "0": [0.1], "1": [0.2], "2": [0.3]})
        assert analyze_table_shape(two) == "long"
        assert analyze_table_shape(three) == "wide"

    def test_the_first_header_is_never_counted(self) -> None:
        """Four number-like headers, but column zero is skipped, so three count."""
        frame = pl.DataFrame({"0": [1], "1": [0.1], "2": [0.2], "3": [0.3]})
        assert analyze_table_shape(frame) == "wide"

        one_fewer = pl.DataFrame({"0": [1], "1": [0.1], "2": [0.2]})
        assert analyze_table_shape(one_fewer) == "long"

    def test_an_ordinary_long_table_is_long(self) -> None:
        frame = pl.DataFrame({"age": [30], "duration": [0], "rate": [0.01]})
        assert analyze_table_shape(frame) == "long"

    def test_a_frame_with_no_headers_is_called_long(self) -> None:
        assert analyze_table_shape(pl.DataFrame()) == "long"


class TestTheColumnTheUserNamedWins:
    """`--value-column` is a declaration, and no inference may overrule it.

    `PRINCIPLES.md` asks the framework to be strict about the meanings it
    infers. A meaning the user has already stated is not one to infer.
    """

    @staticmethod
    def _table(tmp_path: Path) -> Path:
        path = tmp_path / "two_rates.csv"
        path.write_text("age,M,F\n20,0.001,0.0008\n21,0.0011,0.0009\n")
        return path

    def test_the_payload_reports_the_column_the_user_named(
        self,
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(
            app,
            ["describe", "--json", "--value-column", "F", str(self._table(tmp_path))],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["detected_value_column"] == "F"
        assert payload["value_column_source"] == "declared"

    def test_the_suggested_code_uses_the_column_the_user_named(
        self,
        tmp_path: Path,
    ) -> None:
        """The snippet is what the user copies; it cannot say something else."""
        result = runner.invoke(
            app,
            ["describe", "--json", "--value-column", "F", str(self._table(tmp_path))],
        )
        payload = json.loads(result.stdout)
        assert 'value="F"' in payload["suggested_code"]
        assert "MeltDimension" not in payload["suggested_code"]

    def test_both_output_modes_name_the_same_column(self, tmp_path: Path) -> None:
        path = self._table(tmp_path)
        human = runner.invoke(app, ["describe", "--value-column", "F", str(path)])
        payload = json.loads(
            runner.invoke(
                app,
                ["describe", "--json", "--value-column", "F", str(path)],
            ).stdout,
        )
        assert "Value column: F" in human.output
        assert payload["detected_value_column"] == "F"

    def test_a_declared_column_is_never_reported_as_ambiguous(
        self,
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(
            app,
            ["describe", "--json", "--value-column", "F", str(self._table(tmp_path))],
        )
        assert json.loads(result.stdout)["value_column_candidates"] == []

    def test_naming_a_per_period_column_is_still_refused_with_the_way_out(
        self,
        tmp_path: Path,
    ) -> None:
        """The escape describes the scalar part; it cannot make a list the value."""
        path = tmp_path / "results.parquet"
        pl.DataFrame({"policy_id": [1], "cashflow": [[1.0, 2.0]]}).write_parquet(path)
        result = runner.invoke(
            app,
            ["describe", "--value-column", "cashflow", str(path)],
        )
        assert result.exit_code != 0
        assert "cannot be an assumption-table value" in result.output
        assert "policy_id" in result.output


class TestANameThatIsNotInTheFileSaysWhatItIs:
    """An agent must tell a column of the file from a name it will have later."""

    @staticmethod
    def _payload_for(
        frame: pl.DataFrame,
        name: str = "t.parquet",
        declared: str | None = None,
    ) -> dict[str, Any]:
        description = describe_table(frame, Path(name), declared)
        examples = CodeExamples(read_back="read-back", model_points="model-points")
        response = build_describe_response(description, examples)
        return json.loads(response.model_dump_json())

    def test_a_post_melt_name_is_labelled_as_one(self) -> None:
        """`value` is what the column is called AFTER melting, not before."""
        payload = self._payload_for(
            pl.DataFrame({"Age": [20], "0": [0.1], "1": [0.2], "2": [0.3], "3": [0.4]}),
        )
        assert payload["detected_value_column"] == "value"
        assert payload["value_column_source"] == "after_melt"
        assert payload["detected_value_column"] not in payload["columns"]

    def test_an_already_long_table_is_not_melted_into_its_own_value_column(
        self,
    ) -> None:
        """`band, duration, value` is long, and `value` is the rate it carries.

        The wide reading melts several columns into one called `value`, so a
        frame that already HAS a column of that name cannot take it. This
        payload used to mark the file's own `value` column as one of the
        columns to melt INTO `value`, mark the key `band` as melt beside it,
        and call the name `inferred` — three readings of one file in one
        document, against a human mode that reads it as a long table keyed on
        `band` and `duration`.
        """
        payload = self._payload_for(
            pl.DataFrame(
                {
                    "band": [1, 1, 2, 2],
                    "duration": [0, 1, 0, 1],
                    "value": [0.001, 0.0011, 0.002, 0.0021],
                },
            ),
        )
        assert payload["detected_value_column"] == "value"
        assert payload["value_column_source"] == "inferred"
        assert payload["detected_value_column"] in payload["columns"]
        marks = {
            dim["name"]: dim["suggested_type"] for dim in payload["detected_dimensions"]
        }
        assert marks == {"band": "key", "duration": "key"}
        assert "MeltDimension" not in payload["suggested_code"]

    def test_both_modes_read_an_already_long_table_the_same_way(
        self,
        tmp_path: Path,
    ) -> None:
        """The mode `AGENTS.md` points agents at said melt; the other said key."""
        path = tmp_path / "band_duration_value.csv"
        path.write_text("band,duration,value\n1,0,0.001\n1,1,0.0011\n2,0,0.002\n")
        human = " ".join(runner.invoke(app, ["describe", str(path)]).output.split())
        payload = json.loads(
            runner.invoke(app, ["describe", "--json", str(path)]).stdout,
        )
        assert "Value column: value" in human
        assert "Key columns: band, duration" in human
        assert payload["detected_value_column"] == "value"
        assert [dim["name"] for dim in payload["detected_dimensions"]] == [
            "band",
            "duration",
        ]

    def test_a_curve_table_marks_no_column_melt(self) -> None:
        """`melt` is a wide-table word, and the snippet it contradicts is its own.

        `suggest_table_config()` emits every non-value dimension of a curve
        table as a `DataDimension`, so a dimension the same object calls
        `melt` is the payload disagreeing with the code it offers.
        """
        payload = self._payload_for(
            pl.DataFrame(
                {
                    "age": [30, 31, 32],
                    "M": [0.001, 0.001, 0.002],
                    "F": [0.0008, 0.0009, 0.001],
                },
            ),
            declared="F",
        )
        marks = {
            dim["name"]: dim["suggested_type"] for dim in payload["detected_dimensions"]
        }
        assert marks == {"age": "key", "M": "key"}

    def test_an_inferred_column_of_the_file_is_labelled_inferred(self) -> None:
        payload = self._payload_for(
            pl.DataFrame({"age": [30, 31], "rate": [0.01, 0.02]}),
        )
        assert payload["detected_value_column"] == "rate"
        assert payload["value_column_source"] == "inferred"
        assert payload["detected_value_column"] in payload["columns"]

    def test_a_file_with_no_numeric_column_no_longer_invents_the_name_rate(
        self,
    ) -> None:
        """The old fallback named `rate` on a file whose columns are all text."""
        payload = self._payload_for(pl.DataFrame({"name": ["a"], "code": ["x"]}))
        assert payload["detected_value_column"] == "code"
        assert payload["value_column_source"] == "inferred"
        assert payload["detected_value_column"] in payload["columns"]

    def test_projection_output_reports_no_value_column_and_says_so(self) -> None:
        payload = self._payload_for(
            pl.DataFrame({"policy_id": [1], "cashflow": [[1.0, 2.0]]}),
        )
        assert payload["detected_value_column"] == ""
        assert payload["value_column_source"] == "none"
        assert payload["value_column_candidates"] == []


class TestADeclarationSurvivesTheModelPointVerdict:
    """`--value-column` on a model-point extract is the documented escape.

    `_table_inference`'s own module docstring holds it out as the way in: a
    file the rules would describe as results is described as a table when the
    user names one of its SCALAR columns as the value. `--json` dropped the
    declaration on that route and then answered `value_column_source: "none"`
    — *"there is no assumption table here to describe"* — over a declaration
    the user had just made, while human mode printed the column. `AGENTS.md`
    tells an agent to write projection output with `--output-file` and read it
    back with `describe --json`, so this is the shape that workflow produces.
    """

    @staticmethod
    def _frame() -> pl.DataFrame:
        return pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "month": [0, 1, 2],
                "cashflow": [1.0, 2.0, 3.0],
                "premium": [10.0, 11.0, 12.0],
            },
        )

    @staticmethod
    def _payload(frame: pl.DataFrame, declared: str | None) -> dict[str, Any]:
        description = describe_table(frame, Path("mp.parquet"), declared)
        return json.loads(
            build_describe_response(
                description,
                CodeExamples(read_back="read-back", model_points="model-points"),
            ).model_dump_json(),
        )

    def test_the_payload_reports_the_column_the_user_declared(self) -> None:
        payload = self._payload(self._frame(), "policy_id")
        assert payload["detected_value_column"] == "policy_id"
        assert payload["value_column_source"] == "declared"
        assert payload["table_shape"] != "model_points"

    def test_the_payload_offers_the_table_snippet_not_the_frame_one(self) -> None:
        """The snippet is the user's next move; it cannot ignore the declaration."""
        payload = self._payload(self._frame(), "policy_id")
        assert payload["suggested_code"] != "model-points"
        assert 'value="policy_id"' in payload["suggested_code"]

    def test_both_modes_name_the_declared_column(self, tmp_path: Path) -> None:
        path = tmp_path / "mp.parquet"
        self._frame().write_parquet(path)
        flag = ["--value-column", "policy_id", str(path)]
        human = " ".join(runner.invoke(app, ["describe", *flag]).output.split())
        payload = json.loads(runner.invoke(app, ["describe", "--json", *flag]).stdout)
        assert "Value column: policy_id" in human
        assert payload["detected_value_column"] == "policy_id"

    def test_without_the_flag_the_model_point_verdict_still_stands(self) -> None:
        """Only a declaration reaches past it; inference still says results."""
        payload = self._payload(self._frame(), None)
        assert payload["table_shape"] == "model_points"
        assert payload["detected_value_column"] == ""
        assert payload["value_column_source"] == "none"
        assert payload["suggested_code"] == "model-points"


class TestTheScanSaysHowMuchOfTheFileItRead:
    """Full under a cell budget, sampled above it, and the payload says which.

    Reading every row is what made the dimension facts the file's own, and it
    is not free: at 1,000,000 x 50 it is 2.7 s against 20 ms for a
    thousand-row sample. *Optimize for the laptop* will not carry that on the
    command `AGENTS.md` tells every agent to run first, and *Audit by default*
    will not carry the silent sample it replaced — so the scan is bounded and
    the payload states what it read.
    """

    @staticmethod
    def _payload(frame: pl.DataFrame) -> dict[str, Any]:
        description = describe_table(frame, Path("t.parquet"))
        return json.loads(
            build_describe_response(
                description,
                CodeExamples(read_back="r", model_points="m"),
            ).model_dump_json(),
        )

    def test_a_file_inside_the_budget_is_read_whole_and_says_so(self) -> None:
        frame = pl.DataFrame({"policy_id": list(range(3_000)), "rate": [0.1] * 3_000})
        payload = self._payload(frame)
        assert payload["scan"] == "full"
        assert payload["scanned_rows"] == payload["rows"] == 3_000

    def test_the_lifelib_extract_is_still_read_whole(self) -> None:
        """The zero-wrong result is inside the budget and stays there."""
        path = Path(
            "gaspatchio/tutorials/level-4-lifelib/base/model_points_10k.parquet"
        )
        frame = pl.read_parquet(path)
        assert frame.height * frame.width <= _SCAN_CELL_BUDGET
        payload = self._payload(frame)
        assert payload["scan"] == "full"
        assert payload["scanned_rows"] == 10_000

    def test_a_file_over_the_budget_is_sampled_and_says_how_much_it_read(
        self,
    ) -> None:
        width = 12
        rows = _SCAN_CELL_BUDGET // width + 1_000
        frame = pl.DataFrame(
            {f"c{i}": pl.int_range(0, rows, eager=True) for i in range(width)},
        )
        schema = analyze_table(frame, detect_interpolation=False)
        assert schema.row_count == rows
        assert schema.sampled_rows == _SCAN_CELL_BUDGET // width
        assert schema.data_dimensions[0].unique_count == _SCAN_CELL_BUDGET // width

    def test_the_budget_is_cells_not_rows(self) -> None:
        """Cost is linear in cells: the same height costs 3.6x at 50 columns."""
        rows = _SCAN_CELL_BUDGET // 4
        narrow = pl.DataFrame(
            {f"c{i}": pl.int_range(0, rows, eager=True) for i in range(2)},
        )
        wide = pl.DataFrame(
            {f"c{i}": pl.int_range(0, rows, eager=True) for i in range(8)},
        )
        assert analyze_table(narrow, detect_interpolation=False).sampled_rows is None
        assert analyze_table(wide, detect_interpolation=False).sampled_rows == (
            _SCAN_CELL_BUDGET // 8
        )

    def test_a_caller_who_names_a_sample_size_still_gets_it(self) -> None:
        """The explicit escape wins over the budget, either way."""
        frame = pl.DataFrame({"policy_id": list(range(3_000))})
        assert analyze_table(frame, sample_rows=100).sampled_rows == 100


class TestAmbiguityIsNamedRatherThanGuessed:
    """Two columns equally good is a fact about the file, and it gets reported."""

    def test_two_rate_wordings_report_both_as_candidates(self) -> None:
        guess = detect_table_structure(
            pl.DataFrame(
                {"age": [30], "mortality_rate": [0.001], "lapse_rate": [0.05]},
            ),
        )
        assert guess.name == "mortality_rate"
        assert guess.candidates == ("mortality_rate", "lapse_rate")
        assert guess.is_ambiguous

    def test_four_unlabelled_rates_report_every_numeric_column(self) -> None:
        """`core/benches/fixtures/mortality.csv`: rates by sex and smoker status."""
        guess = detect_table_structure(
            pl.DataFrame(
                {
                    "age-last": [1],
                    "MNS": [0.0001],
                    "FNS": [0.000097],
                    "MS": [0.00012],
                    "FS": [0.0001164],
                },
            ),
        )
        assert guess.name == "FS"
        assert guess.candidates == ("age-last", "MNS", "FNS", "MS", "FS")
        assert guess.is_ambiguous

    def test_one_answer_is_not_an_ambiguity(self) -> None:
        guess = detect_table_structure(pl.DataFrame({"age": [30], "rate": [0.01]}))
        assert guess.name == "rate"
        assert guess.candidates == ("rate",)
        assert not guess.is_ambiguous

    def test_the_payload_carries_the_candidates(self) -> None:
        description = describe_table(
            pl.DataFrame(
                {"age": [30], "mortality_rate": [0.001], "lapse_rate": [0.05]},
            ),
            Path("t.parquet"),
        )
        response = build_describe_response(
            description,
            CodeExamples(read_back="r", model_points="m"),
        )
        assert response.value_column_candidates == ["mortality_rate", "lapse_rate"]

    def test_the_human_output_names_the_candidates_and_the_flag(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "rates.csv"
        path.write_text("age-last,MNS,FNS,MS,FS\n20,0.1,0.2,0.3,0.4\n")
        result = runner.invoke(app, ["describe", str(path)])
        assert result.exit_code == 0, result.output
        output = " ".join(result.output.split())
        assert "could not rule out" in output
        assert "--value-column" in output
        for column in ("age-last", "MNS", "FNS", "MS", "FS"):
            assert column in output

    def test_the_line_says_what_the_rule_missed_not_that_a_key_is_a_rate(
        self,
        tmp_path: Path,
    ) -> None:
        """A third of these lines name a column the same payload calls a key.

        The membership stays — `duration` here is a numeric key that rule 2
        could not rule out, and this line naming it beside `mort_scalar` is
        the only thing that tells the reader. What was wrong is the sentence:
        `duration` cannot "be the mortality scalar" while
        `detected_dimensions` in the same command calls it a key.

        The example this used to give — `lapse_id` winning over `lapse_rate`
        on `core/benches/fixtures/lapse_rates.parquet` — is gone: rule 1 reads
        numeric columns only, so the String id is not in the running.
        """
        path = tmp_path / "mortality_scalars.csv"
        path.write_text("duration,mort_scalar\n0,1.1\n1,1.2\n2,1.3\n")
        output = " ".join(runner.invoke(app, ["describe", str(path)]).output.split())
        payload = json.loads(
            runner.invoke(app, ["describe", "--json", str(path)]).stdout,
        )
        assert "duration" in output
        assert "could each be the rate" not in output
        assert "a key column can be among them" in output
        marks = {
            dim["name"]: dim["suggested_type"] for dim in payload["detected_dimensions"]
        }
        assert marks["duration"] == "key"
        assert payload["value_column_candidates"] == ["duration", "mort_scalar"]

    def test_an_unambiguous_table_says_nothing_extra(self, tmp_path: Path) -> None:
        path = tmp_path / "one_rate.csv"
        path.write_text("age,rate\n20,0.1\n21,0.2\n")
        assert "could not rule out" not in " ".join(
            runner.invoke(app, ["describe", str(path)]).output.split(),
        )


class TestTheRulesThatWerePlainlyWrong:
    """Findings from the CLI extraction, judged and fixed."""

    def test_the_unreachable_zero_spot_pattern_is_gone(self) -> None:
        """It could never match: the header loses its underscores, it keeps one."""
        assert "zero_spot" not in _VALUE_COLUMN_PATTERNS
        assert all("_" not in pattern for pattern in _VALUE_COLUMN_PATTERNS)

    def test_a_spot_rate_column_is_still_caught_by_spot(self) -> None:
        guess = detect_table_structure(pl.DataFrame({"term": [1], "zero_spot": [0.01]}))
        assert guess.name == "zero_spot"

    def test_a_decimal_or_uint_or_narrow_int_rate_is_seen_now(self) -> None:
        """A currency-denominated rate arrives as Decimal; it was invisible."""
        for dtype in (pl.Decimal(10, 4), pl.UInt32, pl.Int16):
            frame = pl.DataFrame(
                {"aaa": [1.0], "bbb": [2], "zzz": ["p"]},
                schema={"aaa": pl.Float64, "bbb": dtype, "zzz": pl.String},
            )
            assert detect_table_structure(frame).name == "bbb", dtype

    def test_a_boolean_column_is_not_a_rate(self) -> None:
        """``is_numeric()`` excludes Boolean, so the flag stays a key."""
        frame = pl.DataFrame({"aaa": [1.0], "zzz": [True]})
        assert detect_table_structure(frame).name == "aaa"

    def test_a_blank_named_numeric_column_no_longer_blocks_rule_two(self) -> None:
        """Two numerics, the last blank-named: the named one answers.

        The width at which a filtering rule and a picks-then-discards rule can
        disagree is two, so that is the width this is driven at.
        """
        blank_last = pl.DataFrame({"q": [1.0], "": [2.0], "zz": ["a"]})
        guess = detect_table_structure(blank_last)
        assert guess.name == "q"
        assert guess.dimensions == {"": "", "zz": "zz"}
        assert guess.candidates == ("q",)

    def test_a_csv_header_row_of_q_comma_comma_zz_reaches_that_shape(
        self,
        tmp_path: Path,
    ) -> None:
        csv = tmp_path / "unnamed_index.csv"
        csv.write_text("q,,zz\n1.0,2.0,a\n3.0,4.0,b\n")
        frame = pl.read_csv(csv)
        assert frame.columns == ["q", "", "zz"]
        assert detect_table_structure(frame).name == "q"

    def test_a_blank_named_only_numeric_still_falls_through_to_rule_three(
        self,
    ) -> None:
        guess = detect_table_structure(pl.DataFrame({"": [1.0], "zz": ["a"]}))
        assert guess.name == "zz"
        assert guess.dimensions == {"": ""}

    def test_nan_and_inf_headers_are_not_durations(self) -> None:
        """A CSV whose missing-value marker became a header is not a wide grid."""
        frame = pl.DataFrame({"age": [1], "nan": [1.0], "inf": [2.0], "-inf": [3.0]})
        assert analyze_table_shape(frame) == "long"

    def test_a_genuine_duration_grid_is_still_wide(self) -> None:
        frame = pl.DataFrame({"age": [1], "0": [0.1], "1": [0.2], "1e3": [0.3]})
        assert analyze_table_shape(frame) == "wide"


class TestEveryFactDescribesTheFileNotASample:
    """A number in this payload is true of the thing it names."""

    LIFELIB = Path("gaspatchio/tutorials/level-4-lifelib/base/model_points_10k.parquet")

    def _response(self) -> tuple[pl.DataFrame, Any]:
        frame = pl.read_parquet(self.LIFELIB)
        description = describe_table(frame, self.LIFELIB)
        return frame, build_describe_response(
            description,
            CodeExamples(read_back="r", model_points="m"),
        )

    def test_the_lifelib_model_points_report_the_files_own_counts(self) -> None:
        """10,000 rows, and eight dimensions used to report a sample's counts."""
        frame, response = self._response()
        assert response.rows == frame.height == 10_000
        reported = {dim.name: dim.unique_count for dim in response.detected_dimensions}
        assert reported["point_id"] == frame["point_id"].n_unique() == 10_000
        assert reported["premium_pp"] == frame["premium_pp"].n_unique() == 16
        assert reported["sum_assured"] == frame["sum_assured"].n_unique() == 9_900
        for name, count in reported.items():
            assert count == frame[name].n_unique(), name

    def test_sample_values_are_the_files_lowest_not_a_samples(self) -> None:
        frame, response = self._response()
        shown = {dim.name: dim.sample_values for dim in response.detected_dimensions}
        assert shown["point_id"] == [1, 2, 3, 4, 5]
        assert shown["premium_pp"] == sorted(frame["premium_pp"].unique().to_list())[:5]

    def test_a_dimension_over_the_old_threshold_is_counted_whole(self) -> None:
        """1,500 distinct values in 3,000 rows: the old sample capped it at 1,000."""
        rows = 3_000
        frame = pl.DataFrame(
            {
                "policy_id": list(range(rows)),
                "band": [f"B{i % 7}" for i in range(rows)],
                "rate": [0.001 + (i % 1_500) / 1e6 for i in range(rows)],
            },
        )
        schema = analyze_table(frame)
        counts = {dim.name: dim.unique_count for dim in schema.data_dimensions}
        assert counts["policy_id"] == 3_000
        assert counts["rate"] == 1_500
        assert schema.row_count == 3_000
        assert schema.sampled_rows is None

    def test_a_caller_that_asks_for_a_sample_is_told_it_got_one(self) -> None:
        """The escape survives, and a sampled schema cannot pass for a whole one."""
        frame = pl.DataFrame({"policy_id": list(range(3_000))})
        schema = analyze_table(frame, sample_rows=1_000)
        assert schema.sampled_rows == 1_000
        assert schema.row_count == 3_000
        assert schema.data_dimensions[0].unique_count == 1_000


class TestTheJsonPayloadSaysTheSameThingTwice:
    """`--json` is the documented agent surface, so it has to be reproducible.

    `AGENTS.md` tells an agent to read a file's shape with `describe --json`,
    and *Audit by default* asks for an output that can be diffed against last
    quarter's. A payload whose lists arrive in a different order — or with
    different members — each time cannot be.
    """

    @staticmethod
    def _payload(frame: pl.DataFrame) -> str:
        description = describe_table(frame, Path("mortality_table_defs.parquet"))
        examples = CodeExamples(read_back="read-back", model_points="model-points")
        return build_describe_response(description, examples).model_dump_json(indent=2)

    @staticmethod
    def _many_valued_frame() -> pl.DataFrame:
        """Four text dimensions, each holding more than the five reported.

        ``age`` is deliberately shuffled and does NOT start at its minimum. A
        fixture ascending from its lowest value cannot tell "the lowest five
        ascending" from "the first five in file order", so a change that
        dropped the sort on the numeric path passed both assertions below.
        """
        return pl.DataFrame(
            {
                "table_id": ["T3364", "T3371", "T3275", "T3298", "T887", "T3370"] * 4,
                "sex": ["M", "F", "U", "M", "F", "U"] * 4,
                "segment": pl.Series(
                    ["S", "N", "U", "P", "S", "N"] * 4,
                    dtype=pl.Categorical,
                ),
                "description": [
                    "2015 VBT Unismoke Male ALB",
                    "2017 Loaded CSO Composite Male ALB",
                    "Annuity 2000 Female",
                    "2015 VBT Unismoke Female ALB",
                    "2017 Unloaded CSO Smoker Distinct Smoker Male ALB",
                    "2017 Loaded CSO Smoker Distinct Nonsmoker Male ALB",
                ]
                * 4,
                "age": [37, 25, 43, 20, 31, 28, 40, 22, 35, 26, 44, 21]
                + [38, 24, 42, 23, 33, 29, 41, 27, 36, 30, 39, 32],
                "mortality_rate": [0.001 * n for n in range(24)],
            },
        )

    def test_the_payload_is_identical_over_many_builds(self) -> None:
        frame = self._many_valued_frame()
        assert len({self._payload(frame) for _ in range(60)}) == 1

    def test_sample_values_are_sorted_and_the_file_order_is_kept(self) -> None:
        """The order chosen, pinned, so a change to it is visible not silent."""
        payload = json.loads(self._payload(self._many_valued_frame()))

        # The file's own column order carries information and is kept.
        assert payload["columns"] == [
            "table_id",
            "sex",
            "segment",
            "description",
            "age",
            "mortality_rate",
        ]
        assert [dim["name"] for dim in payload["detected_dimensions"]] == [
            "table_id",
            "sex",
            "segment",
            "description",
            "age",
        ]

        # A dimension's distinct values are a set, so they are sorted.
        sampled = {
            dim["name"]: dim["sample_values"] for dim in payload["detected_dimensions"]
        }
        assert sampled["sex"] == ["F", "M", "U"]
        assert sampled["segment"] == ["N", "P", "S", "U"]
        assert sampled["table_id"] == ["T3275", "T3298", "T3364", "T3370", "T3371"]

        # The lowest five ascending, which the file's own order is not: `age`
        # begins 37, 25, 43, 20 … so a first-five-in-file-order reading would
        # give [37, 25, 43, 20, 31] and this assertion would fail.
        assert sampled["age"] == [20, 21, 22, 23, 24]
        assert payload["sample_rows"][0]["age"] == 37


class TestOneVerdictPrintedByBothSurfaces:
    """The console and `--json` answer with the same value column, or neither.

    They did not. Driven over this repository's 136 tracked `.parquet` and
    `.csv` files on 2026-09-14, the two surfaces agreed on 50: on 39 the
    payload said `model_points` and named nothing while the console named a
    column and printed a `Table(...)` that could not be built; on 38 the
    payload named the post-melt `value` while the console named a real column;
    on 8 both named a real column and the names differed; one was projection
    output and both were silent. The verdict is taken once in `describe_table`
    now, and both surfaces read it off the description.

    Both files below ship in the package, so these assertions are about the
    thing a user actually runs the command on.
    """

    MODEL_POINTS = Path(
        "gaspatchio/tutorials/level-3-mini-va/steps/01-from-files/data/"
        "model_points.parquet",
    )
    LAPSE_RATES = Path(
        "gaspatchio/tutorials/level-4-lifelib/base/assumptions/lapse_rates.parquet",
    )

    @staticmethod
    def _both(path: Path) -> tuple[str, dict[str, Any]]:
        """Run the command twice over one file and return console, payload."""
        console = runner.invoke(app, ["describe", str(path)])
        assert console.exit_code == 0, console.output
        payload = runner.invoke(app, ["describe", "--json", str(path)])
        assert payload.exit_code == 0, payload.output
        return " ".join(console.output.split()), json.loads(payload.stdout)

    @staticmethod
    def _console_value_column(console: str) -> str:
        """The name the console printed as the value column, or "" for none."""
        marker = "Value column: "
        if marker not in console:
            return ""
        return console.split(marker, 1)[1].split(" ", 1)[0]

    def test_a_model_point_extract_reads_the_same_on_both_surfaces(self) -> None:
        """The console named `premium_pp` where the payload named nothing."""
        console, payload = self._both(self.MODEL_POINTS)

        assert payload["table_shape"] == "model_points"
        assert payload["detected_value_column"] == ""
        assert self._console_value_column(console) == payload["detected_value_column"]

        assert "Format: MODEL POINTS" in console
        assert "one row per policy" in console
        assert "no rate to look up" in console
        assert "ActuarialFrame(mp)" in console
        # No table offered for a file that has no rate in it — and the one it
        # used to offer could not be built: the run ended in "Could not create
        # assumption table structure: Float64 keys with decimals".
        assert "Table(" not in console
        assert "Key columns" not in console

    def test_the_lapse_table_names_the_rate_on_both_surfaces(self) -> None:
        """The console named the String `lapse_id`; the payload named the rate."""
        console, payload = self._both(self.LAPSE_RATES)

        assert payload["detected_value_column"] == "lapse_rate"
        assert self._console_value_column(console) == "lapse_rate"
        assert "Key columns: duration, lapse_id" in console
        # The rule that chose is named on every answer, not only on a tie —
        # and this file no longer has a tie to report, because the String id
        # column is out of the running.
        assert "inferred: the leftmost numeric column whose header names a rate" in (
            console
        )
        assert "could not rule out" not in console

    def test_a_string_column_no_longer_wins_the_wording_rule(self) -> None:
        """`lapse_id` is a String and cannot hold a rate, whatever it is called."""
        frame = pl.DataFrame(
            {
                "duration": [0, 1],
                "lapse_id": ["L001", "L001"],
                "lapse_rate": [0.03, 0.04],
            },
        )
        guess = detect_table_structure(frame)
        assert guess.name == "lapse_rate"
        assert guess.candidates == ("lapse_rate",)
        assert guess.rule == "wording"

    def test_a_wide_table_names_the_post_melt_value_on_both_surfaces(
        self,
        tmp_path: Path,
    ) -> None:
        """The console named the last duration header as if it were the rate.

        The one shape where the two engines still name different things: the
        header rule can only ever name a column of the file, and a wide
        table's rate is called `value` only after the melt. The console reads
        the resolved name, so it says `value` and says what that means.
        """
        path = tmp_path / "select.csv"
        path.write_text("Age,0,1,2\n20,0.1,0.3,0.5\n21,0.2,0.4,0.6\n")
        console, payload = self._both(path)

        assert payload["detected_value_column"] == "value"
        assert payload["value_column_source"] == "after_melt"
        assert self._console_value_column(console) == payload["detected_value_column"]
        assert "after melting" in console
        assert "0, 1, 2 are melted into one" in console

        frame = pl.read_csv(path)
        description = describe_table(frame, path)
        assert description.resolved_value_column == "value"
        assert description.melt_columns == ("0", "1", "2")
        # The keys reported beside a post-melt name are the keys, not every
        # header: listing `0, 1, 2` as keys beside a `value` none of them
        # carries was the console contradicting itself.
        assert description.dimensions == {"Age": "Age"}

    def test_the_console_says_which_rule_chose_even_with_one_candidate(
        self,
        tmp_path: Path,
    ) -> None:
        """One candidate is not a tie, and the rule that answered is still named."""
        path = tmp_path / "one_rate.csv"
        path.write_text("age,rate\n20,0.1\n21,0.2\n")
        output = " ".join(runner.invoke(app, ["describe", str(path)]).output.split())
        assert "Value column: rate" in output
        assert "inferred: the leftmost numeric column whose header names a rate" in (
            output
        )
        assert "could not rule out" not in output

    def test_a_declared_column_says_it_was_declared(self, tmp_path: Path) -> None:
        """`declared` is the payload's word for it; the console now uses it too."""
        path = tmp_path / "two_rates.csv"
        path.write_text("age,M,F\n20,0.001,0.0008\n21,0.0011,0.0009\n")
        output = " ".join(
            runner.invoke(app, ["describe", "--value-column", "F", str(path)]).output
            .split(),
        )
        assert "Value column: F" in output
        assert "declared: the column you named with --value-column" in output
        assert "inferred:" not in output
