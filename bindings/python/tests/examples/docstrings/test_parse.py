from pathlib import Path

import pytest

from gaspatchio_core.examples.docstrings.parse import GaspatchioDocstringParser


@pytest.fixture(scope="module")
def sample_module_content() -> str:
    return """\"""A sample module for testing.\"""

def func_with_simple_example(a: int):
    \"""
    This is a simple function.
    >>> print("Hello")
    \"""
    pass

def func_with_output_example(b: str):
    \"""
    This function has output.
    >>> x = 10
    >>> print(f"World {x}")
    World 10
    \"""
    pass

def func_with_multiline_input_and_output():
    \"""
    Multiline input and output.
    >>> for i in range(2):
    ...     print(i)
    0
    1
    \"""
    pass

class MyClass:
    \"""
    A sample class.
    >>> cls_inst = MyClass()
    \"""
    def method_with_example(self, val):
        \"""
        A method with its own example.
        >>> print(f"Method val: {val}")
        Method val: test
        \"""
        return val

def func_no_examples():
    \"""This function has no examples.\"""
    pass

def func_with_params_and_return(param1: int, param2: str = "default") -> dict:
    \"""
    Short desc.

    Longer description here.

    Args:
        param1 (int): The first parameter.
        param2 (str, optional): The second. Defaults to "default".

    Returns:
        dict: A dictionary containing the parameters.
    
    >>> func_with_params_and_return(1, "two")
    {'param1': 1, 'param2': 'two'}
    \"""
    return {"param1": param1, "param2": param2}

"""  # End of sample_module_content string


@pytest.fixture
def temp_sample_module(tmp_path: Path, sample_module_content: str) -> Path:
    """Creates a temporary sample_module.py file for testing."""
    sample_file = tmp_path / "sample_module.py"
    sample_file.write_text(sample_module_content)
    return sample_file


@pytest.fixture
def parser() -> GaspatchioDocstringParser:
    return GaspatchioDocstringParser()


def test_parse_docstring_from_text_simple_example(parser: GaspatchioDocstringParser):
    docstring = """
    Hello there.
    >>> print("Test")
    """
    obj_path = "my_mod.my_func"
    file_path = "/fake/path/my_mod.py"
    start_line = 10

    result = parser.parse_docstring_from_text(
        docstring, obj_path, file_path, start_line
    )

    assert result is not None
    assert result.short_description == "Hello there."
    assert result.object_path == obj_path
    assert result.file_path == file_path
    assert result.start_line == start_line
    assert len(result.examples) == 1
    ex = result.examples[0]
    assert ex.snippet.strip() == 'print("Test")'
    assert ex.output is None
    assert ex.object_context == obj_path
    assert ex.example_index == 0
    assert ex.raw_source_location[0] == file_path
    assert ex.raw_source_location[1] == 1


def test_parse_docstring_from_text_with_output(parser: GaspatchioDocstringParser):
    docstring = """
    Another function.
    >>> y = 20
    >>> print(y * 2)
    40
    """
    obj_path = "another.func"
    file_path = "/other/file.py"
    start_line = 5

    result = parser.parse_docstring_from_text(
        docstring, obj_path, file_path, start_line
    )
    assert result is not None
    assert len(result.examples) == 1

    ex0 = result.examples[0]
    assert ex0.snippet.strip() == "y = 20\nprint(y * 2)".replace("\\n", "\n")
    assert ex0.output == "40"
    assert ex0.object_context == obj_path
    assert ex0.example_index == 0
    assert ex0.raw_source_location[1] == 1


def test_parse_docstring_from_text_params_and_returns(
    parser: GaspatchioDocstringParser,
):
    docstring = """
    My function.

    Args:
        p1 (str): Desc for p1.
        p2 (Optional[int]): Desc for p2.

    Returns:
        bool: Always True.
    """
    result = parser.parse_docstring_from_text(docstring, "mod.fn", "/f.py", 1)
    assert result is not None
    assert len(result.parameters) == 2
    assert result.parameters[0].name == "p1"
    assert result.parameters[0].type_name == "str"
    assert result.parameters[0].description == "Desc for p1."
    assert result.parameters[1].name == "p2"
    assert result.parameters[1].type_name == "Optional[int]"
    assert result.returns is not None
    assert result.returns.type_name == "bool"
    assert result.returns.description == "Always True."


