import ast
import contextlib
import inspect  # Import inspect for cleandoc
import io
import json  # For parsing Ruff's JSON output
import subprocess
from typing import Any, Iterable, List, Optional, Tuple

from pydantic import BaseModel, Field

# Removed top-level Ruff import and RUFF_AVAILABLE flag


class DocstringCodeExample(BaseModel):
    snippet: str
    output: Optional[str] = None
    object_context: str
    example_index: int
    raw_source_location: Tuple[str, int]
    parent_docstring: Optional["GaspatchioDocstring"] = Field(
        default=None, exclude=True
    )

    def _extract_code_from_snippet(self) -> str:
        """Extracts executable Python code from a doctest-style snippet.
        If the snippet does not appear to be a doctest (i.e., no lines start with >>> or ...),
        it is returned as is.
        """
        lines = self.snippet.splitlines()
        if not lines:
            return ""

        # Check if any line looks like a doctest prompt
        is_doctest_formatted = any(
            line.lstrip().startswith(">>> ") or line.lstrip().startswith("... ")
            for line in lines
        )

        if not is_doctest_formatted:
            # If no doctest prompts are found, assume it's already clean code
            return self.snippet

        code_lines = []
        for line in lines:
            stripped_line = (
                line.lstrip()
            )  # Use lstrip to handle potential leading whitespace before >>>
            if stripped_line.startswith(">>> "):
                code_lines.append(stripped_line[4:])
            elif stripped_line.startswith("... "):
                code_lines.append(stripped_line[4:])
            # If it's a doctest formatted block, non-prompt lines after prompts are part of output, not code.
            # The original `elif code_lines: break` was too aggressive if a clean line appeared mid-block.
            # However, for extracting *only code*, if we started collecting and then hit a non-prompt line,
            # that line is not part of the *code* of that specific doctest example snippet.
            # This method is about extracting the *executable code* from what might be a raw doctest snippet.
            # Given that `parse.py` now provides clean snippets, this part is less critical for that path,
            # but kept for robustness if this method is called with raw doctest strings.
            elif (
                code_lines and not stripped_line.startswith("#") and stripped_line
            ):  # if we have started and this line is not a continuation or comment
                pass  # In a raw doctest, this would be an error or unexpected content. Here, we only collect prompted lines.

        return "\n".join(code_lines)

    def lint(self) -> List[str]:
        """Lints the code snippet using Ruff CLI via subprocess."""
        issues: List[str] = []

        try:
            from ruff.__main__ import find_ruff_bin

            ruff_exe = find_ruff_bin()
        except ImportError:
            issues.append(
                "Ruff (__main__.find_ruff_bin) not importable. Linting skipped."
            )
            return issues
        except FileNotFoundError:  # find_ruff_bin can raise this if exe not found
            issues.append(
                "Ruff executable not found by find_ruff_bin. Linting skipped."
            )
            return issues

        code_to_lint = self._extract_code_from_snippet()

        if not code_to_lint.strip():
            return issues  # No code to lint

        try:
            # Command: ruff check --output-format json - (read from stdin)
            # Adding --no-cache to ensure fresh linting of snippet
            # Adding --isolated to prevent pyproject.toml from current dir from interfering too much,
            # though ruff might still pick some global configs. For snippet linting, this is safer.
            command = [
                ruff_exe,
                "check",
                "--output-format",
                "json",
                "--no-cache",
                "--isolated",
                "-",
            ]

            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,  # Work with text streams
            )
            stdout, stderr = process.communicate(
                input=code_to_lint, timeout=10
            )  # 10-second timeout

            if process.returncode == 0:  # No lint issues found by ruff
                return issues

            # Ruff usually exits with 1 if lint issues are found and output is JSON to stdout.
            # If stderr has content, it might be a Ruff error itself, not lint messages.
            if stderr:
                # Attempt to parse stderr as JSON first, as ruff might output JSON errors
                try:
                    error_json = json.loads(stderr)
                    if (
                        isinstance(error_json, list) and error_json
                    ):  # It might be a list of diagnostics
                        for problem in error_json:
                            code = problem.get("code", "UnknownCode")
                            message = problem.get("message", "Unknown error")
                            row = problem.get("location", {}).get("row", 0)
                            issues.append(f"{code}: {message} at line {row}")
                        return issues  # Return parsed errors from stderr if they look like diagnostics
                    elif isinstance(error_json, dict) and error_json.get("message"):
                        issues.append(
                            f"Ruff CLI Error (JSON): {error_json.get('message')}"
                        )
                        return issues

                except json.JSONDecodeError:
                    # If stderr is not JSON, treat it as a general error message
                    issues.append(f"Ruff CLI Error: {stderr.strip()}")
                    return issues  # Return the raw stderr if it wasn't JSON

            # If stdout has content, try to parse it as JSON (expected for --output-format json)
            if stdout:
                try:
                    ruff_output = json.loads(stdout)
                    if isinstance(
                        ruff_output, list
                    ):  # Expected: list of diagnostic dicts
                        for problem in ruff_output:
                            code = problem.get("code", "UnknownCode")
                            message = problem.get("message", "Unknown error")
                            row = problem.get("location", {}).get("row", 0)
                            # Add line number adjustment relative to snippet start if needed here
                            # For now, using Ruff's reported line number within the snippet
                            issues.append(f"{code}: {message} at line {row}")
                    else:
                        issues.append(
                            f"Ruff output was not a list of issues: {stdout[:200]}..."
                        )
                except json.JSONDecodeError:
                    issues.append(
                        f"Could not parse Ruff JSON output: {stdout[:200]}..."
                    )

            # If no specific issues parsed but non-zero exit code, add generic message
            if not issues and process.returncode != 0:
                issues.append(
                    f"Ruff CLI exited with code {process.returncode} but no issues parsed. stdout: {stdout[:100]}, stderr: {stderr[:100]}"
                )

        except subprocess.TimeoutExpired:
            issues.append("Ruff linting timed out.")
        except (
            FileNotFoundError
        ):  # Popen can raise this if ruff_exe is somehow invalid despite find_ruff_bin
            issues.append(f"Ruff executable not found at: {ruff_exe}. Linting skipped.")
        except Exception as e:
            issues.append(
                f"Error during Ruff subprocess execution: {type(e).__name__}: {e}"
            )

        return issues

    def run(
        self, global_vars: Optional[dict] = None
    ) -> Tuple[str, Any, Optional[Exception]]:
        """Executes the code snippet and captures stdout, the value of the last expression, and any exception."""
        raw_code_to_run = self._extract_code_from_snippet()

        code_to_run = inspect.cleandoc(raw_code_to_run)

        if not code_to_run.strip():
            return "", None, None

        # Use a copy of global_vars to avoid polluting it, merge with local_vars
        # The run environment should see global_vars, but assignments go into local_vars
        exec_globals = {}
        if global_vars:
            exec_globals.update(global_vars)

        # All execution will happen with this combined context, but new assignments
        # will effectively be "local" to this run.
        # For simplicity, we use one dict. A more robust setup might use separate globs/locs for exec.
        context_vars = exec_globals  # Start with globals

        captured_stdout = io.StringIO()
        last_expression_value: Any = None
        exception_raised: Optional[Exception] = None

        try:
            with contextlib.redirect_stdout(captured_stdout):
                code_lines = [
                    line for line in code_to_run.strip().splitlines() if line.strip()
                ]
                if not code_lines:
                    return captured_stdout.getvalue(), None, None

                if len(code_lines) == 1:
                    # Single line: try to exec then eval to capture its value if it's an expression
                    line = code_lines[0]
                    try:
                        exec(line, context_vars)
                        try:
                            last_expression_value = eval(line, context_vars)
                        except SyntaxError:
                            pass
                    except Exception as e_inner:
                        raise e_inner
                else:  # Multiple lines
                    # Try to eval the last line if it's an expression, otherwise exec the whole block
                    main_block = "\n".join(code_lines[:-1])
                    last_line = code_lines[-1]
                    if main_block:
                        exec(main_block, context_vars)
                    try:
                        # Check if last_line is an expression
                        parsed = ast.parse(last_line, mode="eval")
                        last_expression_value = eval(last_line, context_vars)
                    except SyntaxError:
                        # Not an expression, just exec it
                        exec(last_line, context_vars)
        except Exception as e:
            exception_raised = e

        return captured_stdout.getvalue(), last_expression_value, exception_raised


