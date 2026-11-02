// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * One box in the cone, and it is four things.
 *
 * On a comparison page it is five: the head carries the mark saying which of
 * the three kinds of change this column holds — model, numbers or data —
 * in the same word and the same outline the changes list and the grid's
 * heading wear.
 *
 * The four: the column's name, its formula on one line, its value at
 * the row cursor, and the tier it belongs to. Every one of them is quoted —
 * the name is the node's `column`, the formula is its `formula` collapsed onto
 * a line by `formatFormula` and otherwise untouched, the value is the element
 * of `value_sample` the cursor sits on written by `formatValue`, and the tier
 * is the node's `tier`. There is nothing on this box the file did not say.
 *
 * Three nodes are not four lines of arithmetic and are drawn as what they are.
 * A node carrying `settings` wears a second chip naming the convention in
 * words, because "start_at: 1.0" is the file's way of writing something an
 * actuary calls beginning-of-period and the reader should not have to know
 * that. A `hole` is dashed amber: the file is admitting it cannot account for
 * the column, and amber is this page's one mark for an admission. A compiled
 * rollforward is one box listing the states it runs and, beside them, how many
 * steps it folds into those balances — every step of the chain, since every
 * step is a movement the file carries an amount for, so the count says how
 * many lines the waterfall in the proof panel is about to be.
 *
 * **The value line reads the cursor itself.** The box is handed the timeline
 * the file sampled — the same array object for the life of the page — and
 * subscribes to its own value line at the row cursor through `state/cursor.ts`,
 * rather than being handed the period already written into its data. That is
 * what keeps the node array React Flow holds identical from one period to the
 * next, so a cursor step re-renders only the boxes whose line it changes, and
 * lays out nothing else. `state/cursor.ts` carries the measurements that made
 * both necessary.
 */

import { memo } from "react";
import type { JSX } from "react";

import { Handle, Position } from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";

import type { ChangeMark } from "../reader/compare";
import { DID_NOT_FOLD, NOT_FOLDED } from "../reader/fold";
import { formatValue } from "../reader/format";
import type { NodeKind } from "../reader/types";
import { useAtCursor } from "../state/cursor";

/** What one box is told, all of it read off the node record. */
export interface ConeNodeData extends Record<string, unknown> {
  /** The column's name, or the node's id where the file gives it no name. */
  column: string;
  /** The formula as the producer recorded it, on one line. */
  formula: string;
  /**
   * What the file sampled: a list node's whole timeline, a scalar's one value.
   *
   * The node record's own member, passed by reference and never copied, so this
   * box's data is the same object from one cursor step to the next.
   */
  sample: unknown;
  /**
   * Whether the selected entry is a fold of the book that did not cover this
   * column.
   *
   * A function of the index and not of the cursor, like everything else in
   * here, so the memo below still holds: it changes when the reader moves
   * along the policy axis, which is when the window is rebuilt anyway.
   */
  unfolded: boolean;
  /** Whether the node's `dtype` says the column holds whole numbers. */
  integer: boolean;
  /** The node's `tier`, or null where it has none. */
  tier: string | null;
  /** The convention its `settings` state, in words, where it carries any. */
  settings?: string;
  /** The node's `kind`, which decides what shape the box takes. */
  kind: NodeKind;
  /**
   * Which of the three kinds of change this column carries, on a comparison page.
   *
   * The same word and the same outline the grid's heading and the changes list
   * wear, so a reader who found a column in the list finds the same mark on its
   * box. Undefined where the page carries one document, or where this column
   * did not move.
   */
  mark?: ChangeMark;
  /**
   * What that mark's title says on this comparison — for a *data* mark, what the
   * record says moved under the column — so the box says what the list says.
   */
  said?: string | undefined;
  /** How many definitions of this column the window holds, this one included. */
  versions: number;
  /** Whether the folded-in definitions are currently shown. */
  revealed: boolean;
  /** A compiled rollforward's states, as the file lists them. */
  states?: string[];
  /**
   * How many steps that chain folds into those states, as the file counts them.
   *
   * Every step, because every step is a movement now: the count is the length
   * of `increments`, which is the summary of what the compilation applies.
   * Undefined on every other kind of box, and on a compilation whose summary
   * the producer could not write — where a zero would say a state machine that
   * moves nothing.
   */
  steps?: number;
  /** Whether this box is the one the rest of the page is looking at. */
  center: boolean;
  /** Fold the other definitions of this column out, or back in. */
  onReveal: (id: string) => void;
}

