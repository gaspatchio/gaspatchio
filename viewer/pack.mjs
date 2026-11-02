// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Put one page together from a fixture, for development.
 *
 * `gaspatchio_viewer.render()` is what writes the file an actuary opens; this
 * is the same document, assembled in JavaScript over a fixture, so the end-to-
 * end tests can have a page without a model run and a Python environment. The
 * two are kept the same deliberately: same assets, same order, same escape,
 * same bytes — a page packed here and a page rendered there differ in nothing,
 * which is what `test_html_export.py` checks and what makes a failure seen in
 * Playwright a failure in the file the command writes.
 *
 * Usage, from `viewer/`:
 *
 *     node pack.mjs level4                   # fixtures/level4.json → dist/level4.html
 *     node pack.mjs after --second before    # the comparison page, two artifacts
 *     node pack.mjs a --second a --as a-self # one fixture both sides, its own page
 *     node pack.mjs after --second before --label "q2" --second-label "q1"
 *     node pack.mjs values-after --second values-before --movement values-movement
 *
 * `--movement` is `render()`'s `movement`: `gspio diff`'s book-wide reading,
 * carried in a block of its own. It names a fixture holding the block's text --
 * a change report's `values` member, compact, as the command writes it with
 * `--html` -- and the page carries that text as it stands.
 * `--label` and `--second-label` are `render()`'s `label` and `second_label`:
 * a name for each document, carried on its block and shown where a comparison
 * names its two sides.
 *
 * `--as` names the page and nothing in it. The file lands at
 * `dist/<first>.html`, which is the fixture's own name — so a fixture compared
 * with itself would be written over the one-artifact page packed from that
 * same fixture, and the two specs would be reading one file. Where the page
 * lands is this script's business and not `render()`'s; what is *in* it is
 * `render()`'s, byte for byte, either way.
 *
 * The assets come from `python/gaspatchio_viewer/assets/`, which is where
 * `npm run copy-assets` put them, so this packs the same bytes the wheel
 * carries rather than a second build of its own. That includes the
 * third-party notices every page ends with, in a comment after `</html>`,
 * under the escape `render()` documents.
 *
 * `--second` used to be the one thing here that `render()` could not do, and
 * the header said that the day the exporter could, `render()` would grow the
 * door and the line would go away. That day came: `gspio diff --html` writes
 * a page carrying both artifacts, `render()` takes the second, and this flag is
 * now the same call rather than a composition of its own. It stays because the
 * end-to-end tests need a comparison page without a Python environment, and
 * what it packs is the document the command writes — which is what
 * `test_html_export.py` holds the two to, byte for byte, on a two-artifact page
 * as well as on a one-artifact one.
 *
 * The page is written through a temporary name and renamed into place. Both
 * Playwright projects run the same spec, so two processes can be packing the
 * same page while a third is opening it, and a rename is the one write a
 * reader cannot catch half-finished.
 */

import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";

const assets = "python/gaspatchio_viewer/assets";

/** One built asset's text, from the distribution's package data. */
function asset(name) {
  return readFileSync(`${assets}/${name}`, "utf8");
}

/** The page's styles, with its three font faces inlined. `styles()`. */
function styles() {
  return `${asset("viewer.css")}\n${asset("fonts.css")}`;
}

/** The notices of everything the page carries that is not ours. `notices()`. */
function notices() {
  return asset("third-party-notices.txt");
}

/** What the notices' comment says first, before a blank line. `_NOTICES_HEAD`. */
const NOTICES_HEAD =
  "Third-party notices: the software and fonts this page carries that are\n" +
  "not Opio Inc.'s work, each with its licence. This is gaspatchio-viewer's\n" +
  "third-party-notices.txt, escaped for a comment, which two hyphens\n" +
  "together could close: each backslash is written as two, and each hyphen\n" +
  "that follows a hyphen has a backslash written before it. The text starts\n" +
  "after the blank line below and ends at the line break before the comment\n" +
  "closes. To read it back, replace each backslash and the character after\n" +
  "it with that character, from left to right.";

/** `text` with no two hyphens together, by the escape the head states. `_for_a_comment()`. */
function forAComment(text) {
  return text.replaceAll("\\", "\\\\").replace(/(?<=-)-/g, "\\-");
}

/** The comment every page ends with: the head, then the notices. `_notices_comment()`. */
function noticesComment() {
  return `<!--\n${NOTICES_HEAD}\n\n${forAComment(notices())}\n-->\n`;
}

/** The soup can as a `data:` URI, which is the whole favicon. `_favicon_href()`. */
function faviconHref() {
  const svg = asset("favicon.svg").trim();
  return `data:image/svg+xml;base64,${Buffer.from(svg, "utf8").toString("base64")}`;
}

