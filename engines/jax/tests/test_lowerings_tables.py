# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The three reads that select a row: ``lookup``, ``mortality.at`` and ``join``.

What they share is the gather. What they do not share is how the operands
find the columns they key on -- a lookup binds by position and a mortality
read by name, which is 11.1.24's own contrast and is the difference between
reading a select basis and mis-keying it silently -- and what a key with no
row means: a lookup's miss policy says, and a join has none, because the null
Polars would put there is a value this engine states no answer over.
"""

from __future__ import annotations

from typing import Any

import pytest

from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal, RunReport
from gaspatchio_jax.engine import JaxEngine
from gaspatchio_jax.vectors import Invocation
from tests.conftest import entry, invocation
from tests.fixtures import make_tables

# The basis the published vectors key on: two ages, two durations, four rates.
_SELECT = "conformance_select_rates"


def _basis(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the select basis as an assumptions entry, under its own name."""
    return entry("table", payload or make_tables.text_keyed(), _SELECT)


def _rates() -> dict[str, Any]:
    """Return a numerically keyed select basis: ages 45 and 55, durations 1 and 2."""
    return {
        "dimensions": ["age", "duration"],
        "value": "rate",
        "columns": [
            {"name": "age", "dtype": "f64"},
            {"name": "duration", "dtype": "f64"},
            {"name": "rate", "dtype": "f64"},
        ],
        "rows": [
            [45.0, 1.0, 0.01],
            [45.0, 2.0, 0.02],
            [55.0, 1.0, 0.03],
            [55.0, 2.0, 0.04],
        ],
    }


def _lookup_tree(
    keys: list[dict[str, Any]], fingerprint: str, on_missing: str, fill: float | None
) -> dict[str, Any]:
    """Return one lookup call over these key trees."""
    return {
        "op": "call",
        "name": "lookup",
        "args": keys,
        "attrs": {
            "table": _SELECT,
            "table_fingerprint": fingerprint,
            "on_missing": on_missing,
            "fill_value": fill,
        },
    }


def _col(name: str) -> dict[str, Any]:
    return {"op": "col", "name": name}


def _computed(name: str) -> dict[str, Any]:
    """Return a key a calculation produced rather than one that arrived."""
    return {
        "op": "binop",
        "kind": "add",
        "left": _col(name),
        "right": {"op": "lit", "value": 0.0},
    }


def _book(ages: list[float], durations: list[float]) -> dict[str, dict[str, Any]]:
    return {
        "age": {"dtype": "f64", "values": ages},
        "duration": {"dtype": "f64", "values": durations},
    }


def _read(
    book: tuple[list[float], list[float]],
    *,
    on_missing: str = "raise",
    fill: float | None = None,
    payload: dict[str, Any] | None = None,
    computed: bool = False,
) -> Invocation:
    """Return one lookup invocation over the numeric select basis."""
    sealed = entry("table", payload or _rates(), _SELECT)
    key = _computed if computed else _col
    return invocation(
        _lookup_tree(
            [key("age"), key("duration")], str(sealed["fingerprint"]), on_missing, fill
        ),
        _book(*book),
        "f64",
        [sealed],
    )


def _answers(one: Invocation, column: str = "answer") -> list[Any]:
    """Run one invocation and return the column it was written for."""
    return (
        JaxEngine().run(one.document, one.inputs, FrameSink()).columns[column].to_list()
    )


def _refusal(one: Invocation) -> RunReport:
    """Run one invocation that refuses, and return the report it refused with."""
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    return refused.value.report


def test_a_lookup_answers_the_rate_its_keys_select() -> None:
    assert _answers(_read(([45.0, 55.0], [2.0, 1.0]))) == pytest.approx([0.02, 0.03])


def test_a_key_the_basis_does_not_carry_answers_nan_where_the_model_asked_for_one() -> (
    None
):
    answered = _answers(_read(([45.0, 99.0], [1.0, 1.0]), on_missing="nan"))
    assert answered[0] == pytest.approx(0.01)
    assert answered[1] != answered[1]


