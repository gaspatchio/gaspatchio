# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .base import ActuarialFrame

def run_model(model_func: Callable, df: ActuarialFrame) -> ActuarialFrame:
    """Run a model function on an ActuarialFrame."""
    ...
