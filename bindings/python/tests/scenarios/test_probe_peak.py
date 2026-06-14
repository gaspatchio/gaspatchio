# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The auto-probe must size from the transient PEAK working set of a batch.

Measuring ``rss_after - rss_before`` undercounts: Polars frees its
materialisation temporaries before ``rss_after`` is read, so a naive delta
misses the spike that actually risks OOM. ``_measure_peak_delta`` samples RSS
during the call and reports peak-over-baseline.
"""

from __future__ import annotations

import time

from gaspatchio_core.scenarios._for_each import _measure_peak_delta


def test_measure_peak_delta_captures_transient_peak() -> None:
    """A spike that is gone by the time the call returns is still captured."""
    state = {"busy": False}

    def reader() -> int:
        return 900 if state["busy"] else 100

    def work() -> None:
        state["busy"] = True  # RSS spikes during the work...
        time.sleep(0.03)
        state["busy"] = False  # ...and is released before returning.

    delta = _measure_peak_delta(work, rss_reader=reader, interval=0.002)
    # Naive (after - before) would be 100 - 100 = 0; peak-aware sees 900 - 100.
    assert delta == 800


def test_measure_peak_delta_flat_when_no_growth() -> None:
    """No allocation -> zero peak delta."""

    def reader() -> int:
        return 500

    delta = _measure_peak_delta(lambda: None, rss_reader=reader, interval=0.002)
    assert delta == 0