/** `text` with the three characters that would end an element. `_escaped()`. */
function escaped(text) {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

/** `text` for a double-quoted attribute, as text and never as markup. `_attribute()`. */
function attribute(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\r", "&#13;");
}

/** Refuse a label holding NUL, the one character no page can carry. `_no_nul()`. */
function noNul(name, label) {
  if (label === undefined || !label.includes("\0")) return;
  throw new Error(
    `${name} holds the character NUL (U+0000), which an HTML page cannot carry: the page ` +
      "would read it back as U+FFFD, the replacement character, and show a label other than " +
      "the one given. Pass the label without it.",
  );
}

/** One artifact, as the document carries it: one block, one escape. `_block()`. */
function block(artifactJson, label) {
  const named = label === undefined ? "" : ` data-label="${attribute(label)}"`;
  return (
    `<script type="application/json" id="artifact"${named}>` +
    artifactJson.replaceAll("<", "\\u003c") +
    "</script>\n"
  );
}

/**
 * One self-contained HTML document around one artifact, or two.
 *
 * Line for line, `gaspatchio_viewer.render()`, down to the parameter names —
 * so that reading one and reading the other is reading the same function, and
 * a change made to either that the other did not get shows up as two pages
 * that are not the same bytes.
 *
 * @param artifactJson - The artifact, as `calc-graph` wrote it. On a comparison
 *   page this is the later document, because it is the one the views are drawn
 *   from.
 * @param second - The earlier artifact, where the page is a comparison.
 * @param title - What to call the document.
 * @param label - A name for the artifact, carried on its block.
 * @param secondLabel - A name for the earlier artifact, which it needs.
 * @param movement - `gspio diff`'s book-wide reading, as text, which needs `second`.
 * @returns The whole page.
 */
function render(artifactJson, { second, title, label, secondLabel, movement }) {
  noNul("--label", label);
  noNul("--second-label", secondLabel);
  if (secondLabel !== undefined && second === undefined) {
    throw new Error(
      "--second-label names the earlier document of a comparison, and this page carries " +
        "one document. Name the earlier fixture with --second as well, or leave --second-label out.",
    );
  }
  if (movement !== undefined && second === undefined) {
    throw new Error(
      "--movement is what moved between the two documents of a comparison, and this page " +
        "carries one document. Name the earlier fixture with --second as well.",
    );
  }
  const blocks =
    (second === undefined
      ? block(artifactJson, label)
      : block(artifactJson, label) + block(second, secondLabel)) +
    (movement === undefined
      ? ""
      : `<script type="application/json" id="movement">${movement.replaceAll("<", "\\u003c")}</script>\n`);
  return (
    "<!doctype html>\n" +
    '<html lang="en">\n' +
    "<head>\n" +
    '<meta charset="utf-8">\n' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n' +
    `<title>${escaped(title)}</title>\n` +
    `<link rel="icon" href="${faviconHref()}">\n` +
    `<style>\n${styles()}\n</style>\n` +
    "</head>\n" +
    "<body>\n" +
    blocks +
    '<div id="root"></div>\n' +
    `<script>\n${asset("viewer.js")}\n</script>\n` +
    "</body>\n" +
    "</html>\n" +
    noticesComment()
  );
}

const [, , first = "level4", ...rest] = process.argv;
const at = rest.indexOf("--second");
const second = at < 0 ? undefined : rest[at + 1];
if (at >= 0 && second === undefined) {
  throw new Error("--second takes a fixture name: node pack.mjs after --second before");
}
const called = rest.indexOf("--as");
const as = called < 0 ? undefined : rest[called + 1];
if (called >= 0 && as === undefined) {
  throw new Error("--as takes a page name: node pack.mjs a --second a --as a-self");
}

/** The text after one option, or undefined where the option is not given. */
function option(name) {
  const at = rest.indexOf(name);
  if (at < 0) return undefined;
  const value = rest[at + 1];
  if (value === undefined) {
    throw new Error(`${name} takes a label: node pack.mjs after --second before ${name} "q2"`);
  }
  return value;
}
const label = option("--label");
const secondLabel = option("--second-label");
const carried = option("--movement");
const movement =
  carried === undefined ? undefined : readFileSync(`fixtures/${carried}.json`, "utf8").trimEnd();

const names = second === undefined ? [first] : [first, second];
const page = render(readFileSync(`fixtures/${first}.json`, "utf8"), {
  second: second === undefined ? undefined : readFileSync(`fixtures/${second}.json`, "utf8"),
  title: first,
  label,
  secondLabel,
  movement,
});

mkdirSync("dist", { recursive: true });
const out = `dist/${as ?? first}.html`;
const partial = `${out}.${String(process.pid)}.part`;
writeFileSync(partial, page);
renameSync(partial, out);

console.log(
  JSON.stringify({ page: out, artifacts: names, bytes: Buffer.byteLength(page) }, null, 2),
);
