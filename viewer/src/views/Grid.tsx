// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The declared policy's timeline, one column per per-period node.
 *
 * An instrument, not a spreadsheet. No column letters, no
 * cell addresses, no formula bar — those belong to a tool that computes, and
 * this one quotes. Every value in the body is an element of some node's
 * `value_sample`, written by `formatValue` and by nothing else; every formula
 * in the second header row is the node's `formula` string as the producer
 * recorded it, collapsed onto one line and otherwise untouched.
 *
 * The one piece of drawing that is not a value is the operand outline: with a
 * column selected, the cells that column's node reads are outlined on the
 * cursor's row, and where the narrowing facet states an `offset` the outline
 * sits that many rows away and says so in `data-offset`. Where it states a
 * window — the `periods` an aggregation read, or the `position` a literal
 * `list.get` took (§9) — every cell of the window is outlined and says which
 * window in `data-window`: a cumulative sum outlines its column from the first
 * row to the cursor, a total the whole column. It is drawable only because the
 * file states the offset and the window — read off the facet, never inferred
 * from the formula's text.
 *
 * The second mark on a cell is the hover: pointing at an operand term in the
 * proof panel lights that operand's cell here, on the row the read points at.
 * It is drawing only — it changes nothing about what is selected — and it is
 * the panel's answer to "which cell is this term?" given by pointing rather
 * than by asking the reader to carry a period index across the page.
 *
 * Rows and body cells are virtualised, and each row in the window is memoised
 * on what it draws, so moving the cursor one period redraws the row it left
 * and the row it arrived on rather than the whole window — the measurement is
 * beside `BodyRow` below. The two header rows are not virtualised: every
 * per-period column the file carries has a `th`, always, because the header is
 * the answer to "what does this model hold", and an answer that depended on
 * where you had scrolled would not be one.
 *
 * A file that carries no values gets one sentence here instead of a table.
 * The headings without the values would be a grid of `·` under the
 * name of a policy the export never read, and a reader who scrolled it would be
 * looking for numbers that are not missing but were never asked for.
 *
 * **On a comparison page a heading may wear a mark**: one word saying
 * which of the three kinds of change this column carries, told apart by its
 * word and its outline rather than by a colour. And the column the reader has
 * selected shows both numbers in every cell — `before → after` — because "what
 * did this column used to be" is the question a marked column raises and
 * answering it in a tooltip would make the reader ask it eighty-three times.
 * Every other changed column keeps the one number and carries the pair in the
 * cell's own title, so the grid stays a grid of values with one column open.
 */

import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ClipboardEvent, JSX, KeyboardEvent } from "react";

import { useVirtualizer } from "@tanstack/react-virtual";
import type { VirtualItem } from "@tanstack/react-virtual";

import type { Comparison } from "../reader/compare";
import { comparedAs } from "../reader/exact";
import { DID_NOT_FOLD, NOT_FOLDED, isFold, noTimelineInThisFold } from "../reader/fold";
import { cellExactly, formatFormula, formatValue, isIntegerDtype } from "../reader/format";
import { windowLabel, windowRows } from "../reader/periods";
import type { Index } from "../reader/index";
import { NO_VALUES_IN_GRID, Refusal } from "../shell/Refusal";
import type { Selection, SelectionAction } from "../state/selection";
import { SHORT_MARKS, markSaid } from "./Changes";
import { followOffset, rowsInBlocks } from "./rows";
import type { Hovered } from "./Proof";

import "./Grid.css";

/** One column's width, in pixels. Fixed, so a column is a column down the page. */
const COLUMN_WIDTH = 132;

/** The row label's width. */
const LABEL_WIDTH = 64;

/**
 * One row's height, as it draws: a 22 px line and the 1 px rule under it.
 *
 * Tight, as an instrument's rows are. It was 22, which is the line alone, and
 * the virtualizer lays out the rows it is not drawing at this height while the
 * rows it draws come out at 23 — so where a row sat depended on which rows
 * happened to be drawn, and the follow below counted a pixel short for every
 * row. A block of rows drawn early (`views/rows.ts`) would have moved every
 * row under it. Measured at 23 in Chromium and WebKit.
 */
const ROW_HEIGHT = 23;

/** Where the outline for one read sits, and the offset or window that put it there. */
interface Operand {
  period: number;
  offset?: number;
  window?: string;
}

