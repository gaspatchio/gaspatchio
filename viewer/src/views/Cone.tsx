// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What fed this, and what does this feed.
 *
 * The cone: the selected node with its ancestors and its descendants
 * to a depth the reader sets, and never the whole graph, which at the zoom it
 * takes to fit a real model on a screen is a grey field. The window is
 * `coneWindow`'s, the controls move it one step at a time, and the count
 * beside them is the window's own size, so what is on the canvas is always
 * something the reader asked for and can see the size of.
 *
 * **Where the boxes go.** `layoutAll` lays the whole graph out once and that
 * layout decides two things: which rank a node is in, and where it sits in
 * that rank. The window is then packed onto those ranks — the empty ranks and
 * the empty rows between the window's nodes taken out — rather than drawn at
 * the layout's own coordinates. Measured on the level-4 export: a twenty-one
 * node window around `net_cf@1` spans 7,420 x 4,323 px at the layout's
 * coordinates, because its nodes are rows 3, 17 and 41 of a rank fifty-eight
 * deep; fitting that into the cone pane needs a zoom of about 0.06 and the
 * pinned floor is 0.3. Packed, the same window is 2,920 x 486 and readable.
 * The order is the layout's, so widening inserts nodes rather than reshuffling
 * the ones already on the screen.
 *
 * **Versions.** A definition the model wrote over is folded into the one that
 * replaced it and the surviving box wears a count. Folding is drawing, not
 * reading: the window still holds both, `cone-count` still says so, and the
 * badge opens the older definition with its own edges. The badge appears only
 * where the file carries `retained: true`.
 *
 * **The cursor is not in the drawing.** The node array below is built without
 * `selection.period`; each box subscribes to the row cursor through
 * `state/cursor.ts` and writes its own value line. So stepping the cursor hands
 * React Flow the array it is already holding and re-renders one line per box
 * rather than every box. `state/cursor.ts` carries what this cost before.
 *
 * **Edges.** Solid where the file says DIRECT, dotted where it says INDIRECT,
 * and where the narrowing facet states an `offset` the reading node also wears
 * the loop, labelled with the distance the facet states. A read whose facet
 * states a window — the `periods` an aggregation read or the `position` a
 * literal `list.get` took (§9) — wears the same loop, labelled with the window
 * (`first…t`, `t…last`, `[0]`), one label per window the read states. Every
 * label is read off the facet and never off the trace's expression text.
 *
 * **Too large to draw.** Above `MAX_LAYOUT_NODES` the whole-graph layout is not
 * attempted, and `layout/dagre.ts` carries the number and the
 * measurement it came from. The pane still opens: the window is laid out on its
 * own, which is the same dagre over the nodes actually being drawn, and the
 * overview is replaced by the sentence saying what was skipped and why. The one
 * thing lost is the answer to "where in the model is this", and the page says
 * so rather than drawing an overview of a layout it never ran.
 */

import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { JSX, RefObject } from "react";

import { ReactFlow, useReactFlow } from "@xyflow/react";
import type { Edge as FlowEdge, EdgeProps, EdgeTypes, NodeMouseHandler, NodeTypes } from "@xyflow/react";

import {
  layoutAll,
  layoutOf,
  MAX_LAYOUT_NODES,
  NODE_SEPARATION,
  NODE_SIZE,
  RANK_SEPARATION,
} from "../layout/dagre";
import type { Placement } from "../layout/dagre";
import { isFold } from "../reader/fold";
import { formatFormula, isIntegerDtype, settingsInWords } from "../reader/format";
import { windowLabel } from "../reader/periods";
import type { Comparison } from "../reader/compare";
import type { Index } from "../reader/index";
import { Refusal, tooLargeToLayOut } from "../shell/Refusal";
import { publishCursorPeriod } from "../state/cursor";
import type { Selection, SelectionAction } from "../state/selection";
import { descendantsOf } from "../reader/impact";
import { coneWindow, windowOf } from "../reader/window";
import { markSaid } from "./Changes";
import { ConeNode } from "./ConeNode";
import type { ConeFlowNode } from "./ConeNode";
import { Minimap } from "./Minimap";

import "@xyflow/react/dist/base.css";
import "./Cone.css";

