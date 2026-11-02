// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The page's entry point.
 *
 * It reads the artifact out of the block the exporter wrote and mounts the
 * shell over it. Parsing happens once, here, and not inside a component: the
 * document does not change while it is open, so a page that re-read it would
 * be doing the same work again to reach the same answer. Indexing is the
 * shell's, because an index is taken along one entry of the policy axis and
 * which entry that is belongs to the reader rather than to the file.
 *
 * The block is read from the document and nowhere else. The page never fetches.
 */

import { createRoot } from "react-dom/client";

import { readMovement } from "./reader/movement";
import { parseArtifacts } from "./reader/parse";
import { App } from "./shell/App";
import { Refusal } from "./shell/Refusal";

import "./theme/tokens.css";

/**
 * Every artifact block the exported page carries, in document order.
 *
 * One from `gspio calc-graph --html`; two from `gspio diff --html`, the later
 * document first and the earlier second, which is the order `render()` writes
 * them in and the order this page reads them in.
 */
function artifactTexts(): string[] {
  const blocks = document.querySelectorAll<HTMLScriptElement>("script#artifact");
  return [...blocks].map((block) => block.textContent ?? "");
}

/**
 * The name the command gave each document, where it gave one, in the same order.
 *
 * The block's `data-label`, read as text: a path, or a path at a revision of a
 * repository, which is something a reader cannot learn from the document
 * itself. A comparison page shows the two where it names its two sides.
 */
function artifactLabels(): (string | undefined)[] {
  const blocks = document.querySelectorAll<HTMLScriptElement>("script#artifact");
  return [...blocks].map((block) => block.getAttribute("data-label") ?? undefined);
}

/**
 * How far each line moved over the whole book, where `gspio diff --html` read
 * the two runs' results files and carried its measurement in a block of its
 * own; null where the page carries none.
 */
function movementText(): string | null {
  return document.querySelector<HTMLScriptElement>("script#movement")?.textContent ?? null;
}

const parsed = parseArtifacts(artifactTexts());
const [label, earlierLabel] = artifactLabels();
const root = document.getElementById("root");

if (root) {
  createRoot(root).render(
    parsed.refused ? (
      // A refusal about the file is the whole page: there is nothing behind it
      // to draw, and a page that drew part of one anyway would be guessing
      // which part was still true.
      <div className="whole-page-refusal">
        <Refusal which={parsed.which} sentence={parsed.sentence} seal={parsed.seal} />
      </div>
    ) : (
      // The first artifact is the page. A second is the document it is being
      // compared against — the earlier of the two, written second by `gspio
      // diff --html` — and what moved between them is derived in the page. A
      // second block that is not the same model is refused by name, travels as
      // the notice, and leaves the first a page on its own.
      <App
        artifact={parsed.artifacts[0]!}
        earlier={parsed.artifacts[1]}
        notice={parsed.notice}
        label={label}
        earlierLabel={earlierLabel}
        movement={parsed.artifacts[1] === undefined ? null : readMovement(movementText())}
      />
    ),
  );
}
