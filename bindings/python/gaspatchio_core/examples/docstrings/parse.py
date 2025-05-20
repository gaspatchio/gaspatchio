import ast
import doctest
import inspect
from pathlib import Path
from typing import List, Optional

import polars as pl
from docstring_parser import parse as docstring_parse_lib
from docstring_parser.common import Docstring  # For type hinting parsed_doc_lib
from loguru import logger

from .models import (
    DocstringCodeExample,
    DocstringParameter,
    DocstringReturn,
    GaspatchioDocstring,
)


class GaspatchioDocstringParser:
    @staticmethod
    def set_polars_print_config(
        tbl_width_chars: int = 1000,
        tbl_cols: int = -1,
        tbl_rows: int = 20,
        fmt_str_lengths: int = 100,
    ):
        pl.Config.set_tbl_width_chars(tbl_width_chars)
        pl.Config.set_tbl_cols(tbl_cols)
        pl.Config.set_tbl_rows(tbl_rows)
        pl.Config.set_fmt_str_lengths(fmt_str_lengths)

    def __init__(self):
        self.set_polars_print_config()

    def _extract_parameters(
        self, parsed_doc_lib: Docstring
    ) -> List[DocstringParameter]:
        params_list = []
        if parsed_doc_lib.params:
            for p_lib in parsed_doc_lib.params:
                params_list.append(
                    DocstringParameter(
                        name=p_lib.arg_name,
                        type_name=p_lib.type_name,
                        description=p_lib.description or "",  # Ensure str
                    )
                )
        return params_list

    def _extract_returns(self, parsed_doc_lib: Docstring) -> Optional[DocstringReturn]:
        if parsed_doc_lib.returns:
            r_lib = parsed_doc_lib.returns
            return DocstringReturn(
                type_name=r_lib.type_name,
                description=r_lib.description or "",  # Ensure str
            )
        return None

    def _extract_examples(
        self,
        docstring_text: str,  # Original full docstring for doctest
        object_path: str,  # For context and doctest naming
        file_path_str: str,  # For DocstringCodeExample model
    ) -> List[DocstringCodeExample]:
        examples_list: List[DocstringCodeExample] = []
        try:
            cleaned_docstring_for_doctest = inspect.cleandoc(docstring_text)
            parsed_by_doctest: List[doctest.Example | str] = (
                doctest.DocTestParser().parse(
                    cleaned_docstring_for_doctest, name=object_path
                )
            )

            current_block_snippets: List[str] = []
            current_block_first_line_no: Optional[int] = None

            doctest_example_objects = [
                ex for ex in parsed_by_doctest if isinstance(ex, doctest.Example)
            ]

            for i, example_obj in enumerate(doctest_example_objects):
                if not current_block_snippets:  # Start of a new block
                    current_block_first_line_no = example_obj.lineno

                # example_obj.source is already clean (no >>> prefixes)
                current_block_snippets.append(example_obj.source)

                if example_obj.want or i == len(doctest_example_objects) - 1:
                    full_snippet = "".join(current_block_snippets)
                    output = example_obj.want.rstrip("\n") if example_obj.want else None

                    line_in_docstring = (
                        current_block_first_line_no
                        if current_block_first_line_no is not None
                        else 0
                    )

                    example_model = DocstringCodeExample(
                        snippet=full_snippet.rstrip("\n"),  # This is the clean snippet
                        output=output,
                        object_context=object_path,
                        example_index=len(examples_list),
                        raw_source_location=(file_path_str, line_in_docstring),
                    )
                    examples_list.append(example_model)

                    current_block_snippets = []
                    current_block_first_line_no = None

        except Exception as e:
            logger.error(
                f"Error during doctest parsing or grouping for {object_path}: {e}"
            )
        return examples_list

    def parse_docstring_from_text(
        self,
        docstring_text: str,
        object_path: str,
        file_path_str: str,
        docstring_start_line: int,
    ) -> Optional[GaspatchioDocstring]:
        """
        Parses a raw docstring string and its context into a GaspatchioDocstring object.

        Args:
            docstring_text: The raw text of the docstring.
            object_path: The fully qualified path of the object this docstring belongs to.
            file_path_str: The string path of the file containing this docstring.
            docstring_start_line: The 1-indexed starting line number of the docstring in the file.

        Returns:
            A GaspatchioDocstring object if parsing is successful, otherwise None.
        """
        if not docstring_text:
            return None

        try:
            # parsed_doc_lib is of type docstring_parser.common.Docstring
            parsed_doc_lib: Docstring = docstring_parse_lib(docstring_text)
        except Exception:
            return GaspatchioDocstring(
                short_description="Error during parsing with docstring_parser.",
                long_description=None,
                parameters=[],
                returns=None,
                examples=[],
                raw_docstring=docstring_text,
                object_path=object_path,
                file_path=file_path_str,
                start_line=docstring_start_line,
            )

        params_list = self._extract_parameters(parsed_doc_lib)
        return_model = self._extract_returns(parsed_doc_lib)
        examples_list = self._extract_examples(
            docstring_text, object_path, file_path_str
        )

        return GaspatchioDocstring(
            short_description=parsed_doc_lib.short_description,
            long_description=parsed_doc_lib.long_description,
            parameters=params_list,
            returns=return_model,
            examples=examples_list,
            raw_docstring=docstring_text,
            object_path=object_path,
            file_path=file_path_str,
            start_line=docstring_start_line,
        )

    def _get_object_path(
        self, node: ast.AST, file_path_obj: Path, parent_map: dict
    ) -> str:
        """Generates a Python-like path for an AST node."""
        name_parts = []
        curr = node
        while curr is not None:
            if isinstance(curr, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name_parts.append(curr.name)
            elif isinstance(curr, ast.Module):
                name_parts.append(file_path_obj.stem)
                break

            if curr not in parent_map or parent_map.get(curr) is None:
                if (
                    not isinstance(curr, ast.Module)
                    and file_path_obj.stem not in name_parts
                ):
                    name_parts.append(file_path_obj.stem)
                break
            curr = parent_map.get(curr)

        return ".".join(reversed(name_parts))

    def process_file(self, file_path: Path) -> List[GaspatchioDocstring]:
        """Processes a single Python file and extracts docstrings."""
        collected_docstrings: List[GaspatchioDocstring] = []
        try:
            file_content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(file_content, filename=str(file_path))

            parent_map = {
                child: parent
                for parent in ast.walk(tree)
                for child in ast.iter_child_nodes(parent)
            }
            parent_map[tree] = None

            for node in ast.walk(tree):
                if not isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    continue

                raw_docstring = ast.get_docstring(node, clean=False)
                if not raw_docstring:
                    continue

                docstring_start_line = 0
                if node.body and isinstance(node.body[0], ast.Expr):
                    if isinstance(node.body[0].value, (ast.Constant, ast.Str)):
                        docstring_start_line = node.body[0].lineno

                if not docstring_start_line:
                    docstring_start_line = node.lineno

                object_path_str = self._get_object_path(node, file_path, parent_map)

                parsed_docstring_obj = self.parse_docstring_from_text(
                    docstring_text=raw_docstring,
                    object_path=object_path_str,
                    file_path_str=str(file_path.resolve()),
                    docstring_start_line=docstring_start_line,
                )
                if parsed_docstring_obj:
                    collected_docstrings.append(parsed_docstring_obj)

        except Exception:
            pass

        return collected_docstrings

    def process_files(self, root_dir: Path) -> List[GaspatchioDocstring]:
        """Recursively processes all Python files in a directory."""
        all_docstrings: List[GaspatchioDocstring] = []
        for py_file in root_dir.rglob("*.py"):
            if py_file.is_file():
                all_docstrings.extend(self.process_file(py_file))
        return all_docstrings