def test_a_key_the_basis_does_not_carry_answers_the_fill_the_model_named() -> None:
    answered = _answers(_read(([45.0, 99.0], [1.0, 1.0]), on_missing="fill", fill=0.5))
    assert answered == pytest.approx([0.01, 0.5])


def test_a_missing_key_on_a_column_that_arrived_refuses_before_any_computing() -> None:
    """Every key arrived with the book, so the finding is one the door could make."""
    report = _refusal(_read(([45.0, 99.0, 99.0], [1.0, 1.0, 2.0])))
    refusal = report.refusals[0]
    assert refusal.group == "inputs"
    assert refusal.count == 2
    assert "99" in refusal.what
    assert report.closing_sentence() == "Nothing was computed."


def test_a_missing_key_a_calculation_produced_refuses_at_completion_with_a_count() -> (
    None
):
    """A computed key is knowable only once it has been computed, so it is."""
    report = _refusal(_read(([45.0, 99.0], [1.0, 1.0]), computed=True))
    refusal = report.refusals[0]
    assert refusal.group == "completion"
    assert refusal.count == 1
    assert "first at row 1" in refusal.what
    assert report.closing_sentence() == "No results were published."


def test_a_text_key_is_matched_through_the_run_s_own_dictionary() -> None:
    sealed = _basis()
    one = invocation(
        _lookup_tree(
            [_col("plan"), _col("duration")], str(sealed["fingerprint"]), "raise", None
        ),
        {
            "plan": {"dtype": "str", "values": ["B", "A"]},
            "duration": {"dtype": "i64", "values": [2, 1]},
        },
        "f64",
        [sealed],
    )
    assert _answers(one) == pytest.approx([0.04, 0.01])


def test_a_lookup_binds_its_operands_to_the_column_order_and_not_to_dimensions() -> (
    None
):
    """11.1.24: ``dimensions`` is a set of names and mis-keys a table silently.

    The basis here is keyed (plan, duration) in its ``columns`` and states
    ``dimensions`` in the other order. An engine binding to ``dimensions``
    answers from the same table without any refusal at all, which is the
    failure this clause is about -- so the witness is a value and not a
    message.
    """
    payload = make_tables.text_keyed()
    payload["dimensions"] = ["duration", "plan"]
    sealed = entry("table", payload, _SELECT)
    one = invocation(
        _lookup_tree(
            [_col("plan"), _col("duration")], str(sealed["fingerprint"]), "raise", None
        ),
        {
            "plan": {"dtype": "str", "values": ["A"]},
            "duration": {"dtype": "i64", "values": [2]},
        },
        "f64",
        [sealed],
    )
    assert _answers(one) == pytest.approx([0.02])


def test_a_lookup_written_with_the_wrong_number_of_keys_refuses_by_name() -> None:
    sealed = entry("table", _rates(), _SELECT)
    one = invocation(
        _lookup_tree([_col("age")], str(sealed["fingerprint"]), "raise", None),
        {"age": {"dtype": "f64", "values": [45.0]}},
        "f64",
        [sealed],
    )
    report = _refusal(one)
    assert "1" in report.refusals[0].what
    assert "2" in report.refusals[0].what


def test_an_answer_cell_a_query_reaches_is_the_miss_the_policy_decides() -> None:
    """Section 11.1.24 end to end: the blank is a miss at the key that reaches it."""
    blank = make_tables.blank_answer()
    answered = _answers(
        _read(([45.0, 45.0], [1.0, 2.0]), on_missing="nan", payload=blank)
    )
    assert answered[0] == pytest.approx(0.01)
    assert answered[1] != answered[1]


def test_an_answer_cell_no_query_reaches_disqualifies_nothing() -> None:
    blank = make_tables.blank_answer()
    assert _answers(_read(([45.0, 55.0], [1.0, 2.0]), payload=blank)) == pytest.approx(
        [0.01, 0.04]
    )


