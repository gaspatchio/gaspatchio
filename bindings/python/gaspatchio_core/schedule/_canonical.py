# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Backwards-compatible re-export of canonical_bytes from
# ABOUTME: gaspatchio_core._identity. New code should import from there directly.

"""Re-export of the shared canonical helper."""

from gaspatchio_core._identity import canonical_bytes

__all__ = ["canonical_bytes"]
