# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The viewer's built page, and the calls that assemble it.

This distribution carries JavaScript, styles, three font faces and a favicon,
and knows how to put them around one artifact. It is not the reader: the reader
is the TypeScript under ``viewer/src`` that the bundle was built from. What is
here is the last step -- one document, with everything it needs inside it.

It is a separate distribution for one reason. The core wheel carries no
JavaScript, so an actuary who installs gaspatchio to run a model downloads a
model runner; someone who wants to look at the graph asks for the extra and
gets the page. Nothing here imports gaspatchio, and gaspatchio imports this
only through :mod:`gaspatchio.frame.graph.html_export`, which refuses by name
when it is absent.

The page the assembled document opens is offline in the strong sense: no
stylesheet is linked, no script is fetched, no font is requested, and the
favicon is the file's own bytes. Hand the HTML to someone with no network and
they see exactly what you saw.

It carries its licences the same way. The bundle and the fonts are other
people's work, each licensed on the condition that its notice travels with it,
and a page travels without the wheel it came from. So every page ends with the
third-party notices, :func:`notices`, in a comment after ``</html>``.
"""

from __future__ import annotations

import base64
import re
from importlib.resources import files

__all__ = ["__version__", "bundle", "notices", "render", "styles"]

__version__ = "0.1.0rc1"


def _asset(name: str) -> str:
    """Return one built asset's text, from the package's own data."""
    return (files(__package__ or "gaspatchio_viewer") / "assets" / name).read_text(
        encoding="utf-8"
    )


def bundle() -> str:
    """Return the built viewer, as one piece of JavaScript.

    The whole reader and its shell, packed by ``viewer/build.mjs`` and shipped
    as package data rather than built at install time: a wheel that had to run
    a JavaScript toolchain to be usable would be a JavaScript toolchain the
    actuary installed without asking for one.

    It carries other people's code -- React, React Flow, dagre and the rest --
    licensed on the condition that their notices travel with it. A page built
    from it must carry :func:`notices` too, as every page :func:`render`
    writes does.

    Returns
    -------
    str
        The bundle, ready to be put inside a ``<script>`` element.
    """
    return _asset("viewer.js")


def styles() -> str:
    """Return the page's styles, with its three font faces inlined.

    Two files, in one string: what the views are drawn with, and the faces they
    are drawn in. The faces arrive as ``data:font/woff2;base64,...`` so that a
    page opened from a disk on a machine that has never seen iA Writer Quattro
    S still renders in it, and asks nobody for it.

    The faces are other people's work, under the SIL Open Font License, whose
    copyright lines have to travel with them, as the bundled packages' notices
    do. A page built from these styles must carry :func:`notices` too, as
    every page :func:`render` writes does.

    Returns
    -------
    str
        The stylesheet, ready to be put inside a ``<style>`` element.
    """
    return _asset("viewer.css") + "\n" + _asset("fonts.css")


def notices() -> str:
    """Return the notices of everything the page carries that is not ours.

    ``third-party-notices.txt``, which ``viewer/build.mjs`` writes from the
    bundle's own metafile on every build: each npm package esbuild bundled, at
    the version bundled, with its licence file verbatim, and the three font
    faces with their copyright lines and the SIL Open Font License. The wheel
    lists the same file as a licence file; :func:`render` puts it at the end
    of every page, and a page assembled from :func:`bundle` and
    :func:`styles` some other way has to carry it as well.

    Returns
    -------
    str
        The notices, as the file holds them.
    """
    return _asset("third-party-notices.txt")


# What the notices' comment says first, before a blank line and the notices.
# It is the escape's documentation for whoever holds only the page, so it says
# how to undo it in full. It holds no two hyphens together itself.
_NOTICES_HEAD = (
    "Third-party notices: the software and fonts this page carries that are\n"
    "not Opio Inc.'s work, each with its licence. This is gaspatchio-viewer's\n"
    "third-party-notices.txt, escaped for a comment, which two hyphens\n"
    "together could close: each backslash is written as two, and each hyphen\n"
    "that follows a hyphen has a backslash written before it. The text starts\n"
    "after the blank line below and ends at the line break before the comment\n"
    "closes. To read it back, replace each backslash and the character after\n"
    "it with that character, from left to right."
)


def _for_a_comment(text: str) -> str:
    """Return ``text`` with no two hyphens together, by the escape the head states.

    A backslash is written twice first, so that every backslash in the result
    starts an escape; then each hyphen that follows a hyphen in ``text`` gets
    one. Nothing else changes, so the notices read as they are.
    """
    doubled = text.replace("\\", "\\\\")
    return re.sub(r"(?<=-)-", lambda _: "\\-", doubled)


def _notices_comment() -> str:
    """Return the comment every page ends with: the head, then the notices."""
    return f"<!--\n{_NOTICES_HEAD}\n\n{_for_a_comment(notices())}\n-->\n"


def _favicon_href() -> str:
    """Return the soup can as a ``data:`` URI, which is the whole favicon.

    Base64 rather than the percent-encoded form the same SVG could take,
    because the SVG names the XML namespace by URL and the page states -- and a
    test asserts -- that it carries no address of anything. Encoded, the
    namespace is what it always was: an identifier the browser matches, never
    an address it visits.
    """
    svg = _asset("favicon.svg").strip()
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _escaped(text: str) -> str:
    """Return ``text`` with the three characters that would end an element."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _attribute(text: str) -> str:
    """Return ``text`` for a double-quoted attribute, as text and never as markup.

    Each character that could end the attribute or open an element is written
    as its entity, and a carriage return as its reference: written as itself,
    the parser reads it, and a carriage return and line feed together, back as
    a line feed.
    """
    return (
        text.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\r", "&#13;")
    )


