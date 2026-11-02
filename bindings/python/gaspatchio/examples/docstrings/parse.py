# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Parse gaspatchio docstrings and extract their code examples."""

import ast
import inspect
import logging
import re
import shlex
import textwrap
from pathlib import Path

import polars as pl
from docstring_parser import parse as docstring_parse_lib
from docstring_parser.common import Docstring  # For type hinting parsed_doc_lib

from .models import (
    DocstringCodeExample,
    DocstringParameter,
    DocstringReturn,
    GaspatchioDocstring,
)

logger = logging.getLogger(__name__)


class GaspatchioDocstringParser:
    """Parse docstrings into GaspatchioDocstring models with their examples."""

    @staticmethod
    def set_polars_print_config(
        tbl_width_chars: int = 1000,
        tbl_cols: int = -1,
        tbl_rows: int = 20,
        fmt_str_lengths: int = 100,
    ) -> None:
        """Set the polars print options docstring examples are checked under."""
        pl.Config.set_tbl_width_chars(tbl_width_chars)
        pl.Config.set_tbl_cols(tbl_cols)
        pl.Config.set_tbl_rows(tbl_rows)
        pl.Config.set_fmt_str_lengths(fmt_str_lengths)

    def __init__(self, include_private: bool = False) -> None:
        """Create a parser and apply the standard polars print options."""
        self.include_private = include_private
        self.set_polars_print_config()

    def _extract_parameters(
        self, parsed_doc_lib: Docstring
    ) -> list[DocstringParameter]:
        params_list: list[DocstringParameter] = []
        if parsed_doc_lib.params:
            params_list.extend(
                DocstringParameter(
                    name=p_lib.arg_name,
                    type_name=p_lib.type_name,
                    description=p_lib.description or "",  # Ensure str
                )
                for p_lib in parsed_doc_lib.params
            )
        return params_list

    def _extract_returns(self, parsed_doc_lib: Docstring) -> DocstringReturn | None:
        if parsed_doc_lib.returns:
            r_lib = parsed_doc_lib.returns
            return DocstringReturn(
                type_name=r_lib.type_name,
                description=r_lib.description or "",  # Ensure str
            )
        return None

    def _extract_when_to_use(self, docstring_text: str) -> str | None:
        """Extract the 'When to use' section from a docstring."""
        cleaned_doc = inspect.cleandoc(docstring_text)
        lines = cleaned_doc.splitlines()

        when_to_use_content_lines: list[str] = []
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
                    # Block ends if line is not indented as expected, or is
                    # non-empty and not indented
                    break

        if when_to_use_content_lines:
            # Join and then rstrip to remove any trailing newlines from
            # potentially multiple empty lines at the end
            return "\n".join(when_to_use_content_lines).rstrip()
        return None

    def _extract_examples(
        self,
        docstring_text: str,
        object_path: str,
        file_path_str: str,
    ) -> list[DocstringCodeExample]:
        examples_list: list[DocstringCodeExample] = []
        if not docstring_text:
            return examples_list

        cleaned_doc = inspect.cleandoc(docstring_text)

        # Regex breakdown for a fenced code block:
        # Group 1: (^ *```) - The opening fence marker (e.g., "  ```"), including
        #   leading spaces on its line.
        # Group 2: ( *) - Spaces immediately after the opening ``` marker
        #   (usually none).
        # Group 3: (.*?) - The info string (e.g., "python", "python skip",
        #   "text"), non-greedy. Ends at newline.
        # Group 4: (.+?) - The actual content of the block. Non-greedy. re.S
        #   (DOTALL) makes . match newlines.
        # \1 at the end: Backreference to what Group 1 matched (e.g., "  ```"),
        #   ensuring closing fence structure matches opening.
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

            if language_specifier in {"python", "py"}:
                # This is a Python code block
                snippet = textwrap.dedent(current_raw_content).rstrip("\n")
                parsed_prefix_tags = shlex_parts[1:]

                # Line number of the opening ``` marker (0-indexed within cleaned_doc)
                line_start_of_block_marker = cleaned_doc[: current_match.start()].count(
                    "\n"
                )

                extracted_output: str | None = None
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

                    # To be an output, the next block must start "immediately"
                    # after current
                    text_between_blocks = cleaned_doc[
                        current_match.end() : next_match.start()
                    ]
                    # Only whitespace (or empty) between the blocks, and it's not
                    # another python block (empty lang spec is OK for output)
                    if not text_between_blocks.strip() and (
                        next_language_specifier not in {"python", "py"}
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
                    # Advance past current python block and its consumed output block
                    i += 2
                else:
                    i += 1  # Advance past current python block
            else:
                # This block was not a python block (based on info string), so
                # just skip it
                i += 1

        logger.debug(
            "===> Finished extracting examples for '%s' using regex. Total found: %s",
            object_path,
            len(examples_list),
        )
        logger.debug(
            "  >>> _extract_examples for %s RETURNING list ID: %s, len: %s",
            object_path,
            id(examples_list),
            len(examples_list),
        )
        return examples_list

    def parse_docstring_from_text(
        self,
        docstring_text: str,
        object_path: str,
        file_path_str: str,
        docstring_start_line: int,
    ) -> GaspatchioDocstring | None:
        """
        Parse a raw docstring string and its context into a GaspatchioDocstring object.

        Args:
            docstring_text: The raw text of the docstring.
            object_path: The fully qualified path of the object this docstring
                belongs to.
            file_path_str: The string path of the file containing this docstring.
            docstring_start_line: The starting line number of the docstring in the file.

        Returns:
            A GaspatchioDocstring object if parsing is successful, otherwise None.

        """
        if not docstring_text:
            return None

        try:
            parsed_doc_lib: Docstring = docstring_parse_lib(docstring_text)
        # docstring_parser raises more than its ParseError: a stray colon before
        # a reST field is an IndexError out of rest._build_meta. A docstring it
        # cannot read must still yield its examples
        # (test_examples_survive_a_docstring_the_field_parser_rejects), so any
        # failure falls back, with a warning naming it.
        except Exception as e:  # noqa: BLE001 -- see above
            logger.warning(
                "Error parsing with docstring_parser for %s in %s: %s. Proceeding "
                "with fenced-block extraction for examples only.",
                object_path,
                file_path_str,
                e,
            )
            # Create a dummy parsed_doc_lib if parsing fails, so we can still try
            # to get examples
            parsed_doc_lib = Docstring()
            # Ensure dummy has necessary attributes even if empty
            parsed_doc_lib.short_description = "Error during parsing (see logs)."
            parsed_doc_lib.long_description = None  # Ensure it has this attribute
            # `params` and `returns` are read-only views of the docstring's
            # sections, and a new Docstring has none: no params, no returns.

        # Extract the fenced code blocks by pattern
        # Pass the original object_path for context in DocstringCodeExample
        extracted_md_examples = self._extract_examples(
            docstring_text, object_path, file_path_str
        )
        logger.debug(
            "  In parse_docstring_from_text for %s: extracted_md_examples (id: "
            "%s, len: %s) before GaspatchioDocstring creation.",
            object_path,
            id(extracted_md_examples),
            len(extracted_md_examples),
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
            "  >>> parse_docstring_from_text for %s CREATED "
            "GaspatchioDocstring (ID: %s). gs_doc_obj.examples (id: %s, len: %s)",
            object_path,
            id(gs_doc_obj),
            id(gs_doc_obj.examples),
            len(gs_doc_obj.examples),
        )
        return gs_doc_obj

    def _get_object_path(
        self,
        node: ast.AST,
        file_path_obj: Path,
        parent_map: dict[ast.AST, ast.AST | None],
    ) -> str:
        """Generate a Python-like path for an AST node."""
        name_parts = []
        curr: ast.AST | None = node
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

    def process_file(self, file_path: Path) -> list[GaspatchioDocstring]:
        """Process a single Python file and extract docstrings."""
        collected_docstrings: list[GaspatchioDocstring] = []
        try:
            file_content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(file_content, filename=str(file_path))
        except OSError:
            logger.exception("Error reading file %s", file_path)
            return collected_docstrings
        except SyntaxError:
            logger.exception("Syntax error parsing AST for %s", file_path)
            return collected_docstrings
        except ValueError:
            # Not UTF-8 (UnicodeDecodeError), or source ast.parse refuses
            logger.exception("Could not decode or parse %s", file_path)
            return collected_docstrings

        parent_map: dict[ast.AST, ast.AST | None] = {
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
                "Processing AST node: %s of type %s",
                current_node_name,
                type(node).__name__,
            )

            object_path_str = (
                "UnknownObjectPath"  # Default in case of error before path is resolved
            )
            try:
                raw_docstring = ast.get_docstring(node, clean=False)
                if not raw_docstring:
                    logger.debug(
                        "  No raw docstring found for node: %s", current_node_name
                    )
                    continue
                logger.debug(
                    "  Raw docstring found for %s (len %s), starts: '%s'",
                    current_node_name,
                    len(raw_docstring),
                    raw_docstring[:100].replace("\n", "\\n"),
                )

                # For Python 3.8+, docstrings are ast.Constant.
                # We need the line number of the docstring node itself.
                docstring_node = None
                if (
                    isinstance(
                        node,
                        (
                            ast.FunctionDef,
                            ast.ClassDef,
                            ast.AsyncFunctionDef,
                            ast.Module,
                        ),
                    )
                    and node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                ):
                    docstring_node = node.body[0].value

                # Falling back to node.lineno + 1 for the docstring's start line
                # might be too naive.
                # A more reliable way is to get the line number of the docstring
                # expression node.
                # ast.get_docstring() doesn't provide this directly.
                # We assume that if a docstring exists (raw_docstring_text is not None),
                # then node.body[0].value IS the docstring node.
                # Fallback to node's line if no specific docstring node found (e.g.
                # empty)
                docstring_actual_start_line = (
                    docstring_node.lineno if docstring_node else node.lineno
                )

                object_path_str = self._get_object_path(node, file_path, parent_map)
                logger.debug(
                    "  Resolved object_path: %s for node: %s",
                    object_path_str,
                    current_node_name,
                )

                parsed_docstring_obj = self.parse_docstring_from_text(
                    docstring_text=raw_docstring,
                    object_path=object_path_str,
                    file_path_str=str(file_path.resolve()),
                    # Pass the determined start line
                    docstring_start_line=docstring_actual_start_line,
                )
                if parsed_docstring_obj:
                    logger.debug(
                        "  In process_file for %s: parsed_docstring_obj (ID: %s) "
                        "BEFORE APPEND. Examples (id: %s, len: %s)",
                        object_path_str,
                        id(parsed_docstring_obj),
                        id(parsed_docstring_obj.examples),
                        len(parsed_docstring_obj.examples),
                    )
                    if parsed_docstring_obj.examples:
                        for idx, ex_item in enumerate(parsed_docstring_obj.examples):
                            logger.debug(
                                "    Example %s context: %s, snippet: '%s'...",
                                idx,
                                ex_item.object_context,
                                ex_item.snippet[:50].replace("\n", "\\n"),
                            )
                    collected_docstrings.append(parsed_docstring_obj)
                    logger.debug(
                        "  In process_file for %s: parsed_docstring_obj (ID: %s) "
                        "AFTER APPEND. Examples (id: %s, len: %s)",
                        object_path_str,
                        id(parsed_docstring_obj),
                        id(parsed_docstring_obj.examples),
                        len(parsed_docstring_obj.examples),
                    )
                else:
                    logger.debug(
                        "  Parsing returned None for docstring of %s", object_path_str
                    )
            except Exception:
                # Log the error with context and continue to the next node
                node_name_for_log = getattr(node, "name", "UnnamedNode")
                logger.exception(
                    "Failed to process docstring for '%s' (or node '%s') in %s",
                    object_path_str,
                    node_name_for_log,
                    file_path,
                )
                continue  # Try to process the next node in the file

        logger.debug("=== FINISHING process_file for %s ===", file_path)
        logger.debug(
            "Total GaspatchioDocstring objects collected: %s", len(collected_docstrings)
        )
        for i, ds_obj in enumerate(collected_docstrings):
            examples_list_id_str = "N/A"
            examples_len_str = "N/A"  # Add length here
            if hasattr(ds_obj, "examples") and ds_obj.examples is not None:
                examples_list_id_str = str(id(ds_obj.examples))
                examples_len_str = str(len(ds_obj.examples))  # Add length here

            logger.debug(
                "  Collected Docstring #%s: Instance ID=%s, path='%s', "
                "examples_count=%s, examples_list_ID=%s",
                i,
                id(ds_obj),
                ds_obj.object_path,
                examples_len_str,
                examples_list_id_str,
            )

        return collected_docstrings

    def process_files(self, root_dir: Path) -> list[GaspatchioDocstring]:
        """Recursively processes all Python files in a directory."""
        all_docstrings: list[GaspatchioDocstring] = []
        for py_file in root_dir.rglob("*.py"):
            if py_file.is_file():
                all_docstrings.extend(self.process_file(py_file))
        return all_docstrings
