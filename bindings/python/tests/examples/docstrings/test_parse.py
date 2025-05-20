from pathlib import Path

import pytest
from gaspatchio_core.examples.docstrings.parse import GaspatchioDocstringParser


@pytest.fixture(scope="module")
def sample_module_content() -> str:
    return """\"\"\"A sample module for testing.\"\"\"

def func_with_simple_example(a: int):
    \"\"\"
    This is a simple function.

    Examples:
    ---------
    ```python
    print(\"Hello\")
    ```
    \"\"\"
    pass

def func_with_output_example(b: str):
    \"\"\"
    This function has output.

    Examples:
    ---------
    ```python
    x = 10
    print(f\"World {x}\")
    ```
    ```text
    World 10
    ```
    \"\"\"
    pass

def func_with_multiline_input_and_output():
    \"\"\"
    Multiline input and output.

    Examples:
    ---------
    ```python
    for i in range(2):
        print(i)
    ```
    ```
    0
    1
    ```
    \"\"\"
    pass

class MyClass:
    \"\"\"
    A sample class.

    Examples:
    ---------
    ```python
    cls_inst = MyClass()
    ```
    \"\"\"
    def method_with_example(self, val):
        \"\"\"
        A method with its own example.

        Examples:
        ---------
        ```python
        print(f\"Method val: {val}\")
        ```
        ```text
        Method val: test
        ```
        # Assuming val will be 'test' contextually for the example output
        \"\"\"
        return val

def func_no_examples():
    \"\"\"This function has no examples.\"\"\"
    pass

def func_with_params_and_return(param1: int, param2: str = \"default\") -> dict:
    \"\"\"
    Short desc.

    Longer description here.

    Args:
        param1 (int): The first parameter.
        param2 (str, optional): The second. Defaults to \"default\".

    Returns:
        dict: A dictionary containing the parameters.
    
    Examples:
    ---------
    ```python
    func_with_params_and_return(1, \"two\")
    ```
    ```json
    {"param1": 1, "param2": "two"}
    ```
    \"\"\"
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
    This is a simple function.

    Examples:
    ---------
    ```python
    print(\"Hello\")
    ```
    """
    obj_path = "my_mod.my_func"
    file_path = "/fake/path/my_mod.py"
    start_line = 10

    result = parser.parse_docstring_from_text(
        docstring, obj_path, file_path, start_line
    )

    assert result is not None
    assert result.short_description == "This is a simple function."
    assert result.object_path == obj_path
    assert result.file_path == file_path
    assert result.start_line == start_line
    assert len(result.examples) == 1
    ex = result.examples[0]
    assert ex.snippet.strip() == 'print("Hello")'
    assert ex.output is None  # No output block provided
    assert ex.object_context == obj_path
    assert ex.example_index == 0
    assert ex.raw_source_location[0] == file_path
    assert ex.raw_source_location[1] >= 0  # Line number from markdown-it


