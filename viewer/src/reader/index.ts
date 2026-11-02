// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The one in-memory index every view reads.
 *
 * Built from one artifact and one position on its policy axis, in one pass over
 * the nodes and one over the edges. It rearranges what the file says; it adds
 * nothing to it. Where a question has no answer in the file — a scalar node's
 * timeline, an offset on a read that carries none — the answer is null or
 * undefined rather than a default, because a default here would be the page
 * quietly making a claim the file does not.
 *
 * **The axis is the one thing here that is not a function of the file alone.**
 * A document may carry several policies (§7.4), and which of them the page is
 * showing is the reader's position on that axis rather than anything the file
 * states. Everything else — the nodes, the edges, the fingerprints, the
 * sources, the line each calculation was written on — is the same whichever
 * entry is selected, and that is a measured property of the format rather than
 * a convention this page adopted: two exports of one model differing only in
 * which policy they carry differ in `value_sample`, `trace` and `branches` and
 * in nothing else. So the values are reached through `sampleOf`, `traceOf` and
 * `branchesOf`, and every other member is read straight off the record.
 */

import { statesWindow } from "./periods";
import { atPolicy, axisOf } from "./policies";
import type {
  Artifact,
  ArtifactNode,
  Branches,
  Narrowing,
  Policy,
  SourceEntry,
  TraceStep,
} from "./types";

/** Where a `source_location` points: one file, and the line inside it. */
export interface SourceAt {
  path: string;
  /** The line, or null where the location named a file and no line. */
  line: number | null;
}

/**
 * Split a node's `source_location` into the file and the line.
 *
 * At the **last** colon, which is how the producer splits it: a path may carry
 * one of its own — a Windows drive letter is the case that makes this a rule
 * rather than a preference — and a reader that split at the first would look up
 * a file whose name it had cut in half. Splitting it in one place is why the
 * path this returns is always the path §7.3 keyed its entry under.
 *
 * @param location - A node's `source_location`, or nothing.
 * @returns The file and the line, or null where there is no location to read.
 */
export function locationOf(location: string | null | undefined): SourceAt | null {
  if (location === null || location === undefined) return null;
  const colon = location.lastIndexOf(":");
  if (colon < 1) return { path: location, line: null };
  const line = Number(location.slice(colon + 1));
  if (!Number.isInteger(line)) return { path: location, line: null };
  return { path: location.slice(0, colon), line };
}

