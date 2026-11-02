# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Where a compiled program is kept between runs, and how a run says it was reused.

Compiling a projection is seconds. Running one, compiled, is milliseconds. An
engine that recompiled on every invocation would be an engine whose
edit-run-refine loop is a compiler's loop rather than a model's, so the
compiled program is kept -- in the process, keyed by the shape it was built
for, and on disk under the user's cache directory, keyed by everything XLA
hashes.

**The two reuses are different facts and the report tells them apart.** A
*process-local* reuse is the same program object answering a second batch: it
costs nothing and it says nothing about whether anything was written down. A
*persistent* reuse is XLA finding the executable on disk and not compiling at
all, which is the one that makes the second run of a model in a new process
fast. A run that reported one number for both would let a cold cache hide
behind a warm process, which is the failure this module exists to stop.

**The cache is an optimisation, and the engine is not.** A location that
cannot be written -- a read-only home, a full disk, a sandboxed runner that
grants the path and not the write -- costs a reader the compiler's seconds and
nothing else: :func:`configure` says so in the run's report and carries on.

**Which of the two is read, and from where.** The persistent answer is read
from jax's own compilation-cache counters -- ``/jax/compilation_cache/
cache_hits`` and ``cache_misses``, recorded through :mod:`jax.monitoring` --
rather than inferred from how long a compilation took. A timing threshold
answers "fast" and not "loaded", and a machine under load would report a cold
cache as warm.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import jax
import platformdirs
from jax import monitoring

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

__all__ = [
    "CACHE_HIT",
    "CACHE_MISS",
    "CacheOutcome",
    "cache_dir",
    "configure",
    "report_key",
    "unusable",
    "watching",
]

# jax's own two counters. Named here because they are what this module reads,
# and a name that moved would be a silent "never a hit" rather than an error.
CACHE_HIT: Final = "/jax/compilation_cache/cache_hits"
CACHE_MISS: Final = "/jax/compilation_cache/cache_misses"

# The key a report carries beside a compilation. This engine's own, not
# jax's: jax's key is a hash over its flags, its version and the lowered
# module, and it is neither stable across releases nor meaningful to a reader.
# This one says which graph, which widths and which batch -- which is what a
# reader comparing two runs wants to know. Its version moves when what every
# program hands back does: at preview.2 a program returns each check's count
# and first caught cell rather than its mask, so a program of preview.1
# and one of preview.2 over one graph, one width and one batch are two
# compilations, and the report names them apart. jax's own key moves with the
# lowered module, so the persistent cache never hands one for the other.
_KEY_VERSION: Final = "gaspatchio-jax-compilation/v0-preview.2"

# jax's own name for where its executables go. Read rather than written over:
# a user who has told jax where to put them has told this engine too.
_CACHE_DIR_VARIABLE: Final = "JAX_COMPILATION_CACHE_DIR"

# What a run says about the cache where it could not be used at all, or None.
# Module state because the answer is about one place and one process, and it
# is settled once, at import, before anything has been compiled.
_UNUSABLE: str | None = None

_LISTENING = threading.Lock()
_COUNTS: dict[str, int] = {}
_REGISTERED = False


def cache_dir() -> Path:
    """Return where compiled programs are kept between runs.

    The directory the environment names where it names one -- jax's own
    ``JAX_COMPILATION_CACHE_DIR``, so a user who has already told jax where
    its executables go is not overruled by this engine -- and otherwise this
    engine's own place under the user's cache directory.
    """
    stated = os.environ.get(_CACHE_DIR_VARIABLE)
    if stated:
        return Path(stated)
    return Path(platformdirs.user_cache_dir("gaspatchio-jax")) / "compilation"