/** The node type React Flow is given for every box in the window. */
export type ConeFlowNode = Node<ConeNodeData, "cone">;

/**
 * The box's value line: the one part of it a cursor step moves.
 *
 * A component of its own, and the subscription to the cursor is its own, so a
 * step whose line changes redraws this span and nothing else of the box. When
 * the subscription was the whole box's, each of the fifteen boxes an average
 * step changes on the comparison page's window drew again entire — its head,
 * its chips, its formula and React Flow's two handles — to write one number:
 * React updated 323 elements a step there, and 219 with the line on its own.
 * The span it draws is the span the box drew.
 *
 * The line itself is what is subscribed to, so a step that leaves it saying
 * the same thing does not render it at all. A scalar's sample is the value
 * itself; a list's is the whole timeline, and a cursor past its end reads as
 * nothing rather than as some other period's number — the same rule the
 * grid's cells are written by. On a fold the book was not totalled by, the
 * foot says so in words: `·` would read as a value the file happens not to
 * carry, and a blank in a box of money reads as a zero — neither of which is
 * what a column with no portfolio value is.
 */
const ValueLine = memo(function ValueLine({
  sample,
  unfolded,
  integer,
}: {
  sample: unknown;
  unfolded: boolean;
  integer: boolean;
}): JSX.Element {
  const value = useAtCursor((period) =>
    unfolded
      ? NOT_FOLDED
      : formatValue(Array.isArray(sample) ? sample[period] : sample, { integer }),
  );
  return (
    <span
      className={`cone-value mono${unfolded ? " unfolded" : ""}`}
      {...(unfolded ? { title: DID_NOT_FOLD } : {})}
    >
      {value}
    </span>
  );
});

/**
 * Draw one box.
 *
 * Memoised, and the memo is load-bearing: everything in `data` is fixed for as
 * long as the window is, so a cursor step does not re-render this body at all.
 * The value line under it subscribes to the cursor for itself, and only it
 * redraws, and only when its line changes.
 *
 * @param props - React Flow's node props, whose `data` is the box's own items.
 * @returns The box.
 */
function Body({ id, data }: NodeProps<ConeFlowNode>): JSX.Element {
  const rollforward = data.kind === "rollforward";

  return (
    <div className={`cone-body${data.center ? " center" : ""}`}>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <div className="cone-head">
        <span className="cone-column" title={id}>
          {data.column}
        </span>
        {data.mark === undefined ? null : (
          <span
            className={`chip mark ${data.mark}`}
            data-testid="cone-mark"
            title={data.said}
          >
            {data.mark}
          </span>
        )}
        {data.versions > 1 ? (
          <button
            type="button"
            className="chip versions"
            data-testid="versions-badge"
            aria-expanded={data.revealed}
            title="the definitions this column replaced"
            onClick={(event) => {
              // The box under the badge is still a box, and clicking it
              // selects. Opening the older definitions is not selecting them.
              event.stopPropagation();
              data.onReveal(id);
            }}
          >
            {data.versions} versions
          </button>
        ) : null}
      </div>
      {rollforward ? (
        <div className="machine">
          <ul className="states mono">
            {(data.states ?? []).map((state) => (
              <li key={state}>{state}</li>
            ))}
          </ul>
          {data.steps === undefined ? null : (
            <span className="chip steps" data-testid="steps-chip" title="the steps it folds">
              {data.steps} {data.steps === 1 ? "step" : "steps"}
            </span>
          )}
        </div>
      ) : null}
      {/* An input column has no formula, and an empty code bar under its name
          would read as one the page failed to draw. */}
      {rollforward || data.formula === "" ? null : (
        <div className="cone-formula mono" title={data.formula}>
          {data.formula}
        </div>
      )}
      <div className="cone-foot">
        <ValueLine sample={data.sample} unfolded={data.unfolded} integer={data.integer} />
        {data.tier === null ? null : <span className="chip tier">{data.tier}</span>}
        {data.settings === undefined ? null : (
          <span className="chip settings" data-testid="settings-chip">
            {data.settings}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}

export const ConeNode = memo(Body);
