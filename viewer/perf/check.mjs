// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Is the page still fast enough to read with?
 *
 * Reads `perf/results.json` — what `perf/measure.mjs` wrote — and exits
 * non-zero when a number in it is worse than the page's budget: a
 * 95th-percentile frame no longer than 33 ms on each of pan, zoom
 * and scrub, and a cold open from `file://` under one second. Thirty-three
 * milliseconds is thirty frames a second, which is where a drag stops feeling
 * attached to the hand holding it; one second is where a double-click stops
 * feeling like opening a file and starts feeling like loading an application.
 *
 * The scrub is judged three times: in the page's two viewports — the default
 * layout, and the cone expanded across the whole pane area — and on the
 * two-document comparison page. One budget for all three.
 * A page that could only hold the frame budget in the layout it opens in would
 * be a page whose lineage layout was a trap; a budget that only covered the
 * one-artifact page would leave the expensive shape free to sit above it. The
 * budget is for **the page**, and the answer to a frame
 * over it is the page, never this number.
 *
 * Split from the harness that takes the numbers on purpose. Measuring and
 * judging are different acts, and a harness that also judged would be a
 * harness nobody could run to simply look. It also means this file fails
 * loudly on a results file that is not there — which is the state a lane is in
 * when the step before it did not run — instead of reporting that nothing was
 * found to be slow.
 *
 * Usage, from `viewer/`:
 *
 *     node perf/check.mjs
 *
 * The one sentence it prints on the way out is the whole report: a check that
 * needs a paragraph to say what failed has not said it.
 *
 * What is judged is the median of the three timed runs' 95th percentiles, not
 * the percentile of all their frames pooled. Frames arrive on the display's
 * 16.7 ms tick, so a frame that misses one tick reads as 33.3 ms, and the
 * budget amounts to "no more than one frame in twenty misses a tick". On a
 * shared two-core runner one run in three can lose that coin toss on its own
 * — three times on unchanged code before this rule — and pooled, that one run
 * decides the answer. A page that is really slower is slower in all three runs
 * and still fails; the pooled figures are still printed beside the judged one.
 */

import { readFileSync } from "node:fs";

import { median } from "./runner.mjs";

/** The slowest frame the 95th percentile may be, in milliseconds. */
const FRAME_MS = 33;

/** The longest a page may take to open from a disk, in milliseconds. */
const COLD_OPEN_MS = 1000;

/** The gestures a reader makes, in the order the harness measures them. */
const INTERACTIONS = ["pan", "zoom", "scrub", "scrubConeExpanded", "scrubCompare"];

const RESULTS = "perf/results.json";

/**
 * Say one thing and stop.
 *
 * @param sentence - What is wrong, and what to do about it.
 */
function refuse(sentence) {
  console.error(sentence);
  process.exit(1);
}

let results;
try {
  results = JSON.parse(readFileSync(RESULTS, "utf8"));
} catch (error) {
  refuse(
    `No frame times to read at viewer/${RESULTS} (${error.message}) — run ` +
      `\`node perf/measure.mjs\` from viewer/ first, which needs ` +
      `dist/level4.html and dist/compare-after.html, the pages ` +
      `\`node pack.mjs level4\` and ` +
      `\`node pack.mjs compare-after --second compare-before\` write.`,
  );
}

const wrong = [];

for (const name of INTERACTIONS) {
  const measured = results.interactions?.[name];
  if (measured === undefined) {
    wrong.push(`${name} was not measured at all`);
    continue;
  }
  // A sample with no frames in it is a broken instrument, not a fast page, and
  // every percentile taken over nothing is under every budget ever written.
  if (!(measured.frames > 0)) {
    wrong.push(`${name} recorded ${String(measured.frames)} frames`);
    continue;
  }
  const runs = measured.perRepetition ?? [];
  const expected = results.meta?.repetitions;
  if (runs.length !== expected || !runs.every((run) => run.frames > 0)) {
    wrong.push(
      `${name} has ${String(runs.length)} timed runs with frames in them where the ` +
        `harness says it took ${String(expected)}`,
    );
    continue;
  }
  const judged = median(runs.map((run) => run.p95));
  if (judged > FRAME_MS) {
    wrong.push(
      `${name} holds a 95th-percentile frame of ${String(judged)} ms, the median of ` +
        `its ${String(runs.length)} runs (${runs.map((run) => String(run.p95)).join(", ")} ms)`,
    );
  }
}

const cold = results.coldOpen?.medianMs;
if (typeof cold !== "number") {
  wrong.push("the cold open was not measured at all");
} else if (cold > COLD_OPEN_MS) {
  wrong.push(`the page takes ${String(cold)} ms to open from a disk`);
}

if (wrong.length > 0) {
  refuse(
    `The page is outside its budget of ${String(FRAME_MS)} ms at the 95th percentile ` +
      `on pan, zoom and the scrub (the scrub in both viewports and on the comparison ` +
      `page) and ${String(COLD_OPEN_MS)} ms to open: ${wrong.join("; ")}.`,
  );
}

const line = INTERACTIONS.map((name) => {
  const measured = results.interactions[name];
  const judged = median(measured.perRepetition.map((run) => run.p95));
  return (
    `${name} p95 ${String(judged)} ms (median of its runs; pooled p50 ` +
    `${String(measured.p50)} ms, p95 ${String(measured.p95)} ms, ` +
    `${String(measured.over33)} of ${String(measured.frames)} frames over ${String(FRAME_MS)} ms)`
  );
}).join("; ");

console.log(
  `Within budget: ${line}; opens from a disk in ${String(cold)} ms ` +
    `(ceilings ${String(FRAME_MS)} ms and ${String(COLD_OPEN_MS)} ms).`,
);
