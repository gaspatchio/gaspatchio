# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The `--html` door: one page, everything inside it, or a refusal by name.

`gspio calc-graph --html` writes the artifact it always wrote and then asks
`gaspatchio_viewer` for the page around it. Two things are being held to here.

The first is that the page carries the artifact rather than a re-serialisation
of it. A reader who extracts the JSON block back out gets the bytes the
exporter wrote, which is what makes the seal in the header a seal over
something they hold. The one change made on the way in is the JSON escape
`\\u003c` for `<`, without which a formula reading `af.month < af.policy_term`
would close the element it sits in.

The second is what happens when the extra is not installed. The core wheel
carries no JavaScript, so this is the ordinary case, not the exceptional one:
the command says what to install and what it did and did not write, and exits
non-zero with the JSON on disk and no half-written page beside it.

The third is the notices the page ends with. The bundle and the fonts are other
people's work, licensed on the condition that their notices travel with them,
and a page travels without its wheel. So every page closes with the viewer's
third-party notices in a comment, escaped so that no two hyphens stand together,
and the escape is one a reader can undo from what the comment itself says.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import types
from html.parser import HTMLParser
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph.html_export import ViewerNotInstalledError, render_html
from tests.graph.test_relative_paths import _a_model_at

runner = CliRunner()


def _real_viewer_importable() -> bool:
    """Whether the extra is installed in the environment running these tests."""
    return importlib.util.find_spec("gaspatchio_viewer") is not None


def _no_viewer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `import gaspatchio_viewer` fail, installed or not.

    A `None` in `sys.modules` is the interpreter's own way of saying "this
    import is known to fail", so the refusal is exercised on a machine that has
    the extra as faithfully as on one that does not.
    """
    monkeypatch.setitem(sys.modules, "gaspatchio_viewer", None)


def _a_stub_viewer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand a minimal viewer in place of the real one.

    The page's shape is asserted against the real bundle further down. What
    this stands in for is the wiring: that the command finds the module, hands
    it the artifact text and the title, and writes back what it is given.
    """
    stub = types.ModuleType("gaspatchio_viewer")
    stub.__version__ = "0.0.0-stub"  # type: ignore[attr-defined]
    stub.bundle = lambda: "console.log('stub')"  # type: ignore[attr-defined]
    stub.styles = lambda: "body{}"  # type: ignore[attr-defined]

    def block(artifact_json: str) -> str:
        return (
            '<script type="application/json" id="artifact">'
            + artifact_json.replace("<", "\\u003c")
            + "</script>"
        )

    def render(
        artifact_json: str, *, second: str | None = None, title: str = "gaspatchio"
    ) -> str:
        return (
            "<title>"
            + title
            + "</title><style>body{}</style>"
            + block(artifact_json)
            + ("" if second is None else block(second))
            + '<div id="root"></div><script>console.log(1)</script>'
        )

    stub.render = render  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gaspatchio_viewer", stub)


def _artifact_block(html: str) -> str:
    """Return the artifact block's text, exactly as the page carries it."""
    found = re.search(
        r'<script type="application/json" id="artifact">(.*?)</script>', html, re.S
    )
    assert found is not None, "the page carries no artifact block"
    return found.group(1)


def _the_documents_own_words(html: str) -> str:
    """Return the page with the three things it only carries lifted out of it.

    The claim being held to is that the page fetches nothing, and the honest
    form of that claim is not "no address appears anywhere in the file".
    Addresses appear in all three parts of it and not one of them is fetched:

    * The artifact carries `_producer` and `_schemaURL` on every facet. The
      specification says in as many words that these are identifiers first,
      that neither is required to resolve, and that a consumer which cannot
      reach either has lost nothing (`spec/graph-artifact/v0-preview.md` §6).
      The page carries the artifact byte for byte, so it carries these too, or
      it is not carrying the artifact.
    * The bundle carries React's production error index, in a sentence it
      prints and never opens, and the XML, MathML and XLink namespaces, which
      are identifiers the DOM matches on and which the specifications defining
      them spell as URLs.
    * The third-party notices the page ends with are the bundled packages'
      licence files verbatim, and one of them names its author's homepage.
      A comment is never fetched, and the notices are carried as written or
      they are not the notices.
    * The document's own words carry nothing of the sort, and that is what is
      asserted here -- together with the two things that would actually make
      the browser reach for something: an external `<link>` and a `<script
      src>`.
    """
    without_artifact = re.sub(
        r'(?s)<script type="application/json" id="artifact">.*?</script>',
        "",
        html,
    )
    without_notices = without_artifact.split("</html>\n<!--\nThird-party notices:")[0]
    return re.sub(r"(?s)<script>.*?</script>", "", without_notices)