def test_parse_docstring_from_text_with_output(parser: GaspatchioDocstringParser):
    docstring = """
    This function has output.

    Examples:
    ---------
    ```python
    x = 10
    print(f"World {x}")
    ```
    ```text
    World 10
    ```
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
    assert (
        ex0.snippet.strip() == 'x = 10\nprint(f"World {x}")'
    )  # Corrected for direct code
    assert ex0.output == "World 10"
    assert ex0.object_context == obj_path
    assert ex0.example_index == 0
    assert ex0.raw_source_location[1] >= 0  # Line number from markdown-it


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

    # Expected number of docstrings based on the updated sample_module_content
    # Module doc, func_with_simple_example, func_with_output_example,
    # func_with_multiline_input_and_output, MyClass, MyClass.method_with_example,
    # func_no_examples, func_with_params_and_return
    assert (
        len(results) == 7
    )  # Module docstring is not parsed by process_file for objects

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
    # Line numbers are relative to the __doc__ string given to markdown-it
    assert ex1_file.raw_source_location[1] >= 0

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
    assert ex_cls.output is None

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
    assert ex_params.output == '{"param1": 1, "param2": "two"}'


def test_process_files(parser: GaspatchioDocstringParser, temp_sample_module: Path):
    temp_dir = temp_sample_module.parent
    results = parser.process_files(temp_dir)
    assert len(results) == 7  # Same count as test_process_file for this setup

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


# @pytest.mark.skip(reason="Relies on >>> doctest format. Needs update for Markdown.")
def test_process_file_with_project_simple_fixture(
    parser: GaspatchioDocstringParser, project_simple_fixture_path: Path
):
    results = parser.process_file(project_simple_fixture_path)
    # Expected: SimpleDateTimeProcessor, get_year, get_month, get_day, utility_function, module_level_function_simple
    assert len(results) == 6

    get_year_doc = next(
        d
        for d in results
        if d.object_path == "simple_module_fixture.SimpleDateTimeProcessor.get_year"
    )
    assert get_year_doc is not None
    assert len(get_year_doc.examples) == 1
    ex = get_year_doc.examples[0]
    expected_snippet_year = 'processor = SimpleDateTimeProcessor("dummy_data")\nprocessor.get_year("2023-01-01")'
    assert ex.snippet.strip() == expected_snippet_year
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
    assert ex_month.snippet.strip() == expected_snippet_month
    assert ex_month.output == "7"

    get_day_doc = next(
        d
        for d in results
        if d.object_path == "simple_module_fixture.SimpleDateTimeProcessor.get_day"
    )
    assert get_day_doc is not None
    assert not get_day_doc.examples  # This one has no examples

    module_func_doc = next(
        d
        for d in results
        if d.object_path == "simple_module_fixture.module_level_function_simple"
    )
    assert module_func_doc is not None
    assert not module_func_doc.examples


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


@pytest.fixture
def dt_proxy_month_md_fixture_path() -> Path:
    path = Path(__file__).parent / "fixtures" / "dt_proxy_month_md_fixture.py"
    if not path.exists():
        pytest.skip(f"Fixture file not found: {path}")
    return path


@pytest.fixture
def dt_proxy_month_md_docstring_content(dt_proxy_month_md_fixture_path: Path) -> str:
    import importlib.util
    import sys  # Import sys

    # Create a unique name for the module to avoid conflicts if run multiple times
    module_name = f"_fixture_module_{dt_proxy_month_md_fixture_path.stem}"
    spec = importlib.util.spec_from_file_location(
        module_name, dt_proxy_month_md_fixture_path
    )
    fixture_module = importlib.util.module_from_spec(spec)
    # Add to sys.modules before loading, remove after, to handle re-runs correctly
    if module_name in sys.modules:
        del sys.modules[module_name]  # Remove if somehow it's already there
    sys.modules[module_name] = fixture_module
    try:
        spec.loader.exec_module(fixture_module)
        docstring = fixture_module.DtNamespaceProxy.month.__doc__
        if docstring is None:
            pytest.skip("Docstring not found in fixture module.")
        return docstring
    finally:
        if module_name in sys.modules:
            del sys.modules[module_name]


def test_parse_markdown_fenced_examples_from_fixture(
    parser: GaspatchioDocstringParser,
    dt_proxy_month_md_docstring_content: str,
    dt_proxy_month_md_fixture_path: Path,  # Pass path for context
):
    file_path_str = str(dt_proxy_month_md_fixture_path.resolve())
    object_path = "dt_proxy_month_md_fixture.DtNamespaceProxy.month"

    # We need to get an approximate start line of the docstring for the model.
    # This is tricky without parsing the fixture file's AST here.
    # For the purpose of this test, we can use a placeholder or find a robust way.
    # Let's assume the docstring content itself is the primary target for parsing examples.
    # The Docstring model's start_line is for the overall docstring, not specific examples inside.
    # The example's raw_source_location[1] is relative to the cleaned docstring text.

    # Let's find the line number of DtNamespaceProxy.month to simulate a more complete parse
    # This is a bit complex for a unit test fixture setup, typically you'd have simpler inputs.
    # For now, the `parse_docstring_from_text` will be tested with a dummy line for the docstring itself.
    # The internal example line numbers come from markdown-it relative to cleandoc string.

    docstring_model = parser.parse_docstring_from_text(
        dt_proxy_month_md_docstring_content,
        object_path,
        file_path_str,
        10,  # Dummy overall docstring start line for this test model
    )

    assert docstring_model is not None
    assert (
        docstring_model.short_description
        == "Extract the month number from a date/datetime expression."
    )
    assert len(docstring_model.examples) == 2, (
        f"Expected 2 examples, found {len(docstring_model.examples)}"
    )

    # Example 1: Scalar
    ex1 = docstring_model.examples[0]
    assert "import polars as pl" in ex1.snippet
    assert 'print(af.select(af["d"].dt.month().alias("m")).collect())' in ex1.snippet
    assert ex1.output is not None, "Example 1 output should not be None"
    assert "shape: (3, 1)" in ex1.output
    assert "┌─────┐" in ex1.output
    assert "│ 1   │" in ex1.output
    assert "│ 2   │" in ex1.output
    assert "│ 3   │" in ex1.output
    assert "└─────┘" in ex1.output
    assert ex1.object_context == object_path
    assert ex1.example_index == 0
    assert ex1.prefix_tags == []
    assert ex1.raw_source_location[0] == file_path_str
    # Check line number from markdown token (0-indexed from start of cleaned docstring)
    # Based on fixture: "Examples\n--------\nScalar example::\n\n            ```python" (line after this is the code block)
    # inspect.cleandoc will handle the initial indentation.
    # `Scalar example::` is line 3 of the docstring body if short desc is line 1.
    # The ```python is on line 5 (approx) of the body content given to markdown-it.
    # Let's verify this more precisely if the test fails.
    # For now, we trust markdown-it's map if the content is right.
    # The first code block ```python is at line 5 of the cleandoc'ed docstring part passed to markdown-it
    # (after short_description, blank line, Examples, --------, Scalar example::, blank line)
    # So token.map[0] should be around 4 or 5 depending on how cleandoc processes the initial lines.
    # Let's check if it's a small positive integer.
    assert ex1.raw_source_location[1] >= 0

    # Example 2: Vector
    ex2 = docstring_model.examples[1]
    assert "import datetime" in ex2.snippet  # Check for 'import datetime'
    assert "import polars as pl" in ex2.snippet  # Check for 'import polars as pl'
    assert "from gaspatchio_core import ActuarialFrame" in ex2.snippet
    assert "data = {" in ex2.snippet
    assert ex2.output is not None, "Example 2 output should not be None"
    assert "shape: (2, 2)" in ex2.output
    assert "│ policy_id ┆ [3, 4]           │" in ex2.output
    assert "│ policy_id ┆ [1, 11]          │" in ex2.output
    assert ex2.object_context == object_path
    assert ex2.example_index == 1
    assert ex2.prefix_tags == []
    assert ex2.raw_source_location[0] == file_path_str
    assert ex2.raw_source_location[1] > ex1.raw_source_location[1]


# Add a test for prefix_tags
@pytest.fixture
def docstring_with_tags_content() -> str:
    return """
    My func with tags.

    Examples:
    --------
    ```python skip no-check whatever
    print("skipped")
    ```

    ```python expect_failure
    raise ValueError("failed as expected")
    ```
    ```
    # This output block for expect_failure might be ignored or used to verify exception message
    # For now, the parser just extracts it.
    # ValueError: failed as expected 
    ```
    """


def test_parse_markdown_fenced_examples_with_tags(
    parser: GaspatchioDocstringParser, docstring_with_tags_content: str
):
    file_path_str = "/fake/tags_file.py"
    object_path = "tags_mod.func_with_tags"

    docstring_model = parser.parse_docstring_from_text(
        docstring_with_tags_content, object_path, file_path_str, 1
    )

    assert docstring_model is not None
    assert len(docstring_model.examples) == 2

    ex1 = docstring_model.examples[0]
    assert ex1.snippet.strip() == 'print("skipped")'
    assert ex1.output is None  # No output block after the first example
    assert ex1.prefix_tags == ["skip", "no-check", "whatever"]

    ex2 = docstring_model.examples[1]
    assert ex2.snippet.strip() == 'raise ValueError("failed as expected")'
    assert ex2.output is not None
    assert "# ValueError: failed as expected" in ex2.output
    assert ex2.prefix_tags == ["expect_failure"]


# @pytest.mark.skip(reason="Old doctest fixture, needs update to MD or removal after new tests cover process_file with MD.")
def test_process_file_dt_proxy_month_md_fixture(
    parser: GaspatchioDocstringParser,
    dt_proxy_month_md_fixture_path: Path,  # Use the MD fixture path
):
    results = parser.process_file(dt_proxy_month_md_fixture_path)
    docstrings_with_examples = [d for d in results if d.examples]

    assert len(docstrings_with_examples) == 1, (
        f"Expected 1 method with examples, found {len(docstrings_with_examples)} in {dt_proxy_month_md_fixture_path}"
    )

    month_method_doc = next(
        (
            d
            for d in docstrings_with_examples
            if d.object_path == "dt_proxy_month_md_fixture.DtNamespaceProxy.month"
        ),
        None,
    )

    assert month_method_doc is not None, (
        "Could not find ParsedDocstring for dt_proxy_month_md_fixture.DtNamespaceProxy.month"
    )

    assert len(month_method_doc.examples) == 2, (
        f"Expected 2 MD examples, got {len(month_method_doc.examples)}"
    )

    # --- Check the first MD example (Scalar example) ---
    ex1 = month_method_doc.examples[0]
    expected_snippet1 = (
        "import polars as pl\n"
        "from gaspatchio_core import ActuarialFrame\n"
        'af = ActuarialFrame({"d": pl.date_range("2022-01-01", "2022-03-01", interval="1mo")})\n'
        'print(af.select(af["d"].dt.month().alias("m")).collect())'
    )
    assert ex1.snippet == expected_snippet1
    assert ex1.output is not None
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
    )
    assert ex1.output == expected_output1
    assert ex1.object_context == "dt_proxy_month_md_fixture.DtNamespaceProxy.month"
    assert ex1.example_index == 0
    assert not ex1.prefix_tags

    # --- Check the second MD example (Vector example) ---
    ex2 = month_method_doc.examples[1]
    expected_snippet2 = (
        "import datetime\n"
        "import polars as pl\n"
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
    assert ex2.snippet == expected_snippet2
    assert ex2.output is not None
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
    )
    assert ex2.output == expected_output2
    assert ex2.object_context == "dt_proxy_month_md_fixture.DtNamespaceProxy.month"
    assert ex2.example_index == 1
    assert not ex2.prefix_tags


def test_validate_structure_detects_legacy_doctests(parser: GaspatchioDocstringParser):
    docstring_with_legacy = """
    A function with old-style doctests.

    Short description is present.

    Examples:
    ---------
    >>> print("This is a legacy doctest")
    This is a legacy doctest

    ... x = 10
    ... print(x)
    10
    """
    obj_path = "legacy_mod.legacy_func"
    file_path = "/fake/path/legacy_mod.py"
    start_line = 1

    # Parse the docstring (even though examples won't be extracted by current _extract_examples)
    gs_docstring = parser.parse_docstring_from_text(
        docstring_with_legacy, obj_path, file_path, start_line
    )

    assert gs_docstring is not None
    # The short description from docstring_parser might pick up the first line
    # if not separated by a blank line after the signature in a real scenario.
    # Here, `inspect.cleandoc` within `parse_docstring_from_text` (via `_extract_examples` and `docstring_parse_lib`)
    # will process the raw string. `docstring_parse_lib` gets the raw string.
    # The short description is extracted by `docstring_parse_lib`.
    # Given the input `docstring_with_legacy`, `docstring_parse_lib` will identify
    # "A function with old-style doctests." as short_description.
    assert gs_docstring.short_description == "A function with old-style doctests."

    # Now validate the structure
    issues = gs_docstring.validate_structure()

    # We expect at least one issue (the legacy doctest one).
    # If short_description was missing, that would be another.
    assert len(issues) >= 1, (
        f"Expected at least one issue, got {len(issues)}. Issues: {issues}"
    )
    expected_issue_message = (
        "[Structure Error] Legacy '>>>' or '...' doctest markers found in the raw docstring. "
        "Please convert all examples to Markdown fenced code blocks (e.g., ```python ... ```)."
    )
    assert any(expected_issue_message in issue for issue in issues), (
        f"Expected legacy doctest warning, but not found. Issues: {issues}"
    )

    # Verify that no examples were parsed into the .examples list by the MD parser
    assert len(gs_docstring.examples) == 0, (
        f"Markdown parser should not extract legacy '>>>' examples into the examples list. Found: {len(gs_docstring.examples)}"
    )
