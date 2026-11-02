# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for rendering a captured filename for a person to read.

A path is printed as written. A notebook cell is not a path -- the
interpreter names it something like ``<ipython-input-3-a1b2c3>``, which
identifies the cell to the machine and tells the reader nothing -- so it
becomes the cell label the notebook itself shows.

Every reader of a calculation's source span goes through these two
functions: the query-plan log, the calculation-graph export, and the
location line on an enriched method error.
"""

from gaspatchio._source import display_filename, is_jupyter_filename


class TestIsJupyterFilename:
    """Which captured filenames came from a notebook cell."""

    def test_a_real_path_is_not_a_notebook(self):
        """An ordinary source file is just a file."""
        assert not is_jupyter_filename("/path/to/model_calculation.py")

    def test_the_bracketed_cell_name_is_a_notebook(self):
        """The spelling the interpreter uses inside a notebook."""
        assert is_jupyter_filename("<ipython-input-1-abc123>")

    def test_the_unbracketed_cell_name_is_also_a_notebook(self):
        """Some environments hand over the same name without the brackets."""
        assert is_jupyter_filename("ipython-input-5-def456")


class TestDisplayFilename:
    """What the reader is shown for each kind of captured filename."""

    def test_a_real_path_is_returned_as_written(self):
        """Nothing to translate -- the reader can open this."""
        assert display_filename("/path/to/script.py") == "/path/to/script.py"

    def test_a_notebook_cell_becomes_the_cell_number(self):
        """The label the notebook shows on the cell, not the machine's name."""
        assert display_filename("<ipython-input-3-abc123>") == "Jupyter Cell 3"

    def test_a_cell_name_with_no_readable_number_degrades_to_the_notebook(self):
        """Saying "a notebook" beats printing a number that was never there."""
        assert display_filename("<ipython-input-malformed") == "Jupyter Notebook"
