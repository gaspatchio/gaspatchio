// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The worked example, printed.
 *
 * This file draws what `reader/proof.ts` assembled and adds
 * nothing to it: every line's text comes out of the `Proof`, in the order the
 * reader put them in, and the only thing the panel decides is what a line of
 * each kind looks like. That division is the point — what is *said* about a
 * number is a property of the file and is testable without a browser; how it is
 * *set* is a property of the page.
 *
 * Two things here are wiring rather than drawing. Hovering an operand term
 * lights that operand's cell in the grid, on the row the read actually points
 * at, so "which cell is this term?" is answered by pointing rather than by
 * reading a period index off a line. And the footer carries the node's source
 * location and both of its fingerprints in full, because "where exactly is this
 * calculation defined?" is the question this panel exists to answer and a
 * truncated stamp is not an answer to it.
 *
 * The location is now a control as well as a stamp. It said
 * `model.py:520` and could not show line 520; the file carries the file now
 * (§7.3), so the same text opens the drawer's Source tab at that line. It stays
 * text where the node records no location, because a control that led nowhere
 * would be worse than a sentence saying there is nowhere to go.
 *
 * **On a comparison page a changed column gets two of these**, *before*
 * on the left and *after* on the right, each assembled by `reader/proof.ts`
 * from its own document. Two things are deliberately not carried across from
 * the earlier one. Its terms do not light the grid, because the grid draws the
 * later document and lighting a cell from the earlier one's proof would be
 * claiming a term's value is a cell it is not. And its footer's location is a
 * stamp rather than a control, because the drawer's Source tab holds the later
 * document's file and would open at a line of the wrong quarter.
 *
 * **The earlier one settles; it does not follow.** Two worked examples cost
 * twice one worked example, and measured on the level-4 comparison page that
 * second `proofOf` per period step was a dropped frame in every scrub. So
 * while the row cursor is moving the earlier document's proof is **not
 * computed at all**: the panel says one word, *settling*, and when the cursor
 * has been still for `SETTLES_MS` the proof is worked out once and filled in.
 *
 * The rule that shape has to keep is the comparison's own: the two sides are never two
 * different periods. A panel showing the earlier document at period 40 beside
 * the later one at period 45 — which is what deferring the render rather than
 * withholding it would draw — is precisely the blur that rule exists to
 * prevent, and it would be at its most convincing exactly when it was most
 * wrong. A word is not a period, so a reader mid-scrub sees one period and a
 * sentence about the other side, which is a thing they can read correctly.
 *
 * The later document's proof is untouched and stays live on every step: it is
 * the one the grid, the cone and the cursor are all showing, and a page whose
 * *current* answer lagged the hand moving it would be a different complaint.
 */

import { useEffect, useState } from "react";
import type { JSX } from "react";

import type { Comparison } from "../reader/compare";
import { exactly, isIntegerDtype, shortFingerprint } from "../reader/format";
import { locationOf } from "../reader/index";
import type { Index } from "../reader/index";
import { proofOf, tracePeriod } from "../reader/proof";
import type { ProofLine, ProofTable } from "../reader/proof";
import { NO_VALUES_IN_PROOF, Refusal } from "../shell/Refusal";
import type { Selection } from "../state/selection";

import "./Proof.css";

/**
 * How long the row cursor rests before the earlier document's proof is worked out.
 *
 * Eighty milliseconds: five frames at sixty a second. Long enough that a scrub
 * — one period per frame — never asks for it, and short enough that a reader
 * who steps one period and looks left has the answer before they have focused
 * on it. It is deliberately not the 250 ms the shell waits before rewriting
 * the address bar: that timer is there to stay inside a browser's rate limit
 * and this one is there to stay out of a frame, and tying the two together
 * would make each hostage to the other's reason.
 */
const SETTLES_MS = 80;

