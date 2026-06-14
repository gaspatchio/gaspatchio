# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for the cgroup-aware memory budget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

from gaspatchio_core.scenarios._memory import (
    DEFAULTS,
    IrreducibleCellError,
    SizingDefaults,
    _parse_limit,
    effective_limit,
    memory_budget,
    read_cgroup_limit,
    read_cgroup_usage,
)


def test_defaults_are_frozen_and_sane() -> None:
    """DEFAULTS is a SizingDefaults with all fields in valid, sane ranges."""
    assert isinstance(DEFAULTS, SizingDefaults)
    assert 0.0 < DEFAULTS.target_memory_fraction <= 1.0
    assert DEFAULTS.seed_sample_cap > 0


def test_irreducible_cell_error_is_runtime_error() -> None:
    """IrreducibleCellError inherits from RuntimeError."""
    assert issubclass(IrreducibleCellError, RuntimeError)


_HOST = 64 * 1024**3  # 64 GB host


def _write(root: Path, rel_files: dict[str, str]) -> None:
    for rel, content in rel_files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def test_v2_finite_limit_read(tmp_path: Path) -> None:
    """A numeric memory.max value is returned as an integer."""
    _write(tmp_path, {"mypod/memory.max": "1610612736"})  # 1.5 GB
    proc = "0::/mypod\n"
    assert read_cgroup_limit(tmp_path, proc, host_physical=_HOST) == 1_610_612_736


def test_v2_max_means_unlimited(tmp_path: Path) -> None:
    """The literal 'max' sentinel in memory.max returns None (unlimited)."""
    _write(tmp_path, {"mypod/memory.max": "max\n"})
    assert read_cgroup_limit(tmp_path, "0::/mypod\n", host_physical=_HOST) is None


def test_v2_walks_to_nearest_finite_parent(tmp_path: Path) -> None:
    """When the leaf is 'max', the nearest finite ancestor limit is used."""
    # leaf is 'max', parent slice sets 2 GB -> use the parent's 2 GB
    _write(
        tmp_path,
        {
            "slice/pod/memory.max": "max\n",
            "slice/memory.max": "2147483648\n",
        },
    )
    assert (
        read_cgroup_limit(tmp_path, "0::/slice/pod\n", host_physical=_HOST)
        == 2_147_483_648
    )


def test_v1_sentinel_means_unlimited(tmp_path: Path) -> None:
    """The large cgroup v1 sentinel value is treated as unlimited (None)."""
    _write(
        tmp_path,
        {"memory/mypod/memory.limit_in_bytes": "9223372036854771712\n"},
    )
    proc = "5:memory:/mypod\n"
    assert read_cgroup_limit(tmp_path, proc, host_physical=_HOST) is None


def test_limit_at_or_above_host_is_unlimited(tmp_path: Path) -> None:
    """A limit >= host physical RAM is treated as effectively unlimited (None)."""
    _write(tmp_path, {"mypod/memory.max": str(_HOST + 1)})
    assert read_cgroup_limit(tmp_path, "0::/mypod\n", host_physical=_HOST) is None


def test_no_cgroup_line_returns_none(tmp_path: Path) -> None:
    """Empty /proc/self/cgroup text returns None (no container detected)."""
    assert read_cgroup_limit(tmp_path, "", host_physical=_HOST) is None


def test_v1_finite_limit_read(tmp_path: Path) -> None:
    """A numeric cgroup v1 memory.limit_in_bytes value is returned as an integer."""
    _write(tmp_path, {"memory/mypod/memory.limit_in_bytes": "1073741824"})  # 1 GB
    assert (
        read_cgroup_limit(tmp_path, "5:memory:/mypod\n", host_physical=_HOST)
        == 1_073_741_824
    )


def test_usage_v2_read(tmp_path: Path) -> None:
    """memory.current is read and returned as an integer."""
    _write(tmp_path, {"mypod/memory.current": "500000000\n"})
    assert read_cgroup_usage(tmp_path, "0::/mypod\n") == 500_000_000


def test_usage_missing_is_zero(tmp_path: Path) -> None:
    """Missing memory.current returns 0 rather than raising."""
    assert read_cgroup_usage(tmp_path, "0::/mypod\n") == 0


def test_effective_limit_uses_cgroup_headroom(tmp_path: Path) -> None:
    """Headroom (limit - usage) is used when smaller than host_available."""
    # 1.5 GB limit, 0.5 GB used -> 1.0 GB headroom; host has 64 GB -> min = 1.0 GB
    _write(
        tmp_path,
        {"mypod/memory.max": "1610612736", "mypod/memory.current": "536870912"},
    )
    eff = effective_limit(
        host_available=64 * 1024**3,
        host_physical=64 * 1024**3,
        root=tmp_path,
        proc_cgroup_text="0::/mypod\n",
    )
    assert eff == 1_610_612_736 - 536_870_912


