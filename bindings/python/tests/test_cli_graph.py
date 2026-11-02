# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio graph``: ``af.graph``'s questions, asked of an audit file at a shell.

Each subcommand is one of ``af.graph``'s methods under its own name, answered
from the file alone by the reader ``gaspatchio.graph.read_artifact`` returns.
What is held here is the shell's part: the answer in text and as JSON, the
period each arrow of a trace read, the classes ``unused`` reports and the
status ``--fail-on`` sets, and the refusals -- an unreadable file or a column
the file does not hold leaves with status 2 and ``af.graph``'s own words.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.graph import read_artifact
from tests.graph.test_lineage_parity import _frame
from tests.test_cli_artifact import _needle, _unwrapped

if TYPE_CHECKING:
    from pathlib import Path

    from click.testing import Result

runner = CliRunner()


@pytest.fixture(scope="module")
def audit(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a valuation's audit file: lookups, a join, shifts and windows."""
    written = tmp_path_factory.mktemp("graph") / "audit.json"
    written.write_text(GraphExporter(_frame("valuation")).export())
    return written


def _graph(*arguments: str | Path) -> Result:
    """Run ``gspio graph`` with ``arguments``."""
    return runner.invoke(app, ["graph", *map(str, arguments)])


def _json(*arguments: str | Path) -> dict[str, Any]:
    """Run ``gspio graph ... --json`` and return the answer it printed."""
    result = _graph(*arguments, "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_the_group_names_af_graph_s_questions() -> None:
    result = _graph("--help")

    assert result.exit_code == 0
    for question in (
        "precedents",
        "dependents",
        "trace",
        "affected",
        "unused",
        "holes",
        "tiers",
    ):
        assert question in result.output


def test_each_answer_is_af_graph_s_answer(audit: Path) -> None:
    af = _frame("valuation")

    assert _json("precedents", audit, "reserve")["nodes"] == list(
        af.graph.precedents("reserve")
    )
    assert _json("dependents", audit, "claims")["nodes"] == list(
        af.graph.dependents("claims")
    )
    assert _json("trace", audit, "reserve")["nodes"] == list(af.graph.trace("reserve"))
    assert _json("trace", audit, "reserve", "--depth", "1")["nodes"] == list(
        af.graph.trace("reserve", depth=1)
    )
    assert _json("affected", audit, "q")["nodes"] == list(af.graph.affected("q"))


def test_a_trace_says_which_periods_each_arrow_read(audit: Path) -> None:
    """Offsets, windows and positions, read off the file and never off a formula."""
    said = {
        column: _unwrapped(_graph("trace", audit, column, "--depth", "1").stdout)
        for column in ("claims_prior", "survival", "reserve", "first_claim")
    }

    assert _needle("claims@1 (t\u22121)") in said["claims_prior"]
    assert _needle("q_monthly@1 (first\u2026t\u22121)") in said["survival"]
    assert _needle("net_cf@2 (t\u2026last)") in said["reserve"]
    assert _needle("claims@1 (position 0)") in said["first_claim"]


def test_the_json_carries_each_read_with_its_narrowing(audit: Path) -> None:
    answer = _json("precedents", audit, "running_claims")

    assert answer["node"] == "running_claims@1"
    assert answer["reads"] == [
        {
            "source": "claims@1",
            "target": "running_claims@1",
            "transformations": [
                {
                    "type": "DIRECT",
                    "subtype": "AGGREGATION",
                    "periods": {"from": "first", "to": 0},
                }
            ],
        }
    ]


def test_output_file_stores_what_json_prints(audit: Path, tmp_path: Path) -> None:
    stored = tmp_path / "answer.json"

    result = _graph("trace", audit, "reserve", "-o", stored)

    assert result.exit_code == 0, result.output
    assert json.loads(stored.read_text()) == _json("trace", audit, "reserve")


def test_affected_of_an_assumption(audit: Path) -> None:
    answer = _json("affected", audit, "--assumption", "valuation_mortality")

    assert answer["assumption"] == "valuation_mortality"
    assert answer["nodes"] == list(
        _frame("valuation").graph.affected(assumption="valuation_mortality")
    )
    assert answer["nodes"][0] == "q@1"


def test_unused_reports_every_class_and_keep_moves_results(
    audit: Path, tmp_path: Path
) -> None:
    keep_file = tmp_path / "results.toml"
    keep_file.write_text('keep = ["claims_total"]\n')

    plain = _json("unused", audit)
    kept = _json(
        "unused", audit, "--keep", "reserve,first_claim", "--keep-from", keep_file
    )

    assert set(plain["classes"]) == {
        "superseded",
        "data",
        "stamp",
        "length_only",
        "terminal",
        "kept",
    }
    assert plain["classes"]["data"] == ["policy_id"]
    assert kept["classes"]["kept"] == ["reserve@1", "claims_total@1", "first_claim@1"]
    assert "reserve@1" not in kept["classes"]["terminal"]
    assert _unwrapped(_graph("unused", audit).stdout).startswith(
        _needle("10 nodes nothing reads, of")
    )


def test_fail_on_exits_1_when_a_named_class_is_not_empty(audit: Path) -> None:
    failing = _graph("unused", audit, "--fail-on", "superseded,terminal")
    passing = _graph("unused", audit, "--fail-on", "superseded")

    assert failing.exit_code == 1
    assert _needle("--fail-on: 6 terminal.") in _unwrapped(failing.stderr)
    assert passing.exit_code == 0, passing.output


def test_fail_on_refuses_a_class_that_does_not_exist(audit: Path) -> None:
    result = _graph("unused", audit, "--fail-on", "dead")

    assert result.exit_code == 2
    assert _needle("'dead', which is not a class") in _unwrapped(result.stderr)


def test_keep_from_refuses_a_file_without_a_keep_array(
    audit: Path, tmp_path: Path
) -> None:
    keep_file = tmp_path / "results.toml"
    keep_file.write_text('results = ["reserve"]\n')

    result = _graph("unused", audit, "--keep-from", keep_file)

    assert result.exit_code == 2
    assert _needle("has no keep = [...] array") in _unwrapped(result.stderr)


def test_holes_and_tiers(audit: Path) -> None:
    assert _json("holes", audit)["holes"] == []
    tiers = _json("tiers", audit)
    census = read_artifact(audit).tiers()
    assert tiers["counts"] == census.counts
    assert tiers["core"] == list(census.core)
    assert _needle("No holes") in _unwrapped(_graph("holes", audit).stdout)


def test_a_column_the_file_does_not_hold_is_refused_in_af_graph_s_words(
    audit: Path,
) -> None:
    result = _graph("trace", audit, "reserv")
    with pytest.raises(ValueError, match="reserv") as refused:
        _frame("valuation").graph.trace("reserv")

    assert result.exit_code == 2
    assert _needle(str(refused.value)) in _unwrapped(result.stderr)
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("content", "said"),
    [
        (None, "could not be read"),
        (b"{not json", "could not be read as an audit file"),
        (b"[1, 2]", "is not an object"),
        (b"{}", "carries no nodes array"),
        (
            b"version https://git-lfs.github.com/spec/v1\n"
            b"oid sha256:" + b"a" * 64 + b"\nsize 12\n",
            "Git LFS pointer",
        ),
    ],
)
def test_an_unreadable_file_exits_2_and_says_why(
    tmp_path: Path, content: bytes | None, said: str
) -> None:
    path = tmp_path / "audit.json"
    if content is not None:
        path.write_bytes(content)

    result = _graph("unused", path)

    assert result.exit_code == 2
    assert _needle(said) in _unwrapped(result.stderr)
