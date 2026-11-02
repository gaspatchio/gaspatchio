// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Where in the model this window is.
 *
 * The whole graph at its one dagre layout, every node a mark, and the window
 * drawn over it as a rectangle: the overview. It is the answer
 * to the question the cone cannot answer on its own: a reader looking at six
 * boxes has no way of knowing whether they are most of the model or a corner
 * of it, and 128 marks with a rectangle around eleven of them says which
 * immediately.
 *
 * This is drawn from `layoutAll` rather than from React Flow's own minimap,
 * and the reason is arithmetic. The cone packs the window onto the layout's
 * rank order so the boxes are readable (see `Cone.tsx`), so the canvas's
 * coordinates are the window's and not the graph's; a minimap over the canvas
 * could only ever draw the window it is meant to locate. The layout is the one
 * coordinate system the whole graph is in, so the overview is drawn in it.
 *
 * Clicking a mark selects that node, which is how the overview moves the
 * window.
 *
 * **Memoised, because a period step does not move it.** Where the window is in
 * the model is a function of the graph and of which nodes are in the window,
 * and the row cursor is neither. Before the memo a scrub through eighty-three
 * periods rebuilt all 128 marks and their titles on every frame to draw the
 * same overview; every one of the five props below is the same object from one
 * step to the next, so now it draws none of them.
 */

import { memo, useMemo } from "react";
import type { JSX } from "react";

import type { Placement } from "../layout/dagre";
import type { Index } from "../reader/index";
import type { SelectionAction } from "../state/selection";

/** How big the overview is drawn, in pixels on the page. */
const BOX = { w: 180, h: 110 };

/** A rectangle in the layout's own coordinates. */
interface Extent {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * The box containing every one of these nodes.
 *
 * @param ids - The nodes to contain.
 * @param placed - The whole layout.
 * @param size - The node body's size, so a node's box is its whole box.
 * @returns The extent, or null where none of the ids is placed.
 */
function extentOf(
  ids: Iterable<string>,
  placed: Map<string, Placement>,
  size: { w: number; h: number },
): Extent | null {
  let left = Infinity;
  let top = Infinity;
  let right = -Infinity;
  let bottom = -Infinity;
  for (const id of ids) {
    const at = placed.get(id);
    if (at === undefined) continue;
    left = Math.min(left, at.x);
    top = Math.min(top, at.y);
    right = Math.max(right, at.x + size.w);
    bottom = Math.max(bottom, at.y + size.h);
  }
  if (!Number.isFinite(left)) return null;
  return { x: left, y: top, w: right - left, h: bottom - top };
}

/** The overview. */
function Overview({
  index,
  placed,
  size,
  window,
  dispatch,
}: {
  index: Index;
  placed: Map<string, Placement>;
  size: { w: number; h: number };
  /** The window's nodes, whose extent is the rectangle. */
  window: string[];
  dispatch: (a: SelectionAction) => void;
}): JSX.Element | null {
  const whole = useMemo(() => extentOf(index.order, placed, size), [index, placed, size]);
  const here = extentOf(window, placed, size);
  if (whole === null) return null;

  // A little air, so a node on the edge of the layout is a mark rather than a
  // line down the side of the box.
  const pad = Math.max(whole.w, whole.h) * 0.02;
  const viewBox = `${whole.x - pad} ${whole.y - pad} ${whole.w + pad * 2} ${whole.h + pad * 2}`;
  // One stroke on the page, whatever the layout's scale is.
  const stroke = (Math.max(whole.w, whole.h) / Math.max(BOX.w, BOX.h)) * 1.5;

  return (
    <svg
      className="minimap"
      data-testid="minimap"
      width={BOX.w}
      height={BOX.h}
      viewBox={viewBox}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="the whole model, with this window marked"
    >
      {index.order.map((id) => {
        const at = placed.get(id);
        if (at === undefined) return null;
        return (
          <rect
            key={id}
            className="minimap-node"
            data-node={id}
            x={at.x}
            y={at.y}
            width={size.w}
            height={size.h}
            onClick={() => dispatch({ select: id })}
          >
            <title>{id}</title>
          </rect>
        );
      })}
      {here === null ? null : (
        <rect
          className="minimap-window"
          data-testid="minimap-window"
          x={here.x}
          y={here.y}
          width={here.w}
          height={here.h}
          strokeWidth={stroke}
        />
      )}
    </svg>
  );
}

export const Minimap = memo(Overview);