/**
 * The distance a read looked, written the way a reviewer writes it.
 *
 * The minus is U+2212 and not a hyphen: this is a number on a diagram, not a
 * word with a dash in it, and the two are different characters.
 *
 * @param offset - The facet's `offset`, in periods.
 * @returns `t−1`, `t+1`, and so on.
 */
function offsetLabel(offset: number): string {
  return offset < 0 ? `t−${Math.abs(offset)}` : `t+${offset}`;
}

/** One read that looked at another period, drawn on the node that made it. */
function OffsetEdge({ sourceX, sourceY, targetX, targetY, data }: EdgeProps): JSX.Element {
  const label = typeof data?.["label"] === "string" ? data["label"] : "";
  const over = Math.min(sourceY, targetY) - NODE_SIZE.h * 0.7;
  const path =
    `M${sourceX},${sourceY} ` +
    `C${sourceX + 48},${over} ${targetX - 48},${over} ${targetX},${targetY}`;
  return (
    <>
      <path className="edge-offset" data-label={label} d={path} fill="none" />
      <text
        className="edge-offset-label mono"
        x={(sourceX + targetX) / 2}
        y={over + 10}
        textAnchor="middle"
      >
        {label}
      </text>
    </>
  );
}

const NODE_TYPES: NodeTypes = { cone: ConeNode };
const EDGE_TYPES: EdgeTypes = { offset: OffsetEdge };

/** Which definition of a column survived, and which the model wrote over. */
interface Versions {
  /** A superseded node's id → the definition that replaced it. */
  survivorOf: Map<string, string>;
}

/**
 * Read the file's `retained` flags into a map from superseded to surviving.
 *
 * The surviving definition is the last one the file carries for that column
 * that is not itself marked retained — last, because the file's order is the
 * order the model wrote them in. A column whose nodes are all retained has no
 * survivor and nothing is folded: the page would rather draw one box too many
 * than fold a definition into one the file does not say replaced it.
 *
 * @param index - The one index.
 * @returns The map, empty where the export carries no retained node.
 */
function versionsIn(index: Index): Versions {
  const byColumn = new Map<string, string[]>();
  for (const id of index.order) {
    const column = index.nodes.get(id)?.column;
    if (typeof column !== "string") continue;
    const seen = byColumn.get(column);
    if (seen) seen.push(id);
    else byColumn.set(column, [id]);
  }

  const survivorOf = new Map<string, string>();
  for (const ids of byColumn.values()) {
    if (ids.length < 2) continue;
    const superseded = ids.filter((id) => index.nodes.get(id)?.retained === true);
    if (superseded.length === 0) continue;
    const surviving = ids.filter((id) => index.nodes.get(id)?.retained !== true).pop();
    if (surviving === undefined) continue;
    for (const id of superseded) survivorOf.set(id, surviving);
  }
  return { survivorOf };
}

/**
 * Pack the window onto the layout's rank order.
 *
 * Ranks that hold none of the window's nodes are taken out, and so are the
 * rows between the ones that do; what is left is the layout's own order at the
 * body's own spacing. See this file's header for why.
 *
 * @param ids - The window's nodes.
 * @param placed - The whole graph's layout.
 * @param size - The node body's size.
 * @returns Where each of `ids` is drawn.
 */
function packed(
  ids: string[],
  placed: Map<string, Placement>,
  size: { w: number; h: number },
): Map<string, Placement> {
  const ranks = new Map<number, string[]>();
  for (const id of ids) {
    const at = placed.get(id)?.x ?? 0;
    const rank = ranks.get(at);
    if (rank) rank.push(id);
    else ranks.set(at, [id]);
  }

  const columns = [...ranks.keys()].sort((a, b) => a - b);
  const tallest = Math.max(...[...ranks.values()].map((rank) => rank.length));
  const step = size.h + NODE_SEPARATION;

  const out = new Map<string, Placement>();
  columns.forEach((at, column) => {
    const rank = (ranks.get(at) ?? []).sort(
      (a, b) => (placed.get(a)?.y ?? 0) - (placed.get(b)?.y ?? 0),
    );
    // Each rank sits in the middle of the tallest one, so the window reads as
    // a cone rather than as a set of columns hanging from a line.
    const top = ((tallest - rank.length) * step) / 2;
    rank.forEach((id, row) => {
      out.set(id, { x: column * (size.w + RANK_SEPARATION), y: top + row * step });
    });
  });
  return out;
}