def test_effective_limit_unlimited_falls_back_to_host(tmp_path: Path) -> None:
    """An unlimited cgroup ('max') returns host_available unchanged."""
    _write(tmp_path, {"mypod/memory.max": "max\n"})
    eff = effective_limit(
        host_available=8 * 1024**3,
        host_physical=64 * 1024**3,
        root=tmp_path,
        proc_cgroup_text="0::/mypod\n",
    )
    assert eff == 8 * 1024**3


def test_effective_limit_unlimited_from_parse_failure(tmp_path: Path) -> None:
    """Unparseable limit content fails open to host_available."""
    _write(tmp_path, {"mypod/memory.max": "not-a-number\n"})
    eff = effective_limit(
        host_available=8 * 1024**3,
        host_physical=64 * 1024**3,
        root=tmp_path,
        proc_cgroup_text="0::/mypod\n",
    )
    assert eff == 8 * 1024**3  # parse failure -> host


def test_effective_limit_failopen_on_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception from read_cgroup_limit fails open to host_available."""

    def _boom(*_args: object, **_kwargs: object) -> int:
        msg = "boom"
        raise RuntimeError(msg)

    monkeypatch.setattr("gaspatchio_core.scenarios._memory.read_cgroup_limit", _boom)
    eff = effective_limit(
        host_available=7 * 1024**3,
        host_physical=64 * 1024**3,
        root=tmp_path,
        proc_cgroup_text="0::/x\n",
    )
    assert eff == 7 * 1024**3  # exception -> fail-open to host


def test_parse_limit_negative_or_zero_is_unlimited() -> None:
    """A negative/zero raw cgroup limit means unlimited, not a 0 budget (#13)."""
    assert _parse_limit("-1", host_physical=_HOST) is None
    assert _parse_limit("0", host_physical=_HOST) is None


def test_effective_limit_uses_binding_level_usage(tmp_path: Path) -> None:
    """Headroom uses the binding level's own usage, not leaf usage (#14)."""
    _write(
        tmp_path,
        {
            "slice/memory.max": "1073741824",  # 1 GB limit at the parent
            "slice/memory.current": "966367641",  # ~922 MB used (incl. siblings)
            "slice/pod/memory.max": "max\n",  # leaf has no own limit
            "slice/pod/memory.current": "104857600",  # 100 MB used by this pod
        },
    )
    eff = effective_limit(
        host_available=_HOST,
        host_physical=_HOST,
        root=tmp_path,
        proc_cgroup_text="0::/slice/pod\n",
    )
    # binding (parent) headroom = 1GB - 922MB, NOT 1GB - the leaf's 100MB.
    assert eff == 1073741824 - 966367641


def test_budget_subtracts_base_rss_before_fraction(tmp_path: Path) -> None:
    """Budget = fraction * (effective_limit - base_rss): unlimited cgroup uses host."""
    # unlimited cgroup -> host 8 GB; base 2 GB; fraction 0.5 -> (8-2)*0.5 = 3 GB
    _write(tmp_path, {"mypod/memory.max": "max\n"})
    b = memory_budget(
        0.5,
        host_available=8 * 1024**3,
        host_physical=64 * 1024**3,
        base_rss_bytes=2 * 1024**3,
        root=tmp_path,
        proc_cgroup_text="0::/mypod\n",
    )
    assert b == 3 * 1024**3


def test_budget_never_negative(tmp_path: Path) -> None:
    """Budget is clamped to zero when base_rss exceeds effective_limit."""
    _write(tmp_path, {"mypod/memory.max": "max\n"})
    b = memory_budget(
        0.5,
        host_available=1 * 1024**3,
        host_physical=64 * 1024**3,
        base_rss_bytes=4 * 1024**3,
        root=tmp_path,
        proc_cgroup_text="0::/mypod\n",
    )
    assert b == 0


def test_sizing_defaults_has_ladder_and_safety_margin():
    from gaspatchio_core.scenarios._memory import DEFAULTS

    assert DEFAULTS.ladder == (1, 4, 16, 64)
    assert DEFAULTS.safety_margin == 1.3
    # ladder is ascending and starts at 1 (the always-feasible-to-probe floor batch)
    assert DEFAULTS.ladder[0] == 1
    assert list(DEFAULTS.ladder) == sorted(DEFAULTS.ladder)