def test_process_file(parser: GaspatchioDocstringParser, temp_sample_module: Path):
    results = parser.process_file(temp_sample_module)

    assert len(results) == 7

    simple_ex_doc = next(
        d for d in results if d.object_path == "sample_module.func_with_simple_example"
    )
    assert simple_ex_doc is not None
    assert simple_ex_doc.short_description == "This is a simple function."
    assert len(simple_ex_doc.examples) == 1
    ex1_file = simple_ex_doc.examples[0]
    assert ex1_file.snippet.strip() == 'print("Hello")'
    assert ex1_file.output is None
    assert ex1_file.object_context == "sample_module.func_with_simple_example"
    assert ex1_file.raw_source_location[0] == str(temp_sample_module.resolve())
    assert ex1_file.raw_source_location[1] == 1

    output_ex_doc = next(
        d for d in results if d.object_path == "sample_module.func_with_output_example"
    )
    assert output_ex_doc is not None
    assert len(output_ex_doc.examples) == 1

    ex2_file = output_ex_doc.examples[0]
    assert ex2_file.snippet.strip() == 'x = 10\nprint(f"World {x}")'
    assert ex2_file.output == "World 10"

    multiline_doc = next(
        d
        for d in results
        if d.object_path == "sample_module.func_with_multiline_input_and_output"
    )
    assert multiline_doc is not None
    assert len(multiline_doc.examples) == 1
    ex3 = multiline_doc.examples[0]
    assert ex3.snippet.strip() == "for i in range(2):\n    print(i)"
    assert ex3.output == "0\n1"

    class_doc = next(d for d in results if d.object_path == "sample_module.MyClass")
    assert class_doc is not None
    assert class_doc.short_description == "A sample class."
    assert len(class_doc.examples) == 1
    ex_cls = class_doc.examples[0]
    assert ex_cls.snippet.strip() == "cls_inst = MyClass()"

    method_doc = next(
        d
        for d in results
        if d.object_path == "sample_module.MyClass.method_with_example"
    )
    assert method_doc is not None
    assert len(method_doc.examples) == 1
    ex_method = method_doc.examples[0]
    assert ex_method.snippet.strip() == 'print(f"Method val: {val}")'
    assert ex_method.output == "Method val: test"

    no_ex_doc = next(
        d for d in results if d.object_path == "sample_module.func_no_examples"
    )
    assert no_ex_doc is not None
    assert len(no_ex_doc.examples) == 0

    params_doc = next(
        d
        for d in results
        if d.object_path == "sample_module.func_with_params_and_return"
    )
    assert params_doc is not None
    assert params_doc.short_description == "Short desc."
    assert params_doc.long_description == "Longer description here."
    assert len(params_doc.parameters) == 2
    assert params_doc.parameters[0].name == "param1"
    assert params_doc.parameters[0].type_name == "int"
    assert params_doc.parameters[1].name == "param2"
    assert params_doc.parameters[1].type_name == "str"
    assert params_doc.returns is not None
    assert params_doc.returns.type_name == "dict"
    assert len(params_doc.examples) == 1
    ex_params = params_doc.examples[0]
    assert ex_params.snippet.strip() == 'func_with_params_and_return(1, "two")'
    assert ex_params.output == "{'param1': 1, 'param2': 'two'}"


def test_process_files(parser: GaspatchioDocstringParser, temp_sample_module: Path):
    temp_dir = temp_sample_module.parent
    results = parser.process_files(temp_dir)
    assert len(results) == 7

    simple_ex_doc = next(
        (
            d
            for d in results
            if d.object_path == "sample_module.func_with_simple_example"
        ),
        None,
    )
    assert simple_ex_doc is not None
    assert simple_ex_doc.short_description == "This is a simple function."
    assert len(simple_ex_doc.examples) == 1


def test_parse_docstring_from_text_empty_or_none(parser: GaspatchioDocstringParser):
    assert parser.parse_docstring_from_text(None, "p", "f", 1) is None
    assert parser.parse_docstring_from_text("", "p", "f", 1) is None


def test_parse_docstring_malformed_example_graceful(parser: GaspatchioDocstringParser):
    docstring_text = """
    This has a malformed example.
    >>> print("ok")
    ok
    >>> print(unclosed_paren ( 
    """
    result = parser.parse_docstring_from_text(
        docstring_text, "mod.bad_example", "file.py", 1
    )
    assert result is not None
    assert result.short_description == "This has a malformed example."
    assert len(result.examples) == 2

    ex_mal_0 = result.examples[0]
    assert ex_mal_0.snippet.strip() == 'print("ok")'
    assert ex_mal_0.output == "ok"

    ex_mal_1 = result.examples[1]
    assert ex_mal_1.snippet.strip().startswith("print(unclosed_paren (")
    assert ex_mal_1.output is None


