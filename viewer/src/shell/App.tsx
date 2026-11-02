// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The shell: the one stateful thing on the page.
 *
 * It holds the selection — which column, which period, how far the cone
 * reaches — in one reducer, and every view is a function of that and the
 * index. That is what makes a click in the grid and a click in the cone the
 * same click, and it is why the reducer lives in `state/selection.ts` where it
 * can be read without a browser.
 *
 * The search query is held here too and is deliberately not part of the
 * selection: it says what is drawn, not what is being looked at, and nothing
 * downstream of the grid has any business knowing it. The hovered operand is
 * held here for the same reason and is not part of the selection either: it is
 * a finger pointing at a cell, gone the moment the pointer leaves, and a
 * selection that recorded it would make the page's one piece of state depend on
 * where the mouse happened to be. Which inspector tab is open is the third of
 * these, and it is held here rather than in the drawer for one reason: the
 * holes chip in the header opens the Model tab, so the tab is something two
 * parts of the page agree about.
 *
 * **Where the panes stand is the fourth**, and it is held here for that
 * same reason: the strip's layout control, the keyboard, each pane's own two
 * controls and the proof's footer all move it, so it belongs to none of them.
 * Its reducer is in `state/layout.ts` with the selection's, and for the same
 * reason — what `t` does to this page is a thing to read and test, not a thing
 * to open a browser and try.
 *
 * **The keyboard is one listener, and it is suppressed while somebody is
 * typing**, so a key typed into the search box stays there. `state/keys.ts`
 * decides what a press means, over a
 * description of the event rather than the event, so the whole of that decision
 * can be tested; this only carries it out. The grid's own arrow keys are not
 * touched: nothing here handles an arrow, and a digit that moves focus into the
 * grid hands the arrows straight back to it.
 *
 * **The Source tab's line is the fifth** — which file and which line the
 * drawer's fourth tab is open at. It is held here rather than in the
 * drawer because the control that sets it is in the proof panel, on the other
 * side of the page, and a tab that reached across for it would be two panes
 * sharing a secret instead of one page holding a fact.
 *
 * **Which policy the values are read under is the sixth**, and it is the
 * one piece of state that is not part of the selection. That is deliberate.
 * The selection is where the reader is standing in the model — the column, the
 * period, how far the cone reaches — and moving along the policy axis must
 * leave every bit of it exactly where it was: the graph is the same graph and
 * the reader has not asked a different question about it, they have asked the
 * same question about another model point. Folding it into the selection would
 * have put "which policy" in a reducer whose other members a switch has no
 * business touching.
 *
 * So the index is rebuilt over the new entry and nothing else moves. What that
 * rebuild does *not* do is the part worth checking rather than believing: the
 * cone's layout, its version folding and its window are memoised on
 * `index.artifact` rather than on `index`, so no box is laid out again and
 * none of them moves. The three fingerprints in the drawer are the file's own
 * strings and a switch cannot reach them.
 *
 * **The comparison is the seventh, and it is not state at all.** A page
 * carrying two documents is a page comparing them, and what moved between them
 * is a function of the two files and of which policy is selected — so it is
 * derived here, memoised on exactly those, and handed to the four views that
 * mark a column. Nothing about it is a thing the reader can move, which is why
 * it is not in a reducer: the floor, which *is* something the reader moves,
 * lives in the list that draws it and is not in the link either.
 *
 * **Three of those six travel in the URL, and only those three**: the policy,
 * the column and the period — the position a reader points a colleague at.
 * `reader/position.ts` holds the grammar and the reasoning; what happens here
 * is that the fragment is read once, before anything is built from it, and
 * written back whenever one of those three moves. Neither half touches
 * `localStorage`, and the rule that an expansion is never persisted is
 * untouched: where the panes stand and which tab is open are not in a link,
 * because a link is a reader pointing at one cell rather than their
 * arrangement posted through somebody else's door.
 */

import { memo, useCallback, useEffect, useMemo, useReducer, useState } from "react";
import type { JSX } from "react";

