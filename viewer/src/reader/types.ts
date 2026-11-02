// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The calculation-graph artifact's members, as TypeScript types.
 *
 * Every name here is the name the format uses, spelled the way the format
 * spells it: `spec/graph-artifact/v0-preview.md` and the published schema
 * `bindings/python/gaspatchio/schemas/gaspatchio-graph-v0.schema.json`. A
 * reader that renamed a member would be answering "where exactly is this
 * defined?" with its own vocabulary instead of the file's.
 *
 * The types describe; they do not validate. Checking that a file means what it
 * says is `gspio validate`'s job, and the page says so rather than doing it
 * again from a second implementation that could disagree.
 */

/** A node's kind — the published schema's enum, verbatim. */
export type NodeKind =
  | "input"
  | "computed"
  | "hole"
  | "rollforward"
  | "state"
  | "state_graph"
  | "nested_valuation";

/** Whether a node holds one value per policy or one per projection period. */
export type Shape = "scalar" | "list" | "unknown";

/**
 * One end of a read's window (§9): a whole number of periods from the period
 * being computed, or the first or last period of that policy's own run.
 */
export type PeriodBound = number | "first" | "last";

/**
 * How one read was narrowed on its way into the result.
 *
 * `type` and `subtype` are OpenLineage's own key names and spellings; `offset`
 * is the distance in periods between the reading row and the row read, and
 * `periods` and `position` are the window an aggregation or a literal
 * `list.get` read (§9). Those three are the only places the page may learn
 * that a formula looked at another period, or at many.
 */
export interface Narrowing {
  type: "DIRECT" | "INDIRECT";
  subtype: string;
  offset?: number;
  periods?: { from: PeriodBound; to: PeriodBound };
  position?: number;
}

/** One source a node read, with every narrowing that read carried. */
export interface FacetRead {
  source: string;
  transformations: Narrowing[];
}

/**
 * One step of a compiled rollforward's chain, as §16's summary states it.
 *
 * `label` is the author's name for the step and is null on a structural one —
 * a `Floor` or a `Round` carries no field for a name. The key that step's
 * amount is filed under in `movements` is the label where there is one and
 * `{operation lowercased}@{ordinal}` where there is not, which is the join
 * between this summary and the numbers.
 */
export interface Increment {
  ordinal: number;
  label: string | null;
  operation: string;
  target: string;
  reads_running_balance: boolean | null;
}

/** One node record: a column's definition, its lineage and its sampled values. */
export interface ArtifactNode {
  id: string;
  column: string | null;
  version: number | null;
  kind: NodeKind;
  dtype: string;
  shape: Shape;
  provenance: string | null;
  formula: string | null;
  reads: string[];
  reads_assumptions: string[];
  extracts?: unknown;
  engines?: string[];
  tier: string | null;
  local_fingerprint: string;
  fingerprint: string;
  in_final_schema: boolean;
  retained?: boolean;
  materialized_at: number | null;
  source_location: string | null;
  anchors_to?: string | null;
  facets: Record<string, unknown> & {
    gaspatchio_column_transformation?: { reads: FacetRead[] };
  };
  settings?: Record<string, unknown>;
  states?: string[];
  /** One compiled rollforward's steps, in the order the chain applies them. */
  increments?: Increment[];
  /**
   * What each of those steps moved, keyed by the kernel's own name for it.
   *
   * Each value is that step's signed per-period amount in the shape
   * `value_sample` takes: the axis goes *inside* the member, so it is the
   * timeline itself on an axis of one policy and an array of those on an axis
   * of several. Read it through `Index.movementsOf`, which is where that
   * reading happens once.
   */
  movements?: Record<string, unknown>;
  expr?: unknown;
  /**
   * What the column held, for every policy on the envelope's axis.
   *
   * One policy on the axis and this is that policy's value — the number, or
   * the whole timeline for a per-period column. More than one and it is an
   * array of those, exactly as long as `policies` and in its order (§8). The
   * axis is the outermost container, so the two shapes are told apart by the
   * axis's length and never by looking at the value: a scalar column of two
   * policies and a per-period column of one policy are both an array of two
   * numbers, and only the envelope says which is which. Read it through
   * `Index.sampleOf`, which is where that reading happens once.
   */
  value_sample?: unknown;
  /** The worked example, or one per policy on the axis. `Index.traceOf`. */
  trace?: TraceStep[] | (TraceStep[] | null)[] | null;
  /** The branch that did not fire, or one per policy on the axis. `Index.branchesOf`. */
  branches?: Branches | (Branches | null)[];
}

/**
 * What each branch of a conditional would have held, and which one fired.
 *
 * `then` and `otherwise` are each in the shape `value_sample` is written in
 * for this node under one policy — one value for a column holding one per
 * policy, the declared context's every period for a per-period column — so
 * that period 37's value and period 37's alternative are indexed the same
 * way. `fired` names the branch the condition chose, in the two words the
 * formula itself uses: one word beside a single value, one word per period
 * beside a run of them.
 */
export interface Branches {
  then: unknown;
  otherwise: unknown;
  fired: string | string[];
}

/** One line of a worked example, as the producer recorded it. */
export interface TraceStep {
  step: number;
  expr?: string;
  values?: Record<string, unknown>;
  result?: unknown;
}

/**
 * Why a source carries no text — §6.1's three reasons, spelled as the file spells them.
 *
 * Each says something different about the same file. `size` was weighed and is
 * above the producer's inline budget. `unavailable` could not be read from
 * where the producer stood, which includes a path resolving outside the model
 * root. `withheld` is a producer that held the text and was asked not to
 * disclose it — a decision the file records rather than a silence.
 */