class DocstringParameter(BaseModel):
    name: str
    type_name: Optional[str] = None
    description: str


class DocstringReturn(BaseModel):
    type_name: Optional[str] = None
    description: str


class GaspatchioDocstring(BaseModel):
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    parameters: List[DocstringParameter] = []
    returns: Optional[DocstringReturn] = None
    examples: List[DocstringCodeExample] = []
    raw_docstring: str
    object_path: str
    file_path: str
    start_line: int

    def validate_structure(self) -> List[str]:
        """Return a list of human-readable issues (empty == OK).

        Checks:
        - short_description exists
        - parameter count + names match inspect.signature() (TODO)
        - each Example has at least one '>>>' line
        - examples[#].output is non-empty **if** snippet ends with a pure expression
        - returns section present when fn actually returns non-None (TODO)
        """
        issues: List[str] = []
        if not self.short_description:
            issues.append("Missing short_description.")

        # TODO: Parameter count + names match inspect.signature()

        for i, example in enumerate(self.examples):
            if not any(
                line.strip().startswith(">>>") for line in example.snippet.splitlines()
            ):
                issues.append(
                    f"[Structure Error] Example #{i} (context: {example.object_context}, file: {self.file_path}, line: {example.raw_source_location[1]}) has no '>>>' lines. Snippet:\n{example.snippet}"
                )

            # Heuristic for checking if snippet ends with a pure expression
            # This is a simplified check. A more robust check might involve ast.parse.
            # It considers the last non-empty, non-comment line of the snippet.
            # It strips '>>> ' or '... ' prefixes.
            last_code_line = ""
            for line in reversed(example.snippet.strip().splitlines()):
                stripped_line = line.strip()
                if stripped_line.startswith(">>> "):
                    last_code_line = stripped_line[4:].strip()
                    break
                elif stripped_line.startswith("... "):
                    last_code_line = stripped_line[4:].strip()
                    break
                elif (
                    stripped_line
                ):  # A non-empty line that is not a prompt continuation
                    last_code_line = stripped_line
                    break

            if last_code_line:
                # Simple heuristic: if not an assignment, def, class, import, or print,
                # and no explicit output is provided, it's an issue.
                is_assignment = (
                    "=" in last_code_line and not last_code_line.strip().endswith("==")
                )
                is_statement_keyword = any(
                    last_code_line.startswith(k)
                    for k in [
                        "def ",
                        "class ",
                        "import ",
                        "from ",
                        "pass",
                        "raise",
                        "return",
                        "yield",
                        "del ",
                        "global ",
                        "nonlocal ",
                    ]
                )
                is_print = last_code_line.startswith("print(")

                if (
                    not is_assignment
                    and not is_statement_keyword
                    and not is_print
                    and not example.output
                ):
                    issues.append(
                        f"[Structure Error] Example #{i} (context: {example.object_context}, file: {self.file_path}, line: {example.raw_source_location[1]}) "
                        f"snippet seems to end with an expression ('{last_code_line}') but has no output. Snippet:\n{example.snippet}"
                    )

        # TODO: returns section present when fn actually returns non-None
        return issues

    def iter_examples(self) -> "Iterable[DocstringCodeExample]":
        yield from self.examples
