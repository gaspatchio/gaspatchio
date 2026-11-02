// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The one thing on the page that changes.
 *
 * Which column is selected, which period the cursor sits on, and how far the
 * cone reaches each way. Every view is a function of the index and this, so a
 * click in the grid and a click in the cone are the same click; the shell holds
 * it in one `useReducer` and nothing else holds any of it.
 *
 * The reducer is pure and lives apart from React so that what the page does
 * when you press a key can be read, and tested, without a browser.
 */

/** Where the reader is looking. */
export interface Selection {
  /** The selected node's id, as the file spells it, or nothing selected yet. */
  nodeId: string | null;
  /** The row cursor's period: an index into the sampled timelines. */
  period: number;
  /**
   * The cone's drawn set, once the reader has explored it; `null` until then.
   *
   * `null` means the cone is the window the depths below describe — the seed a
   * new subject opens with. The moment a reader clicks a node at the edge of
   * that window, the cone stops being a function of the centre and becomes the
   * set they have opened up, which is what lets everything already on the
   * screen stay where it is.
   *
   * Two things put it back to `null`: choosing a column from the grid or the
   * search, which is a new subject, and the depth steppers, which mean "this
   * many steps everywhere" and cannot mean that over a set somebody has been
   * growing by hand.
   */
  revealed: ReadonlySet<string> | null;
  /** How many steps of the cone to draw above the selected node. */
  up: number;
  /** How many steps of the cone to draw below it. */
  down: number;
}

/** Nothing selected, the cursor on the first period, the cone two steps each way. */
export const initialSelection: Selection = {
  nodeId: null,
  period: 0,
  up: 2,
  down: 2,
  revealed: null,
};

/** The four moves. Each names the one member it changes. */
export type SelectionAction =
  | { select: string }
  | { focus: string }
  | { revealed: string[] }
  | { period: number }
  | { up: number }
  | { down: number };

/** No period before the first, and no cone narrower than the node itself. */
function atLeastZero(n: number): number {
  return n < 0 ? 0 : Math.trunc(n);
}

/**
 * Apply one move.
 *
 * Selecting a column keeps the cursor where it was, deliberately: a reviewer
 * comparing two columns at period 12 is asking about period 12, and a selection
 * that reset the row would make them ask again every time.
 *
 * @param s - Where the reader is looking now.
 * @param a - The move.
 * @returns Where the reader is looking next.
 */
export function reduceSelection(s: Selection, a: SelectionAction): Selection {
  // A new subject: the cone opens on its seed window rather than on whatever
  // the reader had opened up around the last column.
  if ("select" in a) return { ...s, nodeId: a.select, revealed: null };
  // The same selection from inside the cone, which must not disturb the
  // drawing: clicking a box that is already on the screen moves the focus and
  // leaves every other box exactly where it is.
  if ("focus" in a) return { ...s, nodeId: a.focus };
  if ("revealed" in a) return { ...s, revealed: new Set(a.revealed) };
  if ("period" in a) return { ...s, period: atLeastZero(a.period) };
  if ("up" in a) return { ...s, up: atLeastZero(a.up), revealed: null };
  return { ...s, down: atLeastZero(a.down), revealed: null };
}
