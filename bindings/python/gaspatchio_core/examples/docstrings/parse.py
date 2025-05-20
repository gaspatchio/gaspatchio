import ast
import inspect
import logging
from pathlib import Path
from typing import List, Optional

import polars as pl
from docstring_parser import parse as docstring_parse_lib
from docstring_parser.common import Docstring  # For type hinting parsed_doc_lib
from loguru import logger  # Ensure this is the logger we use
from markdown_it import MarkdownIt

from .models import (
    DocstringCodeExample,
    DocstringParameter,
    DocstringReturn,
    GaspatchioDocstring,
)

logger = logging.getLogger(__name__)


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
        docstring_text: str,
        object_path: str,
        file_path_str: str,
    ) -> List[DocstringCodeExample]:
        examples_list: List[DocstringCodeExample] = []
        if not docstring_text:
            return examples_list

        # Always run cleandoc on the input docstring text first.
        docstring_to_parse = inspect.cleandoc(docstring_text)

        md = MarkdownIt().disable("code")  # Disable indented code blocks
        tokens = md.parse(docstring_to_parse)
        logger.debug(
            f"Object Path: {object_path}\nCleaned Docstring for MD (len {len(docstring_to_parse)}):\n'''{docstring_to_parse[:500]}...'''"
        )
        logger.debug(
            f"MD Tokens ({len(tokens)} total). First 10: {[str(t) for t in tokens[:10]]}"
        )

        i = 0
        example_idx_counter = 0
        while i < len(tokens):
            token = tokens[i]
            content_preview = (
                token.content.replace("\n", "\\n")[:70] if token.content else "N/A"
            )
            logger.debug(
                f"Token [{i}/{len(tokens) - 1}]: type='{token.type}', info='{token.info}', map={token.map}, hidden={token.hidden}, level={token.level}, content_preview='{content_preview}'"
            )

            if token.type == "fence" and token.info.startswith("python"):
                logger.debug(
                    f"---> Found python code fence: info='{token.info}', map={token.map}"
                )
                code_snippet = token.content
                line_start_in_cleaned_docstring = token.map[0] if token.map else 0

                info_parts = token.info.split()
                parsed_prefix_tags = [part for part in info_parts[1:] if part]

                extracted_output: Optional[str] = None
                consumed_for_output_block = (
                    0  # How many extra tokens the output block consumed
                )

                # Check for an immediately following output block
                if i + 1 < len(tokens):
                    potential_output_token_1 = tokens[i + 1]
                    logger.debug(
                        f"    Checking next token [{i + 1}] for output: type='{potential_output_token_1.type}', info='{potential_output_token_1.info}'"
                    )

                    # If the next token is another Python code block, current one has no output
                    if (
                        potential_output_token_1.type == "fence"
                        and potential_output_token_1.info.startswith("python")
                    ):
                        logger.debug(
                            "    Next token is another Python code fence. Current example has no output."
                        )
                        pass  # extracted_output remains None, consumed_for_output_block remains 0
                    # Else, if it's any other kind of fence, consider it output
                    elif potential_output_token_1.type == "fence":
                        logger.debug(
                            f"    SUCCESS: Output found in fence (info: '{potential_output_token_1.info}')."
                        )
                        extracted_output = potential_output_token_1.content.strip()
                        consumed_for_output_block = 1  # Consumed this output fence
                    # Else, check for paragraph structure for output
                    elif potential_output_token_1.type == "paragraph_open":
                        logger.debug(
                            "    Next token is paragraph_open. Checking structure for output..."
                        )
                        if (
                            i + 3
                            < len(
                                tokens
                            )  # Need paragraph_open, inline, paragraph_close
                            and tokens[i + 2].type == "inline"
                            and tokens[i + 3].type == "paragraph_close"
                        ):
                            inline_content_preview = tokens[i + 2].content.replace(
                                "\n", "\\n"
                            )[:70]
                            logger.debug(
                                f"    SUCCESS: Output found in paragraph (inline content: '{inline_content_preview}')."
                            )
                            extracted_output = tokens[i + 2].content.strip()
                            consumed_for_output_block = (
                                3  # Consumed paragraph_open, inline, paragraph_close
                            )
                        else:
                            logger.debug(
                                f"    Paragraph structure for output not matched. Tokens: {tokens[i + 1 : i + 4]}"
                            )
                    else:
                        logger.debug(
                            f"    No specific output block (fence or paragraph) found immediately after code fence (next token type: {potential_output_token_1.type})"
                        )
                else:
                    logger.debug(
                        "    No more tokens after code fence to check for output."
                    )

                example_model = DocstringCodeExample(
                    snippet=code_snippet.rstrip("\n"),
                    output=extracted_output,
                    object_context=object_path,
                    example_index=example_idx_counter,
                    raw_source_location=(
                        file_path_str,
                        line_start_in_cleaned_docstring,
                    ),
                    prefix_tags=parsed_prefix_tags,
                    # parent_docstring will be set when GaspatchioDocstring is created if needed
                )
                logger.debug(
                    f"---> Added example #{example_idx_counter}: tags={parsed_prefix_tags}, snippet_len={len(code_snippet)}, output_exists={extracted_output is not None}"
                )
                examples_list.append(example_model)
                example_idx_counter += 1
                i += (
                    1 + consumed_for_output_block
                )  # Advance past code block and any consumed output block
            else:
                i += 1  # Not a python code fence, just advance to the next token
        logger.debug(
            f"===> Finished extracting examples for '{object_path}'. Total found: {len(examples_list)}"
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
