// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Which of the grid's rows are drawn: the virtualizer's window, in whole blocks.
 *
 * The virtualizer's own window is the rows in sight and an overscan on each
 * side, and it moves with every row the scroller moves. A scrub moves the row
 * cursor a period a frame, and once the cursor's row reaches the bottom of the
 * grid the grid follows it down a row a frame — so the table took a row in and
 * a row out on every one of those frames. Each is a change to the table's
 * structure, laid out again; and the scroll event that moved the window
 * re-rendered the grid in the middle of the frame, after which the column
 * virtualizer's handler on the same scroller read its offset and forced the
 * page's layout once more. Widened to whole blocks, the window moves once every
 * `ROW_BLOCK` rows, and a scroll between those moves changes nothing in the
 * table at all. Taken out of the finished page, the scrub costs 0.6 ms more
 * main-thread work a frame, 1.0 on the comparison page, and lays the page out
 * 2.77 times a frame rather than 2.06.
 *
 * Every row the virtualizer asks for is still drawn, and the widening only ever
 * adds rows, off the screen, on the far side of the overscan. That leaves the
 * screen exactly as it was only because a row the grid does not draw is laid
 * out at the height of one it does — `ROW_HEIGHT` in `Grid.tsx` says why — and
 * screenshots of eleven states of the page match the tree before this.
 */

import type { Range } from "@tanstack/react-virtual";

/** How many rows the grid's window moves by at once. */
export const ROW_BLOCK = 16;

/**
 * The rows to draw for one of the virtualizer's ranges: its window, widened to
 * whole blocks.
 *
 * The grid's `rangeExtractor`. The virtualizer's own window runs from
 * `overscan` rows above the first row in sight to `overscan` rows below the
 * last; this starts at the block that window starts in and ends where the block
 * it ends in ends, or at the last row.
 *
 * @param range - The rows in sight, the overscan, and how many rows there are.
 * @returns The rows to draw, in order.
 */
export function rowsInBlocks(range: Range): number[] {
  if (range.count <= 0) return [];
  const first = Math.max(0, range.startIndex - range.overscan);
  const last = Math.min(range.count - 1, range.endIndex + range.overscan);
  const from = Math.floor(first / ROW_BLOCK) * ROW_BLOCK;
  const to = Math.min(range.count - 1, Math.ceil((last + 1) / ROW_BLOCK) * ROW_BLOCK - 1);
  const rows: number[] = [];
  for (let at = from; at <= to; at += 1) rows.push(at);
  return rows;
}

/** Where the grid's scroller stands and how much of it a row can be seen through. */
export interface Sight {
  /** The period whose row must be in sight. */
  period: number;
  /** How many rows the grid has. */
  count: number;
  /** Every row's height, which is the height it draws at. */
  rowHeight: number;
  /** How far the scroller is scrolled. */
  offset: number;
  /** The scroller's height. */
  size: number;
  /** How much of that height no row can be seen through: the header, and a scrollbar. */
  obscured: number;
}

/**
 * Where the grid's scroller must be moved to for one period's row to be in sight.
 *
 * The rule is the virtualizer's own — `scrollToIndex` with `align: "auto"` and
 * the grid's `scrollPaddingEnd` — written over numbers the grid already holds,
 * so the answer costs no layout. Asked through the virtualizer, every period
 * step of a scrub read the scroller's `scrollHeight` straight after the step
 * had changed the page, which made the browser lay the whole page out there
 * and then, once the cone's boxes had written their lines, lay it out again
 * for the frame; and a step whose row was already in sight still wrote the
 * offset the scroller stood at, which costs the same layout to move nothing.
 *
 * A row reaching past the bottom of what can be seen is brought up until its
 * lower edge sits on that bottom; a row above the top is brought down to it;
 * a row in sight is left where it is. `test/rows.test.ts` holds this to the
 * virtualizer's `getOffsetForIndex` over every period, offset and size it
 * tries.
 *
 * @param sight - The row, and where the scroller stands.
 * @returns The offset to scroll to, `"bottom"` for the last row brought into
 *   sight from above — the furthest the scroller goes, which only the browser
 *   knows exactly — or null where the row is in sight already. An offset past
 *   either end is the browser's to clamp, as it clamps every scroll.
 */
export function followOffset(sight: Sight): number | "bottom" | null {
  const { count, rowHeight, offset, size, obscured } = sight;
  if (count <= 0) return null;
  const period = Math.max(0, Math.min(sight.period, count - 1));
  const top = period * rowHeight;
  const bottom = top + rowHeight;
  let to: number | "bottom" | null = null;
  if (bottom >= offset + size - obscured) {
    to = period === count - 1 ? "bottom" : bottom + obscured - size;
  } else if (top <= offset) {
    to = top;
  }
  // Already standing there: the virtualizer would write the same offset, and a
  // write is a layout whether or not it moves anything.
  return to === offset ? null : to;
}