class _Comments(HTMLParser):
    """Every comment a page holds, as an HTML parser reads them."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.comments: list[str] = []

    def handle_comment(self, data: str) -> None:
        self.comments.append(data)


def _notices_in(html: str) -> str:
    """Read the notices back out of a page, by what the page says about them.

    Written from the comment's own head rather than from the renderer, so that
    passing says the head is enough: the text starts after the comment's first
    blank line and ends at the line break before the comment closes, and each
    backslash in it stands for the character after it. The comment is found
    by a parser, not by a search for its first line, and it has to be the
    page's last one.
    """
    parser = _Comments()
    parser.feed(html)
    parser.close()
    assert parser.comments, "the page carries no comment, so no notices"
    data = parser.comments[-1]
    head, _, body = data.partition("\n\n")
    assert head.startswith("\nThird-party notices:"), head[:80]
    assert body.endswith("\n")
    return re.sub(r"(?s)\\(.)", r"\1", body[:-1])


def _notices_file() -> bytes:
    """Return the notices the viewer's wheel carries, as bytes."""
    import gaspatchio_viewer

    assets = Path(gaspatchio_viewer.__file__).parent / "assets"
    return (assets / "third-party-notices.txt").read_bytes()


def test_render_html_refuses_by_name_without_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal names the extra, not the module it failed to import."""
    _no_viewer(monkeypatch)
    with pytest.raises(ViewerNotInstalledError) as raised:
        render_html("{}", title="t")
    assert 'pip install "gaspatchio[viewer]"' in str(raised.value)


def test_the_command_refuses_and_still_writes_the_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The artifact is on disk, the page is not, and the exit code says so."""
    _no_viewer(monkeypatch)
    _a_model_at(tmp_path / "model.py", tmp_path / "points.parquet")
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(tmp_path / "model.py"),
            str(tmp_path / "points.parquet"),
            "-o",
            str(tmp_path / "g.json"),
            "--html",
            str(tmp_path / "g.html"),
        ],
    )
    assert result.exit_code == 2, result.output
    assert 'pip install "gaspatchio[viewer]"' in result.output
    assert (tmp_path / "g.json").exists()
    assert not (tmp_path / "g.html").exists()


