# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ActuarialFrame

def run_model(model_func: Callable, df: ActuarialFrame) -> ActuarialFrame:
    """Run a model function on an ActuarialFrame."""
