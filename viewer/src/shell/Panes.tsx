// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The four regions, the dividers between them, and what a pane becomes when it
 * is put away.
 *
 * The page's layout: the grid across the top, the cone bottom left, the proof
 * bottom right, the inspector as a drawer down the right. Each of them gains
 * two controls, expand and collapse, and a third state — the rail — and none of
 * the four places moves.
 *
 * **Nothing railed and nothing expanded is today's page, exactly.** That is not
 * a coincidence to be maintained by care; it is the shape of this file. Every
 * region draws itself the way it drew itself before, the controls are an
 * overlay that takes no room in the layout and is not drawn at rest, and the
 * rails and the layouts are branches nothing enters until a reader asks. The
 * four scripted reads assert against that default, and they assert against it
 * unedited.
 *
 * **A rail is not a hidden pane.** A collapsed pane keeps its name, its
 * one live figure and its place on its own edge, and where the pane is
 * admitting something — a file with holes, a file with no values, a trace that
 * disagrees with its sample — the admission travels to the rail in words and in
 * amber. So a collapse can put a pane away and cannot put away what the file
 * owns up to. The figure is asked for by `rail()` only when a rail is actually
 * drawn, which is what keeps the default layout's cost at exactly what it was.
 *
 * **Refused, and said so here rather than in a note somewhere**:
 *
 * - **No `window.open`, and no second window.** The page is one self-contained
 *   file opened from a disk. A popout would mean re-serialising the document
 *   into another document, and the copy would go stale the moment anything
 *   moved — two pages claiming one run is worse than one page with a small
 *   pane.
 * - **Nothing floats and nothing is draggable but the three dividers.** A fixed
 *   geography is what lets one reviewer say "bottom left" to another and be
 *   understood, and what makes a screenshot of this page legible to somebody
 *   who was not there when it was taken.
 * - **No control hides a pane.** The only way to make a pane smaller is to rail
 *   it, and a rail says what it is holding. There is deliberately no path
 *   through this file from any control to a region that is not on the screen.
 *
 * Where the dividers sit and which panes are railed are remembered per browser
 * under one key, and that key is still the only thing this page writes
 * anywhere. Every read and every write is wrapped: a browser with storage
 * turned off, a private window, a quota already full — none of those is a
 * reason a page cannot be opened, so a refusal to remember is caught and the
 * defaults stand. **An expansion is never written**: it is a gesture, it
 * ends at Escape, and a file you send someone opens the way your page opens.
 */

import { useEffect, useRef, useState } from "react";
import type { CSSProperties, JSX, ReactNode } from "react";

import { PANE_LABELS, railed } from "../state/layout";
import type { PaneAction, PaneName, PaneState } from "../state/layout";
import type { RailFigure } from "./rails";
import { DRAWER_MAX, DRAWER_MIN, remember, remembered, within } from "./remembered";
import type { Remembered } from "./remembered";

/** The three things a reader can drag. */
type Divider = "top" | "drawer";