def test_the_page_carries_the_artifact_byte_for_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What comes back out of the block is what `calc-graph` wrote."""
    _a_stub_viewer(monkeypatch)
    _a_model_at(tmp_path / "model.py", tmp_path / "points.parquet")
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(tmp_path / "model.py"),
            str(tmp_path / "points.parquet"),
            "-o",
            str(tmp_path / "g.json"),
            "--html",
            str(tmp_path / "g.html"),
        ],
    )
    assert result.exit_code == 0, result.output
    html = (tmp_path / "g.html").read_text()
    assert (
        _artifact_block(html).replace("\\u003c", "<")
        == (tmp_path / "g.json").read_text()
    )
    assert not re.search(r"https?://", _the_documents_own_words(html))
    # The title is the model file's stem, so six of these open in six tabs read
    # as six model names rather than six of the same word.
    assert "<title>model</title>" in html


@pytest.mark.skipif(
    not _real_viewer_importable(),
    reason="gaspatchio-viewer not installed in this environment",
)
def test_the_real_bundle_renders_a_self_contained_page(tmp_path: Path) -> None:
    """The page an actuary opens asks the network for nothing."""
    _a_model_at(tmp_path / "model.py", tmp_path / "points.parquet")
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(tmp_path / "model.py"),
            str(tmp_path / "points.parquet"),
            "-o",
            str(tmp_path / "g.json"),
            "--html",
            str(tmp_path / "g.html"),
        ],
    )
    assert result.exit_code == 0, result.output
    html = (tmp_path / "g.html").read_text()

    assert (
        _artifact_block(html).replace("\\u003c", "<")
        == (tmp_path / "g.json").read_text()
    )
    assert "@font-face" in html
    assert "data:font/woff2" in html
    assert "<script src" not in html
    # One linked thing, and it is the file's own bytes: the favicon.
    assert html.count("<link") == 1
    assert '<link rel="icon" href="data:image/svg+xml;base64,' in html
    # Every `url()` in the styles is a font the file already holds. Judged on
    # the document's own words, as the address check below is: the bundle
    # carries React Flow's `url('#marker')` references to its own SVG
    # markers, which point inside the document and fetch nothing.
    own_words = _the_documents_own_words(html)
    assert [
        u for u in re.findall(r"url\(([^)]*)\)", own_words) if not u.startswith("data:")
    ] == []
    assert not re.search(r"https?://", own_words)


@pytest.mark.skipif(
    not _real_viewer_importable(),
    reason="gaspatchio-viewer not installed in this environment",
)
def test_the_escape_keeps_a_formula_from_closing_the_block() -> None:
    """A formula holding `<` comes back out of the page holding it.

    The test above cannot say this. Its model is `sum_assured * 0.00123`,
    whose artifact carries no `<` anywhere, so the escape is a no-op on it and
    removing the escape from `render()` leaves it green. A model with a
    comparison in it -- which is most of them, every maturity test and every
    `when` -- would put a `<` inside the block, and an unescaped one closes the
    element early and takes the rest of the artifact out of the page with it.
    """
    artifact = json.dumps({"formula": "when(af.month < af.policy_term * 12)"})
    block = _artifact_block(render_html(artifact, title="t"))
    # Nothing left in the block that could have ended it.
    assert "<" not in block
    assert block.replace("\\u003c", "<") == artifact
    # And the escape is JSON's own, not a convention of this page's: a parser
    # that knows nothing about how the artifact got here reads it back.
    assert json.loads(block) == json.loads(artifact)


@pytest.mark.skipif(
    not _real_viewer_importable(),
    reason="gaspatchio-viewer not installed in this environment",
)
def test_the_page_ends_with_the_notices_byte_for_byte(tmp_path: Path) -> None:
    """What `calc-graph --html` writes carries the viewer's notices, recoverably.

    Read back from the file on disk, as bytes decoded as the UTF-8 the page
    declares, by the rule the comment states -- and the result is the wheel's
    third-party-notices.txt, byte for byte. Nothing follows the comment, and
    nothing in it could have closed it early: no two hyphens stand together
    anywhere between its opening and its close.
    """
    _a_model_at(tmp_path / "model.py", tmp_path / "points.parquet")
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(tmp_path / "model.py"),
            str(tmp_path / "points.parquet"),
            "-o",
            str(tmp_path / "g.json"),
            "--html",
            str(tmp_path / "g.html"),
        ],
    )
    assert result.exit_code == 0, result.output
    html = (tmp_path / "g.html").read_bytes().decode("utf-8")

    assert _notices_in(html).encode("utf-8") == _notices_file()
    comment = html[html.index("</html>\n") + len("</html>\n") :]
    assert comment.startswith("<!--\n")
    assert comment.endswith("\n-->\n")
    assert "--" not in comment[len("<!--") : -len("-->\n")]
    # The notices hold two hyphens together dozens of times, so the escape is
    # doing work on the real file, not passing because it had none to do.
    assert _notices_file().count(b"--") > 20


@pytest.mark.skipif(
    not _real_viewer_importable(),
    reason="gaspatchio-viewer not installed in this environment",
)
@pytest.mark.parametrize(
    "notices",
    [
        "a -- b",
        "-->",
        "--!>",
        "<!-- a comment inside -->",
        "---- a rule, then a trailing hyphen -",
        "\\-- a backslash before two hyphens",
        "\\\\ two backslashes, \\- one before a hyphen, \\n not a line break",
        "- - spaced hyphens stay as they are - -",
        "ends in <!-",
        "> starts with a bracket",
        "-> starts with an arrow",
        "no newline at the end",
        "\n\nblank lines first, and one in the middle\n\nthen more\n",
        "unicode — © stays itself",
    ],
)
def test_the_escape_carries_any_notices_through_a_comment(
    notices: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whatever the notices hold, the comment closes where the page closes it.

    The real notices are one file; a dependency's next licence is another. The
    cases are the ones a comment is broken by -- two hyphens together, a
    closing sequence, an opening one, a trailing hyphen against the close, an
    opening bracket -- and the ones the escape's own character is: a backslash
    before a hyphen, and before another backslash.
    """
    import gaspatchio_viewer

    monkeypatch.setattr(gaspatchio_viewer, "notices", lambda: notices)
    html = gaspatchio_viewer.render('{"n": 1}', title="t")

    assert _notices_in(html) == notices
    comment = html[html.index("</html>\n") + len("</html>\n") :]
    inside = comment[len("<!--") : -len("-->\n")]
    assert "--" not in inside
    assert not inside.endswith("-")