/**
 * The period, once the cursor has held it still for `SETTLES_MS`.
 *
 * Returns the *previous* settled period while the cursor is moving, which the
 * caller must not draw — see this file's head. What the caller does with the
 * gap is show a word; what it must never do is draw the earlier document at
 * the period the cursor has left.
 *
 * It starts settled on the period it is given, so a page that opens, or a
 * column selected without touching the cursor, draws both proofs at once. Only
 * movement un-settles it.
 *
 * @param period - The row cursor's period.
 * @returns The last period the cursor rested on.
 */
function useSettledPeriod(period: number): number {
  const [settled, setSettled] = useState(period);
  useEffect(() => {
    if (settled === period) return undefined;
    const timer = window.setTimeout(() => {
      setSettled(period);
    }, SETTLES_MS);
    // Each step cancels the step before it, which is what turns a scrub
    // through eighty-three periods into one computation at the end of it.
    return () => {
      window.clearTimeout(timer);
    };
  }, [period, settled]);
  return settled;
}

/** Which grid cell a hovered term points at: a column name and a period. */
export interface Hovered {
  column: string;
  period: number;
}

/** What the label to the left of a line says, per kind. */
const LABELS: Record<ProofLine["kind"], string> = {
  formula: "formula",
  substitution: "with values",
  lowered: "as it ran",
  share: "of the gross",
  result: "result",
  note: "note",
  fired: "fired",
  dead: "not taken",
  excerpt: "table",
  convention: "convention",
  fold: "fold",
  check: "check",
};

/**
 * The name a column is written under, as the grid writes it.
 *
 * The grid keys its cells by this, so a hover that used anything else would
 * light nothing. The file's `column` where it gives one, the node's id where it
 * does not — the same rule, spelled the same way, in both places.
 */
function labelOf(index: Index, id: string): string {
  return index.nodes.get(id)?.column ?? id;
}

/**
 * The producer's own answer for this column, off the last step that carries one.
 *
 * Read here rather than passed down from the reader because it is shown only in
 * the one case where the two accounts differ, and the reader's business is
 * deciding that they do.
 */
function traceResult(index: Index, nodeId: string): unknown {
  const trace = index.traceOf(nodeId);
  if (trace === undefined) return undefined;
  for (let at = trace.length - 1; at >= 0; at -= 1) {
    const step = trace[at];
    if (step !== undefined && "result" in step) return step.result;
  }
  return undefined;
}

/** What the file sampled for this column at one period. */
function sampleAt(index: Index, nodeId: string, period: number): unknown {
  const sample = index.sampleOf(nodeId);
  return Array.isArray(sample) ? sample[period] : sample;
}

