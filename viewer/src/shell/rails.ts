// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What a railed pane says about itself.
 *
 * A rail is not a hidden pane. It keeps its name and **its one live
 * figure** — the cone's count and centre, the proof's idiom and result, the
 * grid's period and selected value, the drawer's tab — so a reader can tell
 * from the edge of the screen whether the pane they put away is still pointed
 * where they left it. One figure and not three: a rail that tried to summarise
 * a pane would be a smaller pane, and the reader would have to open it anyway
 * to find out whether the summary was the part they needed.
 *
 * **An amber admission travels to the rail in words.** Amber on this page means
 * a hole or a disagreement and means nothing else, so a rail wearing it is a
 * rail saying the file is owning up to something — a column the model does not
 * account for, a file that carries no values at all, a trace that disagrees
 * with the sample beside it. That is the clause that makes a collapse safe:
 * whatever else a reader can put away, they cannot put away what the file
 * admits. Without it, collapsing the proof on the one column with a hole in it
 * would turn an admission into a blank strip.
 *
 * Every figure here is read off the index and the selection, the same two
 * things the pane itself is a function of, so a rail and the pane behind it can
 * never disagree. Nothing here is computed from anything else.
 */

import { NOT_FOLDED, unfolded } from "../reader/fold";
import { formatValue, isIntegerDtype } from "../reader/format";
import type { Index } from "../reader/index";
import { proofOf } from "../reader/proof";
import { coneWindow } from "../reader/window";
import type { InspectorTab, PaneName } from "../state/layout";
import type { Selection } from "../state/selection";

/** What a rail says, and whether it is an admission. */
export interface RailFigure {
  says: string;
  admits: boolean;
}

/** The name a column is written under: the file's `column`, its id where it has none. */
function labelOf(index: Index, id: string): string {
  return index.nodes.get(id)?.column ?? id;
}

/**
 * What one column held at one period, written the way the grid writes it.
 *
 * And on a fold the book was not totalled by, the words the grid writes
 * instead. A rail's whole job is to carry the pane's one live figure without
 * the pane, so a rail reading `·` where the pane reads "not folded" would be
 * the one place on the page a reader could take a fold for a missing value.
 */
function held(index: Index, id: string, period: number): string {
  if (unfolded(index, id)) return NOT_FOLDED;
  const node = index.nodes.get(id);
  const sample = index.sampleOf(id);
  return formatValue(Array.isArray(sample) ? sample[period] : sample, {
    integer: node !== undefined && isIntegerDtype(node.dtype),
  });
}

/** The grid's figure: where the row cursor is, and what is under it. */
function gridFigure(index: Index, selection: Selection): RailFigure {
  if (!index.carriesValues) {
    return { says: "this file carries no values", admits: true };
  }
  const at = `period ${String(selection.period)}`;
  if (selection.nodeId === null) return { says: `${at} · no column selected`, admits: false };
  const column = labelOf(index, selection.nodeId);
  return { says: `${at} · ${column} ${held(index, selection.nodeId, selection.period)}`, admits: false };
}

/** The cone's figure: how much of the graph is in the window, and what it is centred on. */
function coneFigure(index: Index, selection: Selection): RailFigure {
  const whole = String(index.order.length);
  if (selection.nodeId === null) {
    return { says: `no centre · ${whole} nodes`, admits: false };
  }
  const window = coneWindow(index, selection.nodeId, selection.up, selection.down);
  const centre = labelOf(index, selection.nodeId);
  const size = `${String(window.nodes.length)} of ${whole}`;
  if (index.nodes.get(selection.nodeId)?.kind === "hole") {
    return { says: `${size} · centre ${centre} unaccounted for`, admits: true };
  }
  return { says: `${size} · centre ${centre}`, admits: false };
}

/** The proof's figure: which worked example is standing, and what it came to. */
function proofFigure(index: Index, selection: Selection): RailFigure {
  const nodeId = selection.nodeId;
  const node = nodeId === null ? undefined : index.nodes.get(nodeId);
  if (nodeId === null || node === undefined) {
    return { says: "no column selected", admits: false };
  }
  const column = labelOf(index, nodeId);
  if (node.kind === "hole") {
    return { says: `hole · ${column} unaccounted for`, admits: true };
  }
  if (!index.carriesValues) {
    return { says: `${column} · this file carries no values`, admits: true };
  }
  const proof = proofOf(index, nodeId, selection.period);
  if (proof.disagreement) {
    // The two numbers themselves are the panel's to print, and the panel prints
    // both. What belongs on a rail is that there are two — enough for a reader
    // to know the pane is worth opening, and not so much that the rail is
    // quoting figures the reader cannot see the working for.
    return { says: `${proof.idiom} · ${column} · the trace and the sample disagree`, admits: true };
  }
  // The fold line stands in for the result where there is no result: a column
  // the fold did not cover has no number, and the rail says which of the two
  // it is rather than falling silent.
  const result = proof.lines.find((line) => line.kind === "result" || line.kind === "fold")
    ?.text;
  return {
    says: result === undefined ? `${proof.idiom} · ${column}` : `${proof.idiom} · ${column} · ${result}`,
    admits: false,
  };
}

/** The drawer's figure: which tab is open, and whether the file admits to holes. */
function drawerFigure(index: Index, tab: InspectorTab): RailFigure {
  const holes = index.artifact.holes.length;
  if (holes === 0) return { says: tab, admits: false };
  // The strip's amber chip never hides, so this is not the only place a
  // reader can learn the count. It is here because the Model tab is where the
  // holes are accounted for with their reasons, and a railed drawer should say
  // that the tab a reader would open for that has something in it.
  return { says: `${tab} · ${String(holes)} ${holes === 1 ? "hole" : "holes"}`, admits: true };
}

/**
 * One pane's live figure, for its rail.
 *
 * Called only when a rail is actually being drawn, which is why the proof's
 * worked example can be built here without the default layout paying for it.
 *
 * @param index - The file, indexed.
 * @param selection - Where the reader is looking.
 * @param tab - Which tab the drawer is on.
 * @param pane - The pane asking.
 * @returns What its rail says, and whether that is an admission.
 */
export function railFigure(
  index: Index,
  selection: Selection,
  tab: InspectorTab,
  pane: PaneName,
): RailFigure {
  if (pane === "grid") return gridFigure(index, selection);
  if (pane === "cone") {
    // The cone pane carries the worked example under it now, so its rail speaks
    // for both: the window on the left of the dot, the proof on the right. An
    // admission from either makes the rail an admission, which is what a
    // rail's amber is for — railing the cone must not be a way to put a hole, a
    // file with no values or a disagreement out of sight.
    const window = coneFigure(index, selection);
    const worked = proofFigure(index, selection);
    return {
      says: `${window.says} · ${worked.says}`,
      admits: window.admits || worked.admits,
    };
  }
  return drawerFigure(index, tab);
}
