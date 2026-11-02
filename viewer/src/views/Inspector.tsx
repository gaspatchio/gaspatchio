// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The drawer: the file, flat, in four tabs.
 *
 * The Node tab is the answer to "where exactly is this defined?", and that
 * question sets the rule the whole file follows: **nothing is
 * chosen and nothing is renamed.** Every member of the selected node's record
 * appears, under the name the format gives it, in the order the file writes it.
 * A tab that showed the interesting members would be a page deciding on a
 * reviewer's behalf which parts of a record matter, and the one question this
 * drawer exists to answer is the one where that decision is not the page's.
 *
 * Two members are folded rather than hidden, and the difference is the point. A
 * `value_sample` is eighty-three numbers and a `trace` is three steps of
 * substituted expressions; printed open they push everything under them off the
 * screen, so each is behind a control that says how much is there. The row is
 * always present, always counted, always openable. Folded is a statement about
 * height; omitted would be a statement about relevance.
 *
 * **The same rule decides what those two show on a document carrying several
 * policies, and it decides against convenience.** They show the member as the
 * file writes it — the whole array, aligned to the envelope's axis — and not
 * the selected policy's share of it. Everywhere else on the page a value is a
 * value and the axis has already been read; here the question is what the
 * record says, and a page that quietly printed one entry under the name
 * `value_sample` would have edited the record while claiming to quote it. The
 * axis itself is on the Model tab, where the rest of the envelope is.
 *
 * **The Table tab** is the whole inline payload and not the proof panel's
 * excerpt. The excerpt answers "is this the right row"; this answers "what else
 * is in this table" — the question a reviewer asks when the right row looks
 * wrong. Nine thousand six hundred rows of `mortality_select` is why it is
 * virtualised and why it has a search box. The hit is the proof's hit: the same
 * row, found by the same rule, because two answers to "which row was read"
 * would be one answer too many.
 *
 * **The Model tab** is the envelope, and it is the tab a reviewer opens first.
 * Every fact on it is a member of the file; where the file records none, the row
 * says so rather than disappearing, because a row that vanished when the file
 * was silent would leave a reader unable to tell "not recorded" from "not
 * shown".
 *
 * **The Source tab** shows the model's own text, carried in the file (§7.3), and it is
 * the one tab a reader normally arrives at from somewhere else: the proof's
 * footer names a line and opens this at it. It is fourth because of that — a tab
 * reached from a control rather than gone looking for through the strip — and
 * putting it first would have moved the three that were already there. What it
 * draws lives in `views/Source.tsx`; what this file decides is only that there
 * are four tabs now instead of three.
 *
 * **The Changes tab** is the comparison's, and it exists only on a page carrying two
 * documents. It is the one tab that goes *first*, because on a comparison it is
 * the question the page was opened to ask and every entry on it is a way into
 * the other four. On a page carrying one document the drawer has four tabs and
 * not five with one inert — the policy switcher's rule,
 * which is also what keeps the four scripted reads asserting against the drawer
 * they assert against today. What it draws lives in `views/Changes.tsx`.
 */

import { Fragment, memo, useEffect, useMemo, useRef, useState } from "react";
import type { JSX } from "react";

import { useVirtualizer } from "@tanstack/react-virtual";

import type { Comparison } from "../reader/compare";
import { asWritten } from "../reader/exact";
import { isFold } from "../reader/fold";
import { cellExactly, shortFingerprint } from "../reader/format";
import { descendantsOf, endsReached } from "../reader/impact";
import { locationOf } from "../reader/index";
import type { Index, SourceAt } from "../reader/index";
import { axisSummary } from "../reader/policies";
import { proofOf } from "../reader/proof";
import { gitSaid, modulesSaid, tableShapedSaid, tableSourceSaid, versionsSaid } from "../reader/record";
import type { Said } from "../reader/record";
import { TIERS, tiersOf } from "../reader/tiers";
import type { Artifact } from "../reader/types";
import { COMPARISON_TABS, TABS } from "../state/layout";
import type { InspectorTab } from "../state/layout";
import type { Selection, SelectionAction } from "../state/selection";
import { Changes } from "./Changes";
import { Copy } from "./Copy";
import { Source } from "./Source";