/** The four regions and everything a reader can do to them. */
export function Panes({
  grid,
  cone,
  proof,
  inspector,
  panes,
  dispatch,
  rail,
}: {
  grid: ReactNode;
  cone: ReactNode;
  proof: ReactNode;
  inspector: ReactNode;
  /** Which panes are railed, and which one has the page. */
  panes: PaneState;
  dispatch: (action: PaneAction) => void;
  /**
   * One pane's live figure, asked for only when its rail is being drawn.
   *
   * A function rather than four computed values, because the proof's figure
   * costs a worked example to produce and the default layout draws no rails at
   * all: a page with everything open must pay nothing for a capability it is
   * not using, and the row cursor moves eighty-three times in a scrub.
   */
  rail: (pane: PaneName) => RailFigure;
}): JSX.Element {
  const [sizes, setSizes] = useState<Remembered>(remembered);
  // Two boxes, because two different things are being measured against them.
  // The drawer's width is taken from the right edge of everything; the grid's
  // share and the cone's are shares of what is left once the drawer has had
  // its width, which is the stack and not the whole.
  const area = useRef<HTMLDivElement>(null);
  const stack = useRef<HTMLDivElement>(null);
  const dragging = useRef<Divider | null>(null);

  // The reader's own railed set is what is remembered. It lives in `panes`
  // while the page is open, beside an expansion that is deliberately never
  // written, for the reason this file's note gives.
  const stored = panes.railed;
  useEffect(() => {
    remember({ ...sizes, railed: stored });
  }, [sizes, stored]);

  useEffect(() => {
    function move(event: PointerEvent): void {
      const which = dragging.current;
      const box = area.current?.getBoundingClientRect();
      const inner = stack.current?.getBoundingClientRect();
      if (which === null || box === undefined || inner === undefined) return;
      event.preventDefault();
      setSizes((was) => {
        if (which === "top") {
          return {
            ...was,
            top: within((event.clientY - inner.top) / inner.height, 0.2, 0.9, was.top),
          };
        }
        return {
          ...was,
          drawer: within(box.right - event.clientX, DRAWER_MIN, DRAWER_MAX, was.drawer),
        };
      });
    }
    function stop(): void {
      dragging.current = null;
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
  }, []);

  /** One divider, which does nothing but say where it has been dragged to. */
  function divider(which: Divider, orientation: "horizontal" | "vertical"): JSX.Element {
    return (
      <div
        className={`divider ${orientation}`}
        role="separator"
        aria-orientation={orientation}
        data-divider={which}
        onPointerDown={(event) => {
          dragging.current = which;
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
      />
    );
  }

  /**
   * The two controls, in a pane's top right corner.
   *
   * An overlay and not a bar, for one reason worth stating: a bar would take
   * height from every pane on a page whose default layout is the thing four
   * scripted reads assert against. This takes none — it is out of the flow, and
   * `visibility: hidden` at rest means it is not drawn at all until the pointer
   * is in the pane or a key has put focus there, which is "never in the page at
   * rest" read literally enough to photograph.
   */
  function controls(pane: PaneName): JSX.Element {
    const expanded = panes.expanded === pane;
    const label = PANE_LABELS[pane];
    return (
      <div className="pane-controls" data-controls={pane}>
        <button
          type="button"
          className="pane-control"
          data-testid={`collapse-${pane}`}
          title={`collapse the ${label} to a rail`}
          aria-label={`collapse the ${label} to a rail`}
          onClick={() => {
            dispatch({ collapse: pane });
          }}
        >
          –
        </button>
        <button
          type="button"
          className={`pane-control${expanded ? " on" : ""}`}
          data-testid={`expand-${pane}`}
          title={expanded ? `restore the ${label}` : `expand the ${label} to the page`}
          aria-label={expanded ? `restore the ${label}` : `expand the ${label} to the page`}
          aria-pressed={expanded}
          onClick={() => {
            dispatch(expanded ? { restore: true } : { expand: pane });
          }}
        >
          {expanded ? "⤡" : "⤢"}
        </button>
      </div>
    );
  }

  /** One region: the pane, with its controls over the corner of it. */
  function region(
    pane: PaneName,
    extra: string,
    style: CSSProperties,
    children: ReactNode,
  ): JSX.Element {
    return (
      <div
        className={`region ${extra}`.trimEnd()}
        data-pane={pane}
        // Reachable from 1–4 without being in the tab order, which belongs to
        // the controls a reader tabs through rather than to the regions.
        tabIndex={-1}
        {...(pane === "inspector" ? { "data-region": "inspector" } : {})}
        style={style}
      >
        {controls(pane)}
        {children}
      </div>
    );
  }

  /**
   * One railed pane: its name, its one live figure, and the way back.
   *
   * The name is the pane's label rather than its id — the id stays on the
   * element for the code and the tests to find it by, and is never drawn.
   */
  function railFor(pane: PaneName, orientation: "horizontal" | "vertical"): JSX.Element {
    const figure = rail(pane);
    const label = PANE_LABELS[pane];
    return (
      <button
        type="button"
        className={`rail ${orientation}`}
        data-rail={pane}
        data-testid={`rail-${pane}`}
        title={`open the ${label}`}
        onClick={() => {
          dispatch({ open: pane });
        }}
      >
        <span className="rail-name">{label}</span>
        <span
          className={`rail-figure mono${figure.admits ? " admits" : ""}`}
          data-testid={`rail-figure-${pane}`}
          {...(figure.admits ? { "data-admits": "true" } : {})}
        >
          {figure.says}
        </span>
        <span className="rail-open" aria-hidden="true">
          open ⤢
        </span>
      </button>
    );
  }

  const gridRailed = railed(panes, "grid");
  const coneRailed = railed(panes, "cone");
  const drawerRailed = railed(panes, "inspector");
  // The bottom half is the cone, and the proof rides under it as a strip rather
  // than beside it as a pane. Three panes and not four: a worked example that
  // is four lines and a disclosure does not need a quarter of the window, and
  // the graph — the thing that gets unreadable when it is small — takes what it
  // used to spend.
  const below = !coneRailed;

  return (
    <div className="panes" ref={area} data-expanded={panes.expanded ?? "none"}>
      <div className="stack" ref={stack}>
        {gridRailed
          ? railFor("grid", "horizontal")
          : region(
              "grid",
              "grid-region",
              below ? { flexBasis: `${String(sizes.top * 100)}%` } : { flex: "1 1 auto" },
              grid,
            )}
        {!gridRailed && below ? divider("top", "horizontal") : null}
        {below ? (
          <div className="below">
            {region(
              "cone",
              "",
              { flex: "1 1 auto" },
              <>
                {cone}
                <div className="proof-strip">{proof}</div>
              </>,
            )}
          </div>
        ) : null}
        {coneRailed ? railFor("cone", "horizontal") : null}
      </div>
      {drawerRailed ? (
        railFor("inspector", "vertical")
      ) : (
        <>
          {divider("drawer", "vertical")}
          {region("inspector", "drawer", { flexBasis: `${String(sizes.drawer)}px` }, inspector)}
        </>
      )}
    </div>
  );
}
