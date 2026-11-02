// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The worked example for one column at one period.
 *
 * Every line this module returns is assembled out of the
 * node's `formula`, its `trace`, its `value_sample`, its `settings`, its
 * `branches`, the assumption payloads and the index — and out of nothing else.
 * The three enrichment members are read through the index rather than off the
 * record, because on a document carrying several policies each is an array of
 * them and which one this panel is about is the reader's position on the axis
 * (§7.4). Nothing below indexes a policy; `reader/policies.ts` does it once.
 * **Nothing here evaluates.** There is no arithmetic in this file beyond adding
 * an offset to a period index, counting rows, and the one sum named below, and
 * that is the whole point: a panel that recomputed the line it was showing
 * would be a second implementation of the model, quietly agreeing with the
 * first until the day it did not.
 *
 * **The one sum is a compiled rollforward's check line**, `closing = opening +
 * Σ movements`, and it is allowed because it is the definition of a
 * rollforward rather than a calculation the model made: every term in it is
 * quoted off the file, and stating it is how a reader sees the movements and
 * the balance agree. It is the same move the disagreement flag below makes,
 * one step further — a page that can be shown to hold is worth more than a
 * page that only claims to.
 *
 * **What the file's trace actually holds**, measured from the level-4 export
 * rather than assumed: three steps. Step 1 is the formula over column names.
 * Step 2 is the same expression with each operand's whole timeline substituted
 * into it, abbreviated by the producer to the first three values, an ellipsis
 * and the last. Step 3 is the result list, and it carries `result`, `shape`,
 * `pointer` and `comment`. `result` is the value at **one** period — the period
 * the trace was taken at, which is `enrichment.periods`' first entry where the
 * export named periods and 0 where it did not. Level 4 names none, so its
 * traces stand at period 0 and `net_cf@1`'s `result` is 49337.576616, which is
 * `value_sample[0]`. A trace can also be shorter: a constant column's trace is
 * two steps, and `result` sits on the last step that carries one.
 *
 * So the panel quotes step 2 verbatim — it is the producer's sentence, not the
 * page's — and then writes the cursor's own substitution beside it, one line
 * per operand, each carrying the value that operand's timeline holds at the
 * period actually read. Those lines are quotations too: the values are elements
 * of the operands' `value_sample`, written by `formatValue`.
 *
 * **Disagreement** is the one place the page checks the file against itself:
 * step 3's `result` against the sample at the period the trace stands at. They
 * are identical on every node of every fixture this repository carries, which
 * is what a reader should expect and not what a reader should assume. When they
 * differ the panel flags it in amber and shows both, because a producer whose
 * account of a number disagrees with the number is the single most useful thing
 * an audit page can say.
 */

import { DID_NOT_FOLD, NOT_FOLDED, foldNote, isFold, unfolded } from "./fold";
import { comparedAs, isExactInteger } from "./exact";
import { formatFormula, formatValue, isIntegerDtype, settingsInWords } from "./format";
import type { Index } from "./index";
import { windowLabel } from "./periods";
import { sharesOf } from "./share";
import type { ArtifactNode, Increment, TraceStep } from "./types";

/** The six shapes a worked example takes, plus the two a node without one takes. */
export type Idiom =
  | "arithmetic"
  | "conditional"
  | "lookup"
  | "accumulation"
  | "rollforward"
  | "hole"
  | "leaf";

/** One line of the panel. `operand` names a node; `offset` is the file's, never inferred. */
export interface ProofLine {
  kind:
    | "formula"
    | "substitution"
    | "lowered"
    | "share"
    | "result"
    | "note"
    | "fired"
    | "dead"
    | "excerpt"
    | "convention"
    | "fold"
    | "check";
  text: string;
  operand?: string;
  offset?: number;
  /**
   * The window the read states (§9), where it states one: `first…t` for a
   * cumulative read, `[0]` for a literal position. The value on the line is
   * still the operand at this period; the window says it is one of a run.
   */
  window?: string;
  /**
   * The page's amber: a statement the file makes that the file does not keep.
   *
   * Only a `check` line carries it, and only when `closing = opening + Σ
   * movements` does not close within the wire's own rounding — which means
   * the movements and the balance beside them are not the same run. It is the
   * same admission the disagreement chip makes about a trace and its sample,
   * drawn on the line it is about.
   */
  flagged?: boolean;
}

/** The excerpt of an inline assumption table around the row the keys name. */
export interface ProofTable {
  name: string;
  fingerprint: string;
  /** Which of `rows` is the hit: 2 in the middle of a table, less at its start. */
  hitRow: number;
  /** The hit and two rows either side, in the payload's own row order. */
  rows: unknown[][];
  header: string[];
}

/** One column's worked example at one period. */
export interface Proof {
  idiom: Idiom;
  nodeId: string;
  period: number;
  lines: ProofLine[];
  /** The trace's `result` differs from the sample at the period the trace stands at. */
  disagreement: boolean;
  table?: ProofTable;
}

/** How many rows of an inline table sit either side of the hit. */
const EITHER_SIDE = 2;

/**
 * The `provenance` of a whole column handed to the model at a known line.
 *
 * The one arrival that carries a place as well as a source, which is why the
 * leaf's sentence branches on it.
 */
const INJECTED = "injected";

/** The reserved id namespace a compilation's running balance sits in (§8.1). */
const STATE_NAMESPACE = "state:";

/** What a waterfall line says where the file carries no number for it. */
const NOT_CARRIED = "not carried";

/**
 * Half of the sixth decimal: how far one rounded term can be from its value.
 *
 * A producer now writes every number as the full double the run held (§8), so
 * a document written today closes its check line to the machine's own
 * arithmetic, far inside this. A document written while the reference producer
 * rounded every number to six decimals is still a document a reader opens, and
 * each of its terms can be up to this far out. The check line's tolerance is
 * this times the number of terms it adds: the budget that document needs, and
 * one a full-precision document passes with room to spare.
 */
const HALF_A_WIRE_DECIMAL = 5e-7;

/**
 * Which worked example a node gets.
 *
 * The order is deliberate, and it matters at two nodes of the level-4 export.
 * `base_lapse_rate@1` and `surr_charge_rate@1` are both a `when(…)` around a
 * table lookup: they read an assumption *and* their formula opens with `when(`.
 * Testing the assumption first makes them lookups, which is the reading that
 * shows the reader the row, and the branch they sit inside is still visible in
 * the formula line above it. Twenty of level 4's formulas open with `when(`;
 * eighteen of them classify `conditional` for that reason.
 *
 * **Read off the record and not through the axis**, `branches` included:
 * whether a column's whole calculation is a conditional is a fact about the
 * model, and a page that classified it per policy would put two different
 * panels under one formula.
 *
 * @param node - The node record, as the file carries it.
 * @returns The idiom its panel takes.
 */
export function classify(node: ArtifactNode): Idiom {
  if (node.kind === "hole") return "hole";
  if (node.kind === "rollforward") return "rollforward";
  if (node.settings !== undefined && node.settings !== null) return "accumulation";
  if (node.reads_assumptions.length > 0) return "lookup";
  const formula = node.formula ?? "";
  if (node.branches !== undefined || formula.trimStart().startsWith("when(")) {
    return "conditional";
  }
  if (node.kind === "computed") return "arithmetic";
  return "leaf";
}

/** The name a column is written under: the file's `column`, or its id where it has none. */
function columnOf(index: Index, id: string): string {
  return index.nodes.get(id)?.column ?? id;
}

/** One node's value at one period: an element of a list, or the scalar itself. */
function valueAt(index: Index, node: ArtifactNode | undefined, period: number): unknown {
  if (node === undefined) return undefined;
  const sample = index.sampleOf(node.id);
  return Array.isArray(sample) ? sample[period] : sample;
}

/** A value written the way the grid writes it, so one number reads one way. */
function written(node: ArtifactNode | undefined, value: unknown): string {
  return formatValue(value, {
    integer: node !== undefined && isIntegerDtype(node.dtype),
  });
}

/**
 * The same, except that on a fold entry an uncovered column says so in words.
 *
 * The grid writes `·` for a value the file does not carry, and a column the
 * fold did not cover is a different claim: the file was asked and there is no
 * such number. Written here as well as there so that a reader following a term
 * from the panel to a cell meets one sentence in both places.
 */
function heldOrNotFolded(
  index: Index,
  node: ArtifactNode | undefined,
  value: unknown,
): string {
  if (node !== undefined && unfolded(index, node.id)) return NOT_FOLDED;
  return written(node, value);
}

/** `net_cf[12]` for a list column, `maturity_month` for a scalar: the file's own shape. */
function subscripted(index: Index, id: string, period: number): string {
  return Array.isArray(index.sampleOf(id))
    ? `${columnOf(index, id)}[${String(period)}]`
    : columnOf(index, id);
}

/**
 * The step the producer numbered `step`, where the trace carries one.
 *
 * The absences are already dealt with by the time a trace reaches here.
 * `trace` is missing on some records, an explicit `null` on others — an input
 * column and a compiled rollforward are both written `"trace": null` — and on
 * an axis of several policies it is an array carrying a null at the position
 * of a policy the producer had no walk-through for. `Index.traceOf` reads all
 * three as the one thing they mean: this node has no worked example for the
 * policy in front of the reader.
 */
function step(trace: TraceStep[] | undefined, wanted: number): TraceStep | undefined {
  if (trace === undefined) return undefined;
  return trace.find((s) => s.step === wanted);
}

/** The last step carrying a `result`, which is the trace's answer. */
function resultStep(trace: TraceStep[] | undefined): TraceStep | undefined {
  if (trace === undefined) return undefined;
  for (let at = trace.length - 1; at >= 0; at -= 1) {
    const candidate = trace[at];
    if (candidate !== undefined && "result" in candidate) return candidate;
  }
  return undefined;
}

/**
 * The period the file's traces stand at.
 *
 * The selected axis entry's `periods` is the list of periods the export sampled
 * at; a trace's `result` is the first of them. Where the export named none —
 * every fixture this repository carries — the traces stand at period 0, which is
 * what each one's own `comment` says ("``result`` is period 0 of 83").
 *
 * Read off the axis entry rather than off `enrichment`, which is the same
 * context stated twice and would be the first entry's whichever policy the
 * reader is standing on.
 *
 * @param index - The index, for the selected policy's context.
 * @returns The period index a trace's `result` belongs to.
 */
export function tracePeriod(index: Index): number {
  const periods = index.policy?.periods;
  return Array.isArray(periods) && periods.length > 0 ? (periods[0] ?? 0) : 0;
}

/** The reads of a node, deduplicated, in the file's own order. */
function operandsOf(index: Index, nodeId: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const source of index.nodes.get(nodeId)?.reads ?? []) {
    if (seen.has(source)) continue;
    seen.add(source);
    out.push(source);
  }
  return out;
}

/**
 * One line per operand: what that column held at the period this node read it.
 *
 * These are the terms the panel lets a reader hover, and the `offset` on a line
 * is the narrowing facet's, so a line pointing at another period says which one
 * and says why. A read pointing off the end of the sampled timeline is written
 * with the same `·` the grid writes for a value the file does not carry.
 *
 * @param index - The index.
 * @param nodeId - The node whose operands these are.
 * @param period - The row cursor.
 * @returns One `substitution` line per read, in the file's order.
 */
function operandLines(index: Index, nodeId: string, period: number): ProofLine[] {
  const lines: ProofLine[] = [];
  for (const source of operandsOf(index, nodeId)) {
    const operand = index.nodes.get(source);
    if (operand === undefined) continue;
    const offset = index.offsetOf(nodeId, source);
    const at = period + (offset ?? 0);
    const line: ProofLine = {
      kind: "substitution",
      text: `${subscripted(index, source, at)} = ${heldOrNotFolded(index, operand, valueAt(index, operand, at))}`,
      operand: source,
    };
    if (offset !== undefined) line.offset = offset;
    const windows = index
      .windowsOf(nodeId, source)
      .map(windowLabel)
      .filter((label): label is string => label !== null);
    if (windows.length > 0) line.window = windows.join(", ");
    lines.push(line);
  }
  return lines;
}

/** One value written so two of them can be compared without arithmetic. */
function canonical(value: unknown): string {
  if (typeof value === "string") return `s:${value}`;
  return JSON.stringify(value) ?? "undefined";
}

/** Every choice of `size` values from `values`, each written canonically and sorted. */
function choices(values: unknown[], size: number): Set<string> {
  const out = new Set<string>();
  const take = (from: number, picked: unknown[]): void => {
    if (picked.length === size) {
      out.add(picked.map(canonical).sort().join("|"));
      return;
    }
    for (let at = from; at < values.length; at += 1) {
      picked.push(values[at]);
      take(at + 1, picked);
      picked.pop();
    }
  };
  take(0, []);
  return out;
}

/** An assumption entry's inline payload, in the shape a table's payload takes. */
interface TablePayload {
  value?: unknown;
  columns?: { name: string }[];
  rows?: unknown[][];
}

/**
 * The row of an inline table the node's key operands name.
 *
 * The file states which table was read (`reads_assumptions`) and which columns
 * the node read (`reads`), but it does not state which operand was passed as
 * which key — that pairing lives in the model's source, in keyword arguments
 * the artifact does not record. So the row is found by the one thing the file
 * does state: a row is named when its key values are exactly the values the
 * node's operands hold at this period, one operand to one key column. Where
 * several rows answer to that, or none does, the panel shows no excerpt and
 * says so. Guessing which of two matching rows was meant would be the page
 * making a claim the file does not support, and a lookup's whole job here is to
 * show the reader a row they can check.
 *
 * Note that the value column is deliberately not used to confirm the hit. A
 * document written while the producer rounded its samples to six decimals has
 * `mortality_scalars` holding 0.9400000000000001 where `mort_scalar@1` samples
 * 0.94, so an equality test there would reject the right row; today's samples
 * are the full double (§8) and would match, but the page reads both.
 *
 * @param payload - The assumption entry's inline payload.
 * @param operandValues - What each of the node's reads held at this period.
 * @returns The hit's index in `payload.rows`, or -1 where no single row answers.
 */
function hitRowIn(payload: TablePayload, operandValues: unknown[]): number {
  const columns = payload.columns ?? [];
  const rows = payload.rows ?? [];
  const keys: number[] = [];
  columns.forEach((column, at) => {
    if (column.name !== payload.value) keys.push(at);
  });
  if (keys.length === 0 || keys.length > operandValues.length) return -1;

  const wanted = choices(operandValues, keys.length);
  let found = -1;
  for (let at = 0; at < rows.length; at += 1) {
    const row = rows[at] ?? [];
    const key = keys
      .map((column) => canonical(row[column]))
      .sort()
      .join("|");
    if (!wanted.has(key)) continue;
    // A second row answering to the same keys means the page cannot say which
    // one was read, and saying neither is the honest answer.
    if (found >= 0) return -1;
    found = at;
  }
  return found;
}

/** The three lines every node with a trace opens with: what it says, and what it said. */
function tracedLines(index: Index, node: ArtifactNode, period: number): ProofLine[] {
  const lines: ProofLine[] = [];
  const formula = formatFormula(node.formula);
  const trace = index.traceOf(node.id);
  const first = formula === "" ? (step(trace, 1)?.expr ?? "") : formula;
  if (first !== "") lines.push({ kind: "formula", text: first });
  const substituted = step(trace, 2)?.expr;
  // Its own kind, and not `substitution`, because it is not the worked
  // example — it is the lowered expression the producer actually ran,
  // `repeat_by` and `_pow(0.0833…)` and all. Both used to be labelled
  // "with values", which put a machine's sentence where an actuary looks
  // for their own arithmetic. It is kept because a reviewer may want
  // exactly it, and folded because they will ask for it rather than read
  // past it.
  if (substituted !== undefined) lines.push({ kind: "lowered", text: substituted });
  lines.push(...operandLines(index, node.id, period));
  return lines;
}

/**
 * The result line: the element of `value_sample` the cursor sits on, and nothing else.
 *
 * Except on a fold entry the fold did not cover, where there is no element and
 * never was one. The line then says so rather than printing the mark a missing
 * value wears, because a reviewer reads that mark as nothing and nothing in a
 * column of money reads as a zero.
 */
function resultLine(index: Index, node: ArtifactNode, period: number): ProofLine {
  if (unfolded(index, node.id)) return { kind: "fold", text: DID_NOT_FOLD };
  return { kind: "result", text: written(node, valueAt(index, node, period)) };
}

/**
 * The line saying this number is the book folded rather than one policy's arithmetic.
 *
 * The entry's own sentence, which already records the fold and how many
 * policies went into it, so the panel and the switcher say one thing rather
 * than two that usually agree. Nothing where the reader is standing on a
 * policy, and nothing on a column the fold did not cover — that column's line
 * is the one above.
 */
function foldLines(index: Index, node: ArtifactNode): ProofLine[] {
  const entry = index.policy;
  if (entry === null || !isFold(entry) || unfolded(index, node.id)) return [];
  return [{ kind: "fold", text: foldNote(entry) }];
}

/** Which branch fired, and what the other one would have held. */
function conditionalLines(index: Index, node: ArtifactNode, period: number): ProofLine[] {
  const branches = index.branchesOf(node.id);
  if (branches === undefined) {
    return [
      {
        kind: "note",
        text:
          "the export states only the branch that fired. Run calc-graph with --branches " +
          "and this panel names it and shows what the other branch would have held.",
      },
    ];
  }
  const chosen = Array.isArray(branches.fired) ? branches.fired[period] : branches.fired;
  const fired = chosen === "then" ? "then" : "otherwise";
  const dead = fired === "then" ? "otherwise" : "then";
  const value = (branch: unknown): unknown => (Array.isArray(branch) ? branch[period] : branch);
  return [
    { kind: "fired", text: `${fired} = ${written(node, value(branches[fired]))}` },
    { kind: "dead", text: `${dead} = ${written(node, value(branches[dead]))}` },
  ];
}

/**
 * The sentence for a column that read several assumption bases.
 *
 * Every base is named, with its own fingerprint, because each is a table the
 * run genuinely read and a reader checking a quarter's pack against the
 * document has to be able to find all of them. What the sentence does not do
 * is pick one: a conditional chooses per row, and which base a particular row
 * took is a fact the file records nowhere -- the condition lives in the
 * formula's text and the bases are keyed by content digest.
 *
 * @param index - The index the page is a function of.
 * @param names - The bases the node read, as the file names them.
 * @returns One note naming them all.
 */
function severalBasesLine(index: Index, names: string[]): ProofLine {
  const named = names.map((name) => {
    const entry = index.tables.get(name) as { fingerprint?: string } | undefined;
    const stamp = entry?.fingerprint;
    return stamp === undefined ? name : `${name} (${stamp})`;
  });
  return {
    kind: "note",
    text:
      `this column read ${String(names.length)} assumption bases and its formula ` +
      `chooses between them row by row: ${named.join(", ")}. The file does not ` +
      "record which of them this row took, so the panel names them all rather " +
      "than picking one.",
  };
}

/** The excerpt around the hit, or the sentence saying why there is none. */
function lookupParts(
  index: Index,
  node: ArtifactNode,
  period: number,
): { lines: ProofLine[]; table?: ProofTable } {
  const names = node.reads_assumptions;
  const name = names[0];
  if (name === undefined) return { lines: [] };
  // A node that read several bases is a formula choosing between them per
  // row -- three rate curves picked on `scenario_id`, say -- and naming the
  // first as though it were *the* table read is the panel stating something
  // the file does not. Which one this row used is not in the file: the
  // condition is in the formula's text and the bases are named by digest, and
  // nothing joins the two. So the chip names every one of them and says the
  // formula chose, which is exactly what the document supports.
  if (names.length > 1) return { lines: [severalBasesLine(index, names)] };
  const entry = index.tables.get(name) as
    | { name?: string; kind?: string; fingerprint?: string; payload?: TablePayload }
    | undefined;
  const payload = entry?.payload;
  const rows = payload?.rows;
  const columns = payload?.columns;
  if (entry === undefined) {
    return {
      lines: [{ kind: "note", text: `the file names ${name} but carries no entry for it.` }],
    };
  }
  if (payload === undefined || !Array.isArray(rows) || !Array.isArray(columns)) {
    return {
      lines: [
        {
          kind: "note",
          text:
            `the file records ${name} as a ${entry.kind ?? "reference"} and carries its ` +
            "settings rather than rows, so there is no row to quote here.",
        },
      ],
    };
  }

  const operandValues = operandsOf(index, node.id).map((source) => {
    const operand = index.nodes.get(source);
    return valueAt(index, operand, period + (index.offsetOf(node.id, source) ?? 0));
  });
  const hit = hitRowIn(payload, operandValues);
  if (hit < 0) {
    return {
      lines: [
        {
          kind: "note",
          text:
            `no single row of ${name} is named by the values the file records this column ` +
            "reading at this period, so the panel quotes none. A key the formula passed as " +
            "a literal is not a read, and the export does not carry it.",
        },
      ],
    };
  }

  const from = Math.max(0, hit - EITHER_SIDE);
  const to = Math.min(rows.length - 1, hit + EITHER_SIDE);
  return {
    lines: [
      {
        kind: "excerpt",
        text: `${name} — the row those keys name, with ${String(EITHER_SIDE)} rows either side`,
      },
    ],
    table: {
      name: entry.name ?? name,
      fingerprint: entry.fingerprint ?? "",
      hitRow: hit - from,
      rows: rows.slice(from, to + 1),
      header: columns.map((column) => column.name),
    },
  };
}

/**
 * The recurrence one step of an accumulation takes, with the numbers in it.
 *
 * `cumulative_survival` records its convention in two members. `start_at` says
 * whether the series opens before any decrement has been applied — a number
 * means it does, which is beginning-of-period and puts period *t*'s value one
 * rate behind, so the rate read is the one at *t−1*; `null` means it does not,
 * which is end-of-period and reads the rate at *t*. `from_survival` says what
 * the operand holds: `false` means decrement rates, so a period's factor is
 * `1 − rate`; `true` means the column already holds survival-shaped factors and
 * they cumulate as they are, with no inversion anywhere. No fixture in this
 * repository carries `from_survival: true`, so the second branch is written
 * from the method's own contract rather than from a measured file, and it is
 * written rather than omitted because omitting it would leave the panel
 * printing the wrong recurrence for a persistency column without saying so.
 *
 * @param index - The index.
 * @param node - The accumulating node.
 * @param period - The row cursor.
 * @returns The recurrence line, or the note that stands where it cannot be written.
 */
function recurrenceLine(index: Index, node: ArtifactNode, period: number): ProofLine {
  const settings = node.settings ?? {};
  const startAt = "start_at" in settings ? settings["start_at"] : undefined;
  const fromSurvival = settings["from_survival"] === true;
  const source = operandsOf(index, node.id)[0];
  const operand = source === undefined ? undefined : index.nodes.get(source);
  const read = startAt === null ? period : period - 1;

  if (operand === undefined || source === undefined) {
    return {
      kind: "note",
      text: "the file records no column for this accumulation to read, so there is no step to write.",
    };
  }
  if (period < 1 || read < 0) {
    return {
      kind: "note",
      text:
        `period ${String(period)} opens the series: settings record start_at as ` +
        `${JSON.stringify(startAt) ?? "nothing"}, and there is no earlier period to read.`,
    };
  }

  const self = columnOf(index, node.id);
  const previous = `${self}[${String(period - 1)}]`;
  const rate = `${columnOf(index, source)}[${String(read)}]`;
  const factor = fromSurvival ? rate : `(1 − ${rate})`;
  const previousValue = written(node, valueAt(index, node, period - 1));
  const rateValue = written(operand, valueAt(index, operand, read));
  const factorValue = fromSurvival ? rateValue : `(1 − ${rateValue})`;
  return {
    kind: "substitution",
    text:
      `${self}[${String(period)}] = ${previous} × ${factor} = ` +
      `${previousValue} × ${factorValue}`,
  };
}

/**
 * The waterfall: opening, one line per step of the chain, closing, and the check.
 *
 * **This panel used to say the export did not carry the movements.** That was
 * true for as long as it said it: a compiled rollforward published its
 * identity, what it read and the movements it applies in the abstract, and the
 * amounts stayed inside the kernel. A rollforward is audited by exactly one
 * question — walk me from opening to closing for this period — and the page
 * could not answer it. The producer carries them now and the sentence is gone.
 * What has not changed is that **nothing here computes**: every line below is a
 * number quoted off the file.
 *
 * The check line is the one exception and it is deliberate. `closing = opening
 * + Σ movements` is the definition of a rollforward rather than a calculation
 * of the model's, every term in it is quoted, and the page states it so a
 * reader can watch it hold. Where it does not hold the panel says so, because
 * the movements and the balance are then not the same run. Where a term is one
 * of the integers this page keeps as digits the line cannot be stated at all,
 * and the panel now says that too rather than leaving a reader to notice the
 * absence.
 *
 * A chain carrying two balances draws two waterfalls. A movement lands on a
 * balance, and two balances added together is not a quantity — so the steps
 * are grouped by the `target` each summary entry states, in the order the
 * chain applies them.
 */
function rollforwardLines(index: Index, node: ArtifactNode, period: number): ProofLine[] {
  const states = node.states ?? [];
  const increments = node.increments ?? [];
  const moved = index.movementsOf(node.id);
  const lines: ProofLine[] = [
    {
      kind: "note",
      text:
        states.length === 0
          ? "the file lists no states for this rollforward."
          : `the states it runs: ${states.join(", ")}`,
    },
  ];
  if (increments.length === 0 || moved.size === 0) {
    lines.push({
      kind: "note",
      text:
        "the file carries no movements for this compilation, so this panel stops at the " +
        "states: what it holds is the machine's identity and not what it moved.",
    });
    return lines;
  }
  for (const target of targetsOf(increments)) {
    lines.push(...waterfall(index, increments, moved, target, period));
  }
  return lines;
}

/** Each balance the chain lands on, in the order its first step reaches it. */
function targetsOf(increments: Increment[]): string[] {
  const seen = new Set<string>();
  for (const increment of increments) seen.add(increment.target);
  return [...seen];
}

/** One balance's waterfall at one period, every term of it quoted. */
function waterfall(
  index: Index,
  increments: Increment[],
  moved: Map<string, unknown>,
  target: string,
  period: number,
): ProofLine[] {
  const balance = index.nodes.get(`${STATE_NAMESPACE}${target}`);
  const steps = increments.filter((increment) => increment.target === target);
  const closing = valueAt(index, balance, period);
  // §16's own rule for the opening: what a period opened at is what the last
  // one closed at. Period 0 opens at the state's initial value, and the audit
  // profile does not carry that — so the line names it rather than printing a
  // number the page has not got.
  const opening = period < 1 ? undefined : valueAt(index, balance, period - 1);
  const lines: ProofLine[] = [
    { kind: "fold", text: `${target}, period ${String(period)}` },
    { kind: "substitution", text: `opening   ${openingText(opening, target, period)}` },
  ];
  let sum = 0;
  let quoted = typeof opening === "number";
  // The terms the sum cannot take, in the order the waterfall draws them, so
  // that a withheld check line can name what withheld it.
  const asDigits: string[] = [];
  if (isExactInteger(opening)) asDigits.push("the opening");
  for (const step of steps) {
    const amount = amountAt(moved.get(movementKey(step)), period);
    if (typeof amount === "number") sum += amount;
    else quoted = false;
    if (isExactInteger(amount)) asDigits.push(stepLabel(step));
    lines.push({
      kind: "substitution",
      text: `${stepLabel(step)}   ${amount === undefined ? NOT_CARRIED : formatValue(amount)}`,
    });
  }
  lines.push({
    kind: "result",
    text: `closing   ${closing === undefined ? NOT_CARRIED : formatValue(closing)}`,
  });
  if (isExactInteger(closing)) asDigits.push("the closing");
  if (quoted && typeof closing === "number" && typeof opening === "number") {
    lines.push(checkLine(opening, sum, closing, steps.length));
  } else if (asDigits.length > 0) {
    lines.push(checkWithheldNote(asDigits));
  }
  return lines;
}

/** What the opening line says when the file does not carry a number for it. */
function openingText(opening: unknown, target: string, period: number): string {
  if (opening !== undefined) return formatValue(opening);
  if (period < 1) {
    return "the state's own initial value, which the audit profile does not carry";
  }
  return `${NOT_CARRIED} — no balance for ${target} at period ${String(period - 1)}`;
}

/**
 * The key one step's amount is filed under, derived the way the kernel names it.
 *
 * The author's label where the step carries one; `{operation}@{ordinal}` where
 * it does not, because a `Floor` and a `Round` have no field for a name. The
 * ordinal is the summary's own, which is what makes the summary row and the
 * amount one step rather than two.
 */
function movementKey(increment: Increment): string {
  if (increment.label !== null && increment.label !== "") return increment.label;
  return `${increment.operation.toLowerCase()}@${String(increment.ordinal)}`;
}

/**
 * How a step's line is labelled: the name the kernel filed its amount under.
 *
 * **No `+` or `−` in front of it**, and that is deliberate against the obvious
 * alternative. A waterfall drawn on paper puts the operator beside each row and
 * the magnitude after it, which means printing `|amount|` — and taking an
 * absolute value is the page computing, which is the one thing this module does
 * not do. The amount is signed on the file, §16.2 says which way, and the sign
 * travels in the number where the producer put it. A prefix beside a signed
 * number would either repeat the sign or contradict it.
 */
function stepLabel(increment: Increment): string {
  return movementKey(increment);
}

/** One movement's amount at one period: an element of its timeline, or the value. */
function amountAt(along: unknown, period: number): unknown {
  if (along === undefined) return undefined;
  return Array.isArray(along) ? along[period] : along;
}

/**
 * `closing = opening + Σ movements`, with the numbers, and whether it holds.
 *
 * **The tolerance is the older wire's, not the machine's.** A document
 * written today carries every term as the full double (§8), and its residual
 * is the machine's own addition, far inside the budget. A document written
 * while the producer rounded each term to six decimals can show a residual
 * bounded by how many rounded numbers the identity adds up — the opening, the
 * closing, and one per movement, each at most half a sixth decimal out — and
 * the page still opens those, so that is the budget. Machine epsilon would flag
 * every such document; a tolerance loose enough to be safe against that would
 * flag none.
 */
function checkLine(opening: number, sum: number, closing: number, terms: number): ProofLine {
  const rounded = terms + 2;
  const residual = Math.abs(closing - (opening + sum));
  const holds = residual <= rounded * HALF_A_WIRE_DECIMAL;
  return {
    kind: "check",
    ...(holds ? {} : { flagged: true }),
    text:
      `closing = opening + Σ movements   ` +
      `${formatValue(closing)} = ${formatValue(opening)} + ${formatValue(sum)}` +
      (holds
        ? ""
        : ` — and it does not. The two are ${formatValue(residual)} apart, more than the ` +
          `${String(rounded)} rounded terms of this line can account for, so the movements ` +
          "and the balance are not the same run."),
  };
}

/**
 * Why there is no check line, where a term is an integer kept as digits.
 *
 * Withholding the line is right: an `ExactInteger` is the file's digits beside
 * a double that is not the file's number, and adding the double would put a
 * figure on the screen the document does not hold — a wide integer rounded to a double,
 * committed by the one sum this panel is allowed to make. Saying nothing was
 * not right. The panel drew every term and then stopped, and from the outside a
 * check the page declined is indistinguishable from one it forgot, on the
 * single arithmetic a rollforward is audited by.
 *
 * So the reason is written, and it names the term: which figure is the one the
 * page will not add is the first thing a reader asks, and it is already on the
 * screen a line or two above, grouped and whole.
 */
function checkWithheldNote(terms: string[]): ProofLine {
  const last = terms[terms.length - 1] ?? "";
  const named = terms.length === 1 ? last : `${terms.slice(0, -1).join(", ")} and ${last}`;
  return {
    kind: "note",
    text:
      `no check line: ${named} ${terms.length === 1 ? "is an integer" : "are integers"} the page ` +
      "keeps as digits and does not add, so closing = opening + Σ movements is not stated for " +
      "this period.",
  };
}

/** The one sentence a hole gets: the column is unaccounted for, and why the file says so. */
function holeLines(index: Index, node: ArtifactNode): ProofLine[] {
  const column = node.column ?? node.id;
  const hole = index.holesByColumn.get(column) as { reason?: unknown } | undefined;
  const reason = typeof hole?.reason === "string" ? hole.reason : null;
  return [
    {
      kind: "note",
      text:
        `${column} is unaccounted for: the file records it as a hole` +
        `${reason === null ? "" : `, reason "${reason}"`}` +
        ", and states no lineage for it. There is nothing here to work through.",
    },
  ];
}

/**
 * An input's two lines: what it held, and where the model was handed it from.
 *
 * `injected` gets a sentence of its own, because it is the one arrival that
 * knows *where*. The other three name a source -- a model-points file, an
 * assumption base, a re-entry -- and the honest thing to say about them is
 * which. An injected column is a whole column handed over at a line inside
 * the run, and the file carries that line: a scenario axis reads "handed to
 * the model at run_scenarios.py:177", which is the difference between a
 * reader knowing the framework put the column there and a reader believing
 * the book did.
 */
function leafLines(index: Index, node: ArtifactNode, period: number): ProofLine[] {
  return [
    ...foldLines(index, node),
    resultLine(index, node, period),
    { kind: "note", text: arrivalSentence(node) },
  ];
}

/** How an input leaf says where its values came from. */
function arrivalSentence(node: ArtifactNode): string {
  const provenance = node.provenance;
  if (provenance === null) {
    return "an input the model was handed; the file records no provenance for it.";
  }
  if (provenance === INJECTED) {
    const where = node.source_location;
    return where === null
      ? "a whole column handed to the model at a line the file does not record."
      : `a whole column handed to the model at ${where}.`;
  }
  return `an input the model was handed, provenance ${provenance}.`;
}

/**
 * The worked example for one column at one period.
 *
 * @param index - The index the page is a function of.
 * @param nodeId - The selected node, as the file spells it.
 * @param period - The row cursor.
 * @returns The lines, in the order the panel prints them.
 * @throws Error - When the artifact carries no node under that id.
 */
export function proofOf(index: Index, nodeId: string, period: number): Proof {
  const node = index.nodes.get(nodeId);
  if (node === undefined) throw new Error(`the artifact carries no node ${nodeId}`);
  const idiom = classify(node);

  const answer = resultStep(index.traceOf(nodeId));
  const stood = tracePeriod(index);
  const sampled = index.sampleOf(nodeId) !== undefined;
  // `comparedAs` on both, so that an integer too wide for a double is judged
  // on the digits the file spelled rather than on two objects that are never
  // the same object. Without it every i64 column past 2⁵³ would carry a
  // disagreement chip saying the trace and the sample differ, quoting two
  // identical numbers.
  const disagreement =
    answer !== undefined && sampled
      ? !Object.is(comparedAs(answer.result), comparedAs(valueAt(index, node, stood)))
      : false;

  const proof: Proof = { idiom, nodeId, period, lines: [], disagreement };

  if (idiom === "hole") {
    proof.lines = holeLines(index, node);
    return proof;
  }
  if (idiom === "rollforward") {
    proof.lines = rollforwardLines(index, node, period);
    return proof;
  }
  if (idiom === "leaf") {
    proof.lines = leafLines(index, node, period);
    return proof;
  }

  const lines = tracedLines(index, node, period);

  if (idiom === "conditional") lines.push(...conditionalLines(index, node, period));

  if (idiom === "lookup") {
    const parts = lookupParts(index, node, period);
    lines.push(...parts.lines);
    if (parts.table !== undefined) proof.table = parts.table;
  }

  if (idiom === "accumulation") {
    const convention = settingsInWords(node.settings);
    if (convention !== undefined) lines.push({ kind: "convention", text: convention });
    lines.push(recurrenceLine(index, node, period));
  }

  // Where the column is a signed sum of other columns, which term is most of
  // the answer is arithmetic rather than inference — `sharesOf` refuses every
  // other shape, so a line here is a line that could not have been wrong.
  const shares = sharesOf(index, node.id, period);
  if (shares !== null) {
    lines.push({
      kind: "share",
      text: shares
        .map(
          (term) =>
            `${columnOf(index, term.id)} ${String(Math.round(term.share * 100))}%`,
        )
        .join(" · "),
    });
  }

  lines.push(...foldLines(index, node));
  lines.push(resultLine(index, node, period));
  proof.lines = lines;
  return proof;
}
