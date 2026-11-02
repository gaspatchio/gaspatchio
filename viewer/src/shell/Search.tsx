// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The first thing the page shows, and the first thing it focuses.
 *
 * A model of any size has more columns than a screen has room for, and the
 * page's answer is search rather than hiding: hiding is a claim about
 * relevance the file does not make, so every column stays and typing narrows
 * what is drawn until you find the one you meant.
 *
 * Enter selects the first match and clears the box. Clearing is not tidiness:
 * a selected column's operand outlines fall on the columns it reads, and a
 * filter still narrowing the grid would have hidden exactly those. Search is
 * how you reach a column; the grid is where you read it.
 */

import { useEffect, useRef, useState } from "react";
import type { JSX } from "react";

import type { Index } from "../reader/index";
import { endsOf } from "../reader/results";
import type { SelectionAction } from "../state/selection";

/**
 * The columns a query narrows to, in the file's order.
 *
 * Every column in the final schema, whatever its shape. A scalar used to be
 * unreachable from here — the box looked through the per-period columns alone,
 * and the only way to select `sum_assured` or `pv_net_cf` was to find it in the
 * strip of pinned scalars above the grid. That strip is gone, and this is the
 * door that replaced it: a column is found by name, and whether it holds one
 * value or one per period decides what the grid can draw, not whether the
 * reader can reach it.
 *
 * Matched on the column's name rather than the node's id, because the name is
 * what an actuary typed into the model and the id is the name with a version
 * on it. A blank query narrows to nothing, which is to say to everything.
 *
 * @param index - The one index.
 * @param query - What has been typed.
 * @returns The matching column ids, or all of them when nothing is typed.
 */
export function matching(index: Index, query: string): string[] {
  const needle = query.trim().toLowerCase();
  if (needle === "") return index.finalColumns;
  return index.finalColumns.filter((id) =>
    (index.nodes.get(id)?.column ?? id).toLowerCase().includes(needle),
  );
}

/** The search box. */
export function Search({
  index,
  query,
  setQuery,
  dispatch,
}: {
  index: Index;
  query: string;
  setQuery: (q: string) => void;
  dispatch: (a: SelectionAction) => void;
}): JSX.Element {
  const box = useRef<HTMLInputElement>(null);
  const [asking, setAsking] = useState(false);

  // The box takes focus on load so a reader can type straight away. That focus
  // is the page's and not the reader's, so it must not open the list: the page
  // has already opened on the model's last result, and a list over the grid
  // that nobody asked for is the empty prompt's problem in another form.
  const touched = useRef(false);
  useEffect(() => {
    // Has anybody touched this page yet? The focus below is the page's own and
    // must not open the list; every focus after a reader has pressed or
    // clicked anything is theirs and does. Listening in the capture phase is
    // what makes it exact: the click that focuses the box marks this first, in
    // the same event, so there is no window in which the answer depends on
    // timing. A guard on a timer got this right on a quiet machine and wrong on
    // a loaded one, which is the worst way to be wrong.
    const mark = (): void => {
      touched.current = true;
    };
    window.addEventListener("pointerdown", mark, { capture: true });
    window.addEventListener("keydown", mark, { capture: true });
    box.current?.focus();
    return () => {
      window.removeEventListener("pointerdown", mark, { capture: true });
      window.removeEventListener("keydown", mark, { capture: true });
    };
  }, []);

  const narrowed = query.trim() !== "";
  const found = matching(index, query);

  // Where a reader who does not know this model starts. The box is focused on
  // load, so an empty box is somebody asking what there is to look at, and
  // these are the columns the model computed and then stopped at. Headed with
  // what was measured rather than with "results": `projection_date` is one of
  // them on every model here and is a label, not an answer, and nothing in the
  // file tells the two apart.
  const ends = endsOf(index);
  const offering = asking && !narrowed && ends.length > 0;

  return (
    <div className="search">
      <input
        ref={box}
        type="search"
        data-testid="search"
        placeholder="Search columns"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => {
          if (!touched.current) return;
          setAsking(true);
        }}
        // Clicking a box that already has the page's own focus fires no focus
        // event, and clicking it is the clearest way a reader asks what there
        // is to look at.
        onClick={() => {
          setAsking(true);
        }}
        onBlur={() => {
          // After the click, so a name in the list is still there to be hit.
          window.setTimeout(() => {
            setAsking(false);
          }, 120);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") setAsking(false);
          if (event.key !== "Enter" || !narrowed) return;
          event.preventDefault();
          const first = found[0];
          if (first === undefined) return;
          dispatch({ select: first });
          setQuery("");
        }}
      />
      {narrowed ? (
        <span className="found" data-testid="search-found">
          {found.length} of {index.finalColumns.length}
        </span>
      ) : null}
      {offering ? (
        <div className="ends" data-testid="search-ends">
          <span className="ends-head">nothing else reads these</span>
          {ends.map((id) => (
            <button
              key={id}
              type="button"
              className="ends-name mono"
              data-end={index.nodes.get(id)?.column ?? id}
              onClick={() => {
                dispatch({ select: id });
                setQuery("");
                setAsking(false);
              }}
            >
              {index.nodes.get(id)?.column ?? id}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
