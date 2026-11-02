// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What a pile of frame times is read as.
 *
 * Ported from the script a prototype of this page was measured with before
 * the page was built — the shape, the percentiles and the two counts are its,
 * so the numbers this repository records stay comparable with the ones that
 * decided React Flow was fast enough to build on. Nothing here opens a
 * browser; `measure.mjs` does that and hands the numbers over.
 *
 * **Two clocks, and why.** The first is `requestAnimationFrame` deltas, which
 * is what a reader's eye is measuring. On a machine that keeps up, every one
 * of them comes back at the display's own interval — 16.7 ms at 60 Hz — and a
 * page that rendered nothing at all would report exactly the same, so on its
 * own that clock cannot tell a fast page from a broken instrument. The second
 * is the browser's own accounting of what the main thread did, differenced
 * across an interaction and divided by the frames in it. That one carries the
 * information once the deltas are on the floor: on the prototype it read 0.3 ms
 * per frame idle against 3–10 ms per frame under interaction, on the same rig
 * that produced 33, 66 and 133 ms frames when the graph was made eight times
 * bigger. Both are written to the results file; only the first has a budget.
 */

/**
 * The value at one percentile of a sample.
 *
 * @param values - The frame times, in any order.
 * @param p - The percentile wanted, 0 to 100.
 * @returns The value at it.
 */
export function percentile(values, p) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
}

/**
 * One interaction's frame times, read.
 *
 * `over16_7` is the frames that missed 60 Hz and `over33` the frames that
 * missed 30 — the second is the one with a budget, because a single missed
 * frame is invisible and a run of them is what a drag catching feels like.
 *
 * @param values - The frame times, in milliseconds.
 * @returns The percentiles, the extremes and the two counts.
 */
export function stats(values) {
  return {
    frames: values.length,
    p50: round(percentile(values, 50)),
    p95: round(percentile(values, 95)),
    p99: round(percentile(values, 99)),
    max: round(Math.max(...values)),
    mean: round(values.reduce((a, b) => a + b, 0) / values.length),
    over16_7: values.filter((ms) => ms > 16.7).length,
    over33: values.filter((ms) => ms > 33).length,
  };
}

/**
 * The middle value of a sample.
 *
 * @param values - The measurements.
 * @returns The median, rounded the way every other figure here is.
 */
export function median(values) {
  return round(percentile(values, 50));
}

/**
 * Two decimal places, as a number rather than as text.
 *
 * @param value - A measurement in milliseconds.
 * @returns The same measurement, at the precision the numbers are quoted in.
 */
export function round(value) {
  return Number(value.toFixed(2));
}

/**
 * The browser's own account of what the main thread has done so far.
 *
 * Cumulative since the page opened, so it is only meaningful as a difference
 * across an interaction — which is what `metricDelta` takes.
 *
 * @param client - A CDP session on the page, with `Performance` enabled.
 * @returns The durations and counts, as the protocol reports them.
 */
export async function mainThreadTotals(client) {
  const { metrics } = await client.send("Performance.getMetrics");
  const all = Object.fromEntries(metrics.map((metric) => [metric.name, metric.value]));
  return {
    ScriptDuration: all.ScriptDuration,
    LayoutDuration: all.LayoutDuration,
    RecalcStyleDuration: all.RecalcStyleDuration,
    TaskDuration: all.TaskDuration,
    LayoutCount: all.LayoutCount,
    RecalcStyleCount: all.RecalcStyleCount,
  };
}

/**
 * What the main thread did per frame, between two readings.
 *
 * The protocol reports durations in seconds and counts as counts, so the
 * durations come out as milliseconds per frame and the counts as counts per
 * frame.
 *
 * @param before - The totals before the interaction.
 * @param after - The totals after it.
 * @param frames - How many frames were recorded in between.
 * @returns One number per metric.
 */
export function mainThreadPerFrame(before, after, frames) {
  const perFrame = {};
  for (const name of Object.keys(before)) {
    const moved = after[name] - before[name];
    perFrame[name] = name.endsWith("Duration")
      ? round((moved * 1000) / frames)
      : round(moved / frames);
  }
  return perFrame;
}

/**
 * The same metric across repetitions, averaged.
 *
 * @param perFrame - One reading per repetition.
 * @returns The mean of each metric.
 */
export function averaged(perFrame) {
  const names = Object.keys(perFrame[0] ?? {});
  return Object.fromEntries(
    names.map((name) => [
      name,
      round(perFrame.reduce((total, one) => total + one[name], 0) / perFrame.length),
    ]),
  );
}