/** Everything the views ask of one artifact, arranged for asking. */
export interface Index {
  artifact: Artifact;
  nodes: Map<string, ArtifactNode>;
  /** Nodes in file order, which the producer writes topologically. */
  order: string[];
  /** target → the sources it reads. */
  readsOf: Map<string, string[]>;
  /** source → the targets that read it. */
  readBy: Map<string, string[]>;
  /** target → source → the facet's one narrowing for that read. */
  narrowing: Map<string, Map<string, Narrowing>>;
  /** The periods between a reading row and the row it read, when the facet states one. */
  offsetOf: (target: string, source: string) => number | undefined;
  /**
   * Every window the facet states for one read — `periods` or `position` (§9) —
   * in the facet's order, which is the strongest narrowing first. Empty where
   * the read states none, which is nearly every read.
   */
  windowsOf: (target: string, source: string) => Narrowing[];
  holesByColumn: Map<string, unknown>;
  /** Assumption tables, schedules and curves by the name the file gives them. */
  tables: Map<string, unknown>;
  /**
   * §7.3's entries, by the path the nodes spell.
   *
   * The same key a `source_location` carries before its colon, so a reader who
   * has followed a node to a line looks the file up under the string the node
   * gave them and does not have to guess a second spelling of it.
   */
  sources: Map<string, SourceEntry>;
  /**
   * Whether the file carries a §7.3 section at all.
   *
   * Not the same question as whether it has entries. A file written before
   * that section existed carries none of it, and an export that found no node
   * with a location writes the empty array — the first is a file this page
   * cannot ask, the second is a producer saying there is nothing to ask about,
   * and the source view says which.
   */
  carriesSources: boolean;
  /**
   * path → line → the nodes whose calculation the producer wrote on that line.
   *
   * Read off `source_location` and off nothing else. A line no node claims is
   * absent here rather than empty, because "nothing accounted for this line"
   * is the answer the source view prints and an empty list would be a second
   * way of writing it.
   */
  accountedLines: Map<string, Map<number, string[]>>;
  /**
   * §7.4's axis, in the producer's own order. Empty where the file has no values.
   *
   * The page draws a switcher over this and the switcher shows each entry's
   * `why`, because the reason a policy is in the file is the thing a reader
   * has to know before the numbers under it mean anything.
   */
  policies: Policy[];
  /** Which entry of `policies` everything below is read under, 0-based. */
  at: number;
  /** That entry, or null where the file carries no values to be read under one. */
  policy: Policy | null;
  /**
   * What one node held for the selected policy: the value, or the whole timeline.
   *
   * This is `value_sample` after §8's positional read, so a caller gets the
   * same shape whether the document carries one policy or fifty. The three
   * accessors below it are the same read over `trace` and `branches`.
   */
  sampleOf: (id: string) => unknown;
  /** That node's worked example for the selected policy, where it carries one. */
  traceOf: (id: string) => TraceStep[] | undefined;
  /** That node's branch record for the selected policy, where it carries one. */
  branchesOf: (id: string) => Branches | undefined;
  /**
   * What each step of one compiled rollforward moved, for the selected policy.
   *
   * Keyed by the kernel's own name for the step, in the order the file writes
   * them, and each value read along the axis exactly as `sampleOf` reads a
   * sample — because the axis goes *inside* the member (§8): one array per
   * step, not one mapping per policy. A step this entry carries no amount for
   * is absent from what comes back, which happens at a fold the amount has no
   * meaning under and never on a policy.
   */
  movementsOf: (id: string) => Map<string, unknown>;
  /** A list node's whole sampled timeline, or null where the file sampled no list. */
  timeline: (id: string) => unknown[] | null;
  /** The length of the longest timeline; 0 when the file carries no values. */
  periods: number;
  /**
   * Whether any node carries a sampled value at all.
   *
   * Read off the nodes rather than off `enrichment`, because the nodes are
   * where a value would be. An export can name a policy and still sample
   * nothing, and a page that took the context's word for it would draw a grid
   * of `·` under the heading of a policy whose values it never had.
   */
  carriesValues: boolean;
  /** List nodes in the final schema, in file order. */
  perPeriodColumns: string[];
  /** Scalar nodes in the final schema, in file order. */
  scalarColumns: string[];
  /**
   * Every column in the final schema, in file order, whatever its shape.
   *
   * What the search box looks through. The two lists above are a fact about
   * the frame — which columns hold one value and which hold one per period —
   * and the grid needs that distinction because it draws a timeline. A reader
   * looking for `pv_net_cf` does not: they are looking for a column, and which
   * shape it happens to have is the page's problem rather than theirs.
   */
  finalColumns: string[];
}

/**
 * A node's reads, as the narrowing facet states them.
 *
 * A read appearing twice — the same source reached by two routes — keeps the
 * first narrowing the facet lists, which is the one the facet's own ordering
 * puts against the node's `reads` entry.
 */
function narrowingsOf(node: ArtifactNode): Map<string, Narrowing> {
  const bySource = new Map<string, Narrowing>();
  const facet = node.facets.gaspatchio_column_transformation;
  if (!facet) return bySource;
  for (const read of facet.reads) {
    for (const transformation of read.transformations) {
      if (!bySource.has(read.source)) bySource.set(read.source, transformation);
    }
  }
  return bySource;
}

/**
 * A node's windowed reads: every transformation that states `periods` or
 * `position`, by source.
 *
 * Unlike the narrowing above, all of them: a name read through two windows in
 * one formula writes one transformation per window, and each is a run the
 * formula read.
 */
function windowsIn(node: ArtifactNode): Map<string, Narrowing[]> {
  const bySource = new Map<string, Narrowing[]>();
  const facet = node.facets.gaspatchio_column_transformation;
  if (!facet) return bySource;
  for (const read of facet.reads) {
    const stated = read.transformations.filter(statesWindow);
    if (stated.length === 0) continue;
    bySource.set(read.source, [...(bySource.get(read.source) ?? []), ...stated]);
  }
  return bySource;
}

/**
 * Index one artifact, read along one entry of its policy axis.
 *
 * @param artifact - The parsed file, already checked for schema and profile.
 * @param at - Which entry of `policies` the values are read under, 0-based.
 *   Out of range is clamped to the first, which is the entry `enrichment`
 *   restates and the one every document carrying values has.
 * @returns The index every view is a function of.
 */