import { compare } from "../reader/compare";
import type { BookMovement } from "../reader/movement";
import { buildIndex } from "../reader/index";
import type { SourceAt } from "../reader/index";
import { axisOf } from "../reader/policies";
import { fragmentFor, landingIn, policyAt, wantedIn } from "../reader/position";
import type { Landing, Wanted } from "../reader/position";
import type { Artifact } from "../reader/types";
import { actionFor, inATextField } from "../state/keys";
import { LAYOUTS, reducePanes } from "../state/layout";
import type { InspectorTab, LayoutName, PaneName } from "../state/layout";
import { openingColumn } from "../reader/results";
import { initialSelection, reduceSelection } from "../state/selection";
import { Cone } from "../views/Cone";
import { Copy } from "../views/Copy";
import { Grid } from "../views/Grid";
import { Inspector } from "../views/Inspector";
import { Proof } from "../views/Proof";
import type { Hovered } from "../views/Proof";
import { Census } from "./Census";
import { Cursor } from "./Cursor";
import { Header } from "./Header";
import { Layouts } from "./Layouts";
import { Panes } from "./Panes";
import { railFigure } from "./rails";
import { remembered } from "./remembered";
import { Refusal } from "./Refusal";
import { matching, Search } from "./Search";

import "./shell.css";

/**
 * How long the address bar is allowed to lag the reader's hand, in ms.
 *
 * The fragment is written on a trailing timer rather than on every change, and
 * the reason is measured rather than tidy: **WebKit refuses a hundred
 * `replaceState` calls in ten seconds** and throws a `SecurityError` on the
 * hundred-and-first. A scrub is one period change per frame, so a reader
 * dragging the period slider across a long projection would spend that budget
 * in a second and a half and then be writing nothing at all. A quarter of a
 * second after the hand stops is both far inside the limit and far inside the
 * time it takes to reach for the copy control.
 */
const SETTLE_MS = 250;

/**
 * The strip's parts a period step does not reach, each behind a memo.
 *
 * Every step of the row cursor is a new selection, so this component draws
 * again on each of the eighty-three frames of a scrub, and everything it
 * draws was drawn again with it: the search box, the identity strip, the
 * census, the copy control and the layout buttons — none of which reads the
 * period, and every one of whose props is held (the index and the comparison
 * in memos, the setters by React, the callbacks below in `useCallback`). The
 * memo is the whole change: what each draws is what it drew. The cursor's own
 * strip is the one part that moves, and it is not wrapped.
 */
const StillSearch = memo(Search);
const StillHeader = memo(Header);
const StillCensus = memo(Census);
const StillCopy = memo(Copy);
const StillLayouts = memo(Layouts);

/**
 * The address bar's text at the moment of a press.
 *
 * One function for the life of the page rather than a new one each render, so
 * the copy control it is handed to can be held behind its memo.
 */
function addressNow(): string {
  return window.location.href;
}

/**
 * Put the keyboard's focus in one pane.
 *
 * A railed pane is focused at its rail, because the rail **is** the pane while
 * it is railed, not hidden, and a page that focused an invisible region instead
 * would have answered "1" by appearing to do nothing. An open pane is focused
 * at whatever inside it already takes focus, which for the grid is the element
 * holding its arrow keys: pressing 1 and then an arrow must move the row
 * cursor, and it would not if the region above the grid had taken the focus.
 *
 * @param pane - The pane to focus.
 */
function focusPane(pane: PaneName): void {
  const rail = document.querySelector(`[data-rail="${pane}"]`);
  if (rail instanceof HTMLElement) {
    rail.focus();
    return;
  }
  const region = document.querySelector(`[data-pane="${pane}"]`);
  if (!(region instanceof HTMLElement)) return;
  const inner = region.querySelector('[tabindex="0"]');
  (inner instanceof HTMLElement ? inner : region).focus();
}