@pytest.fixture
def parser_fixture() -> GaspatchioDocstringParser:
    return GaspatchioDocstringParser()


def test_get_object_path_logic(
    parser_fixture: GaspatchioDocstringParser, tmp_path: Path
):
    content_with_docs = """
import os

class Outer:
    \"""Outer class doc\"""
    def inner_method(self):
        \"""Inner method doc\"""
        pass

def top_level_func():
    \"""Top level func doc\"""
    pass
"""
    p = tmp_path / "path_test_mod.py"
    p.write_text(content_with_docs)
    results_with_docs = parser_fixture.process_file(p)
    paths_with_docs = {r.object_path for r in results_with_docs}

    assert "path_test_mod.Outer" in paths_with_docs
    assert "path_test_mod.Outer.inner_method" in paths_with_docs
    assert "path_test_mod.top_level_func" in paths_with_docs


@pytest.fixture
def project_simple_fixture_path() -> Path:
    path = Path(__file__).parent / "fixtures" / "simple_module_fixture.py"
    if not path.exists():
        pytest.skip(f"Fixture file not found: {path}")
    return path


@pytest.fixture
def project_multi_example_fixture_path() -> Path:
    path = Path(__file__).parent / "fixtures" / "multi_example_fixture.py"
    if not path.exists():
        pytest.skip(f"Fixture file not found: {path}")
    return path


def test_process_file_with_project_simple_fixture(
    parser: GaspatchioDocstringParser, project_simple_fixture_path: Path
):
    results = parser.process_file(project_simple_fixture_path)
    assert len(results) == 5

    get_year_doc = next(
        d
        for d in results
        if d.object_path == "simple_module_fixture.SimpleDateTimeProcessor.get_year"
    )
    assert get_year_doc is not None
    assert len(get_year_doc.examples) == 1
    ex = get_year_doc.examples[0]
    expected_snippet_year = 'processor = SimpleDateTimeProcessor("dummy_data")\nprocessor.get_year("2023-01-01")'
    assert ex.snippet.strip() == expected_snippet_year.replace("\\n", "\n")
    assert ex.output == "2023"

    get_month_doc = next(
        d
        for d in results
        if d.object_path == "simple_module_fixture.SimpleDateTimeProcessor.get_month"
    )
    assert get_month_doc is not None
    assert len(get_month_doc.examples) == 1
    ex_month = get_month_doc.examples[0]
    expected_snippet_month = 'processor = SimpleDateTimeProcessor("dummy_data")\nprocessor.get_month("2023-07-15")'
    assert ex_month.snippet.strip() == expected_snippet_month.replace("\\n", "\n")
    assert ex_month.output == "7"


def test_process_file_with_project_multi_example_fixture(
    parser: GaspatchioDocstringParser, project_multi_example_fixture_path: Path
):
    results = parser.process_file(project_multi_example_fixture_path)
    assert len(results) == 3

    calc_adj_prem_doc = next(
        d
        for d in results
        if d.object_path
        == "multi_example_fixture.PremiumCalculator.calculate_adjusted_premium"
    )
    assert calc_adj_prem_doc is not None
    assert (
        calc_adj_prem_doc.short_description
        == "Calculates an adjusted premium based on several factors."
    )

    assert len(calc_adj_prem_doc.examples) == 2

    ex_grp_1 = calc_adj_prem_doc.examples[0]
    assert "print(df_ex1)" in ex_grp_1.snippet
    assert "Standard Risk" in ex_grp_1.output

    ex_grp_2 = calc_adj_prem_doc.examples[1]
    assert "print(df_ex2)" in ex_grp_2.snippet
    assert "Higher Risk" in ex_grp_2.output
    assert "[200000, 250000, 300000]" in ex_grp_2.output


@pytest.fixture
def dt_proxy_month_fixture_path() -> Path:
    path = Path(__file__).parent / "fixtures" / "dt_proxy_month_fixture.py"
    if not path.exists():
        pytest.skip(f"Fixture file not found: {path}")
    return path


