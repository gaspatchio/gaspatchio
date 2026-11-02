// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The row cursor: which period everything on the page is showing.
 *
 * One number, printed once. The grid marks the row, the cone and the proof
 * will read the same period out of it, and a page that printed the period in
 * three places would eventually print two different ones.
 *
 * The slider is the whole scrub in one gesture; the arrow keys are the same
 * move one period at a time, and live on the grid, which is the thing a reader
 * has their hands on.
 *
 * **The number is as wide as the last period's, whatever period it prints.**
 * Everything after it on the strip stands where it stood through a scrub, and
 * that matters because the strip wraps: a period passing from one digit to two
 * moved every fact after it along, and on a line with no room to spare it put
 * the tier census on a line of its own mid-scrub, moving the panes down the
 * window under a grid that had just scrolled its row to an edge that then
 * moved. The digits are the mono face's, so the width is a count of them.
 */

import type { JSX } from "react";

import type { Index } from "../reader/index";
import type { Selection, SelectionAction } from "../state/selection";

/** The slider and the period it reads. */
export function Cursor({
  index,
  selection,
  dispatch,
}: {
  index: Index;
  selection: Selection;
  dispatch: (a: SelectionAction) => void;
}): JSX.Element | null {
  // A file whose nodes carry no sampled values has no timeline to scrub, and
  // a slider over nothing is a control that lies about what the file holds.
  if (index.periods === 0) return null;

  const last = index.periods - 1;

  return (
    <div className="period-cursor">
      <label htmlFor="period">period</label>
      <input
        id="period"
        type="range"
        data-testid="cursor"
        min={0}
        max={last}
        step={1}
        value={Math.min(selection.period, last)}
        onChange={(event) => dispatch({ period: Number(event.target.value) })}
      />
      <b
        className="mono"
        data-testid="period"
        style={{ minWidth: `${String(String(last).length)}ch` }}
      >
        {Math.min(selection.period, last)}
      </b>
      <span className="of">of {last}</span>
    </div>
  );
}