/**
 * The name to write at the head of a column.
 *
 * The node's `column` where the file gives one; its id where it does not,
 * because a column with no name is still a column and inventing one would be
 * the page naming something the model did not.
 */
function labelOf(index: Index, id: string): string {
  return index.nodes.get(id)?.column ?? id;
}

/**
 * One row of the body: the period's label and a cell per column being drawn.
 *
 * **Memoised, and the memo is the point.** A period step changes one thing
 * about this table — which row wears the cursor, and which cells on it are
 * outlined — and before this component existed it rebuilt every row in the
 * virtual window to say so. Measured on the level-4 export at the window
 * `perf/measure.mjs` opens: **69 rows a step**, about eleven hundred cells,
 * for a highlight that moved one row down. The two rows that actually moved
 * are the row the cursor left and the row it arrived on.
 *
 * So everything this body reads that a cursor step does not move — the columns
 * drawn, their timelines, the selected column, the open column's earlier
 * values — is handed in as the same object from one step to the next, and the
 * three things a step does move are narrowed to this row before they arrive:
 * `cursor` is a boolean, `outlined` is null on every row no read points at,
 * and `hoveredColumn` is null on every row the pointer is not over. A row none
 * of the three touches is handed exactly what it was handed last frame and
 * React draws nothing.
 *
 * Nothing about what is drawn changed with it: the same cells, in the same
 * order, with the same text, the same classes and the same attributes.
 */
function BodyRow({
  period,
  cursor,
  outlined,
  hoveredColumn,
  index,
  columns,
  drawn,
  samples,
  nodeId,
  folded,
  stoodIn,
  dispatch,
}: {
  /** Which period this row is. */
  period: number;
  /** Whether the row cursor is on it. */
  cursor: boolean;
  /**
   * The reads outlined on this row, by column, or null where none is.
   *
   * Null rather than an empty map, because null is the same null every step
   * and an empty map would be a new object each time — which is the memo
   * failing on every row for the sake of the one or two it is about.
   */
  outlined: ReadonlyMap<string, Operand> | null;
  /** The column the proof panel's pointer is on, where it is on this row. */
  hoveredColumn: string | null;
  index: Index;
  columns: string[];
  /** Which of `columns`, by position, the body is drawing. */
  drawn: number[];
  /** The drawn columns' timelines, looked up once for the whole table. */
  samples: ReadonlyMap<string, unknown[] | null>;
  /** The selected column, which draws both numbers on a comparison page. */
  nodeId: string | null;
  /** Whether the selected entry is a fold of the book rather than a policy. */
  folded: boolean;
  /** The open column's earlier values, formatted once, indexed by period. */
  stoodIn: (string | null)[] | null;
  dispatch: (a: SelectionAction) => void;
}): JSX.Element {
  const cells: JSX.Element[] = [];
  let after = 0;
  for (const column of drawn) {
    if (column > after) {
      cells.push(<td className="skip" colSpan={column - after} key={`skip-${after}`} />);
    }
    const id = columns[column];
    after = column + 1;
    if (id === undefined) continue;
    const node = index.nodes.get(id);
    const operand = outlined?.get(id);
    const label = labelOf(index, id);
    const classes = ["value", "mono"];
    if (id === nodeId) classes.push("sel");
    if (operand !== undefined) classes.push("operand");
    if (hoveredColumn === label) classes.push("hover");
    const unfolded = folded && samples.get(id) === null;
    if (unfolded) classes.push("unfolded");
    const integer = node !== undefined && isIntegerDtype(node.dtype);
    const now = formatValue(samples.get(id)?.[period], { integer });
    // What this cell held in the earlier document, read off `stoodIn` — the
    // open column's earlier values, formatted once by the table above.
    const stood = id === nodeId ? (stoodIn?.[period] ?? null) : null;
    if (stood !== null) classes.push("moved");
    cells.push(
      <td
        key={id}
        className={classes.join(" ")}
        data-column={label}
        data-period={period}
        {...(unfolded ? { "data-unfolded": "true", title: DID_NOT_FOLD } : {})}
        {...(stood === null ? {} : { "data-before": stood, title: `was ${stood}` })}
        {...(operand?.offset === undefined ? {} : { "data-offset": String(operand.offset) })}
        {...(operand?.window === undefined ? {} : { "data-window": operand.window })}
        onClick={() => {
          dispatch({ select: id });
          dispatch({ period });
        }}
      >
        {unfolded ? (
          NOT_FOLDED
        ) : stood === null ? (
          now
        ) : (
          <>
            <span className="before">{stood}</span>
            <span className="arrow"> → </span>
            {now}
          </>
        )}
      </td>,
    );
  }
  if (after < columns.length) {
    cells.push(<td className="skip" colSpan={columns.length - after} key="skip-end" />);
  }

  return (
    <tr
      data-period={period}
      className={cursor ? "cursor" : undefined}
      style={{ height: ROW_HEIGHT }}
    >
      <th className="label mono" scope="row">
        {period}
      </th>
      {cells}
    </tr>
  );
}