def test_process_dt_proxy_month_fixture(
    parser: GaspatchioDocstringParser, dt_proxy_month_fixture_path: Path
):
    results = parser.process_file(dt_proxy_month_fixture_path)
    docstrings_with_examples = [d for d in results if d.examples]

    assert len(docstrings_with_examples) == 1, (
        "Expected to find one method with examples in dt_proxy_month_fixture.py"
    )

    month_method_doc = next(
        (
            d
            for d in docstrings_with_examples
            if d.object_path == "dt_proxy_month_fixture.DtNamespaceProxy.month"
        ),
        None,
    )
    assert month_method_doc is not None, (
        "Could not find ParsedDocstring for dt_proxy_month_fixture.DtNamespaceProxy.month"
    )

    assert len(month_method_doc.examples) == 2, (
        f"Expected 2 grouped examples, got {len(month_method_doc.examples)}"
    )

    # --- Check the first grouped example (Scalar example) ---
    ex1 = month_method_doc.examples[0]

    # ex1.snippet is expected to be the clean, executable code directly
    expected_clean_snippet1 = (
        "import polars as pl\n"
        "from gaspatchio_core import ActuarialFrame\n"
        'af = ActuarialFrame({"d": pl.date_range("2022-01-01", "2022-03-01", interval="1mo")})\n'
        'print(af.select(af["d"].dt.month().alias("m")).collect())'
    )
    # print(f"ACTUAL ex1.snippet:\n{ex1.snippet}") # Keep for one more run if needed
    # print(f"EXPECTED clean_snippet1:\n{expected_clean_snippet1}")
    assert ex1.snippet == expected_clean_snippet1

    # _extract_code_from_snippet() should return the same if snippet is already clean
    assert ex1._extract_code_from_snippet() == expected_clean_snippet1

    expected_output1 = (
        "shape: (3, 1)\n"
        "┌─────┐\n"
        "│ m   │\n"
        "│ --- │\n"
        "│ i8  │\n"
        "╞═════╡\n"
        "│ 1   │\n"
        "│ 2   │\n"
        "│ 3   │\n"
        "└─────┘"
    )  # Doctest output has its newlines preserved, then rstrip('\n') by parse logic

    assert ex1.output == expected_output1
    assert ex1.object_context == "dt_proxy_month_fixture.DtNamespaceProxy.month"
    assert ex1.example_index == 0

    # --- Check the second grouped example (Vector example) ---
    ex2 = month_method_doc.examples[1]

    expected_clean_snippet2 = (
        "import datetime, polars as pl\n"
        "from gaspatchio_core import ActuarialFrame\n"
        "data = {\n"
        '    "policy_id": ["C003", "D004"],\n'
        '    "claim_lodgement_dates": [\n'
        "        [datetime.date(2022, 3, 10), datetime.date(2022, 4, 5)],\n"
        "        [datetime.date(2023, 1, 20), datetime.date(2023, 11, 30)],\n"
        "    ],\n"
        "}\n"
        "af = ActuarialFrame(data).with_columns(\n"
        '    pl.col("claim_lodgement_dates").cast(pl.List(pl.Date))\n'
        ")\n"
        'months_expr = af["claim_lodgement_dates"].dt.month()\n'
        'print(af.select("policy_id", months_expr.alias("lodgement_months")).collect())'
    )
    assert ex2.snippet == expected_clean_snippet2
    assert ex2._extract_code_from_snippet() == expected_clean_snippet2

    expected_output2 = (
        "shape: (2, 2)\n"
        "┌───────────┬──────────────────┐\n"
        "│ literal   ┆ lodgement_months │\n"
        "│ ---       ┆ ---              │\n"
        "│ str       ┆ list[i8]         │\n"
        "╞═══════════╪══════════════════╡\n"
        "│ policy_id ┆ [3, 4]           │\n"
        "│ policy_id ┆ [1, 11]          │\n"
        "└───────────┴──────────────────┘"
    )  # Doctest output has its newlines preserved, then rstrip('\n') by parse logic

    assert ex2.output == expected_output2
    assert ex2.object_context == "dt_proxy_month_fixture.DtNamespaceProxy.month"
    assert ex2.example_index == 1

    examples_with_output_count = sum(
        1 for ex in month_method_doc.examples if ex.output is not None
    )
    assert examples_with_output_count == 2, (
        f"Expected 2 examples with output after grouping, got {examples_with_output_count}"
    )