/** One cell of the excerpt, written as the payload holds it. */
function cell(value: unknown): string {
  if (value === null || value === undefined) return "·";
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** The excerpt of the inline table around the row the keys named. */
function Excerpt({ table }: { table: ProofTable }): JSX.Element {
  return (
    <div className="excerpt">
      <div className="excerpt-head">
        <span className="excerpt-name">{table.name}</span>
        <span
          className="chip fingerprint-chip mono"
          data-testid="table-chip"
          title={table.fingerprint}
        >
          {shortFingerprint(table.fingerprint)}
        </span>
      </div>
      <table className="excerpt-rows mono">
        <thead>
          <tr>
            {table.header.map((name) => (
              <th key={name} scope="col">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, at) => (
            <tr
              // The payload's rows are plain arrays with no identity of their
              // own; their position in the excerpt is what distinguishes them.
              key={`row-${String(at)}`}
              {...(at === table.hitRow ? { "data-hit": "true" } : {})}
            >
              {row.map((value, column) => (
                <td key={`cell-${String(at)}-${String(column)}`}>{cell(value)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One worked example: the lines, the excerpt, the flag, the footer. */
function OneProof({
  index,
  nodeId,
  period,
  setHovered,
  openSource,
  side,
}: {
  index: Index;
  nodeId: string;
  period: number;
  setHovered: (hovered: Hovered | null) => void;
  openSource: ((at: NonNullable<ReturnType<typeof locationOf>>) => void) | null;
  /** Which of the two documents this one is, on a comparison page. */
  side?: "before" | "after";
}): JSX.Element {
  const node = index.nodes.get(nodeId);
  const proof = proofOf(index, nodeId, period);
  const where = locationOf(node?.source_location);
  const integer = node !== undefined && isIntegerDtype(node.dtype);

  return (
    <div className={`proof-one${side === undefined ? "" : ` ${side}`}`} data-side={side ?? "only"}>
      {side === undefined ? null : (
        <div className="proof-side" data-testid={`proof-side-${side}`}>
          {side}
        </div>
      )}
      <header className="proof-head">
        <span className="idiom" data-testid={side === "before" ? "proof-idiom-before" : "proof-idiom"}>
          {proof.idiom}
        </span>
        <span className="at mono">
          {node?.column ?? nodeId} · period {proof.period}
        </span>
        {proof.disagreement ? (
          // Both numbers, never reconciled: the producer's account of this
          // figure and the figure it sampled, at the period the trace stands
          // at. The page does not decide which is right — it cannot, it
          // computes nothing — and saying only that they differ would leave a
          // reader with the flag and no way to act on it.
          //
          // Every digit of each, and not the grid's rounding: the flag is
          // raised on the numbers, and two numbers that differ past the sixth
          // significant figure would otherwise be printed as the same number
          // with a chip between them saying they differ.
          <span className="chip disagreement" data-testid="disagreement">
            at period {tracePeriod(index)} the trace says{" "}
            <b className="mono" data-testid="disagreement-trace">
              {exactly(traceResult(index, nodeId), { integer }) ?? "·"}
            </b>{" "}
            and the sample says{" "}
            <b className="mono" data-testid="disagreement-sample">
              {exactly(sampleAt(index, nodeId, tracePeriod(index)), { integer }) ?? "·"}
            </b>
          </span>
        ) : null}
      </header>

      <ol className="lines">
        {proof.lines.map((line, at) => {
          const operand = line.operand;
          const column = operand === undefined ? undefined : labelOf(index, operand);
          // The lowered expression is folded away. It is evidence rather than
          // explanation — the producer's own sentence, kept verbatim — and a
          // reader who wants it asks for it, where a reader who does not would
          // otherwise have to read past a wall of `repeat_by` to reach their
          // own arithmetic.
          const body =
            line.kind === "lowered" ? (
              <details className="lowered">
                <summary>the expression that ran</summary>
                <span className="text">{line.text}</span>
              </details>
            ) : (
              <span className={`text${line.kind === "result" ? " mono" : ""}`}>{line.text}</span>
            );
          return (
            <li
              // Two lines of one kind can carry the same text — two operands
              // holding the same value at the same period — so position is what
              // tells them apart.
              key={`line-${String(at)}`}
              data-kind={line.kind}
              // The one line that can carry the page's amber, and it carries
              // it as a class rather than as a second kind: a check that does
              // not close is the same line saying a different thing.
              {...(line.flagged === true ? { "data-flagged": "true" } : {})}
              className={`line ${line.kind}${line.flagged === true ? " flagged" : ""}`}
            >
              <span className="label">{LABELS[line.kind]}</span>
              {operand === undefined || column === undefined ? (
                body
              ) : (
                <span
                  className="term mono"
                  data-operand={operand}
                  {...(line.offset === undefined ? {} : { "data-offset": String(line.offset) })}
                  {...(line.window === undefined ? {} : { "data-window": line.window })}
                  onMouseEnter={() => {
                    setHovered({ column, period: proof.period + (line.offset ?? 0) });
                  }}
                  onMouseLeave={() => {
                    setHovered(null);
                  }}
                >
                  {line.text}
                  {line.window === undefined ? null : (
                    <span className="window"> reads {line.window}</span>
                  )}
                </span>
              )}
            </li>
          );
        })}
      </ol>

      {proof.table === undefined ? null : <Excerpt table={proof.table} />}

      <footer className="proof-foot mono" data-testid={side === "before" ? "proof-footer-before" : "proof-footer"}>
        {where === null || openSource === null ? (
          <span className="where">{where === null ? "no source location recorded" : node?.source_location}</span>
        ) : (
          <button
            type="button"
            className="where open-source"
            data-testid="open-source"
            title={`open ${where.path} at line ${String(where.line ?? 0)}`}
            onClick={() => {
              openSource(where);
            }}
          >
            {node?.source_location}
          </button>
        )}
        <span className="stamp">local {node?.local_fingerprint}</span>
        <span className="stamp">graph {node?.fingerprint}</span>
      </footer>
    </div>
  );
}

/** The panel: one worked example, or two side by side on a changed column. */
export function Proof({
  index,
  selection,
  setHovered,
  openSource,
  comparison,
}: {
  index: Index;
  selection: Selection;
  setHovered: (hovered: Hovered | null) => void;
  /** Open the drawer's Source tab at the file and line the footer names. */
  openSource: (at: NonNullable<ReturnType<typeof locationOf>>) => void;
  /** The two documents and what moved between them, on a comparison page. */
  comparison?: Comparison | undefined;
}): JSX.Element {
  // Above every early return below, because the number of hooks this component
  // runs must not be a function of what the file carries.
  const settled = useSettledPeriod(selection.period);
  const nodeId = selection.nodeId;
  // A hole's note is the one thing this panel says that is not about a value.
  // The file records the column as unaccounted for, and it records that whether
  // or not the export carried a policy's numbers — so a file with no values
  // refuses everything else here and lets the hole through. Found in the
  // written reads on the holes fixture, which is the published corpus and
  // carries none: the no-values sentence stood in front of the one sentence a
  // reviewer had opened that column to read.
  const selected = nodeId === null ? undefined : index.nodes.get(nodeId);
  if (!index.carriesValues && selected?.kind !== "hole") {
    // A file with no values: there is no worked example to print, and a panel that
    // printed the formula alone would be showing an unworked example.
    return (
      <section className="proof" data-testid="proof">
        <Refusal which="values" sentence={NO_VALUES_IN_PROOF} />
      </section>
    );
  }
  if (nodeId === null || !index.nodes.has(nodeId)) {
    return (
      <section className="proof" data-testid="proof">
        <p className="prompt">Select a column to see how it was worked out.</p>
      </section>
    );
  }

  // Both proofs where this column is one the comparison says moved and both
  // documents hold it: *before* on the left and *after* on the right, each in
  // this strip's own form. On a model change the two formulas differ and the
  // reader is looking at the edit; on a numbers change the formula is one
  // sentence written twice and what differs is the values substituted into it.
  // Saying which is which is the changes list's job, not this panel's — what
  // this panel does is put the two accounts where they can be read together.
  const change = comparison?.byNode.get(nodeId);
  const bothHold = comparison !== undefined && comparison.before.nodes.has(nodeId);
  const together = change !== undefined && bothHold;

  return (
    <section className={`proof${together ? " compared" : ""}`} data-testid="proof">
      {!together ? null : settled === selection.period ? (
        <OneProof
          index={comparison.before}
          nodeId={nodeId}
          period={selection.period}
          // The grid draws the later document, so pointing at a term in the
          // earlier one's proof lights nothing there. A hover that lit the
          // *after* cell would be this panel claiming a term's value is a cell
          // it is not.
          setHovered={() => undefined}
          openSource={null}
          side="before"
        />
      ) : (
        // The cursor is moving, so this side is not worked out — and says so
        // in a word rather than in a stale number. It keeps the pane's shape
        // and its heading, because a panel that collapsed and came back would
        // move the other one under the reader's eyes on every period step.
        <div className="proof-one before settling" data-side="before">
          <div className="proof-side" data-testid="proof-side-before">
            before
          </div>
          <p className="settles" data-testid="proof-settling">
            settling
          </p>
        </div>
      )}
      <OneProof
        index={index}
        nodeId={nodeId}
        period={selection.period}
        setHovered={setHovered}
        openSource={openSource}
        {...(together ? { side: "after" as const } : {})}
      />
    </section>
  );
}