def _viewer_source() -> Path | None:
    """The `viewer/` directory of this repository, where it is on disk.

    The distribution installed in the environment carries only built assets, so
    a machine holding the wheel and not the repository has no packer to compare
    against. That is a skip and not a failure: what this pair of tests holds to
    is that the two writers agree in the tree where both exist.
    """
    here = Path(__file__).resolve()
    viewer = here.parents[4] / "viewer"
    return viewer if (viewer / "pack.mjs").is_file() else None


def _packed(viewer: Path, first: str, second: str | None = None) -> str:
    """Return the page `pack.mjs` writes, over committed fixtures."""
    args = [first] if second is None else [first, "--second", second]
    subprocess.run(  # noqa: S603
        ["node", "pack.mjs", *args],  # noqa: S607
        cwd=viewer,
        check=True,
        capture_output=True,
    )
    return (viewer / "dist" / f"{first}.html").read_text()


@pytest.mark.skipif(
    not _real_viewer_importable() or _viewer_source() is None,
    reason="needs both the installed viewer and this repository's viewer/ tree",
)
@pytest.mark.parametrize("second", [None, "compare-before"])
def test_render_and_the_packer_write_the_same_bytes(second: str | None) -> None:
    """The page an actuary is sent and the page Playwright opens are one file.

    `pack.mjs` exists so the end-to-end tests can have a page without a model
    run and a Python environment, and it is worth having only while what it
    packs is what the command writes. The two are held to the same bytes here
    -- on a one-artifact page and on a two-artifact one -- so a change made to
    either that the other did not get is a failure in this repository rather
    than a surprise in somebody's browser.

    The two-artifact case is the comparison page. `--second` used to compose a
    page `render()` could not write; it is the same call now, and this is what
    says so.
    """
    viewer = _viewer_source()
    assert viewer is not None
    import gaspatchio_viewer

    name = "compare-after"
    artifacts = (viewer / "fixtures" / f"{name}.json").read_text()
    earlier = (
        None if second is None else (viewer / "fixtures" / f"{second}.json").read_text()
    )
    rendered = gaspatchio_viewer.render(artifacts, second=earlier, title=name)
    assert rendered == _packed(viewer, name, second)


