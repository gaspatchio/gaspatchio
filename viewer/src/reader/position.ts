// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * A position a reader can send: the policy, the column and the period.
 *
 * **Three things and nothing else.** Not the layout, not which panes are
 * railed, not what the reader had expanded, not which drawer tab was open.
 * The rule the panes keep is the one that decides this: a file you send
 * someone opens the way your page opens, and a link is a deliberate act of
 * pointing at one cell rather than a way of persisting an arrangement. Sending
 * somebody a link that rearranged their page would be the persisted expansion
 * the panes refuse, posted through a different door.
 *
 * **Nothing here touches storage.** The fragment belongs to the URL — it
 * travels in a link and dies with it — and `shell/remembered.ts` remains the
 * one thing this page writes anywhere.
 *
 * **The column travels as its name**, because the name is what an actuary
 * typed into the model; the id is the name with a version on it and is the
 * producer's spelling rather than theirs. It is resolved against the same list
 * the search box looks through and on the same key — `column`, over the final
 * schema, in the file's own order — so a document carrying two versions of one
 * column lands a link on the one pressing Enter in the search box lands on.
 *
 * **The policy travels as the strip's own name for it** (`reader/policies.ts`),
 * which is the id, or the fold's name where the entry is the book. An entry the
 * file names neither way cannot be pointed at, and the link omits the policy
 * rather than inventing a name or falling back to a position on the axis: a
 * number counted into `policies` would point at a different model point the
 * moment somebody exported the book with one more row in it.
 *
 * **And the entry's `filter` travels beside it, where the entry has one.** A
 * cross-joined scenario run gives one policy one row per scenario, so three
 * entries are all called `1` and only the cut tells them apart — which is why
 * each entry carries one. Before this, all three wrote `#policy=1` and all three
 * landed on the first, as an external review found: the same defect the
 * comparison had. The link now carries `&filter=…`, encoded, so a scenario
 * position is a position and not a guess. A link that names a policy this file
 * carries under more than one cut opens the page where it opens and says so in
 * the line the strip already has for a stale link, rather than choosing one of three
 * scenarios on the reader's behalf.
 *
 * **What a link cannot do is refuse.** A column this file does not carry, a
 * policy not on its axis, a period past the sampled timeline — each is ignored,
 * the page opens where it opens, and the strip says in one line what was asked
 * for. A link is often a quarter old by the time it is followed, and a page
 * that would not open is worse to its reader than a page that opens and says
 * what has moved.
 *
 * The fragment is read **once, on load**. There is deliberately no `hashchange`
 * listener: a link is followed by opening it, and a page that rearranged itself
 * because the address bar changed under it would be a second way for the
 * selection to move that no control on the page is responsible for.
 */

import { policyName } from "./policies";
import type { Index } from "./index";
import type { Policy } from "./types";

/**
 * The entry a fragment named, whole.
 *
 * The name and the cut together, because on a cross-joined file the name alone
 * is three entries. One object rather than two members so that every caller
 * asking "which entry" is handed the same complete answer — a caller that took
 * the name and left the cut behind is exactly the defect this replaced.
 */
export interface WantedPolicy {
  /** The name the strip gives the entry: the id, or the fold's own label. */
  name: string;
  /** The entry's `filter`, or null where the link named none. */
  filter: string | null;
}

/** What a fragment asked for. Each member is null where it asked for nothing. */
export interface Wanted {
  /** The entry of the axis, named as the strip names it and cut as the file cut it. */
  policy: WantedPolicy | null;
  /** The column, by the name the model wrote. */
  column: string | null;
  /** The period, as an index into the sampled timelines. */
  period: number | null;
}

/** Where a link actually lands, once the file has been asked. */
export interface Landing {
  /** The entry of the axis to read under, 0-based. */
  at: number;
  /** The node the column named, or null where the link named none this file has. */
  nodeId: string | null;
  /** The row cursor. */
  period: number;
  /** One line saying what the link asked for and this file does not carry. */
  note: string | null;
}

/** Nothing asked for: a page opened from a link that carries no position. */
const NOTHING: Wanted = { policy: null, column: null, period: null };

/**
 * Read a fragment.
 *
 * A fragment that is not this grammar asks for nothing, and the page opens as
 * it opens. These links are the page's own output, so a fragment that does not
 * parse is a typo in one rather than a statement about the file, and there is
 * nothing to say about it in the identity strip.
 *
 * @param hash - `window.location.hash`, leading `#` and all, or empty.
 * @returns What was asked for, member by member.
 */
export function wantedIn(hash: string): Wanted {
  const body = hash.startsWith("#") ? hash.slice(1) : hash;
  if (body === "") return NOTHING;
  const params = new URLSearchParams(body);
  const period = params.get("period");
  const asNumber = period === null ? Number.NaN : Number(period);
  const name = params.get("policy");
  return {
    policy: name === null ? null : { name, filter: params.get("filter") },
    column: params.get("column"),
    period: Number.isInteger(asNumber) ? asNumber : null,
  };
}

/**
 * What this file has to say about the entry a link named.
 *
 * The name narrows the axis; the cut narrows it again where the link carried
 * one. A link written before there was a `filter` key in the grammar carries
 * only the name, and on a scenario file that names three entries — so it is
 * **ambiguous** rather than the first of them: a link that dropped the cut
 * used to land on whichever scenario came first.
 *
 * @param axis - `policies`, in the producer's order.
 * @param wanted - The entry the link named, or null where it named none.
 * @returns Its position; `"absent"` where nothing was asked for or no entry
 *   answers, `"ambiguous"` where more than one does.
 */