import "./Inspector.css";

/** The members printed folded, because printed open they are the whole drawer. */
const FOLDED = new Set(["value_sample", "trace"]);

/** One payload row's height, in pixels. Tight, as the grid's rows are. */
const ROW_HEIGHT = 22;

/**
 * One member's value, written for a label-and-value row.
 *
 * A string is itself — the file's own text, not a quoted rendering of it. Every
 * other shape is compact JSON, which is the file's own notation and is the one
 * form in which an object and an array are unambiguous. Nothing is truncated:
 * the two members long enough to need it are folded instead.
 *
 * `asWritten` rather than `JSON.stringify`, for the one value that differs: an
 * integer past what a double carries is written bare, as the document writes
 * it, and not as the quoted string it would have to become to survive
 * `JSON.stringify` at all.
 *
 * @param value - The member, as the file carries it.
 * @returns The text to print.
 */
function written(value: unknown): string {
  if (typeof value === "string") return value;
  return asWritten(value);
}

/** How much is behind a fold, said before it is opened. */
function sizeOf(value: unknown): string {
  if (Array.isArray(value)) return `${String(value.length)} entries`;
  if (value === null || value === undefined) return "nothing";
  return "1 entry";
}

/** One member of the node record: its name, and what the file puts against it. */
function Member({ name, value }: { name: string; value: unknown }): JSX.Element {
  const [open, setOpen] = useState(false);
  const folds = FOLDED.has(name);

  return (
    <div className="member" data-member={name}>
      <span className="member-name mono">{name}</span>
      <div>
        {folds ? (
          <button
            type="button"
            className="unfold"
            data-testid="unfold"
            aria-expanded={open}
            onClick={() => { setOpen(!open); }}
          >
            {sizeOf(value)} — {open ? "hide" : "show"}
          </button>
        ) : null}
        {!folds || open ? (
          <span className="member-value mono">{written(value)}</span>
        ) : null}
      </div>
    </div>
  );
}

/** The Node tab. */
/**
 * What moves if this column changes, under the record rather than in it.
 *
 * The block above is the file's own record, key for key. This is not: it is the
 * page reading the edges, and it is separated and said so, because a reviewer
 * who quotes a line out of this drawer needs to know which half of it the
 * producer wrote.
 *
 * Reach and not influence. "Forty-two columns depend on this" is a fact about
 * the edges; "this drives the result" would be a claim about magnitudes the
 * artifact does not carry. So the count is stated, the model's own ends that a
 * change here would travel to are named — which is the part an actuary is
 * actually asking for — and nothing is said about how much any of them move.
 */
function Impact({
  index,
  nodeId,
  dispatch,
}: {
  index: Index;
  nodeId: string;
  dispatch: (action: SelectionAction) => void;
}): JSX.Element {
  const downstream = descendantsOf(index, nodeId);
  const ends = endsReached(index, nodeId);
  const named = (id: string): string => index.nodes.get(id)?.column ?? id;

  return (
    <section className="impact" data-testid="impact">
      <h3 className="impact-head">what moves if this changes</h3>
      {downstream.length === 0 ? (
        <p className="impact-none">
          Nothing reads {named(nodeId)}, so a change here moves nothing else in this model. It is
          where a chain ends.
        </p>
      ) : (
        <>
          <p className="impact-count">
            <b className="mono" data-testid="impact-count">
              {downstream.length}
            </b>{" "}
            {downstream.length === 1 ? "column reads" : "columns read"} this, directly or through
            others.
          </p>
          {ends.length === 0 ? (
            <p className="impact-none" data-testid="impact-ends-none">
              None of them is a column the model stopped at, so a change here does not reach any of
              this model&rsquo;s own ends.
            </p>
          ) : (
            <p className="impact-ends" data-testid="impact-ends">
              <span className="impact-label">reaching</span>
              {ends.map((id) => (
                <button
                  key={id}
                  type="button"
                  className="impact-end mono"
                  data-end={named(id)}
                  onClick={() => {
                    dispatch({ select: id });
                  }}
                >
                  {named(id)}
                </button>
              ))}
            </p>
          )}
        </>
      )}
    </section>
  );
}