@pytest.mark.skipif(
    not _real_viewer_importable() or _viewer_source() is None,
    reason="needs both the installed viewer and this repository's viewer/ tree",
)
def test_render_and_the_packer_carry_the_book_s_movement_alike() -> None:
    """The page ``gspio diff --html`` writes with values read, packed the same way.

    ``render(movement=)`` carries the change report's ``values`` member in a
    block of its own, compact, as the command writes it; ``pack.mjs
    --movement`` packs the same block from the committed report, so the page
    the end-to-end tests open is the page the command writes.
    """
    viewer = _viewer_source()
    assert viewer is not None
    import gaspatchio_viewer

    fixtures = viewer / "fixtures"
    values = json.loads((fixtures / "values-report.json").read_text())["values"]
    block = (fixtures / "values-movement.json").read_text().rstrip()
    rendered = gaspatchio_viewer.render(
        (fixtures / "values-after.json").read_text(),
        second=(fixtures / "values-before.json").read_text(),
        title="values-after",
        movement=block,
    )
    subprocess.run(
        [  # noqa: S607
            "node",
            "pack.mjs",
            "values-after",
            "--second",
            "values-before",
            "--movement",
            "values-movement",
        ],
        cwd=viewer,
        check=True,
        capture_output=True,
    )

    # The block is the report's member, as the command writes it with --html.
    assert block == json.dumps(values, separators=(",", ":"))
    assert rendered.count('id="movement"') == 1
    assert rendered == (viewer / "dist" / "values-after.html").read_text()


# --- a name for each side -------------------------------------------------------

# Two labels a command could hand `render()`: a path at a revision, and one
# holding every character that could end an attribute, open an element or
# close the block it sits on.
_LABEL_AFTER = "model.audit.json at v2026.Q2 (3f2a91c)"
_LABEL_BEFORE = "q1 \"<b>\" & 'quoted' </script><script>alert(1)</script>\r\nq\r1"


class _Blocks(HTMLParser):
    """Every artifact block a page holds: its label, and its text."""

    def __init__(self) -> None:
        super().__init__()
        self.labels: list[str | None] = []
        self.texts: list[str] = []
        self._inside = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        named = dict(attrs)
        self._inside = tag == "script" and named.get("id") == "artifact"
        if self._inside:
            self.labels.append(named.get("data-label"))
            self.texts.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._inside = False

    def handle_data(self, data: str) -> None:
        if self._inside:
            self.texts[-1] += data


def _blocks_of(html: str) -> _Blocks:
    """Return the artifact blocks of a page, as an HTML parser reads them."""
    parsed = _Blocks()
    parsed.feed(html)
    parsed.close()
    return parsed


@pytest.mark.skipif(
    not _real_viewer_importable(),
    reason="gaspatchio-viewer not installed in this environment",
)
def test_a_label_is_text_on_its_block_and_never_markup() -> None:
    """A label comes back out of the page as the label it was, and opens nothing.

    The page reads each block's label as text, so what is held here is what a
    parser reads: the same two labels, on the two blocks, in their order, and
    the two documents still whole. A label that closed its block, or opened a
    script of its own, would show here as a third element or a document cut
    short.
    """
    import gaspatchio_viewer

    after = json.dumps({"n": "after", "formula": "af.month < 12"})
    before = json.dumps({"n": "before"})
    plain = gaspatchio_viewer.render(after, second=before, title="t")
    named = gaspatchio_viewer.render(
        after,
        second=before,
        title="t",
        label=_LABEL_AFTER,
        second_label=_LABEL_BEFORE,
    )

    blocks = _blocks_of(named)
    assert blocks.labels == [_LABEL_AFTER, _LABEL_BEFORE]
    assert [json.loads(text) for text in blocks.texts] == [
        json.loads(after),
        json.loads(before),
    ]
    assert named.count("<script") == plain.count("<script")
    assert "</script><script>alert" not in named


@pytest.mark.skipif(
    not _real_viewer_importable(),
    reason="gaspatchio-viewer not installed in this environment",
)
def test_a_page_without_labels_is_the_page_it_always_was() -> None:
    """No label, no attribute: the blocks are the ones every page has carried."""
    import gaspatchio_viewer

    after = json.dumps({"n": "after"})
    before = json.dumps({"n": "before"})
    page = gaspatchio_viewer.render(after, second=before, title="t")

    blocks = page.split("<body>\n", 1)[1].split('<div id="root">', 1)[0]
    assert blocks == (
        f'<script type="application/json" id="artifact">{after}</script>\n'
        f'<script type="application/json" id="artifact">{before}</script>\n'
    )
    assert _blocks_of(page).labels == [None, None]