/** The page, over one artifact, or over two of one model at two states. */
export function App({
  artifact,
  earlier,
  notice,
  label,
  earlierLabel,
  movement = null,
}: {
  artifact: Artifact;
  /** The earlier document, where the page is a comparison. */
  earlier?: Artifact | undefined;
  /** The sentence for a second block the page cannot compare, where it carried one. */
  notice?: string | undefined;
  /** The name the command gave the document, where it gave one. */
  label?: string | undefined;
  /** The name it gave the earlier one. */
  earlierLabel?: string | undefined;
  /** How far each line moved over the whole book, where `gspio diff` measured it. */
  movement?: BookMovement | null;
}): JSX.Element {
  // What the link this page was opened from asked for, read once. Everything
  // below is built from it, so it has to be read before the index is.
  const [wanted] = useState<Wanted>(() => wantedIn(window.location.hash));
  // Where on the policy axis the values are read. Not remembered anywhere,
  // for the reason no expansion is — a file you send someone opens the way
  // your page opens, which is on the entry the producer put first. A link is
  // the exception the rule is about: somebody pointed at this entry on purpose.
  const [at, setAt] = useState(() => policyAt(axisOf(artifact), wanted.policy) ?? 0);
  const index = useMemo(() => buildIndex(artifact, at), [artifact, at]);
  // What moved, derived from the two documents and read along the entry the
  // reader is standing on. Undefined on a page carrying one document, which is
  // what every view below branches on: there is no "empty comparison" shape,
  // because a page with nothing to compare must draw no mark, no tab and no
  // second proof rather than empty ones.
  const comparison = useMemo(
    () => (earlier === undefined ? undefined : compare(artifact, earlier, at, movement)),
    [artifact, earlier, at, movement],
  );
  // The link, followed against this file: which node the column named, which
  // period it asked for, and the one line about whatever this file does not
  // carry. Resolved once, against the index the page mounted with, because a
  // link is a statement about how the page opened and not a thing it keeps
  // re-deciding.
  const [landing] = useState<Landing>(() => landingIn(index, wanted));
  // The page opens on the link's column, or on the model's last result rather
  // than on nothing. A lazy initialiser, so this is read off the index once
  // when the page mounts and never again: what the reader does from there is
  // theirs, and a selection that reasserted itself would be the page arguing
  // with them.
  const [selection, dispatch] = useReducer(reduceSelection, landing, (one) => ({
    ...initialSelection,
    nodeId: one.nodeId ?? openingColumn(index),
    period: one.period,
  }));
  // Where the panes start: the rails the reader left behind, and no expansion.
  // Never remembering an expansion is written here as a shape rather than as a
  // rule to remember — there is nowhere for an expansion to have been stored and
  // nothing here to read it from, so a page always opens with every pane it has
  // room for.
  const [panes, movePanes] = useReducer(reducePanes, undefined, () => ({
    railed: remembered().railed,
    expanded: null,
  }));
  const [query, setQuery] = useState("");
  const [hovered, setHovered] = useState<Hovered | null>(null);
  // A comparison opens on its changes, because that is the question the page
  // was opened to ask; every other page opens where it always opened.
  const [tab, setTab] = useState<InspectorTab>(earlier === undefined ? "node" : "changes");
  const [sourceAt, setSourceAt] = useState<SourceAt | null>(null);
  // Held, not recomputed: the grid scrolls itself to a newly selected column,
  // and a column list that was a new array on every scroll would have the page
  // scrolling back every time the reader scrolled away.
  // What the search found, and of that, what the grid can actually draw. A
  // timeline grid draws timelines: a scalar has one value and no row to put it
  // on, so it is findable and selectable but never a column here. Selecting one
  // still drives the proof, the cone and the drawer, which is where a scalar's
  // answer lives now that nothing pins it above the grid.
  const found = useMemo(() => matching(index, query), [index, query]);
  const perPeriod = useMemo(() => new Set(index.perPeriodColumns), [index]);
  const columns = useMemo(() => found.filter((id) => perPeriod.has(id)), [found, perPeriod]);

  /** One layout, which is a set of pane states and, for one of them, a tab. */
  const chooseLayout = useCallback((name: LayoutName) => {
    movePanes({ layout: name });
    const wants = LAYOUTS[name].tab;
    if (wants !== undefined) setTab(wants);
  }, []);

  /**
   * Open the drawer on the Model tab, where the file accounts for itself.
   *
   * The holes chip and the census's "and N more" both land here: each is a
   * count in the strip whose whole account is on that tab.
   */
  const showModel = useCallback(() => {
    setTab("model");
    movePanes({ open: "inspector" });
  }, []);

  /**
   * Open the drawer's Source tab at one line.
   *
   * Three moves and they are one gesture: remember the line, put the drawer on
   * the tab that shows it, and open the drawer where the reader had railed it —
   * because a control that set a tab inside a pane standing as a rail would
   * have done its work somewhere nobody could see it.
   */
  const openSource = useCallback((at: SourceAt) => {
    setSourceAt(at);
    setTab("source");
    movePanes({ open: "inspector" });
  }, []);

  /**
   * Keep the address bar pointed where the reader is standing.
   *
   * `replaceState` and never `pushState`: the back button must not walk back
   * through every cell somebody clicked on their way to this one. A link is a
   * position, not a trail.
   *
   * On a timer, for the reason `SETTLE_MS` states, and cleared on the way out
   * so that each move cancels the write the move before it had scheduled —
   * which is what turns a scrub through eighty-three periods into one write.
   */
  useEffect(() => {
    const fragment = fragmentFor(index, selection.nodeId, selection.period);
    if (fragment === "" || fragment === window.location.hash) return undefined;
    const timer = window.setTimeout(() => {
      try {
        window.history.replaceState(null, "", fragment);
      } catch {
        // A browser that will not let a page rewrite its own address bar is
        // still a browser this page opens in. What is lost is the link, not
        // the reading: the copy control puts whatever the address bar holds on
        // the clipboard, which is then the file and no position.
      }
    }, SETTLE_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [index, selection.nodeId, selection.period]);

  useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      // Typing stays typing. Everything below is one unmodified key, so a page
      // that took them while the search box had focus would be a page a column
      // name could not be typed into.
      if (inATextField(document.activeElement)) return;
      const action = actionFor(event);
      if (action === null) return;
      event.preventDefault();
      if ("focus" in action) {
        focusPane(action.focus);
        return;
      }
      if ("expand" in action) {
        movePanes({ expand: action.expand });
        return;
      }
      if ("restore" in action) {
        movePanes({ restore: true });
        return;
      }
      if ("drawer" in action) {
        movePanes({ toggle: "inspector" });
        return;
      }
      chooseLayout(action.layout);
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [chooseLayout]);

  return (
    <div className="shell">
      <div className="strip">
        <StillSearch index={index} query={query} setQuery={setQuery} dispatch={dispatch} />
        <Cursor index={index} selection={selection} dispatch={dispatch} />
        <StillHeader
          index={index}
          comparison={comparison}
          label={label}
          earlierLabel={earlierLabel}
          note={landing.note}
          choosePolicy={setAt}
          showHoles={showModel}
        />
        {comparison === undefined ? (
          <StillCensus artifact={index.artifact} dispatch={dispatch} showModel={showModel} />
        ) : null}
        {/* Beside the identity rather than in it: the strip's own contents are
            facts the envelope states, and this is a verb. `location.href` read
            at the press, which on a page opened from a disk is the file's path
            with the fragment on the end — exactly what a colleague holding the
            same file needs, and nothing a colleague who does not hold it could
            have used anyway. */}
        <StillCopy
          what={addressNow}
          name="link"
          title="copy a link to this policy, column and period"
          className="copy-link"
          testid="copy-link"
        />
        <StillLayouts panes={panes} choose={chooseLayout} />
      </div>
      {notice === undefined ? null : (
        <div className="notice">
          <Refusal which="artifacts" sentence={notice} />
        </div>
      )}
      <Panes
        panes={panes}
        dispatch={movePanes}
        rail={(pane) => railFigure(index, selection, tab, pane)}
        grid={
          <Grid
            index={index}
            selection={selection}
            dispatch={dispatch}
            columns={columns}
            hovered={hovered}
            comparison={comparison}
          />
        }
        cone={
          <Cone
            index={index}
            selection={selection}
            dispatch={dispatch}
            comparison={comparison}
          />
        }
        proof={
          <Proof
            index={index}
            selection={selection}
            setHovered={setHovered}
            openSource={openSource}
            comparison={comparison}
          />
        }
        inspector={
          <Inspector
            index={index}
            selection={selection}
            dispatch={dispatch}
            tab={tab}
            setTab={setTab}
            sourceAt={sourceAt}
            comparison={comparison}
          />
        }
      />
    </div>
  );
}
