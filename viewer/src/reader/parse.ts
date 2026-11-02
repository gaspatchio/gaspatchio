// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Reading the artifact, and refusing the files this page cannot read.
 *
 * Four things are checked here and nothing else: that the text is JSON, that
 * the schema identifier is the one this page reads, that the profile is one of
 * the format's two, and that a second file can be compared with the first.
 * Whether a file means what it says — fingerprints recomputed, invariants held
 * — is `gspio validate`'s answer, and the page shows the file's own seal rather
 * than asserting a second opinion from a second implementation.
 *
 * Every refusal is one sentence: what the file said, what this page reads, and
 * the one move available.
 *
 * Three of the four stop the page. The fourth does not: a second block this
 * page cannot compare with the first leaves the first block a perfectly good
 * page, so it comes back as a `notice` beside the artifacts rather than in
 * place of them — the first shown, the second refused, no comparison.
 *
 * **Two blocks are a comparison.** `gspio diff --html` writes a page
 * carrying the later document first and the earlier second, and the page
 * derives what moved between them. That is why the fourth check is no longer
 * "the same graph fingerprint": a comparison whose two graphs were identical
 * would be a comparison with no model change in it, which is the uninteresting
 * half of the question this page was grown to answer. What the check asks
 * instead is the one question `gspio diff` asks before it compares: whether
 * the two digests were taken under one fingerprint algorithm —
 * `reader/compare.ts` holds that rule and the reasoning behind it.
 *
 * **The parse keeps what the file carries.** `reader/exact.ts` holds the one
 * reviver: an integer literal a double would round arrives as its own digits,
 * because i64 is exact in the format (§10) and a page that rounded one would
 * be quoting a number the document does not hold. It is still one parse,
 * and every other value comes through untouched.
 */

import { refusedComparison } from "./compare";
import { parseExactly } from "./exact";
import type { Artifact } from "./types";
import { READS_SCHEMA } from "./types";

/**
 * A file this page will not draw, and the sentence saying why.
 *
 * `which` names the case rather than describing it — `block`, `json`,
 * `schema`, `profile` — so that the page can mark the refusal it printed and a
 * test can ask for one by name instead of matching on its wording. The wording
 * is the thing most likely to be improved; the case is not.
 */
export type Refusal = {
  refused: true;
  which: "block" | "json" | "schema" | "profile";
  sentence: string;
  seal?: string;
};

/**
 * One or more artifacts of one model, ready to index.
 *
 * `notice` is the sentence for a block the page read and will not draw, where
 * the block it was handed first is still a page. It is a refusal about a part
 * rather than about the file, which is why it travels beside the artifacts
 * rather than in place of them.
 */
export type Loaded = { refused: false; artifacts: Artifact[]; notice?: string };

/** The two profiles the format defines. An `executable` file is read and its `expr` ignored. */
const PROFILES = ["audit", "executable"];

/**
 * The seal, lifted out of text that would not parse.
 *
 * A file that is not JSON still usually carries a readable `document_digest`,
 * and a reviewer looking at a refusal wants to know which file they are
 * holding. Read by regex precisely because the parser has already failed.
 */
function sealOf(text: string): string | undefined {
  const m = /"document_digest"\s*:\s*"(sha256:[0-9a-f]{64})"/.exec(text);
  return m ? m[1] : undefined;
}

/**
 * Read one or more artifact texts.
 *
 * @param texts - The JSON texts, in the order the page carries them. The first
 *   is the one the rest are compared with.
 * @returns Every artifact the first can be compared with, with the sentence for
 *   any block it cannot beside them; or the one sentence saying why none of
 *   them will be drawn.
 */
export function parseArtifacts(texts: string[]): Loaded | Refusal {
  if (texts.length === 0) {
    return {
      refused: true,
      which: "block",
      sentence: "This page carries no artifact block; export it again with gspio calc-graph --html.",
    };
  }

  const artifacts: Artifact[] = [];

  for (const text of texts) {
    let parsed: unknown;
    try {
      parsed = parseExactly(text);
    } catch {
      const seal = sealOf(text);
      const refusal: Refusal = {
        refused: true,
        which: "json",
        sentence:
          "The artifact block could not be read as JSON; export it again with gspio calc-graph --html.",
      };
      if (seal !== undefined) refusal.seal = seal;
      return refusal;
    }

    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {
        refused: true,
        which: "json",
        sentence:
          "The artifact block could not be read as JSON: it holds no object; export it again with gspio calc-graph --html.",
      };
    }

    const artifact = parsed as Artifact;

    if (artifact.schema !== READS_SCHEMA) {
      return {
        refused: true,
        which: "schema",
        sentence:
          `The file says ${String(artifact.schema)} and this page reads ${READS_SCHEMA}; ` +
          "regenerate the page with the matching gaspatchio-viewer.",
        ...(artifact.document_digest ? { seal: artifact.document_digest } : {}),
      };
    }

    if (!PROFILES.includes(artifact.profile)) {
      return {
        refused: true,
        which: "profile",
        sentence:
          `The file claims the profile ${String(artifact.profile)} and this page reads ` +
          `${PROFILES.join(" or ")}; regenerate the page with the matching gaspatchio-viewer.`,
        ...(artifact.document_digest ? { seal: artifact.document_digest } : {}),
      };
    }

    artifacts.push(artifact);
  }

  // Two files on one page are a comparison, and the page compares them
  // wherever `gspio diff` would. A second file the report refuses — digests
  // under another fingerprint algorithm — is refused here too, and the first,
  // the one the document names first, which is the exporter's own order and
  // not a preference this reader formed, is still a perfectly good page.
  // `refusedComparison` holds the rule and says why a differing model path is
  // not a reason to refuse.
  const first = artifacts[0]!;
  const comparable: Artifact[] = [first];
  let notice: string | undefined;
  for (const artifact of artifacts.slice(1)) {
    const refused = refusedComparison(first, artifact);
    if (refused === null) {
      comparable.push(artifact);
      continue;
    }
    notice ??= refused;
  }

  return notice === undefined
    ? { refused: false, artifacts: comparable }
    : { refused: false, artifacts: comparable, notice };
}