@pytest.mark.skipif(
    not _real_viewer_importable(),
    reason="gaspatchio-viewer not installed in this environment",
)
def test_a_label_for_the_earlier_document_needs_one() -> None:
    """A name for a document the page does not carry is refused, not dropped."""
    import gaspatchio_viewer

    with pytest.raises(ValueError, match="second_label names the earlier document"):
        gaspatchio_viewer.render("{}", title="t", second_label="q1")


@pytest.mark.skipif(
    not _real_viewer_importable() or _viewer_source() is None,
    reason="needs both the installed viewer and this repository's viewer/ tree",
)
@pytest.mark.parametrize("second", [None, "compare-before"])
def test_render_and_the_packer_write_the_same_bytes_with_labels(
    second: str | None,
) -> None:
    """The two writers agree on a labelled page as on an unlabelled one.

    The same fixtures as the test above, each side given a label, the earlier
    one holding every character an attribute must not carry as written. A
    page carrying one document carries its label too, and shows none.
    """
    viewer = _viewer_source()
    assert viewer is not None
    import gaspatchio_viewer

    name = "compare-after"
    fixtures = viewer / "fixtures"
    artifacts = (fixtures / f"{name}.json").read_text()
    earlier = None if second is None else (fixtures / f"{second}.json").read_text()
    labels = ["--label", _LABEL_AFTER]
    if second is not None:
        labels += ["--second-label", _LABEL_BEFORE]
    rendered = gaspatchio_viewer.render(
        artifacts,
        second=earlier,
        title=name,
        label=_LABEL_AFTER,
        second_label=None if second is None else _LABEL_BEFORE,
    )

    page = "render-labels"
    args = [name] if second is None else [name, "--second", second]
    subprocess.run(  # noqa: S603
        ["node", "pack.mjs", *args, *labels, "--as", page],  # noqa: S607
        cwd=viewer,
        check=True,
        capture_output=True,
    )
    # Read as bytes: reading as text would turn any carriage return the page
    # carried into a line feed and compare a page that was never written.
    packed = (viewer / "dist" / f"{page}.html").read_bytes().decode("utf-8")
    assert rendered == packed


@pytest.mark.skipif(
    not _real_viewer_importable(),
    reason="gaspatchio-viewer not installed in this environment",
)
def test_a_label_s_carriage_returns_are_written_as_references() -> None:
    """A carriage return travels as ``&#13;``, so a browser reads it back as one.

    An HTML parser reads a carriage return in an attribute's text, and a
    carriage return and line feed together, back as a line feed: the page
    would read a label other than the one it was given. Written as its
    character reference it is read back as itself.
    """
    import gaspatchio_viewer

    label = "cr\r\nlf\rlone cr"
    page = gaspatchio_viewer.render("{}", title="t", label=label)

    tag = page[page.index('<script type="application/json"') :].split(">", 1)[0]
    assert "\r" not in tag
    assert 'data-label="cr&#13;\nlf&#13;lone cr"' in tag
    assert _blocks_of(page).labels == [label]


@pytest.mark.skipif(
    not _real_viewer_importable(),
    reason="gaspatchio-viewer not installed in this environment",
)
@pytest.mark.parametrize("keyword", ["label", "second_label"])
def test_a_label_holding_nul_is_refused_by_name(keyword: str) -> None:
    """NUL is the one character no page can carry, so a label holding one is refused.

    A browser reads U+0000 in an attribute back as U+FFFD, however it is
    written, so the page would show a label other than the one it was given.
    """
    import gaspatchio_viewer

    with pytest.raises(ValueError, match=rf"{keyword} holds the character NUL"):
        gaspatchio_viewer.render("{}", second="{}", title="t", **{keyword: "q\x001"})