def configure(
    directory: Path | None = None, *, min_compile_seconds: float = 0.0
) -> Path:
    """Turn on the persistent compilation cache, and say where it is.

    **Called once, when this package is imported, and before anything has
    been compiled.** XLA reads the cache directory when it first compiles
    something and does not read it again; a run that turned the cache on
    after its first compilation would write nothing and report every run as
    cold, which is exactly what it did before this moved to the import.

    Args:
        directory: Where to keep executables. The user's own cache directory
            by default, which is the one place a laptop already expects
            large regenerable files to be.
        min_compile_seconds: How long a compilation has to take before it is
            worth writing down. Nought by default, because the programs this
            engine compiles are projections and every one of them is worth
            keeping; a test that wants both ends of the cache in one second
            sets it explicitly.

    Returns:
        The directory it settled on, whether or not it could be used.

    """
    global _UNUSABLE  # noqa: PLW0603 -- one process, one answer about one place
    where = cache_dir() if directory is None else Path(directory)
    try:
        where.mkdir(parents=True, exist_ok=True)
        # Written to and removed again, because a directory that exists is not
        # the same as a directory that can be written: a read-only mount, a
        # full disk and a sandbox that grants the path but not the write all
        # pass ``mkdir`` and fail the first executable.
        probe = where / ".writable"
        probe.touch()
        probe.unlink()
    except OSError as refused:
        # **The cache is an optimisation and the engine is not.** A read-only
        # home, a full disk or a sandboxed runner should cost a reader some
        # seconds of compiler, not the ability to run a model at all -- and
        # certainly not an error blaming their installation, which is what an
        # exception out of this function becomes by the time it has travelled
        # through provider discovery.
        _UNUSABLE = (
            f"the compilation cache at {where} cannot be used "
            f"({refused.strerror or refused}), so every run of this model "
            "compiles from cold: point "
            f"{_CACHE_DIR_VARIABLE} somewhere writable to keep the compiled "
            "programs between runs"
        )
        # And jax is told to stop looking. It reads the environment variable
        # itself, so a run that only *returned* here still had XLA trying the
        # unusable location on every compilation and warning about it once per
        # program -- survivable, but a page of warnings about a thing the
        # report already says in one sentence. The degrade is quiet as well as
        # survivable.
        jax.config.update("jax_compilation_cache_dir", None)  # type: ignore[no-untyped-call]
        return where
    _UNUSABLE = None
    # jax ships no annotations for ``config.update``, and each of these is one
    # line into a library this package does not own.
    jax.config.update("jax_compilation_cache_dir", str(where))  # type: ignore[no-untyped-call]
    jax.config.update(  # type: ignore[no-untyped-call]
        "jax_persistent_cache_min_compile_time_secs", min_compile_seconds
    )
    # An executable of any size is worth keeping: the default floor is there
    # for programs a compiler answers instantly, and none of these are.
    jax.config.update("jax_persistent_cache_min_entry_size_bytes", 0)  # type: ignore[no-untyped-call]
    return where


def unusable() -> str | None:
    """Return what a run should say about the cache, or None where it works."""
    return _UNUSABLE


@dataclass(frozen=True, slots=True)
class CacheOutcome:
    """What one compilation cost, and which of the two reuses it got.

    Attributes:
        process_local: The same program object, already built in this
            process for this shape, handed back.
        persistent: XLA loaded the executable from the cache directory
            rather than compiling it, as jax's own counters report.
        compile_seconds: Wall time the compilation took, nought where the
            program was already in the process.

    """

    process_local: bool
    persistent: bool
    compile_seconds: float


def _listen() -> None:
    """Start counting jax's compilation-cache events, once per process."""
    global _REGISTERED  # noqa: PLW0603 -- one listener per process is the contract
    with _LISTENING:
        if _REGISTERED:
            return

        def took(event: str, **_metadata: Any) -> None:  # noqa: ANN401 -- jax's own signature
            _COUNTS[event] = _COUNTS.get(event, 0) + 1

        monitoring.register_event_listener(took)
        _REGISTERED = True


@contextmanager
def watching() -> Iterator[_Held]:
    """Count what one compilation did, and hand back the outcome after it.

    Yields a mutable holder that is filled in on exit; read it after the
    block. A context manager rather than a wrapper around the compile call
    because what is being measured is a *region* of a caller's code -- the
    lowering and the compilation together -- and threading a callable through
    that would be the same measurement with a signature around it.

    ``process_local`` is False here and set by the caller: whether a program
    object was already in the process is something the caller knows outright,
    and inferring it from the absence of cache events would read a jax that
    logged nothing as a reuse that never happened.
    """
    _listen()
    before = _COUNTS.get(CACHE_HIT, 0)
    started = time.perf_counter()
    held = _Held()
    try:
        yield held
    finally:
        held.outcome = CacheOutcome(
            process_local=False,
            persistent=_COUNTS.get(CACHE_HIT, 0) > before,
            compile_seconds=time.perf_counter() - started,
        )


class _Held:
    """What :func:`watching` fills in when its block ends."""

    outcome: CacheOutcome = CacheOutcome(
        process_local=False, persistent=False, compile_seconds=0.0
    )


def report_key(
    document: Mapping[str, Any],
    buckets: tuple[int, ...],
    batch: int,
    returns: Iterable[str] | None = None,
) -> str:
    """Return the key a report names a compilation by.

    The graph's own fingerprint, the widths the program was built around and
    the batch it takes -- which together are what makes two compilations of
    one model different, and are all a reader needs to see why a run compiled
    four programs rather than one. And, for a program that hands back only
    some of the model's columns -- a fold's -- which columns: it is a
    different program from the one that hands back every column, over the
    same batch.
    """
    stated: dict[str, object] = {
        "version": _KEY_VERSION,
        "graph": str(document.get("graph_fingerprint") or ""),
        "buckets": list(buckets),
        "batch": batch,
    }
    if returns is not None:
        stated["returns"] = sorted(returns)
    written = json.dumps(stated, sort_keys=True)
    return f"sha256:{hashlib.sha256(written.encode()).hexdigest()[:16]}"
