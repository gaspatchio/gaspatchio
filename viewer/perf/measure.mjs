// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * How the page behaves under a reader's hands, measured.
 *
 * The harness a prototype of this page was measured with before the page was
 * built — the measurement that decided React Flow was fast enough to build on —
 * kept: headless Chromium at 1440 x 900 and one device pixel per CSS pixel,
 * `dist/level4.html` opened from `file://` because that is the only way this
 * page is ever opened, one discarded warm-up and three measured repetitions of
 * each of pan, zoom and scrub, and the same clock — the delta between
 * successive `requestAnimationFrame` callbacks, with the step of the
 * interaction made inside the callback so its cost lands in the next delta.
 * `perf/check.mjs` reads what this writes and says whether it is inside the
 * budget; this file only measures.
 *
 * **What is different from the prototype, and why.** The prototype's page
 * carried a `window.__bench` object with the three interactions written
 * against React Flow's own handle. The exported page carries nothing of the
 * kind and is not going to: a measuring surface in the shipped file is a
 * surface somebody eventually reads, and the page's contract is that it
 * computes nothing. So the three interactions are made here, from outside,
 * against the page exactly as it stands — the cone canvas gets the mouse and
 * wheel events a hand and a trackpad send it, and the scrub moves the page's
 * own period slider. The prototype was measured both ways, through React
 * Flow's handle and through real input events, and gave the same picture from
 * each; this keeps the second one, which is the one a reader actually
 * performs.
 *
 * **What is measured, on what.** The level-4 export: 128 nodes, 184 edges, 83
 * periods. The cone is opened on `net_cf` and widened through the page's own
 * control until the window stops growing, which is that column's whole
 * ancestor cone — 101 of the 128 nodes, the heaviest window the page will draw
 * over this file. The prototype was measured on the same graph at the same
 * size, on the 111-node ancestor cone of `pv_net_cf`, which this page cannot
 * open a cone on because it is a scalar and the search offers per-period
 * columns; `net_cf` is the other of the two most-read nodes, and its cone
 * counted 101 there as it does here. Every figure the results file records
 * about the shape is read off the page rather than out of the fixture, so a
 * page that drew less than it claims cannot report a shape it did not draw.
 *
 * **An expanded cone is a fourth measurement, because it is a new viewport.**
 * The same 101-node window, drawn across the whole pane area instead of
 * the bottom-left quarter of it, is more nodes on the canvas at a readable zoom
 * and is the state the `lineage` layout puts a reader in. It is the scrub that
 * is repeated there rather than the pan and the zoom: a period step is the one
 * interaction whose cost is a function of how much is being drawn at once, and
 * it is the one that was over the budget before the cursor moved into a store.
 * The budget does not move for it. Note what the expansion also does: the grid
 * and the proof become rails, so the work of a period step is the cone's plus
 * two short strings, where in the default layout it is the cone's plus a grid
 * and a worked example.
 *
 * Usage, from `viewer/`:
 *
 *     node pack.mjs level4      # writes dist/level4.html from the built assets
 *     node perf/measure.mjs     # writes perf/results.json
 *     node perf/check.mjs       # judges it
 *
 *     VIEWER_PERF_CPU_THROTTLE=1.25 node perf/measure.mjs   # a slower runner; see CPU_THROTTLE
 *
 * `perf/results.json` is a measurement of the machine it was taken on and is
 * not committed. The figures worth keeping are quoted in the commit that takes
 * them, naming the tree and the browser they were taken on, so a later run can
 * be compared against a named rig.
 */

import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { chromium } from "@playwright/test";

import {
  averaged,
  mainThreadPerFrame,
  mainThreadTotals,
  median,
  round,
  stats,
} from "./runner.mjs";

/** The page measured: the biggest of the tutorial exports, packed for the tests. */
const PAGE = "dist/level4.html";

/**
 * The comparison page, which is the same graph carrying a second document.
 *
 * Measured by the same instrument and judged against the same budget, because
 * the budget is for **the page** and not for the
 * one-artifact page. A comparison is a thing a reader opens and scrubs like
 * any other, and a ceiling that only covered the cheaper of the two shapes
 * would be a ceiling the expensive one was free to sit above.
 */
