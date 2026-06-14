# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def sample_py_file_1(tmp_path: Path) -> Path:
    content = textwrap.dedent("""
    def func_a():
        \"\"\"Short desc for A.

        >>> print("Hello from A")
        Hello from A
        >>> 1 + 1
        2
        \"\"\"
        pass

    class MyClass:
        \"\"\"Docs for MyClass.\"\"\"
        def method_b(self):
            \"\"\"Short desc for method_b.

            >>> print("Method B here")
            Method B here
            \"\"\"
            pass
    """)
    file_path = tmp_path / "sample_module_1.py"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def sample_py_file_2(tmp_path: Path) -> Path:
    content = textwrap.dedent("""
    def func_c():
        \"\"\"Only one example.
        >>> "C".lower()
        'c'
        \"\"\"
        pass
    """)
    file_path = tmp_path / "sample_module_2.py"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def empty_py_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "empty_module.py"
    file_path.write_text("# No docstrings here")
    return file_path