export type OmittedReason = "size" | "unavailable" | "withheld";

/** One source file's payload: the file's own text, or the stand-in saying why not. */
export type SourcePayload = { text: string } | { omitted: OmittedReason; bytes?: number };

/**
 * One entry of §7.3: a file some calculation in this document was written in.
 *
 * `path` is the same string a node's `source_location` carries before the
 * colon, produced the same way, so a reader who followed a node to
 * `model.py:520` looks up `model.py` here and arrives. The entry whose path is
 * `model.source_path` carries exactly `model.source_sha`, which is what lets a
 * page showing the source say the source it shows is the source that ran.
 */
export interface SourceEntry {
  path: string;
  fingerprint: string | null;
  payload: SourcePayload;
}

/** One lineage edge. The relationship travels here; the narrowing travels on the node. */
export interface Edge {
  source: string;
  target: string;
  relationship: "DIRECT" | "INDIRECT";
}

/** The context the sampled values were taken in: which policy, which fold, which periods. */
export interface Enrichment {
  policy_id: string | null;
  /**
   * The fold this entry is an account of, or null where its values are one
   * policy's.
   *
   * A name rather than a union of two words: §7.4 widened it to whatever the
   * producer's framework spells the aggregator that performed the fold —
   * `sum`, `period_sum`, `mean`, `count` — because the two words it carried
   * were chosen before there was an aggregator set to name. The page reads it
   * as a label and branches on nothing but whether it is null, which is
   * `reader/fold.ts`.
   */
  aggregation: string | null;
  periods: number[] | null;
  filter: string | null;
}

/**
 * One entry of §7.4's policy axis: a model point the file carries values for.
 *
 * `Enrichment`'s four members, with `enrichment`'s meanings, and a fifth. `why`
 * is the producer's plain sentence saying how this policy came to be in the
 * file, recording the row it sits at and the id it carries — *"row 0 of 1,000
 * in model_points_1k.parquet"*, *"named on the command line, row 6 of 1,000 in
 * model_points_1k.parquet"*. It is on every entry, including the one a document
 * nobody narrowed produces, and that case is the one it was written for: a
 * reader who meets a single policy and no account of how it was chosen assumes
 * somebody chose it, and on the ordinary export nobody did.
 *
 * So the page shows it. A switcher listing ids would put the reader back where
 * the sentence was written to get them out of — knowing *which* policy and not
 * how much to read into its being the one in front of them.
 */
export interface Policy extends Enrichment {
  why: string;
}

/** The whole file. */
export interface Artifact {
  schema: string;
  profile: "audit" | "executable";
  fingerprint_algorithm: string;
  producer: unknown;
  created_at: string;
  model: {
    source_path: string | null;
    source_sha?: string | null;
    model_points?: { path: string; fingerprint: string } | null;
    results?: { path: string; fingerprint: string };
    /**
     * Every local module the model imports, path and the hash of its bytes.
     *
     * Empty where the model imports nothing from beside itself; absent on a
     * document written before the member and where no model file is named.
     * `reader/record.ts` is where the page reads it.
     */
    modules?: { path: string; fingerprint: string | null }[];
    /**
     * The revision the model was at; null where git found no working tree
     * beside it; or §6.1's unavailable form, `detail` saying why git could
     * not answer. `reader/record.ts` says which.
     */
    git?: { commit: string; dirty: boolean } | { omitted: "unavailable"; detail?: string } | null;
  };
  graph_fingerprint: string;
  /**
   * §12.6: the same fold with every content digest masked and the tables
   * section left out, so it moves when a formula does and holds when only a
   * table, a curve, a schedule or a column of handed-over values does.
   * Optional because a file written before the member carries none.
   */
  formulas_fingerprint?: string;
  /**
   * §7.5: the policy data the model was built over, identified by content.
   *
   * The columns the model reads, in name order, and their digest under §12.3's
   * grammar — or `{omitted: "unavailable", detail}` where the producer could
   * not vouch for its book, `detail` saying why. Optional here only because a
   * file written before the member existed carries none; every document written
   * since states one.
   */
  book?: { columns: string[]; digest: string | { omitted: string; detail?: string } };
  facets_used: string[];
  facets_required: string[];
  nodes: ArtifactNode[];
  edges: Edge[];
  assumptions: unknown[];
  holes: unknown[];
  boundaries: unknown[];
  /**
   * §7.3, and the one optional array in the envelope.
   *
   * It was added at `v0-preview.2` and every artifact written before that line
   * carries none, so a reader that required it would make a document that was
   * valid invalid. Absent and empty are different claims: absent is a file
   * written before the section existed, and empty is a producer saying this
   * document accounts for no file.
   */
  sources?: SourceEntry[];
  enrichment: Enrichment | null;
  /**
   * §7.4's axis: the policies the values are read along, in the producer's order.
   *
   * `enrichment` is this array's first entry with `why` left off, so the two
   * never disagree and the page reads the axis rather than the pair. Empty
   * exactly where `enrichment` is null — an artifact carrying no values states
   * no context to read them under.
   */
  policies: Policy[];
  facets: Record<string, unknown>;
  document_digest?: string;
}

/**
 * The one schema identifier this page reads. Anything else is refused by name.
 *
 * Including the edition before it. A preview's change policy is documentation
 * rather than compatibility work (§1), so a reader written for one edition
 * reads that edition and says so; the alternative is a shim that would have to
 * invent the `why` a `v0-preview.2` file does not carry, which is the page
 * writing a sentence the producer did not. The page and the artifact leave the
 * exporter in the same file, so the two are the same edition wherever one was
 * handed to somebody.
 */
export const READS_SCHEMA = "gaspatchio-graph/v0-preview.3";
