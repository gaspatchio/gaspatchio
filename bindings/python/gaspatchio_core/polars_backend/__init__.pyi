# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Type stubs for gaspatchio_core.polars_backend subpackage."""

from .list_eval import unwrap_for_list_eval as unwrap_for_list_eval
from .masks import boolean_and as boolean_and
from .masks import boolean_not as boolean_not
from .masks import boolean_or as boolean_or
from .masks import to_boolean_expr as to_boolean_expr
from .operators import dispatch_list_op as dispatch_list_op
from .operators import execute_list_clip as execute_list_clip
from .operators import execute_list_pow as execute_list_pow
from .plugins import accumulate as accumulate
from .plugins import fill_series as fill_series
from .plugins import floor as floor
from .plugins import list_clip as list_clip
from .plugins import list_conditional as list_conditional
from .plugins import list_pow as list_pow
from .plugins import round as round
from .plugins import round_to_int as round_to_int

__all__ = [
    "accumulate",
    "boolean_and",
    "boolean_not",
    "boolean_or",
    "dispatch_list_op",
    "execute_list_clip",
    "execute_list_pow",
    "fill_series",
    "floor",
    "list_clip",
    "list_conditional",
    "list_pow",
    "round",
    "round_to_int",
    "to_boolean_expr",
    "unwrap_for_list_eval",
]
