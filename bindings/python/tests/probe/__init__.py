# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Performance-probe harness.

Brackets hot-path work with a reproducible timing, peak-memory, and
streaming-engine-fallback measurement against a machine-local model that is
not part of this repository, named by the ``GASPATCHIO_PROBE_WORKLOAD_DIR``
environment variable; there is no default, and unset means every probe
entry point skips or refuses by name (see ``synthesize_fixture.py`` for what
that directory must hold). Excluded from the default ``pytest`` run via the
``probe`` marker; select it explicitly with ``pytest -m probe``.
"""