const Row = memo(BodyRow);

/**
 * The row labels, drawn as one column that sticks down the left.
 *
 * Each body row keeps its own label cell, the row's header, which is what
 * anything reading the table asks a row for. Those cells used to stick, one
 * compositing layer each; this column draws the same labels over them as one
 * block, and the row it hangs from has no height, so it starts where the drawn
 * rows start and the scroller carries it with them. `Grid.css` has the layers
 * it saves. Hidden from assistive technology, which reads the row's own cell.
 *
 * @param drawn - The rows the body is drawing, in order.
 * @param cursor - The row cursor's period.
 * @param span - How many columns the table has, so the row holding the
 *   column spans all of them and the column can stick across its width.
 * @param width - The label's width, the table's first column.
 */
function LabelColumn({
  drawn,
  cursor,
  span,
  width,
}: {
  drawn: VirtualItem[];
  cursor: number;
  span: number;
  width: number;
}): JSX.Element {
  return (
    <tr className="labels" aria-hidden="true">
      <td colSpan={span}>
        <div className="label-host">
          <div className="label-column" style={{ width }}>
            {drawn.map((row) => (
              <div
                key={row.key}
                className={row.index === cursor ? "label mono cursor" : "label mono"}
              >
                {row.index}
              </div>
            ))}
          </div>
        </div>
      </td>
    </tr>
  );
}

/**
 * Whether the label column would draw what it drew: the same rows, the same
 * cursor, the same span and width.
 *
 * By the rows' keys and positions rather than by the array's identity, because
 * the virtualizer hands the grid a new array whenever the scroller moves, and
 * on a scrub the scroller moves a row a frame while the rows drawn — whole
 * blocks of them, `views/rows.ts` — move once every sixteen. The scroll that
 * follows the cursor draws the grid a second time in the frame after it, and
 * this is what keeps that second drawing from writing out every label to
 * arrive at the labels already there.
 */
function sameLabels(
  was: Parameters<typeof LabelColumn>[0],
  now: Parameters<typeof LabelColumn>[0],
): boolean {
  return (
    was.cursor === now.cursor &&
    was.span === now.span &&
    was.width === now.width &&
    was.drawn.length === now.drawn.length &&
    was.drawn.every((row, at) => row.key === now.drawn[at]?.key && row.index === now.drawn[at]?.index)
  );
}

const Labels = memo(LabelColumn, sameLabels);