def _no_nul(name: str, label: str | None) -> None:
    """Refuse a label holding NUL, the one character no page can carry.

    Raises:
        ValueError: If ``label`` holds U+0000, which a browser reads back as
            U+FFFD however it is written.

    """
    if label is not None and "\0" in label:
        msg = (
            f"{name} holds the character NUL (U+0000), which an HTML page "
            "cannot carry: the page would read it back as U+FFFD, the "
            "replacement character, and show a label other than the one "
            "given. Pass the label without it."
        )
        raise ValueError(msg)


def _block(artifact_json: str, label: str | None = None) -> str:
    """Return one artifact as the document carries it: one block, one escape.

    A label travels on the block as its ``data-label`` attribute, written as
    text and never as markup -- each character that could end the attribute
    or open an element is written as its entity -- so the page reads back the
    label it was given. With no label the block is what it always was.
    """
    named = "" if label is None else f' data-label="{_attribute(label)}"'
    return (
        f'<script type="application/json" id="artifact"{named}>'
        + artifact_json.replace("<", "\\u003c")
        + "</script>\n"
    )


def render(
    artifact_json: str,
    *,
    second: str | None = None,
    title: str = "gaspatchio",
    label: str | None = None,
    second_label: str | None = None,
    movement: str | None = None,
) -> str:
    """Return one self-contained HTML document around one artifact, or two.

    The artifact travels as text, not as a re-serialisation: whatever
    ``calc-graph`` wrote is what the page carries, byte for byte, so the seal
    in the header is a seal over the bytes a reader can extract back out. The
    one change made to it is the JSON escape ``\\u003c`` for ``<``, which is
    what stops an artifact holding ``af.month < 12`` in a formula from closing
    the element it is sitting in. JSON reads the escape back as ``<``, so the
    document the page parses is the document the exporter wrote.

    **The page ends with the third-party notices**, :func:`notices`, in a
    comment after ``</html>``: the licences of the bundle's packages and of
    the three font faces, which a page has to carry wherever it is sent.
    Before the notices, the comment says what they are and how they are
    escaped. A comment cannot safely hold two hyphens together, and a notice
    can, so each backslash is written as two and each hyphen that follows a
    hyphen has a backslash before it. Replacing each backslash and the
    character after it with that character gives the file back byte for byte.
    It costs every page about 34 KB, none of it on screen.

    **A second artifact makes the page a comparison**, which is what ``gspio
    diff --html`` writes: the first block is the *later* of the two documents
    and the second is the earlier, and the page derives what moved between them
    rather than being handed a verdict. Two blocks and never three -- a
    comparison has two sides, and a page carrying a third would have no answer
    to "compared with what".

    Parameters
    ----------
    artifact_json
        The artifact, as ``calc-graph`` wrote it. On a comparison page this is
        the later document, because it is the one every view is drawn from.
    second
        The earlier artifact, where the page is a comparison. It travels
        exactly as the first does, under the same block and the same escape.
    title
        What to call the document. The command passes the model file's stem,
        so a reader with six of these open reads six model names.
    label
        A short name for the artifact, in the caller's own words -- a path, or
        a path at a revision, ``model.audit.json at v2026.Q2 (3f2a91c)``. It
        travels on the artifact's block, and a comparison page shows it where
        it names its two sides, beside the later document's date and seal. A
        page carrying one document names its model and its graph rather than
        the file it was read from, so it carries the label and does not show
        it. Text, never markup, whatever it holds, and read back exactly as it
        was given; a label holding NUL, which no page can carry, is refused.
    second_label
        The same for ``second``, which it needs: a label for an earlier
        document the page does not carry is refused rather than dropped.
    movement
        On a comparison, ``gspio diff``'s ``values`` member as JSON, where the
        command read the two runs' results files: how far each line moved over
        the whole book. It travels in a block of its own, ``id="movement"``,
        under the artifacts' escape. The page still derives every mark from
        the two documents; this is shown beside them, and the page holds its
        own reading of the policy it carries against it. Like ``second_label``
        it needs ``second``.

    Returns
    -------
    str
        The whole page: title, favicon, styles, the artifacts, root, bundle,
        and the notices after it.

    Examples
    --------
    >>> page = render('{"schema": "gaspatchio-graph/v0-preview.2"}', title="term")
    >>> page.startswith("<!doctype html>")
    True
    >>> "<title>term</title>" in page
    True
    >>> page.count('id="artifact"')
    1

    The notices close it, after ``</html>``:

    >>> tail = page[page.index("</html>\\n") :]
    >>> tail.startswith("</html>\\n<!--\\nThird-party notices:")
    True
    >>> tail.endswith("\\n-->\\n")
    True

    A comparison carries both, the later one first:

    >>> both = render('{"n": "after"}', second='{"n": "before"}', title="term")
    >>> both.count('id="artifact"')
    2
    >>> both.index('{"n": "after"}') < both.index('{"n": "before"}')
    True

    Each side can carry a label, which is text whatever it holds:

    >>> named = render(
    ...     '{"n": "after"}',
    ...     second='{"n": "before"}',
    ...     label="model.audit.json at v2026.Q2 (3f2a91c)",
    ...     second_label='a "<label>" & </script>',
    ... )
    >>> 'data-label="model.audit.json at v2026.Q2 (3f2a91c)"' in named
    True
    >>> 'data-label="a &quot;&lt;label&gt;&quot; &amp; &lt;/script&gt;"' in named
    True
    >>> '<script type="application/json" id="artifact">{"n": "before"}' in both
    True

    The book's movement travels after the two documents, in a block of its own:

    >>> moved = render(
    ...     '{"n": "after"}', second='{"n": "before"}', movement='{"lines": []}'
    ... )
    >>> '<script type="application/json" id="movement">{"lines": []}</script>' in moved
    True
    """
    _no_nul("label", label)
    _no_nul("second_label", second_label)
    if second_label is not None and second is None:
        msg = (
            "second_label names the earlier document of a comparison, and this "
            "page carries one document. Pass the earlier artifact as second= "
            "as well, or leave second_label out."
        )
        raise ValueError(msg)
    if movement is not None and second is None:
        msg = (
            "movement is what moved between the two documents of a comparison, "
            "and this page carries one document. Pass the earlier artifact as "
            "second= as well, or leave movement out."
        )
        raise ValueError(msg)
    blocks = _block(artifact_json, label)
    if second is not None:
        blocks += _block(second, second_label)
    if movement is not None:
        blocks += (
            '<script type="application/json" id="movement">'
            + movement.replace("<", "\\u003c")
            + "</script>\n"
        )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_escaped(title)}</title>\n"
        f'<link rel="icon" href="{_favicon_href()}">\n'
        f"<style>\n{styles()}\n</style>\n"
        "</head>\n"
        "<body>\n" + blocks + '<div id="root"></div>\n'
        f"<script>\n{bundle()}\n</script>\n"
        "</body>\n"
        "</html>\n" + _notices_comment()
    )
