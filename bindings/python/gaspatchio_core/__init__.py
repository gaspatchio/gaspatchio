# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The import name 1.0 removed, kept only to say what to write instead.

It re-exports nothing, so code cannot keep running on the old name. A model
written for 0.9 reaches this before ``gaspatchio`` has loaded, so nothing inside
``gaspatchio`` could answer in its place.
"""

_MSG = (
    "gaspatchio_core was renamed in 1.0: write `import gaspatchio`, or "
    "`from gaspatchio import ...`, and the same modules are there. It is listed "
    "under Breaking changes in the CHANGELOG: "
    "https://github.com/gaspatchio/gaspatchio/blob/main/CHANGELOG.md"
)
raise ModuleNotFoundError(_MSG, name="gaspatchio_core")