export function locate(axis: Policy[], wanted: WantedPolicy | null): number | "absent" | "ambiguous" {
  if (wanted === null) return "absent";
  const answering: number[] = [];
  for (const [at, entry] of axis.entries()) {
    if (policyName(entry) !== wanted.name) continue;
    if (wanted.filter !== null && entry.filter !== wanted.filter) continue;
    answering.push(at);
  }
  if (answering.length === 0) return "absent";
  if (answering.length > 1) return "ambiguous";
  return answering[0]!;
}

/**
 * Which entry of the axis a link points at, where exactly one does.
 *
 * `locate` narrowed for the caller that only wants a position to open on: a
 * link that names nobody and a link that names three entries both open the
 * page where it opens. `landingIn` uses `locate`, because the line it prints
 * differs between the two.
 *
 * @param axis - `policies`, in the producer's order.
 * @param wanted - The entry the link named, or null where it named none.
 * @returns The entry's position, or null where no single entry answers.
 */
export function policyAt(axis: Policy[], wanted: WantedPolicy | null): number | null {
  const found = locate(axis, wanted);
  return typeof found === "number" ? found : null;
}

/**
 * Which node a column name points at.
 *
 * The same list the search looks through and the same key: the final schema,
 * in file order, matched on `column` rather than on the node id. Where a
 * document carries two versions of one column the first is taken, which is the
 * one pressing Enter in the search box takes.
 *
 * Exactly, and not by the substring the search narrows on. A link is the
 * page's own output, so the name in it is a name this file wrote; a link that
 * fell back to a partial match would answer `#column=net_cf` with `pv_net_cf`
 * on a file where the first had gone and the second had not, which is a
 * quietly wrong answer where a note saying the column has gone is a true one.
 */
function columnAt(index: Index, name: string | null): string | null {
  if (name === null) return null;
  const found = index.finalColumns.find((id) => index.nodes.get(id)?.column === name);
  return found ?? null;
}

/** The clauses of the note, in the order the fragment writes its keys. */
function said(clauses: string[]): string {
  if (clauses.length === 1) return clauses[0] ?? "";
  return `${clauses.slice(0, -1).join(", ")} and ${clauses[clauses.length - 1] ?? ""}`;
}

/**
 * Follow a link against this file.
 *
 * @param index - The document, indexed at the entry `policyAt` chose.
 * @param wanted - What the fragment asked for.
 * @returns Where the page opens, and the one line to say about what it could
 *   not honour.
 */
export function landingIn(index: Index, wanted: Wanted): Landing {
  const missed: string[] = [];

  const found = locate(index.policies, wanted.policy);
  const at = typeof found === "number" ? found : null;
  if (wanted.policy !== null && found === "absent") {
    missed.push(`policy ${wanted.policy.name}, which is not on this file's axis`);
  }
  if (found === "ambiguous") {
    // A link written without the cut, on a file that carries this policy under
    // several. Landing on the first would answer a question the link did not
    // ask, with one scenario's numbers under a name three of them answer to.
    missed.push(
      `policy ${wanted.policy?.name ?? ""}, which this file carries under more than one filter`,
    );
  }

  const nodeId = columnAt(index, wanted.column);
  if (wanted.column !== null && nodeId === null) {
    missed.push(`column ${wanted.column}, which this file does not carry`);
  }

  const asked = wanted.period;
  const inside = asked !== null && asked >= 0 && asked < index.periods;
  if (asked !== null && !inside) {
    missed.push(
      index.periods === 0
        ? `period ${String(asked)}, and this file samples no timeline at all`
        : `period ${String(asked)}, past the ${String(index.periods)} this file sampled`,
    );
  }

  return {
    at: at ?? 0,
    nodeId,
    period: inside ? asked : 0,
    note:
      missed.length === 0
        ? null
        : `This link asked for ${said(missed)}. The page opened where it opens.`,
  };
}

/**
 * The fragment for where the reader is standing now.
 *
 * Omitted rather than defaulted, key by key, because every key a link carries
 * is a key the page will be asked about when the link is followed. A single
 * policy is not named — there is nothing to choose between and the file opens
 * on it anyway — and a file that samples no timeline carries no period, which
 * would otherwise come back on the round trip as a period past a timeline of
 * none.
 *
 * The cut goes immediately after the policy, because the two are one fact: an
 * entry's identity is what the file writes about it, and a reader scanning a
 * pasted link reads the scenario beside the policy rather than past a column
 * name. It is omitted on an entry the file gave no `filter`, which is every
 * ordinary export.
 *
 * @param index - The document, read at the selected entry.
 * @param nodeId - The selected node, or null where nothing is selected.
 * @param period - The row cursor.
 * @returns The fragment, `#` and all, or the empty string where this page has
 *   no position to point at.
 */
export function fragmentFor(index: Index, nodeId: string | null, period: number): string {
  const params = new URLSearchParams();

  const entry = index.policies.length > 1 ? index.policy : null;
  const policy = entry === null ? null : policyName(entry);
  if (policy !== null) params.set("policy", policy);
  if (policy !== null && entry?.filter != null) params.set("filter", entry.filter);

  const column = nodeId === null ? undefined : index.nodes.get(nodeId)?.column;
  if (typeof column === "string" && column !== "") params.set("column", column);

  if (index.periods > 0) params.set("period", String(period));

  const body = params.toString();
  return body === "" ? "" : `#${body}`;
}