/** The whole grid: the timeline, one row per period. */
export function Grid({
  index,
  selection,
  dispatch,
  columns,
  hovered,
  comparison,
}: {
  index: Index;
  selection: Selection;
  dispatch: (a: SelectionAction) => void;
  /**
   * The per-period columns to draw, in the file's order — every one of them
   * unless the shell's search has narrowed them. The grid never reorders what
   * it is given: the file's order is topological, so a column's inputs are
   * always to its left, and a grid that sorted by relevance would take that
   * away.
   */
  columns: string[];
  /** The cell the proof panel's pointer is on, where it is on one. */
  hovered: Hovered | null;
  /** The two documents and what moved between them, on a comparison page. */
  comparison?: Comparison | undefined;
}): JSX.Element {
  const scrollRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<HTMLTableSectionElement>(null);

  // How much of the scroller's height no row can be seen through: the sticky
  // header over its top and, where the platform draws one, the horizontal
  // scrollbar along its bottom. Measured off the page below, because the
  // header's height is the stylesheet's to set and a number written here would
  // be a second copy of it.
  const [obscured, setObscured] = useState(0);

  const operands = useMemo(() => {
    const found = new Map<string, Operand[]>();
    const id = selection.nodeId;
    if (id === null) return found;
    for (const source of index.readsOf.get(id) ?? []) {
      if (found.has(source)) continue;
      const windows = index.windowsOf(id, source);
      if (windows.length > 0) {
        // Every cell of every window the read states, the first window's label
        // on a cell two of them cover. The run is the source's own, which on a
        // per-policy timeline may be shorter than the grid's.
        const length = index.timeline(source)?.length ?? index.periods;
        const cells = new Map<number, Operand>();
        for (const window of windows) {
          const label = windowLabel(window) ?? "";
          for (const period of windowRows(window, selection.period, length)) {
            if (!cells.has(period)) cells.set(period, { period, window: label });
          }
        }
        found.set(source, [...cells.values()]);
        continue;
      }
      const offset = index.offsetOf(id, source);
      const period = selection.period + (offset ?? 0);
      // A read pointing off either end of the sampled timeline has no cell to
      // outline, and the page says nothing rather than outlining the edge.
      if (period < 0 || period >= index.periods) continue;
      found.set(source, [offset === undefined ? { period } : { period, offset }]);
    }
    return found;
  }, [index, selection.nodeId, selection.period]);

  const rows = useVirtualizer({
    count: index.periods,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
    // Whole blocks of rows, so a scrub that scrolls a row a frame changes the
    // table's rows once a block rather than on every frame; `views/rows.ts`
    // has the measurement.
    rangeExtractor: rowsInBlocks,
    // The rows sit under the header, so the virtualizer's own row positions
    // leave the header's height out: a row it has scrolled to the top of the
    // view lands just under the header, which is right. Its view is the
    // scroller's whole box, though, so a row it scrolled to the bottom of that
    // box landed the header's height below the bottom of what can be seen,
    // and a scrollbar's height further where one takes room. Taking both off
    // the bottom of the view puts that row's lower edge on the view's.
    scrollPaddingEnd: obscured,
  });

  const cols = useVirtualizer({
    horizontal: true,
    count: columns.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => COLUMN_WIDTH,
    overscan: 4,
  });

  const selected = selection.nodeId === null ? -1 : columns.indexOf(selection.nodeId);

  // What the body draws: the horizontal window, plus the selected column and
  // every column it reads. The outlines are the reason for the "plus" — an
  // operand that stopped existing because it had scrolled out of the window
  // would be an outline the reader could never scroll back to.
  const wanted = new Set(cols.getVirtualItems().map((item) => item.index));
  if (selected >= 0) wanted.add(selected);
  for (const source of operands.keys()) {
    const at = columns.indexOf(source);
    if (at >= 0) wanted.add(at);
  }
  const sorted = [...wanted].sort((a, b) => a - b);

  // The same array object for as long as the same columns are being drawn.
  // The row above is memoised and a memo compares by identity, so a list
  // rebuilt out of the same numbers every frame would fail that comparison
  // eighty-three times in a scrub and redraw every row to draw what was
  // already there. What is held is a cache and not state: it decides nothing
  // about what the table shows, only whether the thing shown is recognisably
  // the thing already on the screen. A horizontal scroll, a new selection or a
  // new set of operands changes the contents and a new array is taken.
  const held = useRef<number[]>(sorted);
  if (
    held.current.length !== sorted.length ||
    held.current.some((at, column) => at !== sorted[column])
  ) {
    held.current = sorted;
  }
  const drawn = held.current;

  // The timelines of the columns actually drawn, looked up once rather than
  // once per cell — and memoised, because every row is handed this map and a
  // new map each frame would be a new prop on all of them.
  const samples = useMemo(() => {
    const found = new Map<string, unknown[] | null>();
    for (const at of drawn) {
      const id = columns[at];
      if (id !== undefined) found.set(id, index.timeline(id));
    }
    return found;
  }, [drawn, columns, index]);

  // The outlines, grouped by the row each one sits on. A row no read points at
  // is handed null — the same null on every step — which is what lets the memo
  // hold for the eighty-one rows a period step does not touch.
  const outlines = useMemo(() => {
    const byRow = new Map<number, Map<string, Operand>>();
    for (const [id, cells] of operands) {
      for (const operand of cells) {
        const row = byRow.get(operand.period) ?? new Map<string, Operand>();
        row.set(id, operand);
        byRow.set(operand.period, row);
      }
    }
    return byRow;
  }, [operands]);

  // On an entry that is the book folded rather than one policy, a column no
  // accumulator covered has no number here and never will. Said in words
  // rather than left as the mark a missing value wears: a reviewer scanning a
  // column of money reads a blank as a zero, and a total of nothing is the one
  // wrong answer this page must not let them reach.
  const folded = isFold(index.policy);

  const period = selection.period;
  const periods = index.periods;
  const nodeId = selection.nodeId;

  // Whether the table is drawn at all; the two early returns below draw a
  // sentence instead, with no scroller or header to measure.
  const drawsTable = index.carriesValues && !(folded && periods === 0);

  // What `obscured` says, read once as the table is drawn and again whenever
  // the scroller or its header changes size — so never on a period step, which
  // changes neither. A layout effect, so that the measurement, and the follow
  // it sets off again, both land before the page is first drawn.
  useLayoutEffect(() => {
    const scroller = scrollRef.current;
    const head = headRef.current;
    if (!drawsTable || scroller === null || head === null) return undefined;
    const measure = (): void => {
      setObscured(head.offsetHeight + scroller.offsetHeight - scroller.clientHeight);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(scroller);
    observer.observe(head);
    return () => {
      observer.disconnect();
    };
  }, [drawsTable]);

  // The offset this grid last wrote to its scroller, until the scroller says
  // it has moved. The virtualizer learns where the scroller stands from its
  // scroll event, which arrives in the frame after the write; a second step in
  // the same frame — a key held down — must start from where the first one
  // left it rather than from where the virtualizer last heard it was.
  const wrote = useRef<number | null>(null);
  useEffect(() => {
    const scroller = scrollRef.current;
    if (!drawsTable || scroller === null) return undefined;
    const heard = (): void => {
      wrote.current = null;
    };
    scroller.addEventListener("scroll", heard, { passive: true });
    return () => {
      scroller.removeEventListener("scroll", heard);
    };
  }, [drawsTable]);

  // Keep the cursor's row in sight. `obscured` is among the dependencies
  // because the grid's first follow runs before its measurement has reached
  // the virtualizer, and a page opened from a link onto a late period has to
  // be followed again once it has.
  //
  // **Worked out from numbers the grid holds, and written once the step has
  // finished writing the page.** `followOffset` is the virtualizer's own rule
  // with nothing read off the layout, so a step whose row is in sight — every
  // step until the cursor reaches the bottom edge — costs the follow nothing.
  // A step that does scroll is a layout, because the browser lays a page out
  // before it moves a scroller; it is made in a microtask, which runs after
  // the cone's boxes have written their lines for the same step, so that one
  // layout takes in everything the step changed and the frame's own finds
  // nothing left to do. Before, the follow asked the virtualizer here, in the
  // middle of the step, and the page was laid out twice a frame: once for the
  // follow and once more for the boxes.
  useEffect(() => {
    if (periods <= 0) return undefined;
    let live = true;
    queueMicrotask(() => {
      const scroller = scrollRef.current;
      if (!live || scroller === null) return;
      const to = followOffset({
        period,
        count: periods,
        rowHeight: ROW_HEIGHT,
        offset: wrote.current ?? rows.scrollOffset ?? 0,
        size: rows.scrollRect?.height ?? 0,
        obscured,
      });
      if (to === null) return;
      scroller.scrollTop = to === "bottom" ? scroller.scrollHeight : to;
      // Read back rather than assumed: the browser clamps an offset past
      // either end, and the scroller's layout is current after the write.
      wrote.current = scroller.scrollTop;
    });
    return () => {
      live = false;
    };
  }, [period, periods, rows, obscured]);

  useEffect(() => {
    const at = nodeId === null ? -1 : columns.indexOf(nodeId);
    if (at >= 0) cols.scrollToIndex(at, { align: "center" });
  }, [nodeId, columns, cols]);

  // The two header rows, memoised on the four things they are a function of —
  // and the row cursor is not one of them. The heads are deliberately not
  // virtualised (every per-period column the file carries has a `th`, always),
  // so a scrub through eighty-three periods otherwise rebuilt a hundred and
  // sixty-six cells a frame to say that nothing about any of them had changed.
  // It was affordable before a comparison put a chip in each of them; it is
  // measured now. Above every early return below, because the number of hooks
  // this component runs must not be a function of what the file carries.
  /**
   * The open column's earlier values, formatted once, indexed by period.
   *
   * Null at a period where the two documents agree, so a cell that did not
   * move carries nothing extra — a `1234 → 1234` on eighty of eighty-three
   * rows would bury the three that moved.
   *
   * **Computed here rather than in the cell, and the reason is measured.** The
   * earlier document's numbers for one column do not change while the row
   * cursor moves, so formatting them inside the row meant formatting forty of
   * them again on every frame of a scrub to arrive at the same forty strings.
   * Held here, it is also one prop the memoised row can compare by identity
   * rather than forty strings it has to build to find out nothing moved. It is
   * one column because only one is open: the mark on a heading says a column
   * moved, and opening it is what says what it was.
   */
  const stoodIn = useMemo(() => {
    if (comparison === undefined || nodeId === null) return null;
    if (!comparison.byNode.has(nodeId)) return null;
    const earlier = comparison.before.timeline(nodeId);
    const now = index.timeline(nodeId);
    if (earlier === null || now === null) return null;
    const integer = isIntegerDtype(index.nodes.get(nodeId)?.dtype ?? "");
    // `comparedAs` on both sides, because an integer the file spells past what
    // a double carries arrives as its own digits and two of those are never
    // the same object — without it every cell of an i64 column would claim to
    // have moved, on a page where nothing had.
    return earlier.map((value, at) =>
      comparedAs(value) === comparedAs(now[at]) ? null : formatValue(value, { integer }),
    );
  }, [comparison, index, nodeId]);

  const heads = useMemo(
    () => (
      <thead ref={headRef}>
        <tr className="names">
          <th className="label corner" scope="col">
            period
          </th>
          {columns.map((id) => {
            const change = comparison?.byNode.get(id);
            return (
              <th
                key={id}
                scope="col"
                data-column={labelOf(index, id)}
                {...(change === undefined ? {} : { "data-mark": change.mark })}
                title={id}
                className={id === nodeId ? "sel" : undefined}
                onClick={() => dispatch({ select: id })}
              >
                {labelOf(index, id)}
                {change === undefined || comparison === undefined ? null : (
                  <span className={`chip mark ${change.mark}`} title={markSaid(change, comparison)}>
                    {SHORT_MARKS[change.mark]}
                  </span>
                )}
              </th>
            );
          })}
        </tr>
        <tr className="formulas">
          <th className="label corner" scope="col" />
          {columns.map((id) => {
            const formula = index.nodes.get(id)?.formula ?? null;
            return (
              <td
                key={id}
                data-formula-for={labelOf(index, id)}
                title={formula ?? ""}
                className={`formula mono${id === nodeId ? " sel" : ""}`}
              >
                {formatFormula(formula)}
              </td>
            );
          })}
        </tr>
      </thead>
    ),
    [columns, index, nodeId, comparison, dispatch],
  );

  // The column widths, held for the same reason as the heads: a `col` per
  // per-period column the file carries, each with a style object of its own,
  // and nothing about any of them moves with the row cursor. Drawn again on
  // every step they were a fresh style object per column — seventy-one on the
  // level-4 export — for React to compare against the ones it already had,
  // twice in a frame where the grid follows the cursor down.
  const widths = useMemo(
    () => (
      <colgroup>
        <col style={{ width: LABEL_WIDTH }} />
        {columns.map((id) => (
          <col key={id} style={{ width: COLUMN_WIDTH }} />
        ))}
      </colgroup>
    ),
    [columns],
  );

  const last = Math.max(0, periods - 1);

  /** The row cursor on the arrow keys, with the grid focused. */
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const moves: Record<string, number | undefined> = {
      ArrowDown: Math.min(last, period + 1),
      ArrowUp: period - 1,
      PageDown: Math.min(last, period + 12),
      PageUp: period - 12,
      Home: 0,
      End: last,
    };
    const next = moves[event.key];
    if (next === undefined) return;
    event.preventDefault();
    dispatch({ period: next });
  }

  /**
   * Copying a cell copies what the file holds, not what the cell shows.
   *
   * A cell is written rounded for reading, and a reviewer who copies one into
   * a spreadsheet to check it is checking the file, so the clipboard gets the
   * value's every digit in the file's own spelling (`exactly`). Which cell: the
   * one the reader's highlight sits in, where it sits in one, or the selected
   * cell where nothing is highlighted. A highlight across several cells is the
   * reader's own choice of text and is copied as drawn.
   */
  function onCopy(event: ClipboardEvent<HTMLDivElement>): void {
    const highlight = window.getSelection();
    let target: { id: string; period: number } | null = null;
    if (highlight === null || highlight.isCollapsed) {
      if (nodeId !== null && columns.includes(nodeId)) target = { id: nodeId, period };
    } else {
      const cellOf = (at: Node | null): HTMLElement | null =>
        (at instanceof Element ? at : (at?.parentElement ?? null))?.closest<HTMLElement>("td.value") ?? null;
      const from = cellOf(highlight.anchorNode);
      if (from !== null && from === cellOf(highlight.focusNode)) {
        const id = columns.find((one) => labelOf(index, one) === from.dataset["column"]);
        if (id !== undefined) target = { id, period: Number(from.dataset["period"]) };
      }
    }
    if (target === null) return;
    const digits = cellExactly(index, target.id, target.period);
    if (digits === null) return;
    event.clipboardData.setData("text/plain", digits);
    event.preventDefault();
  }

  if (!index.carriesValues) {
    // The pane keeps its own name and its own place: what is missing is the
    // table, not the region, and the sentence is printed where the table was.
    // The branch sits below every hook this component runs, so that what the
    // page does with a file is never a function of the order React called us in.
    return (
      <div className="grid empty" data-testid="grid">
        <Refusal which="values" sentence={NO_VALUES_IN_GRID} />
      </div>
    );
  }

  if (folded && index.periods === 0) {
    // A fold across the book of a column holding one value per policy is one
    // number, not a run of them, so this entry has no timeline at all. An
    // empty table under a selected entry reads as a projection of nothing,
    // which is the misreading the sentence is here to prevent. It is not a
    // refusal and is not drawn as one: nothing was withheld and nothing is
    // admitted, there is simply no such run of numbers.
    return (
      <div className="grid empty" data-testid="grid">
        <p className="says" data-unfolded="true">
          {noTimelineInThisFold(index.policy?.aggregation ?? "")}
        </p>
      </div>
    );
  }

  // The two header rows, memoised on the four things they are a function of —
  // and the row cursor is not one of them. The heads are deliberately not
  // virtualised (every per-period column the file carries has a `th`, always),
  // so a scrub through eighty-three periods otherwise rebuilt a hundred and
  // sixty-six cells a frame to say nothing had changed about any of them. It
  // was affordable before a comparison put a chip in each of them; it is
  // measured now.
  const drawnRows = rows.getVirtualItems();
  const firstRow = drawnRows[0];
  const finalRow = drawnRows[drawnRows.length - 1];
  const above = firstRow === undefined ? 0 : firstRow.start;
  const below = finalRow === undefined ? 0 : rows.getTotalSize() - finalRow.end;
  const span = columns.length + 1;

  return (
    <div className="grid" data-testid="grid" tabIndex={0} onKeyDown={onKeyDown} onCopy={onCopy}>
      <div className="scroll" ref={scrollRef}>
        <table style={{ width: LABEL_WIDTH + columns.length * COLUMN_WIDTH }}>
          {widths}
          {heads}
          <tbody>
            {above > 0 ? (
              <tr className="skip" style={{ height: above }}>
                <td colSpan={span} />
              </tr>
            ) : null}
            <Labels drawn={drawnRows} cursor={period} span={span} width={LABEL_WIDTH} />
            {drawnRows.map((row) => (
              <Row
                key={row.key}
                period={row.index}
                cursor={row.index === period}
                outlined={outlines.get(row.index) ?? null}
                hoveredColumn={
                  hovered !== null && hovered.period === row.index ? hovered.column : null
                }
                index={index}
                columns={columns}
                drawn={drawn}
                samples={samples}
                nodeId={nodeId}
                folded={folded}
                stoodIn={stoodIn}
                dispatch={dispatch}
              />
            ))}
            {below > 0 ? (
              <tr className="skip" style={{ height: below }}>
                <td colSpan={span} />
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