/**
 * How far a fit may scale the drawing up to fill the pane.
 *
 * The cone used to stop at 1, which meant a pane twice the size drew the same
 * boxes with twice the empty space around them — expanding it bought margin
 * rather than legibility. A fit that may enlarge turns the expansion into what
 * a reader expects from it: a few nodes in a big pane are drawn big, and the
 * same nodes railed back into a small one shrink to fit it again.
 *
 * Short of the 2 the reader can reach by hand, deliberately. The last of the
 * zoom belongs to them — a two-node cone taken automatically to the ceiling is
 * a page shouting a number nobody asked to have shouted.
 */
const FIT_MAX_ZOOM = 1.75;

/**
 * Put the window in view whenever it changes, and whenever the pane resizes.
 *
 * Two things move the frame and only one of them is the graph. A reader
 * expanding the cone, railing a neighbour or dragging a divider changes how
 * much canvas there is without changing a single node, so the node set cannot
 * be the only thing this watches: it was, and the drawing stayed the size it
 * had been in the smaller pane, in the corner of the larger one.
 *
 * Every fit is coalesced into one animation frame. A divider drag resizes on
 * every frame it moves, and a fit is a transform on the canvas rather than a
 * re-layout, so following the drag costs the pane's own frame and not a second
 * one.
 */
function Frame({
  center,
  ids,
  canvas,
}: {
  /** The focused node. A new one is a new subject and reframes at once. */
  center: string;
  ids: string[];
  /** The element whose size decides how much room the drawing has. */
  canvas: RefObject<HTMLDivElement | null>;
}): null {
  const flow = useReactFlow();
  const key = ids.join(" ");
  // What the frame was last computed for. A set that grew under the same centre
  // is the reader opening the graph up, and the view glides to take the new
  // boxes in; a different centre is a different question, and jumps.
  const subject = useRef<string | null>(null);
  useEffect(() => {
    const moved = subject.current !== center;
    subject.current = center;
    let frame = 0;
    // After the commit, so React Flow has the new nodes in its own store.
    const fit = (): void => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        // A pane mid-layout has no height to fit into, and a fit computed
        // against it leaves a transform that puts most of the drawing outside
        // the viewport — where `onlyRenderVisibleElements` then culls it, nodes
        // and the offset loops between them alike. Skipping is safe because the
        // observer fires again the moment the pane has a size.
        const box = canvas.current?.getBoundingClientRect();
        if (box === undefined || box.width < 1 || box.height < 1) return;
        void flow.fitView({
          nodes: key.split(" ").map((id) => ({ id })),
          // Enough room above the top rank for an offset edge's loop, which
          // is drawn 0.7 of a node body higher than the nodes it joins and is
          // therefore outside the bounds a fit computed from nodes alone.
          // At the old ceiling of 1 the slack was incidental; scaling up to
          // fill a pane took it away and culled the loop with it.
          padding: 0.14,
          maxZoom: FIT_MAX_ZOOM,
          duration: moved ? 0 : 220,
        });
      });
    };

    fit();
    const element = canvas.current;
    if (element === null) {
      return () => {
        cancelAnimationFrame(frame);
      };
    }
    const observer = new ResizeObserver(fit);
    observer.observe(element);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [flow, key, center, canvas]);
  return null;
}

/**
 * The canvas: React Flow over the drawing, and the frame that fits it.
 *
 * Its own component, behind a memo, so that a period step does not reach it.
 * The pane around it draws again on every step, because its selection is a new
 * object each time; and React Flow drew again with it — its providers, its
 * store updater, its wrapper and each part of its tree — to be handed the same
 * nodes, the same edges and the same handlers it already had. Everything it is
 * given here is held (the drawing and the click handler in memos, the canvas
 * in a ref, the centre a string), so a step reaches the boxes through the
 * cursor they subscribe to and nothing else. What the canvas draws is what it
 * drew.
 */
