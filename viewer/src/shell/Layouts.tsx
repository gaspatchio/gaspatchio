// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The four layouts, as one control in the strip.
 *
 * Each is a saved set of pane states and nothing more — no layout knows
 * a pixel or a divider position — so choosing one costs nothing beyond the
 * controls it is made of and leaves the reader's own dividers exactly where
 * they dragged them.
 *
 * **Four letters rather than four words**, and the word is in the title and in
 * the label a screen reader is given. The strip already carries the search box,
 * the period cursor and the file's identity at 1,440 px, and the identity is
 * what a screenshot of this page is for: a control wide enough to wrap the
 * strip would push the panes down and make the default layout a different
 * layout, which is the one thing this control may not do. The letters are the
 * keyboard's own, so the control also teaches the shortcut.
 *
 * It sits after the identity for the same reason. If anything on a narrow
 * window has to wrap, it is this, and everything a reader came to the strip for
 * stays on the line it is on today.
 *
 * Which layout is current is derived from where the panes stand and is never
 * stored: a reader who picks `table` and then opens the cone is no longer in
 * `table`, and a control that went on claiming otherwise would be naming a
 * state the page is not in.
 */

import type { JSX } from "react";

import { LAYOUT_NAMES, LAYOUTS, layoutOf } from "../state/layout";
import type { LayoutName, PaneState } from "../state/layout";

/** The layout control. */
export function Layouts({
  panes,
  choose,
}: {
  panes: PaneState;
  choose: (layout: LayoutName) => void;
}): JSX.Element {
  const current = layoutOf(panes);
  return (
    <div className="layouts" role="group" aria-label="layout" data-testid="layouts">
      {LAYOUT_NAMES.map((name) => {
        const layout = LAYOUTS[name];
        const on = current === name;
        return (
          <button
            key={name}
            type="button"
            className={`layout${on ? " sel" : ""}`}
            data-testid={`layout-${name}`}
            data-layout={name}
            aria-pressed={on}
            aria-label={`${layout.says} layout`}
            title={`${layout.says} — ${layout.key}`}
            onClick={() => {
              choose(name);
            }}
          >
            {layout.key}
          </button>
        );
      })}
    </div>
  );
}