const COMPARE_PAGE = "dist/compare-after.html";

/** Where the numbers go. Ignored by git: this is a fact about a machine. */
const RESULTS = "perf/results.json";

/** The viewport every measurement has been taken at, so the numbers compare. */
const VIEWPORT = { width: 1440, height: 900 };

/** Repetitions kept, after one discarded warm-up. */
const REPETITIONS = 3;

/** How long pan and zoom are held, in milliseconds. */
const GESTURE_MS = 2000;

/** The column the cone is opened on: the model's net cashflow. */
const COLUMN = "net_cf";

/** A ceiling on the widening loop, so a page that never settles still ends. */
const WIDENING_LIMIT = 30;

/** Long enough for a click to have been drawn before the next is sent. */
const SETTLE_MS = 250;

/**
 * How many times slower the page's CPU is made to run. Off unless asked for.
 *
 * `VIEWER_PERF_CPU_THROTTLE=1.25 node perf/measure.mjs` opens every page this
 * harness opens under the DevTools protocol's `Emulation.setCPUThrottlingRate`
 * at 1.25, set before the page loads so the whole of it runs throttled. Unset,
 * empty or 1 is no throttling at all, which is what CI runs: the step measures
 * the runner it is on, and a throttled figure is a figure about a machine that
 * does not exist.
 *
 * It is here because a page can be over the budget only on somebody else's
 * machine. The step's first run on a 2-core CI runner put both scrubs over it
 * while the development Mac held them, and a frame that is only slow over
 * there cannot be profiled or fixed over here until it is slow over here too.
 * On that Mac (an i9-9880H) 1.25 is the rate that reproduces the runner: both
 * scrubs over the budget by about as many frames as CI counted, and pan, zoom
 * and the expanded scrub inside it.
 *
 * It is a slower main thread, not a smaller machine: the protocol slows the
 * page's own thread, and the compositor and raster threads beside it keep this
 * machine's speed. The cold open shows the difference — 630 ms at 1.25 where
 * the runner read 480 — so the rate is matched to the scrubs, which are what
 * failed, and nothing else it reads is a claim about the runner. The rate is
 * written into the results file, so a throttled reading cannot be taken for a
 * native one.
 */
const CPU_THROTTLE = throttleAsked(process.env.VIEWER_PERF_CPU_THROTTLE);

/**
 * Read the throttling rate a run asked for.
 *
 * @param asked - The environment's `VIEWER_PERF_CPU_THROTTLE`, if it is set.
 * @returns The rate, 1 where nothing was asked for.
 */
function throttleAsked(asked) {
  if (asked === undefined || asked.trim() === "") return 1;
  const rate = Number(asked);
  if (Number.isFinite(rate) && rate >= 1) return rate;
  console.error(
    `VIEWER_PERF_CPU_THROTTLE is how many times slower the page's CPU runs — a number ` +
      `of at least 1 — and was "${asked}". Unset it to measure this machine as it is.`,
  );
  process.exit(1);
}

for (const [page, packs] of [
  [PAGE, "node pack.mjs level4"],
  [COMPARE_PAGE, "node pack.mjs compare-after --second compare-before"],
]) {
  if (existsSync(page)) continue;
  console.error(
    `There is no ${page} to measure — run \`${packs}\` from viewer/ first, ` +
      `which packs that page from the built assets.`,
  );
  process.exit(1);
}

const FILE = pathToFileURL(resolve(PAGE)).href;
const COMPARE_FILE = pathToFileURL(resolve(COMPARE_PAGE)).href;

/**
 * Everything that runs inside the page.
 *
 * Installed before the document's own script, on every page this harness
 * opens. It defines two recorders — one over a duration and one over a fixed
 * number of steps — the three interactions written against the page's real
 * elements, and the marker the cold open is timed to.
 *
 * It is one function because that is how Playwright gets it into the page: it
 * is serialised and evaluated at document start, so it closes over nothing
 * from this file and can be read as the whole of what the browser runs.
 */