const Canvas = memo(function Canvas({
  drawing,
  center,
  canvas,
  onNodeClick,
}: {
  drawing: { nodes: ConeFlowNode[]; edges: FlowEdge[]; drawn: string[] };
  center: string;
  canvas: RefObject<HTMLDivElement | null>;
  onNodeClick: NodeMouseHandler<ConeFlowNode>;
}): JSX.Element {
  return (
    <ReactFlow
      nodes={drawing.nodes}
      edges={drawing.edges}
      nodeTypes={NODE_TYPES}
      edgeTypes={EDGE_TYPES}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable
      onlyRenderVisibleElements
      minZoom={0.3}
      maxZoom={2}
      onNodeClick={onNodeClick}
    >
      <Frame center={center} ids={drawing.drawn} canvas={canvas} />
    </ReactFlow>
  );
});

/** The cone pane: the controls, the canvas, the overview. */
export function Cone({
  index,
  selection,
  dispatch,
  comparison,
}: {
  index: Index;
  selection: Selection;
  dispatch: (a: SelectionAction) => void;
  /** The two documents and what moved between them, on a comparison page. */
  comparison?: Comparison | undefined;
}): JSX.Element {
  // Empty above `MAX_LAYOUT_NODES`: the whole-graph layout is not attempted,
  // and the window gets one of its own below.
  // The element the drawing has to fit into. Watched by `Frame`, so a pane
  // that grows or shrinks refits rather than keeping the zoom it had.
  const canvas = useRef<HTMLDivElement>(null);
  const tooLarge = index.order.length > MAX_LAYOUT_NODES;
  // Published rather than passed: the boxes subscribe to it, and the node array
  // below is built without it so that stepping the cursor hands React Flow the
  // array it already has. A layout effect rather than a plain one because the
  // value line must be right in the frame the cursor moved in, not the one
  // after it; `state/cursor.ts` carries the measurement this is the answer to.
  useLayoutEffect(() => {
    publishCursorPeriod(selection.period);
  }, [selection.period]);
  // Both of these are functions of the **graph**, and the graph is the same
  // whichever policy the reader is standing on — which is why the dependency
  // is `index.artifact` and not `index`. It is not a shortcut: the drawing
  // below is a function of the index because the value line on each box is,
  // and separating the two is what makes switching policy re-read values and
  // move nothing. Dagre does not run again, so no box moves under the pointer
  // and the cone the reader had arranged is the cone they still have.
  const placed = useMemo(() => layoutAll(index, NODE_SIZE), [index.artifact]);
  const versions = useMemo(() => versionsIn(index), [index.artifact]);
  const [revealed, setRevealed] = useState<ReadonlySet<string>>(new Set());

  const reveal = useCallback((id: string) => {
    setRevealed((was) => {
      const next = new Set(was);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const nodeId = selection.nodeId;
  // Two windows, and which one is drawn is the whole of the interaction. A
  // column just chosen from the grid opens on the seed: everything within the
  // stepper's depths of it. From then on, a click inside the cone grows a set,
  // and the cone draws that set — so the boxes already on the screen stay where
  // they are and the drawing gains the ones the reader asked for.
  const explored = selection.revealed;
  const window = useMemo(
    () =>
      nodeId === null
        ? null
        : explored === null
          ? coneWindow(index, nodeId, selection.up, selection.down)
          : windowOf(index, nodeId, explored),
    // The artifact again, for the reason the layout gives: which nodes are in
    // the window is a walk over the edges, and no policy changes an edge.
    [index.artifact, nodeId, explored, selection.up, selection.down],
  );

  /**
   * A click on a box: move the focus, and open one step where it is closed.
   *
   * The rule is the reader's own — clicking a box whose neighbours are already
   * drawn only moves the focus, and clicking one at the edge of the drawing
   * opens the next step out of it. One step and not two: reaching the node
   * after that is another click, which is what makes this exploring rather than
   * re-centring. Nothing already drawn is taken away, so the boxes do not move
   * under the pointer that is clicking them.
   */
  const exploreFrom = useCallback(
    (id: string) => {
      dispatch({ focus: id });
      if (window === null) return;
      const shown = new Set(window.nodes);
      const opening = [...(index.readsOf.get(id) ?? []), ...(index.readBy.get(id) ?? [])].filter(
        (neighbour) => !shown.has(neighbour),
      );
      // Pinned even when nothing opens, and that is the load-bearing line. Until
      // a set is pinned the cone is still the seed window — a function of the
      // centre — so moving the focus to a box whose neighbours are all drawn
      // would quietly recompute the whole drawing around it, which is the
      // re-centring this replaces. Clicking inside the cone fixes what is on
      // the screen and adds to it; it never recomputes it.
      dispatch({ revealed: [...shown, ...opening] });
    },
    [dispatch, index, window],
  );

  // Held, not written inline on the canvas. React Flow hands this to the
  // wrapper it draws around every box, so a new function on each render
  // re-rendered all forty-six of those wrappers in the window `perf/measure.mjs`
  // scrubs, on every period step, to arrive at the boxes it already had —
  // 0.7 ms of script a frame of the scrub, 0.8 on the comparison page. Nothing
  // it closes over moves with the cursor, so a period step now leaves the
  // canvas to the value lines the boxes redraw for themselves.
  const onNodeClick = useCallback<NodeMouseHandler<ConeFlowNode>>(
    (_event, node) => {
      exploreFrom(node.id);
    },
    [exploreFrom],
  );

  const drawing = useMemo(() => {
    if (window === null) return null;
    const inWindow = new Set(window.nodes);

    // A superseded definition is folded into its survivor unless the badge on
    // that survivor has been opened.
    const foldedInto = new Map<string, string>();
    const folded = new Map<string, number>();
    for (const id of window.nodes) {
      const survivor = versions.survivorOf.get(id);
      if (survivor === undefined || !inWindow.has(survivor)) continue;
      folded.set(survivor, (folded.get(survivor) ?? 0) + 1);
      if (!revealed.has(survivor)) foldedInto.set(id, survivor);
    }
    const drawnAs = (id: string): string => foldedInto.get(id) ?? id;
    const drawn = window.nodes.filter((id) => !foldedInto.has(id));
    // The window's rank order: the whole graph's where there is one, and the
    // window's own where the graph was too large to lay out. Either way the
    // packing is the same and so is what the reader sees on the canvas.
    const ranked = tooLarge ? layoutOf(window.nodes, window.edges, NODE_SIZE) : placed;
    const at = packed(drawn, ranked, NODE_SIZE);

    // Whether the reader is standing on a fold of the book rather than on a
    // policy. Read once for the window: it is a fact about the selected entry
    // and not about any box.
    const foldedEntry = isFold(index.policy);

    const nodes: ConeFlowNode[] = drawn.map((id) => {
      const node = index.nodes.get(id);
      // The selected policy's own array, by reference: the box writes the
      // period's element itself, off the cursor it subscribes to, so nothing
      // here is a function of where the cursor stands and this array survives
      // a scrub. It is a function of which policy is selected, which is why
      // this memo takes the index and the three above it take the artifact.
      const sample = index.sampleOf(id);
      const change = comparison?.byNode.get(id);
      // The kind is a class as well as a chip, so a hole is dashed amber from
      // the stylesheet rather than from a branch in the body.
      const classes = ["cone-node", node === undefined ? "unplaced" : node.kind];
      if (versions.survivorOf.has(id)) classes.push("retained");
      return {
        id,
        type: "cone",
        position: at.get(id) ?? { x: 0, y: 0 },
        width: NODE_SIZE.w,
        height: NODE_SIZE.h,
        draggable: false,
        connectable: false,
        className: classes.join(" "),
        data: {
          column: node?.column ?? id,
          formula: formatFormula(node?.formula ?? null),
          sample,
          unfolded: foldedEntry && sample === undefined,
          integer: node !== undefined && isIntegerDtype(node.dtype),
          tier: node?.tier ?? null,
          settings: settingsInWords(node?.settings),
          kind: node?.kind ?? "computed",
          mark: change?.mark,
          said: change === undefined || comparison === undefined ? undefined : markSaid(change, comparison),
          versions: (folded.get(id) ?? 0) + 1,
          revealed: revealed.has(id),
          states: node?.states,
          // Every step, because every step is a movement the file carries an
          // amount for. Undefined where the compilation states no summary,
          // which is a producer that could not write one rather than a chain
          // of no steps.
          steps: node?.increments?.length,
          center: id === window.center,
          onReveal: reveal,
        },
      };
    });

    const edges: FlowEdge[] = [];
    const already = new Set<string>();
    for (const edge of window.edges) {
      const source = drawnAs(edge.source);
      const target = drawnAs(edge.target);
      const offset = index.offsetOf(edge.target, edge.source);
      const windows = index
        .windowsOf(edge.target, edge.source)
        .map(windowLabel)
        .filter((label): label is string => label !== null);
      const looped =
        offset !== undefined
          ? [offsetLabel(offset), ...windows]
          : windows.length > 0
            ? windows
            : null;
      if (looped !== null) {
        const id = `offset:${edge.target}:${edge.source}`;
        if (!already.has(id)) {
          already.add(id);
          edges.push({
            id,
            source: target,
            target,
            type: "offset",
            data: { label: looped.join(", ") },
          });
        }
      }
      // An edge whose two ends fold into one node is the supersession itself,
      // and the badge says that better than a line from a box to itself.
      if (source === target) continue;
      const id = `${source}->${target}`;
      if (already.has(id)) continue;
      already.add(id);
      const opened = versions.survivorOf.has(edge.source) || versions.survivorOf.has(edge.target);
      edges.push({
        id,
        source,
        target,
        className: [
          edge.relationship === "INDIRECT" ? "edge-indirect" : "edge-direct",
          opened ? "edge-retained" : "",
        ]
          .join(" ")
          .trim(),
      });
    }

    return { nodes, edges, drawn };
    // `selection.period` is deliberately not here. See the note beside the
    // layout effect above: the boxes read the cursor, so this array is the same
    // array from one period to the next and React Flow is handed no work.
  }, [index, window, placed, tooLarge, revealed, versions, reveal, comparison]);

  const step = (which: "up" | "down", by: number): void => {
    dispatch(which === "up" ? { up: selection.up + by } : { down: selection.down + by });
  };

  return (
    <div className="cone" data-testid="cone">
      <div className="cone-bar">
        <span className="reach">
          <button
            type="button"
            data-testid="narrow-up"
            title="one step fewer above"
            onClick={() => step("up", -1)}
          >
            −
          </button>
          <b className="mono">↑{selection.up}</b>
          <button
            type="button"
            data-testid="widen-up"
            title="one step more above"
            onClick={() => step("up", 1)}
          >
            +
          </button>
        </span>
        <span className="reach">
          <button
            type="button"
            data-testid="narrow-down"
            title="one step fewer below"
            onClick={() => step("down", -1)}
          >
            −
          </button>
          <b className="mono">↓{selection.down}</b>
          <button
            type="button"
            data-testid="widen-down"
            title="one step more below"
            onClick={() => step("down", 1)}
          >
            +
          </button>
        </span>
        <button
          type="button"
          data-testid="direction"
          title="swap what is drawn above for what is drawn below"
          onClick={() => {
            // Two moves that read as one. Both are computed from this render's
            // selection, so the second is not the first's answer.
            dispatch({ up: selection.down });
            dispatch({ down: selection.up });
          }}
        >
          ⇅
        </button>
        <button
          type="button"
          className="step"
          data-testid="cone-downstream"
          title="open everything this feeds"
          disabled={nodeId === null}
          onClick={() => {
            if (nodeId === null || window === null) return;
            // The reviewer's question in one move: everything a change here
            // would travel to, opened into the drawing rather than walked to a
            // step at a time. It goes through the same revealed set a click
            // builds, so what this opens and what a hundred clicks would open
            // are the same drawing.
            dispatch({ revealed: [...window.nodes, ...descendantsOf(index, nodeId)] });
          }}
        >
          ↘all
        </button>
        {window === null ? null : (
          <span className="count">
            <b className="mono" data-testid="cone-count">
              {window.nodes.length}
            </b>{" "}
            of {index.order.length}
          </span>
        )}
      </div>
      <div className="cone-canvas" ref={canvas}>
        {drawing === null || window === null ? (
          <p className="cone-nothing">Search for a column to see what feeds it.</p>
        ) : (
          <Canvas
            drawing={drawing}
            center={window.center}
            canvas={canvas}
            onNodeClick={onNodeClick}
          />
        )}
        {window === null ? null : tooLarge ? (
          <div className="minimap-instead">
            <Refusal
              which="layout"
              sentence={tooLargeToLayOut(index.order.length, MAX_LAYOUT_NODES)}
            />
          </div>
        ) : (
          <Minimap
            index={index}
            placed={placed}
            size={NODE_SIZE}
            window={window.nodes}
            dispatch={dispatch}
          />
        )}
      </div>
    </div>
  );
}
