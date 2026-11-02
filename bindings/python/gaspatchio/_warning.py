# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The warning gaspatchio raises when a user must hear something unasked.

Used as a library, gaspatchio mutes its own log records, because a library
speaks only when asked. A few things it has to say regardless: an
assumption table re-registered under a name it already had, a slow pattern
in the user's own code, a request it could not honour and answered another
way. Those are not log records. They are raised through Python's own
:mod:`warnings` as a :class:`GaspatchioWarning`, so they are shown by
default, filtered with :func:`warnings.filterwarnings`, and captured by
pytest, and each is raised through one channel only.
"""

from __future__ import annotations

import sys
import warnings
from typing import TYPE_CHECKING

from gaspatchio._source import is_framework_or_interpreter_file

if TYPE_CHECKING:
    from types import FrameType

# Added where no frame on the stack is the user's, so the warning says why it
# names a line of gaspatchio's own rather than pointing into whatever ran it.
_NO_LINE_OF_YOURS = (
    " (No line of your own code led here, so this names the line in "
    "gaspatchio that raised it.)"
)


class GaspatchioWarning(UserWarning):
    """Something gaspatchio did, or could not do, that the user should know.

    Python's default filters show it once for each line of the user's code
    that leads to it. ``warnings.filterwarnings("ignore",
    category=GaspatchioWarning)`` silences every one, and ``"error"`` in
    place of ``"ignore"`` turns each into an exception.
    """


def warn(message: str, category: type[GaspatchioWarning] = GaspatchioWarning) -> None:
    """Raise ``message`` as a warning, located at the user's line that led to it.

    The stack is walked with ``is_framework_or_interpreter_file``, the rule
    the error locators and the capture of each calculation's source line
    follow, so all three agree on whose line it is: a model run in place
    under the package's tutorials is the user's, and the interpreter's own
    frames are nobody's. Where no frame on the stack is the user's -- the
    framework running on its own, as under gspio -- the message says so and
    the warning is located where gaspatchio raised it.

    Whatever ran the user's code -- a script, a notebook cell,
    :func:`runpy.run_path`, ``python -m`` -- the warning reaches it; as with
    :func:`warnings.warn`, only a filter set to ``"error"`` turns it into an
    exception.

    Args:
        message: What the user needs to hear, and the next move.
        category: The warning's class, ``GaspatchioWarning`` or a subclass.

    """
    site = sys._getframe(1)  # noqa: SLF001 -- the frame that raised it
    frame: FrameType | None = site
    while frame is not None and is_framework_or_interpreter_file(
        frame.f_code.co_filename
    ):
        frame = frame.f_back
    if frame is None:
        frame = site
        message += _NO_LINE_OF_YOURS
    # What warnings.warn() does once it has found its frame: the same
    # filters, the same once-per-line registry, and the source line read when
    # the warning is shown. Like warnings.warn(), it keeps the frame's globals
    # from warn_explicit(), which would ask their loader for the source and
    # raise where it cannot answer: a notebook cell or a runpy.run_path script
    # has no loader, a module run with python -m has one that does not answer
    # to __main__, and a module whose file has gone since import has no
    # source to give.
    namespace = frame.f_globals
    warnings.warn_explicit(
        message,
        category,
        frame.f_code.co_filename,
        frame.f_lineno,
        module=namespace.get("__name__", "<string>"),
        registry=namespace.setdefault("__warningregistry__", {}),
    )