function NodeTab({
  index,
  nodeId,
  dispatch,
}: {
  index: Index;
  nodeId: string | null;
  dispatch: (action: SelectionAction) => void;
}): JSX.Element {
  const node = nodeId === null ? undefined : index.nodes.get(nodeId);
  if (node === undefined) {
    return (
      <div className="panel" data-panel="node">
        <p className="prompt">Select a column to see its record.</p>
      </div>
    );
  }
  return (
    <div className="panel" data-panel="node">
      <nav className="impact-ends" data-testid="direct-inputs" aria-label="Direct inputs">
        <span className="impact-label">direct inputs</span>
        {node.reads.length === 0 ? <span>none recorded</span> : node.reads.map((id) => (
          <button
            key={id}
            type="button"
            className="impact-end mono"
            data-input={id}
            onClick={() => { dispatch({ select: id }); }}
          >
            {id}
          </button>
        ))}
      </nav>
      {/* The file's own key order. `Object.keys` preserves it for every key a
          producer writes, which are all strings and none of them integer-like. */}
      {Object.keys(node).map((name) => (
        <Member key={name} name={name} value={(node as unknown as Record<string, unknown>)[name]} />
      ))}
      {nodeId === null ? null : <Impact index={index} nodeId={nodeId} dispatch={dispatch} />}
    </div>
  );
}

/** An assumption entry's inline payload, in the shape a table's payload takes. */
interface TablePayload {
  columns?: { name: string }[];
  rows?: unknown[][];
}

/** One cell, as the payload holds it. The same rule as the proof's excerpt. */
function cell(value: unknown): string {
  if (value === null || value === undefined) return "·";
  return typeof value === "string" ? value : asWritten(value);
}

