# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable

from .base import ActuarialFrame

def run_model(
    model_func: Callable[[ActuarialFrame], ActuarialFrame | None], df: ActuarialFrame
) -> ActuarialFrame: ...
