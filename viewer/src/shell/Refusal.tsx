// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What the page says when it will not draw something, and where it says it.
 *
 * Every refusal is one sentence in the framework's voice, shown in place of
 * the view it replaces. Both halves of that are load-bearing.
 * One sentence, because a refusal that needed a paragraph is a page that has not
 * decided what it is telling you. In place of the view, because a refusal in a
 * banner at the top leaves the reader looking at an empty region and guessing
 * which of the two is the truth.
 *
 * Every sentence says the same three things in the same order: what the file
 * claimed, what this page does with that claim, and the one move available. The
 * one move is a command or a regeneration, never "try again" and never a
 * suggestion to edit the file, because a file edited into opening is a file
 * whose seal no longer describes it.
 *
 * The sentences this page can say about a whole file live in `reader/parse.ts`,
 * because they are conclusions about the text and are testable without a
 * browser. The two that belong to a region live here, next to the component
 * that prints them, because they name the region.
 *
 * What this component does not do is decide. It is handed a sentence and it
 * prints it, and the `data-refusal` attribute says which case it is, so a
 * refusal can be found by name from a test and pointed at in a bug report.
 */

import type { JSX } from "react";

/**
 * A grid with no values in it, said where the grid would be.
 *
 * `calc-graph` samples the frame it just ran, so an artifact without a policy's
 * values is an artifact written from the graph alone — the published corpus, or
 * an export somebody produced for the lineage and not the numbers.
 */
export const NO_VALUES_IN_GRID =
  "This file carries no values: its enrichment context is null and not one of its nodes " +
  "carries a value_sample, so there is no timeline to put in the grid. Run gspio calc-graph " +
  "model.py points.parquet --policy-id <id> --html and the grid fills.";

/** The same absence, said where the worked example would be. */
export const NO_VALUES_IN_PROOF =
  "This file carries no values: its enrichment context is null and not one of its nodes " +
  "carries a value_sample or a trace, so there is no worked example to show. Run gspio " +
  "calc-graph model.py points.parquet --policy-id <id> --html and this panel fills.";

/**
 * The layout the page did not attempt, said where the overview would be.
 *
 * @param nodes - How many nodes the file carries.
 * @param max - The count above which the whole-graph layout is skipped.
 * @returns The sentence, naming both numbers and the reason for the rule.
 */
export function tooLargeToLayOut(nodes: number, max: number): string {
  return (
    `This model has ${String(nodes)} nodes and the whole-graph layout is skipped above ` +
    `${String(max)}, so the overview is not drawn and the cone is laid out on the selected ` +
    `window alone. The grid and the proof are unaffected. The count is fixed rather than timed ` +
    `because a number you can read beats a behaviour that varies by laptop.`
  );
}

/**
 * One refusal, printed.
 *
 * @param sentence - The whole of it. One sentence, assembled by whoever knows
 *   what the file claimed.
 * @param which - The case, for `data-refusal`.
 * @param seal - The file's `document_digest` where it carried one a reader can
 *   quote back. A refused file is still a file somebody was sent, and "which
 *   one were you holding?" is the first question asked about it.
 */
export function Refusal({
  sentence,
  which,
  seal,
}: {
  sentence: string;
  which: string;
  seal?: string | undefined;
}): JSX.Element {
  return (
    <div className="refusal" data-testid="refusal" data-refusal={which}>
      <p className="refusal-sentence">{sentence}</p>
      {seal === undefined ? null : (
        <p className="refusal-seal mono" data-testid="refusal-seal">
          {seal}
        </p>
      )}
    </div>
  );
}
