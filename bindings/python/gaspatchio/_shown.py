# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Renders text a file supplied into the places that would interpret it.
# ABOUTME: A terminal and Rich markup (shown, spelled); Python source (python_literal).
r"""Text a file supplied, written where something would otherwise act on it.

The read-only commands print names and values out of files other people
wrote: a column of a model-point extract, a node id in an audit file, a
policy id, a file's own name. Three places interpret such text instead of
showing it:

* **The terminal.** An escape sequence inside a column name sets the
  window's title, writes the clipboard (OSC 52), or erases the line above
  -- the line that said ``✗``. :func:`spelled` writes every C0 and C1
  control character, ESC, BEL and CR among them, as the escape Python
  writes for it (``\x1b``, ``\x07``, ``\r``), the form ``gspio
  validate`` already shows an id in; :func:`terminal_console` makes a Rich
  console that does so to everything it prints.
* **Rich markup.** ``[link=...]`` in a name becomes a live hyperlink and
  ``[/bogus]`` raises ``MarkupError`` mid-command. :func:`shown` escapes
  the markup *and* spells the controls, for a name going into a markup
  string.
* **Python source.** ``gspio describe`` writes code a reader, or an agent,
  runs next. :func:`python_literal` writes a name as a string literal that
  reads back as that name, so a name holding a quote cannot close the
  literal and run what follows it.

Ordinary text passes through all three unchanged, so nothing a reviewer
reads moves for a name that holds none of these characters. This serves
*Audit by default*: what a reviewer reads is what the file holds.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rich.console import Console, ConsoleRenderable, RenderHook
from rich.markup import escape
from rich.segment import Segment

if TYPE_CHECKING:
    from collections.abc import Iterator

    from rich.console import ConsoleOptions

# Every C0 control, DEL and every C1 control. The second leaves the newline
# alone, for text that is several lines on purpose: a rendered table, or a
# report that breaks its own lines.
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f]")
_CONTROL_BUT_NEWLINE = re.compile("[\x00-\x09\x0b-\x1f\x7f-\x9f]")


def _spell(match: re.Match[str]) -> str:
    """Return one control character as the escape Python writes for it."""
    return repr(match.group())[1:-1]


def spelled(text: str, *, lines: bool = False) -> str:
    """Return ``text`` with every control character written out as its escape.

    Args:
        text: Text a file supplied.
        lines: Keep newlines, for text that breaks its own lines. Off, a
            newline is spelled too, so a name cannot start a line of its own.

    Returns:
        ``text`` itself where it holds no control character.

    """
    return (_CONTROL_BUT_NEWLINE if lines else _CONTROL).sub(_spell, text)


def shown(text: object, *, lines: bool = False) -> str:
    """Return ``text`` ready to go into a Rich markup string, as it reads.

    Args:
        text: Text a file supplied, or anything whose ``str`` is.
        lines: Keep newlines, as :func:`spelled` does.

    Returns:
        The text with its markup escaped and its control characters spelled.

    """
    return escape(spelled(str(text), lines=lines))


def python_literal(text: str) -> str:
    """Return a Python string literal that reads back as ``text``, and nothing else.

    ``repr`` is always such a literal. Double quotes are kept where the text
    allows them, so an ordinary name is written as it always was.

    Args:
        text: A name to write into generated code.

    Returns:
        The literal, quotes included.

    """
    literal = repr(text)
    if literal.startswith("'") and '"' not in text:
        # Neither quote is in the text, so nothing inside needs escaping again.
        return f'"{literal[1:-1]}"'
    return literal


class _Spelled:
    """A renderable whose text segments reach the terminal with controls spelled."""

    __slots__ = ("_renderable",)

    def __init__(self, renderable: ConsoleRenderable) -> None:
        """Wrap one renderable a console was asked to print."""
        self._renderable = renderable

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Iterator[Segment]:
        """Yield the renderable's segments, spelling the controls its text holds.

        A control segment is Rich's own cursor movement and is passed through,
        as is the styling, which Rich writes after this.
        """
        for segment in console.render(self._renderable, options):
            if segment.control or not _CONTROL_BUT_NEWLINE.search(segment.text):
                yield segment
            else:
                yield Segment(spelled(segment.text, lines=True), segment.style)


class _SpellControls(RenderHook):
    """Spell the control characters in everything a console prints."""

    def process_renderables(
        self, renderables: list[ConsoleRenderable]
    ) -> list[ConsoleRenderable]:
        """Wrap each renderable so its text cannot drive the terminal."""
        return [_Spelled(renderable) for renderable in renderables]


def terminal_console(*, stderr: bool = False) -> Console:
    """Return a Rich console that never writes a control character it was handed.

    Whatever is printed through it -- markup, a table, a frame's text -- has
    every control character in its text spelled out, newlines aside, while
    Rich's own styling and cursor movement reach the terminal as before.

    Args:
        stderr: Write to standard error rather than standard output.

    Returns:
        The console.

    """
    console = Console(stderr=stderr)
    console.push_render_hook(_SpellControls())
    return console