/** The Table tab. */
function TableTab({
  index,
  selection,
}: {
  index: Index;
  selection: Selection;
}): JSX.Element {
  const [query, setQuery] = useState("");
  const scroll = useRef<HTMLDivElement>(null);
  const nodeId = selection.nodeId;
  const node = nodeId === null ? undefined : index.nodes.get(nodeId);
  const name = node?.reads_assumptions[0];
  const entry = name === undefined ? undefined : index.tables.get(name);
  const known = entry as { kind?: string; fingerprint?: string; payload?: TablePayload } | undefined;
  const payload = known?.payload;
  const rows = Array.isArray(payload?.rows) ? payload.rows : [];
  const header = Array.isArray(payload?.columns) ? payload.columns.map((c) => c.name) : [];
  const shaped = tableShapedSaid(entry);

  // The proof's hit, not a second search for it: one rule for "which row was
  // read", stated once, in the reader.
  const hit = useMemo(() => {
    if (nodeId === null || rows.length === 0) return -1;
    const table = proofOf(index, nodeId, selection.period).table;
    if (table === undefined) return -1;
    const named = table.rows[table.hitRow];
    return named === undefined ? -1 : rows.indexOf(named);
  }, [index, nodeId, selection.period, rows]);

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const all = rows.map((_row, at) => at);
    if (needle === "") return all;
    return all.filter((at) =>
      (rows[at] ?? []).some((value) => cell(value).toLowerCase().includes(needle)),
    );
  }, [rows, query]);

  const virtual = useVirtualizer({
    count: shown.length,
    getScrollElement: () => scroll.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });

  // Open on the row that was read. Nine thousand six hundred rows scrolled to
  // the top is a table with the answer in it and no way to see the answer; the
  // reviewer came here from a hit and the hit is where the table opens. Any
  // other scrolling after that is theirs.
  const hitAt = shown.indexOf(hit);
  useEffect(() => {
    if (hitAt >= 0) virtual.scrollToIndex(hitAt, { align: "center" });
  }, [hitAt, virtual]);

  if (node === undefined) {
    return (
      <div className="panel" data-panel="table">
        <p className="prompt">Select a column to see the table it reads.</p>
      </div>
    );
  }

  if (name === undefined) {
    return (
      <div className="panel" data-panel="table">
        <p className="prompt">
          {node.column ?? node.id} reads no assumption: its reads_assumptions is empty, so there
          is no table to show here.
        </p>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="panel" data-panel="table">
        <p className="prompt">
          The file names {name} and records it as a {known?.kind ?? "reference"}, carrying its
          settings rather than rows, so there are no rows to show here.
        </p>
      </div>
    );
  }

  const drawn = virtual.getVirtualItems();
  const first = drawn[0];
  const last = drawn[drawn.length - 1];
  const above = first === undefined ? 0 : first.start;
  const below = last === undefined ? 0 : virtual.getTotalSize() - last.end;

  return (
    <div className="panel table-panel" data-panel="table">
      <div className="table-head">
        <span className="table-name" data-testid="table-name">
          {name}
        </span>
        <span className="chip fingerprint-chip mono" title={known?.fingerprint ?? ""}>
          <span data-testid="table-fingerprint">{shortFingerprint(known?.fingerprint ?? "")}</span>
        </span>
        <span className="table-size">
          <b className="mono" data-testid="table-rows">
            {rows.length}
          </b>{" "}
          rows
        </span>
      </div>
      {/* Where the table was read from, and whether it is a plain read of that
          file: what a reviewer holding the file needs before re-reading it,
          and what `gspio verify --assumptions` holds it to. */}
      <p className="table-source" data-testid="table-source">
        {tableSourceSaid(entry)}
      </p>
      {shaped === null ? null : (
        <p className="table-shaped" data-testid="table-shaped">
          {shaped}
        </p>
      )}
      <div className="table-search">
        <input
          type="search"
          data-testid="table-search"
          placeholder="Filter rows"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
        />
        <span className="table-matches">
          <b className="mono" data-testid="table-matches">
            {shown.length}
          </b>{" "}
          shown
        </span>
      </div>
      <div className="table-scroll" ref={scroll}>
        <table className="payload mono">
          <thead>
            <tr>
              {header.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {above > 0 ? (
              <tr style={{ height: above }}>
                <td colSpan={header.length} />
              </tr>
            ) : null}
            {drawn.map((item) => {
              const at = shown[item.index] ?? 0;
              return (
                <tr
                  key={at}
                  style={{ height: ROW_HEIGHT }}
                  {...(at === hit ? { "data-hit": "true" } : {})}
                >
                  {(rows[at] ?? []).map((value, column) => (
                    <td key={`cell-${String(at)}-${String(column)}`}>{cell(value)}</td>
                  ))}
                </tr>
              );
            })}
            {below > 0 ? (
              <tr style={{ height: below }}>
                <td colSpan={header.length} />
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** One fact of the envelope: what it is called, and what the file says it is. */
function Fact({
  name,
  label,
  value,
  title,
}: {
  name: string;
  label: string;
  value: string;
  /** The whole value, where `value` is a shortened one. */
  title?: string | undefined;
}): JSX.Element {
  return (
    <div className="fact-row" data-fact={name}>
      <span className="fact-name">{label}</span>
      <span className="fact-value mono" {...(title === undefined ? {} : { title })}>
        {value}
      </span>
    </div>
  );
}

/** Several facts the record reader worded, in the order it gave them. */
function Facts({ said }: { said: Said[] }): JSX.Element {
  return (
    <>
      {said.map((fact) => (
        <Fact key={fact.name} name={fact.name} label={fact.label} value={fact.value} title={fact.title} />
      ))}
    </>
  );
}

/**
 * The envelope's producer, without the library its `versions` member states.
 *
 * Those have a section of their own, one fact per key, and printing them a
 * second time here as one line of JSON would be the same facts twice.
 */
function producerWithoutVersions(producer: unknown): unknown {
  if (typeof producer !== "object" || producer === null || !("versions" in producer)) return producer;
  const { versions: _versions, ...rest } = producer as Record<string, unknown>;
  return rest;
}

/** What the file says, or the sentence saying it says nothing. */
function said(value: unknown, absent: string): string {
  if (value === null || value === undefined) return absent;
  return written(value);
}

/**
 * The book's digest, or which of the two absences this file is (§7.5).
 *
 * A file written before the member existed says nothing about its book; a
 * producer that held no book, or could not read it, says so in the member.
 * Those are different sentences, and the drawer prints the one the file wrote.
 */
function bookSaid(book: Artifact["book"]): string {
  if (book === undefined) return "no book recorded";
  if (typeof book.digest === "string") return book.digest;
  const why = book.digest.detail;
  return why === undefined ? "the producer could not vouch for its book" : `not vouched for: ${why}`;
}

/**
 * The tier census, beside the holes, so that the two lines are not read as one.
 *
 * "No holes — every column is accounted for" is true of a model with a line
 * written in an engine's own expression language: that line is recorded, so
 * nothing is unaccounted for, and it is still a line only that engine can run.
 * A reader who meets the holes line alone reads it as the stronger claim, so
 * the census stands under it and says how many of the calculations sit at each
 * tier, naming every one below core. Each name selects its node.
 *
 * Where the file states no census the row says why, as every row on this tab
 * does rather than disappearing: no node carries a tier at all, or one
 * calculation carries none the format defines, which is named with what it
 * carries instead.
 */
function TiersFact({
  index,
  dispatch,
}: {
  index: Index;
  dispatch: (action: SelectionAction) => void;
}): JSX.Element {
  const read = useMemo(() => tiersOf(index.artifact), [index.artifact]);
  let value: JSX.Element | string;
  if (read === null) value = "no tiers recorded";
  else if ("untiered" in read) {
    value =
      read.tier === null || read.tier === undefined
        ? `no census — ${read.untiered} computes and carries no tier`
        : `no census — ${read.untiered} carries the tier ${asWritten(read.tier)}, ` +
          "which this page does not know";
  } else {
    const { census } = read;
    value = (
      <>
        {TIERS.map((tier, at) => (
          <span key={tier} data-tier={tier}>
            {at === 0 ? "" : ", "}
            {census[tier].length} {tier}
            {tier === "core" || census[tier].length === 0 ? null : (
              <>
                {" ("}
                {census[tier].map((id, named) => (
                  <Fragment key={id}>
                    {named === 0 ? null : ", "}
                    <button
                      type="button"
                      className="impact-end"
                      data-node={id}
                      onClick={() => {
                        dispatch({ select: id });
                      }}
                    >
                      {id}
                    </button>
                  </Fragment>
                ))}
                {")"}
              </>
            )}
          </span>
        ))}
      </>
    );
  }
  return (
    <div className="fact-row" data-fact="tiers">
      <span className="fact-name">tiers</span>
      <span className="fact-value mono">{value}</span>
    </div>
  );
}

/**
 * The Model tab.
 *
 * The values block is the **selected** entry of §7.4's axis, under that entry's
 * own path in the file. It used to be `enrichment`, which was the same object
 * while a document could only carry one policy and is `policies[0]` now that it
 * can carry several — so a page that kept printing it would have gone on saying
 * "policy 1" while the strip said policy 3, and a reviewer quoting the drawer
 * would have quoted the wrong model point. The entry's `why` is here for a
 * second reason: it is where a reader of a single-policy file meets it, that
 * file drawing no switcher to read it off.
 */
function ModelTab({
  index,
  dispatch,
}: {
  index: Index;
  dispatch: (action: SelectionAction) => void;
}): JSX.Element {
  const file = index.artifact;
  const model = file.model;
  const entry = index.policy;
  const where = `policies[${String(index.at)}]`;
  const holes = file.holes as { column?: string; reason?: string; closes_with?: string }[];
  const git = gitSaid(model.git);

  return (
    <div className="panel" data-panel="model">
      <h3>the model</h3>
      <Fact name="model.source_path" label="source" value={said(model.source_path, "no model file recorded")} />
      <Fact name="model.source_sha" label="source sha" value={said(model.source_sha, "no source sha recorded")} />
      <Fact
        name="model.results.path"
        label="results"
        value={said(model.results?.path, "no results file recorded — export with --results")}
      />
      <Fact
        name="model.results.fingerprint"
        label="results sha"
        value={said(model.results?.fingerprint, "no results fingerprint recorded")}
      />
      <Fact
        name="model.model_points.path"
        label="model points"
        value={said(model.model_points?.path, "no model points recorded")}
      />
      <Fact
        name="model.model_points.fingerprint"
        label="points sha"
        value={said(model.model_points?.fingerprint, "no model points fingerprint recorded")}
      />
      <Fact name="book.digest" label="book" value={bookSaid(file.book)} />
      <Fact
        name="book.columns"
        label="book columns"
        value={file.book === undefined ? "no book recorded" : file.book.columns.join(", ") || "none"}
      />
      <Fact name="model.git.commit" label="git commit" value={git.commit} />
      <Fact name="model.git.dirty" label="git dirty" value={git.dirty} />

      <h3>the model&rsquo;s own files</h3>
      <Facts said={modulesSaid(model.modules)} />

      <h3>the library</h3>
      <Facts said={versionsSaid(file.producer)} />

      <h3>the file</h3>
      <Fact name="schema" label="schema" value={file.schema} />
      <Fact name="profile" label="profile" value={file.profile} />
      <Fact name="fingerprint_algorithm" label="algorithm" value={file.fingerprint_algorithm} />
      <Fact name="graph_fingerprint" label="graph" value={file.graph_fingerprint} />
      <p className="fact-covers" data-testid="covers-graph">
        the model as run: its formulas and the tables, curves and schedules they read
      </p>
      <Fact
        name="formulas_fingerprint"
        label="formulas"
        value={said(file.formulas_fingerprint, "not recorded — the file was written before the figure")}
      />
      <p className="fact-covers" data-testid="covers-formulas">
        its formulas alone: a re-sourced table, curve or schedule leaves this where it was
      </p>
      <Fact name="document_digest" label="document" value={said(file.document_digest, "no document digest recorded")} />
      <Fact name="created_at" label="created" value={file.created_at} />
      <Fact name="producer" label="producer" value={written(producerWithoutVersions(file.producer))} />

      <h3>the values, and what they are of</h3>
      <Fact
        name="policies"
        label="on the axis"
        value={axisSummary(index.policies)}
      />
      <Fact
        name={`${where}.policy_id`}
        label="policy"
        value={entry === null
          ? "no policy — this file carries no values"
          : isFold(entry) ? "portfolio fold"
          : said(entry.policy_id, "no id recorded")}
      />
      <Fact
        name={`${where}.why`}
        label="why"
        value={said(entry?.why, "no reason recorded — this file carries no values")}
      />
      <Fact
        name={`${where}.aggregation`}
        label="aggregation"
        value={said(entry?.aggregation, "none — one policy, not a fold over the book")}
      />
      <Fact
        name={`${where}.periods`}
        label="periods"
        value={said(entry?.periods, "every period the projection ran")}
      />
      <Fact name={`${where}.filter`} label="filter" value={said(entry?.filter, "no filter")} />

      <h3>what the model does not account for</h3>
      {holes.length === 0 ? (
        <Fact name="holes" label="holes" value="no holes — every column is accounted for" />
      ) : (
        holes.map((hole, at) => (
          <div
            className="hole-row"
            key={hole.column ?? `hole-${String(at)}`}
            data-hole={hole.column ?? ""}
          >
            <span className="fact-name mono">{hole.column ?? "unnamed column"}</span>
            <span className="fact-value">{hole.reason ?? "no reason recorded"}</span>
            {hole.closes_with === undefined ? null : (
              <span className="hole-closes">{hole.closes_with}</span>
            )}
          </div>
        ))
      )}
      <TiersFact index={index} dispatch={dispatch} />
    </div>
  );
}

/**
 * Where the Source tab opens when nothing has named a line.
 *
 * A reader who clicked the tab rather than arriving from the proof's footer is
 * asking about the column they have selected, so the tab opens on that column's
 * own location. With no column selected it falls back to the file the envelope
 * names as the model, which is the one file every artifact of a run has. Both
 * are read off the document; neither invents a path.
 *
 * @param index - The file, indexed.
 * @param selection - Where the reader is looking.
 * @param at - The line a control named, which wins over both.
 * @returns The file and line to open on, or null where the file names none.
 */
function opensAt(index: Index, selection: Selection, at: SourceAt | null): SourceAt | null {
  if (at !== null) return at;
  const node = selection.nodeId === null ? undefined : index.nodes.get(selection.nodeId);
  const own = locationOf(node?.source_location);
  if (own !== null) return own;
  const model = index.artifact.model.source_path;
  return model === null ? null : { path: model, line: null };
}

/**
 * The selected cell, every digit of it: what the file holds where the cursor stands.
 *
 * The grid, the proof and the cone write a value for reading — two decimals,
 * or six significant figures below one — and that is a decision about display
 * the page states here rather than leaves to be found: "shown rounded; the
 * file holds every digit". The line under it is the other answer, the value
 * the document carries at the selected column and period in the file's own
 * spelling (`exactly`), which reads back as the value the results file holds.
 * The control beside it copies those digits and not the rounded text, and so
 * does copying a cell out of the grid.
 *
 * Above the tabs rather than on one of them, because the question it answers
 * is about the cell and not about the record, the table or the envelope, and a
 * reader who selected a cell with the Model tab open has asked it too.
 */
function Held({ index, selection }: { index: Index; selection: Selection }): JSX.Element | null {
  const nodeId = selection.nodeId;
  const node = nodeId === null ? undefined : index.nodes.get(nodeId);
  if (nodeId === null || node === undefined || !index.carriesValues) return null;
  const digits = cellExactly(index, nodeId, selection.period);
  const where = node.shape === "list" ? ` at period ${String(selection.period)}` : "";
  return (
    <div className="held" data-testid="held">
      <p className="held-note" data-testid="held-note">
        shown rounded; the file holds every digit
      </p>
      <p className="held-line">
        <span className="mono">{node.column ?? node.id}</span>
        {where}:{" "}
        {digits === null ? (
          <span data-testid="held-value-none">the file holds no value here</span>
        ) : (
          <>
            the file holds{" "}
            <b className="mono held-value" data-testid="held-value">
              {digits}
            </b>{" "}
            <Copy
              what={() => digits}
              name="value"
              title="copy every digit the file holds for this cell"
              className="copy-held"
              testid="copy-held"
            />
          </>
        )}
      </p>
    </div>
  );
}

/**
 * The two tabs a period step does not reach, each behind a memo.
 *
 * The drawer draws again on every step of the row cursor, because the cell it
 * states above its tabs is the cursor's. The Node tab is the record of the
 * selected column and the Model tab is the envelope, and neither reads the
 * period — but each was drawn again with the drawer: on a scrub with a column
 * selected, the Node tab rebuilt its twenty members and walked the graph for
 * what the column reaches on every one of eighty-three frames, to say what it
 * said before. Their props are the index, the selected column and the
 * dispatcher, which a step moves none of. What they draw is unchanged.
 */
const StillNodeTab = memo(NodeTab);
const StillModelTab = memo(ModelTab);

/** The drawer. */
export function Inspector({
  index,
  selection,
  dispatch,
  tab,
  setTab,
  sourceAt,
  comparison,
}: {
  index: Index;
  selection: Selection;
  dispatch: (action: SelectionAction) => void;
  tab: InspectorTab;
  setTab: (tab: InspectorTab) => void;
  /** The file and line the proof's footer opened this on, where it did. */
  sourceAt: SourceAt | null;
  /** The two documents and what moved between them, on a comparison page. */
  comparison?: Comparison | undefined;
}): JSX.Element {
  return (
    <section className="inspector" data-testid="inspector">
      <div className="tabs" role="tablist">
        {(comparison === undefined ? TABS : COMPARISON_TABS).map((which) => (
          <button
            key={which}
            type="button"
            role="tab"
            className={`tab${which === tab ? " sel" : ""}`}
            data-tab={which}
            aria-selected={which === tab}
            onClick={() => {
              setTab(which);
            }}
          >
            {which}
          </button>
        ))}
      </div>
      <Held index={index} selection={selection} />
      {tab === "changes" && comparison !== undefined ? (
        <Changes comparison={comparison} selected={selection.nodeId} dispatch={dispatch} />
      ) : null}
      {tab === "node" ? (
        <StillNodeTab index={index} nodeId={selection.nodeId} dispatch={dispatch} />
      ) : null}
      {tab === "table" ? <TableTab index={index} selection={selection} /> : null}
      {tab === "model" ? <StillModelTab index={index} dispatch={dispatch} /> : null}
      {tab === "source" ? (
        <Source index={index} at={opensAt(index, selection, sourceAt)} dispatch={dispatch} />
      ) : null}
    </section>
  );
}
