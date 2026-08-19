# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""User-vs-framework frame classification must anchor to the installed package.

A bare ``/gaspatchio/`` substring also matches user model files that merely
live under a directory called gaspatchio — the documented multi-repo
workspace layout — which silently drops the user's source line from error
messages and expression lineage. These tests pin the anchoring.
"""

from __future__ import annotations

import gaspatchio.frame.base
import gaspatchio.frame.tracing
from gaspatchio.errors.frame_utils import is_user_code_frame

# The documented workspace shape: the framework repo and the user's models
# both live under a parent directory named gaspatchio.
USER_MODEL_PATHS = [
    "/Users/x/projects/gaspatchio/gaspatchio-models/models/term/model.py",
    "/home/x/gaspatchio/errors/model.py",
    "/work/gaspatchio/frame/my_model.py",
]


class TestIsUserCodeFrame:
    """The error-message classifier."""

    def test_user_models_under_gaspatchio_named_dirs_are_user_code(self):
        """A directory named gaspatchio does not make a file framework code."""
        for path in USER_MODEL_PATHS:
            assert is_user_code_frame(path), path

    def test_framework_modules_are_internal(self):
        """The framework's own files must still classify as internal."""
        assert not is_user_code_frame(gaspatchio.frame.base.__file__)


class TestTracePatterns:
    """The expression-lineage classifier mirrors the same anchoring."""

    def test_patterns_do_not_match_user_paths(self):
        """Lineage capture must not skip user frames on a name coincidence."""
        patterns = gaspatchio.frame.tracing._INTERNAL_TRACE_PATTERNS  # noqa: SLF001
        for path in USER_MODEL_PATHS:
            assert not any(p in path for p in patterns), path

    def test_patterns_match_framework_paths(self):
        """The framework's own frame/ files must still be skipped."""
        patterns = gaspatchio.frame.tracing._INTERNAL_TRACE_PATTERNS  # noqa: SLF001
        assert any(p in gaspatchio.frame.base.__file__ for p in patterns)