def test_a_basis_on_the_fallback_path_is_reported_by_name_with_its_condition() -> None:
    sparse = make_tables.sparse_1pct()
    sealed = entry("table", sparse, _SELECT)
    one = invocation(
        _lookup_tree(
            [_col("age"), _col("duration")], str(sealed["fingerprint"]), "raise", None
        ),
        _book([10.0], [1.0]),
        "f64",
        [sealed],
    )
    result = JaxEngine().run(one.document, one.inputs, FrameSink())
    assert result.columns["answer"].to_list() == pytest.approx([0.01])
    assert any("sorted-rows" in note for note in result.report.notes)
    assert any("density" in note for note in result.report.notes)


def _mortality_tree(
    keys: list[dict[str, Any]], fingerprint: str, stated: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return one convention-aware read, as ``MortalityTable.at`` emits it."""
    attrs: dict[str, Any] = {
        "mortality": "sha256:" + "0" * 64,
        "structure": "select_ultimate",
        "select_period": 2,
        "age_basis": "age_last_birthday",
        "dimensions": "age,duration",
        "table": _SELECT,
        "table_fingerprint": fingerprint,
    }
    attrs.update(stated or {})
    return {
        "op": "call",
        "name": "mortality.at",
        "args": keys,
        "attrs": {name: value for name, value in attrs.items() if value is not None},
    }


def _mortality(
    book: tuple[list[float], list[float]], stated: dict[str, Any] | None = None
) -> Invocation:
    """Return one mortality read over the numeric select basis."""
    sealed = entry("table", _rates(), _SELECT)
    return invocation(
        _mortality_tree(
            [_col("age"), _col("duration")], str(sealed["fingerprint"]), stated
        ),
        _book(*book),
        "f64",
        [sealed],
    )


def test_a_select_and_ultimate_read_holds_the_duration_at_the_select_period() -> None:
    """A duration past the select period reads the select period's own row."""
    assert _answers(_mortality(([45.0, 55.0], [7.0, 2.0]))) == pytest.approx(
        [0.02, 0.04]
    )


def test_a_duration_below_the_first_row_is_a_miss_and_not_a_floor_invented() -> None:
    report = _refusal(_mortality(([45.0], [0.0])))
    assert report.refusals[0].group == "inputs"
    assert "duration" in report.refusals[0].what


def test_a_mortality_read_that_states_no_miss_policy_takes_the_stated_default() -> None:
    """Where the node carries no ``on_missing``, a consumer applies raise."""
    report = _refusal(_mortality(([99.0], [1.0])))
    assert report.refusals[0].group == "inputs"
    assert report.refusals[0].clause == "11.1.10"


def test_a_mortality_read_that_states_a_miss_policy_is_read_under_it() -> None:
    answered = _answers(_mortality(([99.0], [1.0]), {"on_missing": "nan"}))
    assert answered[0] != answered[0]


def test_a_mortality_read_binds_its_operands_by_the_names_it_states() -> None:
    """The other rule: ``dimensions`` is in operand order and binds by name."""
    sealed = entry("table", _rates(), _SELECT)
    one = invocation(
        _mortality_tree(
            [_col("duration"), _col("age")],
            str(sealed["fingerprint"]),
            {"dimensions": "duration,age"},
        ),
        _book([45.0], [2.0]),
        "f64",
        [sealed],
    )
    assert _answers(one) == pytest.approx([0.02])


def test_an_aggregate_read_takes_no_select_period_and_no_clamp() -> None:
    sealed = entry("table", _rates(), _SELECT)
    one = invocation(
        _mortality_tree(
            [_col("age"), _col("duration")],
            str(sealed["fingerprint"]),
            {"structure": "aggregate", "select_period": None},
        ),
        _book([45.0], [2.0]),
        "f64",
        [sealed],
    )
    assert _answers(one) == pytest.approx([0.02])


def test_a_read_naming_a_dimension_the_basis_does_not_carry_refuses_by_name() -> None:
    sealed = entry("table", _rates(), _SELECT)
    one = invocation(
        _mortality_tree(
            [_col("age"), _col("duration")],
            str(sealed["fingerprint"]),
            {"dimensions": "age,policy_year"},
        ),
        _book([45.0], [2.0]),
        "f64",
        [sealed],
    )
    assert "policy_year" in _refusal(one).refusals[0].what


def _right(rows: list[list[Any]], key: str = "product") -> dict[str, Any]:
    """Return a right side keyed by product, bringing one loading."""
    return {
        "columns": [
            {"name": key, "dtype": "str"},
            {"name": "loading", "dtype": "f64"},
        ],
        "rows": rows,
    }


def _join(
    products: list[str],
    rows: list[list[Any]],
    *,
    how: str = "left",
    computed: bool = False,
    key: str = "product",
) -> Invocation:
    """Return one join invocation, keying on a column that arrived or was computed."""
    sealed = entry("join", _right(rows, key))
    held = "source" if computed else key
    one = invocation(
        {
            "op": "call",
            "name": "join",
            "args": [],
            "attrs": {
                "on": key,
                "how": how,
                "right_fingerprint": str(sealed["fingerprint"]),
            },
        },
        {held: {"dtype": "str", "values": products}},
        "f64",
        [sealed],
        "loading",
    )
    return _with_a_computed_key(one) if computed else one


def _with_a_computed_key(one: Invocation) -> Invocation:
    """Return the same document with the key column written by a line of the model.

    A join keys on whatever the frame is holding under that name when the
    join happens, and that is as often a column the model wrote as one that
    arrived -- a normalised product code, a plan identifier built from two
    fields. Which of the two it is decides when an unmatched key becomes
    knowable, so the document carries both shapes and the tests read the
    group off the report.
    """
    import copy

    from gaspatchio_jax.vectors import _sealed

    document = copy.deepcopy(one.document)
    key = copy.deepcopy(document["nodes"][-1])
    key.update(
        {
            "id": "product@1",
            "column": "product",
            "version": 1,
            "dtype": "str",
            "reads": ["source"],
            "expr": {
                "op": "call",
                "name": "to_text",
                "args": [_col("source")],
                "attrs": {},
            },
            "reads_assumptions": [],
            "in_final_schema": True,
        }
    )
    document["nodes"].insert(-1, key)
    # 11.1.2: the join reads the key it was matched on, as it stood when the
    # join ran -- the line of the model that wrote it.
    document["nodes"][-1]["reads"] = ["product@1"]
    document["edges"].extend(
        [
            {"source": "source", "target": "product@1", "relationship": "DIRECT"},
            {"source": "product@1", "target": "loading@1", "relationship": "INDIRECT"},
        ]
    )
    return Invocation(
        case_id=one.case_id,
        document=_sealed(document),
        inputs=one.inputs,
        resources=one.resources,
        expected_kind=one.expected_kind,
        expected=one.expected,
        refusal=one.refusal,
        comparison=one.comparison,
    )


def test_a_join_brings_the_right_side_s_column_for_a_matched_key() -> None:
    answered = _answers(_join(["A", "B"], [["A", 0.05], ["B", 0.07]]), "loading")
    assert answered == pytest.approx([0.05, 0.07])


def test_a_key_with_spaces_in_its_name_binds_to_the_column_that_has_them() -> None:
    """11.1.2: the attribute is read as written, so ``" code "`` is not ``"code"``."""
    one = _join(["A", "B"], [["A", 0.05], ["B", 0.07]], key=" code ")

    assert _answers(one, "loading") == pytest.approx([0.05, 0.07])


@pytest.mark.parametrize(
    "stated",
    [
        "product",
        "product,issue_age",
        " code ",
        "a , b",
        "pol_num=policy_id",
        "a,b=x,y",
        " code = other ",
    ],
)
def test_every_reader_of_a_join_s_keys_reads_them_alike(stated: str) -> None:
    """One attribute, one reading, wherever it is read.

    The graph's lineage (and the execution inspector, which binds through
    it), this engine's binding of the key, its reading of which columns a
    tree names for the conformance cases, and its split of key reads from
    value reads all read the ``on`` attribute through the format's one
    reader, trimming nothing -- so the column the lineage says a join read
    is the column the engine matches on.
    """
    from gaspatchio.engines.format import Call, join_key_sides
    from gaspatchio.frame.graph.edges import join_keys
    from gaspatchio_jax.lowerings.tables import _sides
    from gaspatchio_jax.plan import _reads_inside
    from gaspatchio_jax.vectors import _columns_in

    this_frame, other_table = join_key_sides(stated)
    tree = {"op": "call", "name": "join", "args": [], "attrs": {"on": stated}}
    keys: set[str] = set()
    values: set[str] = set()
    _reads_inside(tree, keys, values)

    assert join_keys(Call("join", (), (("on", stated),))) == this_frame
    assert _sides(stated) == (this_frame, other_table)
    assert tuple(_columns_in(tree)) == this_frame
    assert keys == set(this_frame)
    assert values == set()


def test_a_join_s_document_reads_the_key_it_was_matched_on() -> None:
    """11.1.2: the join's node reads its key, as the producer now writes it."""
    one = _join(["A", "B"], [["A", 0.05], ["B", 0.07]])
    joined = next(node for node in one.document["nodes"] if node["id"] == "loading@1")
    assert joined["reads"] == ["product"]


def test_a_join_whose_node_does_not_read_its_key_refuses_by_name() -> None:
    """A document written before the join read its key is refused, naming both.

    The key is bound through the node's reads, never through whatever the run
    holds under the name, so a join that names a key it does not read has no
    definition of that key to be matched on -- and says so rather than
    guessing at one.
    """
    from gaspatchio_jax.vectors import _sealed

    one = _join(["A", "B"], [["A", 0.05], ["B", 0.07]])
    document = one.document
    for node in document["nodes"]:
        if node["id"] == "loading@1":
            node["reads"] = []
    document["edges"] = [
        edge for edge in document["edges"] if edge["target"] != "loading@1"
    ]
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(_sealed(document), one.inputs, FrameSink())
    said = refused.value.report.render()
    assert "loading@1" in said
    assert "product" in said


def test_a_right_side_with_a_repeated_key_refuses_by_name() -> None:
    """11.1.2: a right side with repeated key values multiplies rows."""
    report = _refusal(_join(["A"], [["A", 0.05], ["A", 0.07]]))
    refusal = report.refusals[0]
    assert refusal.group == "tree"
    assert "multiplies rows" in refusal.what
    assert refusal.clause == "11.1.2"


def test_an_unmatched_left_key_that_arrived_refuses_in_the_inputs_group() -> None:
    report = _refusal(_join(["A", "C"], [["A", 0.05], ["B", 0.07]]))
    refusal = report.refusals[0]
    assert refusal.group == "inputs"
    assert refusal.count == 1
    assert "C" in refusal.what
    assert refusal.clause == "11.1.2"


def test_an_unmatched_left_key_a_calculation_produced_refuses_at_completion() -> None:
    report = _refusal(_join(["A", "C"], [["A", 0.05], ["B", 0.07]], computed=True))
    refusal = report.refusals[0]
    assert refusal.group == "completion"
    assert refusal.count == 1
    assert report.closing_sentence() == "No results were published."


def test_a_join_that_is_not_a_left_join_refuses_by_name() -> None:
    report = _refusal(_join(["A"], [["A", 0.05]], how="inner"))
    assert "inner" in report.refusals[0].what
    assert report.refusals[0].group == "tree"


def test_validate_tree_says_of_an_inner_join_what_run_does() -> None:
    one = _join(["A"], [["A", 0.05]], how="inner")
    refused = [
        status
        for status in JaxEngine().validate_tree(one.document)
        if status.status == "refused"
    ]
    assert len(refused) == 1
    assert "inner" in (refused[0].condition or "")


@pytest.mark.parametrize("carrier", ["bool", "date"])
def test_a_key_outside_the_key_domain_is_refused_by_both_halves(carrier: str) -> None:
    """The hand sweep: a declared operand domain and its lowering agree.

    ``lookup`` is swept here rather than in the domain sweep next door
    because that sweep builds its own forms and a read has a basis travelling
    with it -- so the two carriers 11.1.24 puts outside its key domain are
    offered with a real payload in the document, which is the only way the
    lowering gets as far as having an opinion.
    """
    sealed = entry("table", _rates(), _SELECT)
    values = {"bool": [True], "date": ["2024-01-31"]}[carrier]
    one = invocation(
        _lookup_tree(
            [_col("k"), _col("duration")], str(sealed["fingerprint"]), "raise", None
        ),
        {
            "k": {"dtype": carrier, "values": values},
            "duration": {"dtype": "f64", "values": [1.0]},
        },
        "f64",
        [sealed],
    )
    refused = [
        status
        for status in JaxEngine().validate_tree(one.document)
        if status.status == "refused"
    ]
    assert len(refused) == 1
    report = _refusal(one)
    assert report.refusals[0].clause == refused[0].clause


def test_a_text_answer_cell_spelled_like_a_number_keeps_its_own_text() -> None:
    """Section 10's three spellings are a rule about an ``f64`` column only.

    A plan identifier is text, and a plan called ``Infinity`` is a plan and
    not an infinity. Applied before the answer column's carrier was known,
    the non-finite mapping rewrote one into the other -- and the published
    column then carried a number nobody had written, at full confidence.
    """
    sealed = entry(
        "join",
        {
            "columns": [
                {"name": "product", "dtype": "str"},
                {"name": "plan", "dtype": "str"},
            ],
            "rows": [["A", "NaN"], ["B", "Infinity"], ["C", "ok"]],
        },
    )
    one = invocation(
        {
            "op": "call",
            "name": "join",
            "args": [],
            "attrs": {
                "on": "product",
                "how": "left",
                "right_fingerprint": str(sealed["fingerprint"]),
            },
        },
        {"product": {"dtype": "str", "values": ["A", "B", "C"]}},
        "str",
        [sealed],
        "plan",
    )
    assert _answers(one, "plan") == ["NaN", "Infinity", "ok"]


def test_a_text_answer_cell_spelled_like_a_number_is_not_a_blank() -> None:
    """The same rule read at the storage: those cells are answers, not holes."""
    from gaspatchio_jax.interning import Dictionary
    from gaspatchio_jax.tables import Basis, build

    storage, _note = build(
        {
            "columns": [
                {"name": "product", "dtype": "str"},
                {"name": "plan", "dtype": "str"},
            ],
            "rows": [["A", "NaN"], ["B", "Infinity"], ["C", "ok"]],
        },
        interning=Dictionary(),
        basis=Basis(name="a right side", keys=("product",), answer="plan"),
    )
    assert not bool(storage.bad_answer.any())


def _with_an_overwritten_key(
    one: Invocation, reads: list[str] | None = None
) -> Invocation:
    """Return the same read over a key column the model wrote over.

    ``duration = duration + 10`` is an ordinary line, and it leaves a
    document carrying an input node *and* a computed node under that one
    name. The read is written after it and therefore reads the computed
    account, which is the shape the group rule has to answer for.
    """
    import copy

    from gaspatchio_jax.vectors import _sealed

    document = copy.deepcopy(one.document)
    answer = document["nodes"][-1]
    written = copy.deepcopy(answer)
    written.update(
        {
            "id": "duration@1",
            "column": "duration",
            "version": 1,
            "dtype": "f64",
            "reads": ["duration"],
            "expr": {
                "op": "binop",
                "kind": "add",
                "left": _col("duration"),
                "right": {"op": "lit", "value": 10.0},
            },
            "reads_assumptions": [],
        }
    )
    document["nodes"].insert(-1, written)
    answer["reads"] = reads if reads is not None else ["age", "duration@1"]
    document["edges"] = [
        {"source": "duration", "target": "duration@1", "relationship": "DIRECT"},
        *(
            {"source": read, "target": answer["id"], "relationship": "DIRECT"}
            for read in answer["reads"]
        ),
    ]
    return Invocation(
        case_id=one.case_id,
        document=_sealed(document),
        inputs=one.inputs,
        resources=one.resources,
        expected_kind=one.expected_kind,
        expected=one.expected,
        refusal=one.refusal,
        comparison=one.comparison,
    )


def test_a_key_column_the_model_wrote_over_is_a_computed_key_and_not_an_arrival() -> (
    None
):
    """The group is the resolved node's kind, never the name it stands under.

    Deciding on the name put this refusal in the inputs group, named a key
    the book never carried, and closed "Nothing was computed." about a run
    that had computed the very key it was refusing over.
    """
    report = _refusal(_with_an_overwritten_key(_read(([45.0], [1.0]))))
    refusal = report.refusals[0]
    assert refusal.group == "completion"
    assert refusal.count == 1
    assert report.closing_sentence() == "No results were published."


def test_a_key_the_basis_has_no_row_for_says_extend_the_basis() -> None:
    refusal = _refusal(_read(([45.0, 99.0], [1.0, 1.0]))).refusals[0]
    assert "reach no row the basis carries" in refusal.what
    assert "extend the basis" in refusal.move


def test_a_key_that_reaches_a_blank_answer_cell_says_fill_the_cell() -> None:
    """Section 11.1.24 makes it a miss, but not the miss of a key with no row."""
    refusal = _refusal(
        _read(([45.0], [2.0]), payload=make_tables.blank_answer())
    ).refusals[0]
    assert "answer cell is not there" in refusal.what
    assert "fill the cells" in refusal.move


def test_a_select_ultimate_read_with_no_select_period_refuses_in_both_halves() -> None:
    """11.1.10 defines that structure by the period, so both halves say so."""
    one = _mortality(([45.0], [7.0]), {"select_period": None})
    refused = [
        status
        for status in JaxEngine().validate_tree(one.document)
        if status.status == "refused"
    ]
    assert len(refused) == 1
    assert "select_period" in (refused[0].condition or "")
    assert _refusal(one).refusals[0].clause == refused[0].clause


def test_a_read_naming_more_dimensions_than_it_has_operands_refuses_by_name() -> None:
    """Silently truncating the pair would key the read on a prefix of itself."""
    one = _mortality(([45.0], [2.0]), {"dimensions": "age,duration,plan"})
    refusal = _refusal(one).refusals[0]
    assert "3 dimensions" in refusal.what
    assert "2 operands" in refusal.what


def _text_of_a_duration(*, overwritten: bool) -> Invocation:
    """Return ``to_text(duration)``, over the arriving column or over a written one."""
    one = invocation(
        {
            "op": "call",
            "name": "to_text",
            "args": [_col("duration")],
            "attrs": {},
        },
        {"duration": {"dtype": "f64", "values": [1.0]}},
        "str",
    )
    return _with_an_overwritten_key(one, ["duration@1"]) if overwritten else one


def test_a_host_operation_over_an_overwritten_column_refuses_in_both_halves() -> None:
    """The operand condition is about the node an operand resolves to, here too.

    The same shape as the read above, and the same failure it had: a column
    the model wrote over has an input node and a computed one under one name.
    Answered by name, the status read *lowered off the trace* under "operands
    are inputs or literals" and the host stage published the text of the
    values the column held **before** the model wrote over it -- a wrong
    answer, at full confidence, with nothing in the report to say so.

    This read lives beside the table reads rather than with the other
    conversions because it is that defect's other half, and the document it
    needs is the one built here.
    """
    one = _text_of_a_duration(overwritten=True)
    refused = [
        status
        for status in JaxEngine().validate_tree(one.document)
        if status.status == "refused"
    ]
    assert len(refused) == 1
    assert "which a calculation produced" in (refused[0].condition or "")
    assert "duration" in (refused[0].condition or "")

    report = _refusal(one)
    assert report.refusals[0].clause == refused[0].clause
    assert "which a calculation produced" in report.refusals[0].what
    assert report.closing_sentence() == "Nothing was computed."


def test_a_host_operation_over_a_column_that_arrived_still_answers_from_the_book() -> (
    None
):
    """The unchanged case: an arrival is an arrival, and is answered off the trace."""
    one = _text_of_a_duration(overwritten=False)
    statuses = JaxEngine().validate_tree(one.document)
    off_trace = [one for one in statuses if one.status == "lowered-off-trace"]
    assert len(off_trace) == 1
    assert _answers(one) == ["1.0"]


@pytest.mark.parametrize("period", ["2", 2.5], ids=["text", "a-decimal"])
def test_a_select_period_that_is_not_a_whole_number_refuses_in_both_halves(
    period: object,
) -> None:
    """11.1.10 calls it an integer number of durations, and the clamp holds one.

    Declaring only that the attribute is *present* left the narrower half
    open: a period written as text or as a decimal satisfied the presence
    rule, so the table read *lowered* while the lowering refused it for not
    being a number it could hold a duration at.
    """
    one = _mortality(([45.0], [7.0]), {"select_period": period})
    refused = [
        status
        for status in JaxEngine().validate_tree(one.document)
        if status.status == "refused"
    ]
    assert len(refused) == 1
    assert "select_period" in (refused[0].condition or "")
    assert _refusal(one).refusals[0].clause == refused[0].clause


# Past the range in which a double names every whole number, so the basis
# could not carry it whatever rows it had (tables.EXACT_KEY_LIMIT).
_PAST_THE_INTERVAL = float(2**53) + 2048.0


def test_a_key_that_arrived_past_the_interval_refuses_before_anything_is_computed() -> (
    None
):
    """The book alone settles it, so the run never starts.

    11.1.24 states a matching over an interval of keys, and a query outside it
    is not a key the basis could carry however many rows it has. Every key of
    this read came with the book, so the answer is knowable before a program
    exists -- and the closing sentence says the run cost nothing.
    """
    report = _refusal(_read(([45.0, _PAST_THE_INTERVAL], [1.0, 1.0])))
    assert report.closing_sentence() == "Nothing was computed."
    assert [one.group for one in report.refusals] == ["inputs"]
    assert "outside the interval" in report.refusals[0].what
    assert report.refusals[0].clause == "11.1.24"
    assert report.refusals[0].count == 1


def test_a_computed_key_past_the_interval_refuses_at_completion_by_its_check() -> None:
    """A calculation produced it, so it waits for the calculation to run.

    The same cell, reached through a key the model computed rather than one
    that arrived. It cannot be answered before the program runs, so it travels
    as the declared check ``lookup.key_range`` and is read at completion with
    every output withheld -- a different sentence and a different group from
    the case above, which is the whole distinction the two closing sentences
    draw.
    """
    report = _refusal(_read(([45.0, _PAST_THE_INTERVAL], [1.0, 1.0]), computed=True))
    assert report.closing_sentence() == "No results were published."
    assert {one.group for one in report.refusals} == {"completion"}
    ranged = [one for one in report.refusals if "lookup.key_range" in one.what]
    assert len(ranged) == 1, report.render()
    assert ranged[0].clause == "11.1.24"
    assert ranged[0].count == 1
    # And the key that is outside the interval also reaches no row, which is
    # the other thing that is true of it and is said separately: a reader
    # told only "no row" would go looking for a row to add.
    assert any("lookup.miss_raise" in one.what for one in report.refusals)