export function buildIndex(artifact: Artifact, at = 0): Index {
  const policies = axisOf(artifact);
  const carried = policies.length;
  const position = carried === 0 ? 0 : Math.min(Math.max(at, 0), carried - 1);

  const nodes = new Map<string, ArtifactNode>();
  const order: string[] = [];
  const narrowing = new Map<string, Map<string, Narrowing>>();
  const windows = new Map<string, Map<string, Narrowing[]>>();
  const perPeriodColumns: string[] = [];
  const scalarColumns: string[] = [];
  const finalColumns: string[] = [];
  let periods = 0;
  let carriesValues = false;

  /** This policy's share of one member of one node's enrichment. */
  const mine = (id: string, member: "value_sample" | "trace" | "branches"): unknown =>
    atPolicy(nodes.get(id)?.[member], position, carried);

  for (const node of artifact.nodes) {
    nodes.set(node.id, node);
    order.push(node.id);

    const bySource = narrowingsOf(node);
    if (bySource.size > 0) narrowing.set(node.id, bySource);
    const windowed = windowsIn(node);
    if (windowed.size > 0) windows.set(node.id, windowed);

    if (node.in_final_schema) {
      if (node.shape === "list") perPeriodColumns.push(node.id);
      else if (node.shape === "scalar") scalarColumns.push(node.id);
      if (node.shape === "list" || node.shape === "scalar") finalColumns.push(node.id);
    }

    // Under the selected policy, and not over the member as the file writes
    // it: on an axis of four a scalar column's `value_sample` is four numbers,
    // and counting those as periods would put a grid of four rows under a
    // projection of eighty-three.
    const sample = atPolicy(node.value_sample, position, carried);
    if (sample !== undefined) carriesValues = true;
    if (Array.isArray(sample) && sample.length > periods) periods = sample.length;
  }

  const readsOf = new Map<string, string[]>();
  const readBy = new Map<string, string[]>();
  for (const edge of artifact.edges) {
    const sources = readsOf.get(edge.target);
    if (sources) sources.push(edge.source);
    else readsOf.set(edge.target, [edge.source]);

    const targets = readBy.get(edge.source);
    if (targets) targets.push(edge.target);
    else readBy.set(edge.source, [edge.target]);
  }

  const holesByColumn = new Map<string, unknown>();
  for (const hole of artifact.holes) {
    const column = (hole as { column?: unknown }).column;
    if (typeof column === "string") holesByColumn.set(column, hole);
  }

  const tables = new Map<string, unknown>();
  for (const assumption of artifact.assumptions) {
    const name = (assumption as { name?: unknown }).name;
    if (typeof name === "string") tables.set(name, assumption);
  }

  const sources = new Map<string, SourceEntry>();
  for (const entry of artifact.sources ?? []) sources.set(entry.path, entry);

  const accountedLines = new Map<string, Map<number, string[]>>();
  for (const node of artifact.nodes) {
    const where = locationOf(node.source_location);
    if (where === null || where.line === null) continue;
    const { path, line } = where;
    let byLine = accountedLines.get(path);
    if (byLine === undefined) {
      byLine = new Map<number, string[]>();
      accountedLines.set(path, byLine);
    }
    const claiming = byLine.get(line);
    if (claiming) claiming.push(node.id);
    else byLine.set(line, [node.id]);
  }

  return {
    artifact,
    nodes,
    order,
    readsOf,
    readBy,
    narrowing,
    offsetOf: (target, source) => narrowing.get(target)?.get(source)?.offset,
    windowsOf: (target, source) => windows.get(target)?.get(source) ?? [],
    holesByColumn,
    tables,
    sources,
    carriesSources: artifact.sources !== undefined,
    accountedLines,
    policies,
    at: position,
    policy: policies[position] ?? null,
    sampleOf: (id) => mine(id, "value_sample"),
    traceOf: (id) => {
      const trace = mine(id, "trace");
      return Array.isArray(trace) ? (trace as TraceStep[]) : undefined;
    },
    movementsOf: (id) => {
      const moved = nodes.get(id)?.movements;
      const mapped = new Map<string, unknown>();
      if (moved === undefined || moved === null) return mapped;
      for (const [key, along] of Object.entries(moved)) {
        const amount = atPolicy(along, position, carried);
        if (amount !== undefined) mapped.set(key, amount);
      }
      return mapped;
    },
    branchesOf: (id) => {
      const branches = mine(id, "branches");
      // An object and not an array: on an axis of several the member is an
      // array of these and `atPolicy` has already taken this policy's, so
      // anything still array-shaped is a file that did not conform.
      return typeof branches === "object" && branches !== null && !Array.isArray(branches)
        ? (branches as Branches)
        : undefined;
    },
    timeline: (id) => {
      const sample = mine(id, "value_sample");
      return Array.isArray(sample) ? sample : null;
    },
    periods,
    carriesValues,
    perPeriodColumns,
    scalarColumns,
    finalColumns,
  };
}
