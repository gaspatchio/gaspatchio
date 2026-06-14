# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for the scenario test suite.

(The batch-size calibration cache and its per-test isolation fixture were removed when
``batch_size="auto"`` moved to a measured-every-run streaming-batch search — there is no
longer a cache to isolate.)
"""

from __future__ import annotations