function inThePage() {
  /**
   * Frame times across `durationMs`, with `step` made inside each callback.
   *
   * The step's cost lands in the *next* delta, which is what makes a dropped
   * frame show up as a delta over 33 ms rather than as a shorter one later.
   */
  function overDuration(durationMs, step) {
    return new Promise((done) => {
      const times = [];
      let last = null;
      let first = null;
      function frame(now) {
        if (first === null) first = now;
        if (last !== null) times.push(now - last);
        last = now;
        step((now - first) / durationMs);
        if (now - first >= durationMs) {
          done(times);
          return;
        }
        requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    });
  }

  /** The same, over a fixed number of steps rather than a duration. */
  function overSteps(steps, step) {
    return new Promise((done) => {
      const times = [];
      let last = null;
      let at = 0;
      function frame(now) {
        if (last !== null) times.push(now - last);
        last = now;
        step(at);
        at += 1;
        if (at > steps) {
          done(times);
          return;
        }
        requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    });
  }

  const pane = () => document.querySelector(".react-flow__pane");

  /** The canvas's current zoom, read off the transform React Flow wrote. */
  function zoomNow() {
    const transform = document.querySelector(".react-flow__viewport")?.style.transform ?? "";
    const scale = /scale\(([\d.]+)\)/.exec(transform);
    return scale === null ? 1 : Number(scale[1]);
  }

  /** Where an event happened, in the form every event here takes. */
  const at = (x, y) => ({
    clientX: x,
    clientY: y,
    bubbles: true,
    cancelable: true,
    view: window,
  });

  /** The same, plus the left button held, which is what a drag is. */
  const dragging = (x, y) => ({ ...at(x, y), button: 0, buttons: 1 });

  window.__perf = {
    /** How many node bodies the canvas is drawing right now. */
    rendered: () => document.querySelectorAll(".react-flow__node").length,

    /**
     * Drag the cone canvas leftwards, wrapping back when it runs out of pane.
     *
     * A press, a move every frame and a release — the events a hand on a
     * trackpad sends, which is the path through React Flow's own drag
     * handling rather than around it.
     */
    pan: (durationMs) => {
      const box = pane().getBoundingClientRect();
      const y = box.top + box.height / 2;
      const from = box.right - 24;
      const to = box.left + 24;
      let x = from;
      pane().dispatchEvent(new MouseEvent("mousedown", dragging(x, y)));
      return overDuration(durationMs, () => {
        x -= 6;
        if (x < to) x = from;
        window.dispatchEvent(new MouseEvent("mousemove", dragging(x, y)));
      }).then((times) => {
        window.dispatchEvent(new MouseEvent("mouseup", { ...at(x, y), button: 0, buttons: 0 }));
        return times;
      });
    },

    /**
     * Wheel the cone canvas between the zooms the page allows.
     *
     * One tick a frame, reversing at each end, so the sweep covers the whole
     * range a reader can reach rather than one comfortable part of it.
     */
    zoom: (durationMs) => {
      const box = pane().getBoundingClientRect();
      const x = box.left + box.width / 2;
      const y = box.top + box.height / 2;
      let closer = true;
      return overDuration(durationMs, () => {
        const zoom = zoomNow();
        if (zoom >= 1.9) closer = false;
        if (zoom <= 0.32) closer = true;
        pane().dispatchEvent(
          new WheelEvent("wheel", { ...at(x, y), deltaY: closer ? -40 : 40 }),
        );
      });
    },

    /**
     * Move the row cursor one period a frame, through the page's own slider.
     *
     * The value is set through the prototype's own setter before the event is
     * sent, because React holds the last value it wrote and would otherwise
     * treat an assignment it did not make as nothing having changed.
     */
    scrub: (periods) => {
      const slider = document.querySelector('[data-testid="cursor"]');
      const write = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      return overSteps(periods, (step) => {
        write.call(slider, String(Math.min(step, periods - 1)));
        slider.dispatchEvent(new Event("input", { bubbles: true }));
      });
    },
  };

  // The cold open's end: the frame after the grid's first row is in the
  // document. `performance.now()` counts from this document's navigation, so
  // the number needs no start of its own.
  const watch = () => {
    if (document.querySelector('tr[data-period="0"]') === null) {
      requestAnimationFrame(watch);
      return;
    }
    requestAnimationFrame(() => {
      window.__openedMs = performance.now();
    });
  };
  requestAnimationFrame(watch);
}

const browser = await chromium.launch({
  args: ["--force-device-scale-factor=1", "--hide-scrollbars"],
});

/**
 * A page with nothing of the last one left in it.
 *
 * @param file - Which document to open. The level-4 export unless a
 *   measurement is about another shape of page.
 * @returns The opened page, once its first frame has been drawn.
 */
async function fresh(file = FILE) {
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  await context.addInitScript(inThePage);
  const page = await context.newPage();
  // Before the navigation, which it survives, so that a throttled run is
  // throttled from the document's first task and its cold open with it.
  if (CPU_THROTTLE > 1) {
    const client = await context.newCDPSession(page);
    await client.send("Emulation.setCPUThrottlingRate", { rate: CPU_THROTTLE });
  }
  await page.goto(file, { waitUntil: "load" });
  await page.waitForFunction("window.__openedMs !== undefined", null, { timeout: 60_000 });
  return page;
}

/**
 * Open the page and put it in the state the interactions are measured in.
 *
 * Search for the column, select it, then widen the cone one step at a time
 * until a step adds nothing — all through the controls a reader uses, so the
 * state being measured is a state a reader can get to. Expanding it is the
 * page's own keyboard, for the same reason: `Shift+2` is what a reader presses,
 * and focus is on the widening control by then rather than in the search box,
 * where the page suppresses every shortcut.
 *
 * @param expandCone - Whether to give the cone the whole pane area.
 * @param file - Which document to open.
 * @returns The page, and what it says it is drawing — every figure read off
 *   the page itself, so a page that drew less than the fixture holds cannot
 *   report a shape it did not draw.
 */
async function opened(expandCone = false, file = FILE) {
  const page = await fresh(file);
  await page.locator('[data-testid="search"]').fill(COLUMN);
  await page.locator('[data-testid="search"]').press("Enter");
  await page.waitForSelector('[data-testid="cone-count"]');

  let last = null;
  for (let click = 0; click < WIDENING_LIMIT; click += 1) {
    await page.locator('[data-testid="widen-up"]').click();
    await page.waitForTimeout(SETTLE_MS);
    const now = Number(await page.locator('[data-testid="cone-count"]').textContent());
    if (now === last) break;
    last = now;
  }

  if (expandCone) {
    await page.keyboard.press("Shift+Digit2");
    // The rails are what say the expansion took: the grid and the drawer are
    // strips now, and a measurement taken without it would be the default
    // layout's under another name. The proof is not among them — it stopped
    // being a pane and rides under the cone, so an expanded cone carries it
    // rather than railing it.
    await page.waitForSelector('[data-rail="grid"]');
    await page.waitForSelector('[data-rail="inspector"]');
  }
  await page.waitForTimeout(SETTLE_MS);

  const counted = await page.locator(".cone-bar .count").textContent();
  const pane = await page.locator('[data-pane="cone"]').boundingBox();
  return {
    page,
    shape: {
      column: COLUMN,
      coneWindow: last,
      graph: Number(counted.replace(/^.*\bof\s+/, "")),
      periods: Number(await page.locator('[data-testid="cursor"]').getAttribute("max")) + 1,
      renderedAtFit: await page.evaluate("window.__perf.rendered()"),
      conePane: { width: Math.round(pane.width), height: Math.round(pane.height) },
      coneExpanded: expandCone,
      // What the page says it is comparing, where it is comparing anything.
      // Read off the page for the same reason every other figure here is: a
      // comparison page that had failed to derive its changes would otherwise
      // be measured as a comparison page and be one of the cheap ones.
      compared: await page.locator('[data-testid="changes-count"]').count() === 0
        ? null
        : await page.locator('[data-testid="changes-count"]').textContent(),
    },
  };
}

const interactions = {};
const warmUp = {};
const shapes = {};

if (CPU_THROTTLE > 1) {
  console.error(`every page throttled to 1/${String(CPU_THROTTLE)} of this machine's CPU`);
}

const SCRUB = "window.__perf.scrub(Number(document.querySelector('[data-testid=\"cursor\"]').max) + 1)";

for (const [name, call, expandCone, file] of [
  ["pan", `window.__perf.pan(${String(GESTURE_MS)})`, false, FILE],
  ["zoom", `window.__perf.zoom(${String(GESTURE_MS)})`, false, FILE],
  ["scrub", SCRUB, false, FILE],
  // The same scrub with the cone across the whole pane area: the expanded
  // viewport, judged against the same budget as the other three.
  ["scrubConeExpanded", SCRUB, true, FILE],
  // The same scrub on a page carrying two documents: the comparison page, on the
  // same graph, with `net_cf` selected — which is a column the comparison
  // marks, so the proof panel is in its two-sided state and the grid's open
  // column is drawing both numbers. Judged against the same budget as the
  // other four, because the budget is for the page, whichever shape it takes.
  ["scrubCompare", SCRUB, false, COMPARE_FILE],
]) {
  const pooled = [];
  const perRepetition = [];
  const perFrame = [];

  // One page per repetition, so each one starts from the same fitted canvas
  // and the same period rather than from wherever the one before it stopped.
  for (let repetition = 0; repetition <= REPETITIONS; repetition += 1) {
    const { page, shape: drawn } = await opened(expandCone, file);
    shapes[name] ??= drawn;
    const client = await page.context().newCDPSession(page);
    await client.send("Performance.enable");

    const before = await mainThreadTotals(client);
    const times = await page.evaluate(call);
    const after = await mainThreadTotals(client);

    if (repetition > 0) {
      pooled.push(...times);
      perRepetition.push(stats(times));
      perFrame.push(mainThreadPerFrame(before, after, times.length));
    } else {
      warmUp[name] = stats(times);
    }

    await page.context().close();
  }

  interactions[name] = {
    ...stats(pooled),
    perRepetition,
    mainThreadMsPerFrame: averaged(perFrame),
  };
  console.error(
    `${name}: p50 ${String(interactions[name].p50)} ms, ` +
      `p95 ${String(interactions[name].p95)} ms, ` +
      `${String(interactions[name].over33)} of ${String(interactions[name].frames)} frames over 33 ms`,
  );
}

const coldOpen = [];
for (let repetition = 0; repetition <= REPETITIONS; repetition += 1) {
  const page = await fresh();
  const openedMs = round(await page.evaluate("window.__openedMs"));
  await page.context().close();
  if (repetition > 0) coldOpen.push(openedMs);
}
console.error(`cold open: median ${String(median(coldOpen))} ms of ${JSON.stringify(coldOpen)}`);

const results = {
  meta: {
    // Both pages, because two of the five interactions are measured on the
    // second one. `page` stays the name it was: the cold open is the level-4
    // page's, and a reader of an old results file would otherwise have to work
    // out which of two the one number was about.
    page: FILE,
    comparePage: COMPARE_FILE,
    engine: "chromium",
    browserVersion: browser.version(),
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
    repetitions: REPETITIONS,
    gestureMs: GESTURE_MS,
    // 1 on every native run, which is every run CI makes. See `CPU_THROTTLE`.
    cpuThrottlingRate: CPU_THROTTLE,
    measuredAt: new Date().toISOString(),
    // One shape per interaction, read off the page each was measured on.
    shapes,
  },
  interactions,
  warmUp,
  coldOpen: {
    medianMs: median(coldOpen),
    repetitionsMs: coldOpen,
  },
};

await browser.close();

mkdirSync("perf", { recursive: true });
writeFileSync(RESULTS, `${JSON.stringify(results, null, 2)}\n`);
console.error(`wrote ${RESULTS}`);
