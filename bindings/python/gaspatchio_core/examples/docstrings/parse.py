import ast
import inspect
import logging
import re
import shlex
import textwrap
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

    def __init__(self, include_private: bool = False):
        self.include_private = include_private
        self.set_polars_print_config()
        # Initialize markdown-it parser once
        self.md_parser = MarkdownIt().disable(
            "code"
        )  # For parsing overall docstring structure
        self.md_parser_for_examples = MarkdownIt()  # For extracting code examples

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

    def _extract_when_to_use(self, docstring_text: str) -> Optional[str]:
        """Extracts the 'When to use' section from a docstring."""
        cleaned_doc = inspect.cleandoc(docstring_text)
        lines = cleaned_doc.splitlines()

        when_to_use_content_lines: List[str] = []
        in_when_to_use_block = False
        marker_line_found = False

        marker = '!!! note "When to use"'

        for line in lines:
            if not marker_line_found:
                if line.strip() == marker:
                    marker_line_found = True
                    in_when_to_use_block = True
                continue

            if in_when_to_use_block:
                # Content lines must be indented (typically 4 spaces)
                if line.startswith("    "):
                    when_to_use_content_lines.append(line[4:])
                elif (
                    line.strip() == "" and when_to_use_content_lines
                ):  # Allow empty lines within the block if content has started
                    when_to_use_content_lines.append("")
                else:
                    # Block ends if line is not indented as expected, or is non-empty and not indented
                    break

        if when_to_use_content_lines:
            # Join and then rstrip to remove any trailing newlines from potentially multiple empty lines at the end
            return "\n".join(when_to_use_content_lines).rstrip()
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

        cleaned_doc = inspect.cleandoc(docstring_text)

        # Regex breakdown for a fenced code block:
        # Group 1: (^ *```) - The opening fence marker (e.g., "  ```"), including leading spaces on its line.
        # Group 2: ( *) - Spaces immediately after the opening ``` marker (usually none).
        # Group 3: (.*?) - The info string (e.g., "python", "python skip", "text"), non-greedy. Ends at newline.
        # Group 4: (.+?) - The actual content of the block. Non-greedy. re.S (DOTALL) makes . match newlines.
        # \1 at the end: Backreference to what Group 1 matched (e.g., "  ```"), ensuring closing fence structure matches opening.
        # [ \t]*$: Optional trailing spaces/tabs on the closing fence line.
        # Using re.MULTILINE for ^ and re.DOTALL for . matching newlines in content.
        block_regex = re.compile(
            r"(^ *```)( *)(.*?)\n(.+?)\n\1[ \t]*$", re.MULTILINE | re.DOTALL
        )

        all_matches = list(block_regex.finditer(cleaned_doc))

        i = 0
        example_idx_counter = 0
        while i < len(all_matches):
            current_match = all_matches[i]

            # info_string is from Group 3
            current_info_string = current_match.group(3).strip()
            # raw_content is from Group 4
            current_raw_content = current_match.group(4)

            shlex_parts = shlex.split(current_info_string)
            if not shlex_parts:
                # Empty info string, treat as non-python or skip
                i += 1
                continue

            language_specifier = shlex_parts[0].lower()

            if language_specifier == "python" or language_specifier == "py":
                # This is a Python code block
                snippet = textwrap.dedent(current_raw_content).rstrip("\n")
                parsed_prefix_tags = shlex_parts[1:]

                # Line number of the opening ``` marker (0-indexed within cleaned_doc)
                line_start_of_block_marker = cleaned_doc[: current_match.start()].count(
                    "\n"
                )

                extracted_output: Optional[str] = None
                consumed_next_block = False

                # Check if there's a next block that could be an output
                if i + 1 < len(all_matches):
                    next_match = all_matches[i + 1]
                    next_info_string_shlex_parts = shlex.split(
                        next_match.group(3).strip()
                    )
                    next_language_specifier = ""
                    if next_info_string_shlex_parts:
                        next_language_specifier = next_info_string_shlex_parts[
                            0
                        ].lower()

                    # To be an output, the next block must start "immediately" after current
                    text_between_blocks = cleaned_doc[
                        current_match.end() : next_match.start()
                    ]
                    if not text_between_blocks.strip():  # Only whitespace (or empty)
                        # And it's not another python block (empty lang spec is OK for output)
                        if (
                            next_language_specifier != "python"
                            and next_language_specifier != "py"
                        ):
                            extracted_output = textwrap.dedent(
                                next_match.group(4)
                            ).strip()  # Dedent and strip for output
                            consumed_next_block = True

                example_model = DocstringCodeExample(
                    snippet=snippet,
                    output=extracted_output,
                    object_context=object_path,
                    example_index=example_idx_counter,
                    raw_source_location=(file_path_str, line_start_of_block_marker),
                    prefix_tags=list(parsed_prefix_tags),  # Ensure it's a list
                )
                examples_list.append(example_model)
                example_idx_counter += 1

                if consumed_next_block:
                    i += 2  # Advance past current python block and its consumed output block
                else:
                    i += 1  # Advance past current python block
            else:
                # This block was not a python block (based on info string), so just skip it
                i += 1

        logger.debug(
            f"===> Finished extracting examples for '{object_path}' using regex. Total found: {len(examples_list)}"
        )
        logger.debug(
            f"  >>> _extract_examples for {object_path} RETURNING list ID: {id(examples_list)}, len: {len(examples_list)}"
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
            docstring_start_line: The starting line number of the docstring in the file.

        Returns:
            A GaspatchioDocstring object if parsing is successful, otherwise None.
        """
        if not docstring_text:
            return None

        try:
            parsed_doc_lib: Docstring = docstring_parse_lib(docstring_text)
        except Exception as e:  # Catch errors from docstring_parser library
            logger.warning(
                f"Error parsing with docstring_parser for {object_path} in {file_path_str}: {e}. "
                f"Proceeding with markdown-it-py for examples only."
            )
            # Create a dummy parsed_doc_lib if parsing fails, so we can still try to get examples
            parsed_doc_lib = Docstring()
            # Ensure dummy has necessary attributes even if empty
            parsed_doc_lib.short_description = "Error during parsing (see logs)."
            parsed_doc_lib.long_description = None  # Ensure it has this attribute
            parsed_doc_lib.params = []
            parsed_doc_lib.returns = None

        # Use markdown-it-py for reliable code block extraction
        # Pass the original object_path for context in DocstringCodeExample
        extracted_md_examples = self._extract_examples(
            docstring_text, object_path, file_path_str
        )
        logger.debug(
            f"  In parse_docstring_from_text for {object_path}: extracted_md_examples (id: {id(extracted_md_examples)}, len: {len(extracted_md_examples)}) before GaspatchioDocstring creation."
        )

        current_line_number = docstring_start_line

        # Extract parameters and returns using the helper methods
        # These will now use the DocstringParameter and DocstringReturn from .models
        # because the local DocstringParameter class definition was removed.
        extracted_params = self._extract_parameters(parsed_doc_lib)
        extracted_returns = self._extract_returns(parsed_doc_lib)
        extracted_when_to_use = self._extract_when_to_use(docstring_text)

        gs_doc_obj = GaspatchioDocstring(
            raw_docstring=docstring_text,
            # Populate all fields from parsed_doc_lib and extracted parts
            short_description=parsed_doc_lib.short_description,
            long_description=parsed_doc_lib.long_description,
            when_to_use=extracted_when_to_use,
            parameters=extracted_params,
            returns=extracted_returns,
            examples=list(extracted_md_examples),  # Force a copy
            file_path=file_path_str,
            object_path=object_path,
            start_line=current_line_number,
        )
        logger.debug(
            f"  >>> parse_docstring_from_text for {object_path} CREATED GaspatchioDocstring (ID: {id(gs_doc_obj)}). "
            f"gs_doc_obj.examples (id: {id(gs_doc_obj.examples)}, len: {len(gs_doc_obj.examples)})"
        )
        return gs_doc_obj

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
        except (IOError, OSError) as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return collected_docstrings
        except SyntaxError as e:
            logger.error(f"Syntax error parsing AST for {file_path}: {e}")
            return collected_docstrings
        except Exception as e:
            logger.error(f"Unexpected error during initial parsing of {file_path}: {e}")
            return collected_docstrings

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

            current_node_name = getattr(
                node, "name", "UnnamedNode"
            )  # Get current node name for logging
            logger.debug(
                f"Processing AST node: {current_node_name} of type {type(node).__name__}"
            )

            object_path_str = (
                "UnknownObjectPath"  # Default in case of error before path is resolved
            )
            try:
                raw_docstring = ast.get_docstring(node, clean=False)
                if not raw_docstring:
                    logger.debug(
                        f"  No raw docstring found for node: {current_node_name}"
                    )
                    continue
                logger.debug(
                    f"  Raw docstring found for {current_node_name} (len {len(raw_docstring)}), starts: '{raw_docstring[:100].replace('\n', '\\n')}'"
                )

                # For Python 3.8+, docstrings are ast.Constant. For older, ast.Str.
                # We need the line number of the docstring node itself.
                docstring_node = None
                if isinstance(
                    node,
                    (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef, ast.Module),
                ):
                    if node.body and isinstance(node.body[0], ast.Expr):
                        if isinstance(
                            node.body[0].value, (ast.Constant, ast.Str)
                        ):  # ast.Str for <3.8
                            docstring_node = node.body[0].value

                # docstring_start_line = docstring_node.lineno if docstring_node else node.lineno + 1
                # Fallback to node.lineno + 1 might be too naive.
                # A more reliable way is to get the line number of the docstring expression node.
                # ast.get_docstring() doesn't provide this directly.
                # We assume that if a docstring exists (raw_docstring_text is not None),
                # then node.body[0].value IS the docstring node.
                docstring_actual_start_line = (
                    docstring_node.lineno if docstring_node else node.lineno
                )  # Fallback to node's line if no specific docstring node found (e.g. empty)

                object_path_str = self._get_object_path(node, file_path, parent_map)
                logger.debug(
                    f"  Resolved object_path: {object_path_str} for node: {current_node_name}"
                )

                parsed_docstring_obj = self.parse_docstring_from_text(
                    docstring_text=raw_docstring,
                    object_path=object_path_str,
                    file_path_str=str(file_path.resolve()),
                    docstring_start_line=docstring_actual_start_line,  # Pass the determined start line
                )
                if parsed_docstring_obj:
                    logger.debug(
                        f"  In process_file for {object_path_str}: parsed_docstring_obj (ID: {id(parsed_docstring_obj)}) "
                        f"BEFORE APPEND. Examples (id: {id(parsed_docstring_obj.examples)}, len: {len(parsed_docstring_obj.examples)})"
                    )
                    if parsed_docstring_obj.examples:
                        for idx, ex_item in enumerate(parsed_docstring_obj.examples):
                            logger.debug(
                                f"    Example {idx} context: {ex_item.object_context}, snippet: '{ex_item.snippet[:50].replace('\n', '\\n')}'..."
                            )
                    collected_docstrings.append(parsed_docstring_obj)
                    logger.debug(
                        f"  In process_file for {object_path_str}: parsed_docstring_obj (ID: {id(parsed_docstring_obj)}) "
                        f"AFTER APPEND. Examples (id: {id(parsed_docstring_obj.examples)}, len: {len(parsed_docstring_obj.examples)})"
                    )
                else:
                    logger.debug(
                        f"  Parsing returned None for docstring of {object_path_str}"
                    )
            except Exception as e:
                # Log the error with context and continue to the next node
                node_name_for_log = getattr(node, "name", "UnnamedNode")
                logger.error(
                    f"Failed to process docstring for '{object_path_str}' (or node '{node_name_for_log}') "
                    f"in {file_path}: {e}",
                    exc_info=True,  # Include stack trace for the error
                )
                continue  # Try to process the next node in the file

        logger.debug(f"=== FINISHING process_file for {file_path} ===")
        logger.debug(
            f"Total GaspatchioDocstring objects collected: {len(collected_docstrings)}"
        )
        for i, ds_obj in enumerate(collected_docstrings):
            examples_list_id_str = "N/A"
            examples_len_str = "N/A"  # Add length here
            if hasattr(ds_obj, "examples") and ds_obj.examples is not None:
                examples_list_id_str = str(id(ds_obj.examples))
                examples_len_str = str(len(ds_obj.examples))  # Add length here

            logger.debug(
                f"  Collected Docstring #{i}: Instance ID={id(ds_obj)}, path='{ds_obj.object_path}', "
                f"examples_count={examples_len_str}, "
                f"examples_list_ID={examples_list_id_str}"
            )

        return collected_docstrings

    def process_files(self, root_dir: Path) -> List[GaspatchioDocstring]:
        """Recursively processes all Python files in a directory."""
        all_docstrings: List[GaspatchioDocstring] = []
        for py_file in root_dir.rglob("*.py"):
            if py_file.is_file():
                all_docstrings.extend(self.process_file(py_file))
        return all_docstrings
