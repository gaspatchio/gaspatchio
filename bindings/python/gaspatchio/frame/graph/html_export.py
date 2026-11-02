# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The door between the artifact and the page that reads it.

`gspio calc-graph --html` writes one self-contained HTML file, and `gspio diff
--html` writes one carrying two artifacts and deriving what moved between them.
The bundle inside either file is JavaScript, and the core wheel carries none: an
actuary who installed gaspatchio to run a model installed a model runner, and
a page is something you ask for. So the page lives in its own distribution,
`gaspatchio-viewer`, and this module is the whole of what gaspatchio knows
about it -- one lazy import, one call, and one sentence for when the import
fails.

The sentence is the point. A traceback ending in `ModuleNotFoundError:
gaspatchio_viewer` names a module nobody asked for; what the reader needs is
the extra to install, and the fact that the artifact they came for was written
anyway.
"""

from __future__ import annotations

# The one sentence this module exists to be able to say. It names what is
# missing and both ways of installing it. The double spaces are deliberate:
# they set the commands off from the prose in a terminal that has no other way
# to show a command.
NOT_INSTALLED = (
    "The viewer is not installed. Writing an HTML page needs the "
    "gaspatchio-viewer package: install the extra with  "
    'pip install "gaspatchio[viewer]"  (or  uv add "gaspatchio[viewer]")  and '
    "run the command again."
)

# What each command adds to it, because `--html` is the second half of a
# request whose first half has already run and the reader needs to know what is
# and is not on disk. Two commands, two true sentences: `calc-graph` wrote an
# artifact and `diff` wrote a report to the terminal, and one sentence covering
# both would have to be vague about the thing the reader came for.
WROTE_THE_ARTIFACT = " The JSON artifact was written; the page was not."
WROTE_THE_REPORT = " The report above is the whole answer; the page was not written."


class ViewerNotInstalledError(RuntimeError):
    """The `gaspatchio[viewer]` extra is not installed.

    Raised by :func:`render_html`, caught by the command, printed as the one
    sentence it carries. A distinct type rather than a bare `ImportError`
    because the command treats this as a refusal with an exit code of its own,
    not as an unexpected failure to report a traceback for.
    """


def render_html(  # noqa: PLR0913 -- one or two documents, their labels, a title and the book's movement
    artifact_json: str,
    *,
    title: str,
    second: str | None = None,
    label: str | None = None,
    second_label: str | None = None,
    movement: str | None = None,
) -> str:
    """Return one self-contained HTML page around one artifact, or two.

    Parameters
    ----------
    artifact_json
        The artifact, as the exporter wrote it. It travels as text and is
        embedded as text: the page carries the bytes, not a re-serialisation
        of them, so the document digest in the header seals what a reader can
        extract back out. On a comparison page this is the later of the two
        documents, because it is the one every view is drawn from.
    title
        What to call the document. The command passes the model file's stem.
    second
        The earlier artifact, where the page is a comparison -- what ``gspio
        diff --html`` writes. What moved between the two is derived in the
        page from the two documents themselves; no report travels with them.
    label
        What to call ``artifact_json`` on the page, such as the path it was
        read from or ``model.audit.json at v2026.Q2``. A comparison page shows
        it beside that side's date; it travels as text and never as markup.
    second_label
        What to call ``second``, in the same way. It needs ``second``.
    movement
        On a comparison page, the change report's ``values`` member as JSON,
        where ``gspio diff`` read the two runs' results files: how far each
        line moved over the whole book. The page shows it beside each change
        it derives, and holds its own reading of the policy it carries
        against the member's. It needs ``second``.

    Returns
    -------
    str
        The whole page -- bundle, styles, fonts, favicon and artifacts, with
        nothing left outside it.

    Raises
    ------
    ViewerNotInstalledError
        When the `gaspatchio[viewer]` extra is not installed. The message is
        :data:`NOT_INSTALLED`, to which the command adds its own sentence
        about what it did write -- :data:`WROTE_THE_ARTIFACT` or
        :data:`WROTE_THE_REPORT`.

    Examples
    --------
    >>> from gaspatchio.frame.graph.html_export import render_html
    >>> page = render_html('{"schema": "x"}', title="term")  # doctest: +SKIP
    >>> page.startswith("<!doctype html>")  # doctest: +SKIP
    True
    """
    # Imported here and not at the top of the file, because the top of the file
    # is imported by everyone who imports gaspatchio and this package is
    # installed by almost none of them.
    try:
        import gaspatchio_viewer  # noqa: PLC0415 -- the optional `viewer` extra (pyproject [project.optional-dependencies]); absent, it becomes ViewerNotInstalledError here rather than an ImportError on `import gaspatchio`
    except ImportError as missing:
        raise ViewerNotInstalledError(NOT_INSTALLED) from missing

    # A label is passed only where there is one, so a page with none is asked
    # for exactly as it always was.
    labels = {
        name: value
        for name, value in (
            ("label", label),
            ("second_label", second_label),
            ("movement", movement),
        )
        if value is not None
    }
    return gaspatchio_viewer.render(artifact_json, second=second, title=title, **labels)
