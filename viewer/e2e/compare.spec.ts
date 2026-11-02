// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The comparison page, read off the page itself.
 *
 * The page carries `fixtures/compare-after.json` and `fixtures/compare-before.json`
 * — two exports of level 4 with two changes between them and no others, both
 * known before the page is asked: `maint_fee_pp`'s formula edited in place, and
 * the `lapse_rates` table re-sourced at duration 0 on `L001`.
 *
 * **The case that matters most is the first one.** The set of columns the page
 * marks as model-changed must equal the set `gspio diff` reports as
 * calculations somebody edited, and the set it marks as numbers-changed must
 * equal the set the report attributes to what moved underneath — in both
 * directions. Two implementations of one definition, checked against each
 * other, which is §12.5's own discipline. The fixed reference is the committed
 * report; where this machine has the Python venv, the report is taken again
 * from the command and held to being the same report, so a fixture that drifted
 * away from the code would be caught here rather than trusted.
 *
 * **The agreement is over `model` and `numbers`, and it says so.** The
 * page later gained a third mark, *data*, for a column whose sampled
 * values moved under an unmoved fingerprint — and `gspio diff`'s report
 * carries no such kind, because it is a report of definitions and this is not
 * one. So the two readings are held to each other over the two kinds they both
 * express, and *data* is asserted separately against the fixtures' own
 * `value_sample` arrays. Holding the page to a report for something the report
 * does not state would be asserting the report says something it does not.
 *
 * The *data* mark's own page is `dist/compare-book-after.html`, from
 * `fixtures/compare-book-{before,after}.json`: one model over two books —
 * level 4 against `model_points.parquet` and against
 * `model_points_2022Q4IF.parquet` — so nothing in the model moved at all and
 * the mark has a fixture it is the only thing in.
 *
 * **And one page carries the scenario export on both sides**,
 * `dist/scenarios-self.html`. Which entry of the earlier axis answers to the
 * one the reader is standing on is the comparison's own question, and it was
 * once answered in the unit test alone: with the `filter` dropped from the entry
 * identity, `test/compare.test.ts` failed and not one of the nineteen
 * end-to-end cases for scenarios and comparisons moved. A document compared
 * with itself is the case that cannot be got right by accident — every entry
 * has exactly one right answer and it is itself — and on a cross-joined axis
 * six entries differ in nothing but the cut.
 *
 * **The results file has a page of its own too**, packed from
 * `fixtures/compare-before.json` compared with itself as though each run had
 * named a different results file, so the file is the only thing that moved.
 * The two documents are written here under names git ignores, and
 * `fixtures/compare-results-report.json` is `gspio diff`'s report over them,
 * held to the command where the venv is installed as the first report is.
 */

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { RESULTS_FILE_MOVED } from "../src/reader/compare";
import { formatValue } from "../src/reader/format";
import type { Artifact, ArtifactNode } from "../src/reader/types";

/** The page `pack.mjs` wrote from the two fixtures. */
const PAGE = pathToFileURL(resolve("dist/compare-after.html")).href;

/** The page where one model was run over two books, and nothing else moved. */
const BOOK_PAGE = pathToFileURL(resolve("dist/compare-book-after.html")).href;

/** The page carrying one cross-joined scenario export as both of its documents. */
const SELF_PAGE = pathToFileURL(resolve("dist/scenarios-self.html")).href;

/** Where `gspio` lives when this repository's Python environment is installed. */
const GSPIO = resolve("../bindings/python/.venv/bin/gspio");

/** One committed fixture, parsed. */
function artifact(name: string): Artifact {
  return JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact;
}

/** The change report, as `gspio diff` writes it. */
interface Report {
  calculations: { node: string; kind: string; change_origin: string | null }[];
  data: { kind: string; name: string | null; before: string | null; after: string | null }[];
}

/** The committed report, which is this spec's fixed reference. */
const committed = JSON.parse(readFileSync(resolve("fixtures/compare-report.json"), "utf8")) as Report;

/**
 * `gspio diff --json` over two fixtures, as text — the committed pair unless told.
 *
 * The command exits 1 when something moved, which is the answer here and not a
 * failure — so the report is read off stdout either way. An exit of 2 would be
 * the two artifacts refusing to be compared at all, and that is a failure: it
 * would mean the page compared what the command will not.
 */
function reportFrom(
  gspio: string,
  earlier = resolve("fixtures/compare-before.json"),
  later = resolve("fixtures/compare-after.json"),
): string {
  const args = ["diff", earlier, later, "--json"];
  try {
    return execFileSync(gspio, args, {
      cwd: resolve("."),
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    });
  } catch (failed) {
    const ran = failed as { status?: number; stdout?: string };
    if (ran.status !== 1 || ran.stdout === undefined) throw failed;
    return ran.stdout;
  }
}

/** Open the page and wait until the grid has drawn. */
async function opened(page: Page): Promise<void> {
  await page.goto(PAGE);
  await expect(page.getByTestId("grid")).toBeVisible();
}

/** Every entry of the changes list, as the page draws it. */
async function listed(page: Page): Promise<{ node: string; mark: string; size: string }[]> {
  return page.locator('[data-testid="changes"] li.change').evaluateAll((rows) =>
    rows.map((row) => ({
      node: row.getAttribute("data-node") ?? "",
      mark: row.getAttribute("data-mark") ?? "",
      size: row.querySelector(".change-size")?.textContent ?? "",
    })),
  );
}

test("what the page marks is what gspio diff reports, in both directions", async ({ page }) => {
  await opened(page);
  const entries = await listed(page);

  const marked = (which: string): string[] =>
    entries
      .filter((entry) => entry.mark === which)
      .map((entry) => entry.node)
      .sort();
  const reported = (self: boolean): string[] =>
    committed.calculations
      .filter((one) =>
        self ? one.kind !== "changed" || one.change_origin === "self" : one.change_origin === "inherited",
      )
      .map((one) => one.node)
      .sort();

  // Both directions in one assertion each: set equality is symmetric, so
  // neither reading marks a node the other does not. Over the two kinds the
  // report expresses — it has no kind for a moved value under an unmoved
  // fingerprint, and these two fixtures were exported over one book, so there
  // is no *data* entry here to have to set aside.
  expect(marked("model")).toEqual(reported(true));
  expect(marked("numbers")).toEqual(reported(false));
  expect(marked("data")).toEqual([]);
  expect(entries).toHaveLength(committed.calculations.length);

  // And the two changes that were actually made, named.
  expect(marked("model")).toEqual(["maint_fee_pp@1"]);
  const bases = await page.getByTestId("bases").innerText();
  expect(bases).toContain("lapse_rates");
});

test("the committed report is the report the command writes today", async () => {
  // The fixture is a fixed reference and this is what keeps it fixed to the
  // code rather than to the day it was written. Skipped where the Python
  // environment is not installed, which is the case on a viewer-only machine;
  // the agreement above still runs, against the committed report.
  test.skip(!existsSync(GSPIO), "the repository's Python environment is not installed here");
  const written = JSON.parse(reportFrom(GSPIO)) as Report;
  expect(written.calculations).toEqual(committed.calculations);
  expect(written.data).toEqual(committed.data);
});

test("the changes list is ranked by the magnitude the two files' own samples give", async ({
  page,
}) => {
  await opened(page);
  const entries = await listed(page);

  const before = artifact("compare-before");
  const after = artifact("compare-after");
  const sampleOf = (file: Artifact, id: string): unknown =>
    file.nodes.find((node: ArtifactNode) => node.id === id)?.value_sample;
  /** The largest relative move, recomputed here from the two documents. */
  const largest = (id: string): number | null => {
    const was = sampleOf(before, id);
    const now = sampleOf(after, id);
    const wasRun = Array.isArray(was) ? was : [was];
    const nowRun = Array.isArray(now) ? now : [now];
    let best: number | null = null;
    for (let at = 0; at < Math.min(wasRun.length, nowRun.length); at += 1) {
      const b = wasRun[at];
      const a = nowRun[at];
      if (typeof a !== "number" || typeof b !== "number" || b === 0 || a === b) continue;
      const ratio = Math.abs(a - b) / Math.abs(b);
      if (best === null || ratio > best) best = ratio;
    }
    return best;
  };

  // The model changes come first, exact and in the model's own order.
  const model = entries.filter((entry) => entry.mark === "model").length;
  expect(entries.slice(0, model).every((entry) => entry.mark === "model")).toBe(true);

  // Then the numbers, largest first, by the ratios these two files carry.
  const measured = entries
    .slice(model)
    .filter((entry) => /%$/.test(entry.size))
    .map((entry) => ({ node: entry.node, size: largest(entry.node) ?? 0 }));
  expect(measured.length).toBeGreaterThan(20);
  const descending = [...measured].sort((a, b) => b.size - a.size);
  expect(measured.map((one) => one.node)).toEqual(descending.map((one) => one.node));

  // A column the digests say moved and whose sampled numbers did not is last
  // and says so, rather than being hidden or being given a magnitude of zero.
  const still = entries.filter((entry) => entry.size.trim() === "no move here");
  expect(still.map((one) => one.node)).toContain("base_lapse_rate@1");
  expect(entries.slice(entries.length - still.length).map((one) => one.node)).toEqual(
    still.map((one) => one.node),
  );
});

test("the floor hides exactly the entries below it and nothing else", async ({ page }) => {
  await opened(page);
  const all = await listed(page);
  // Default zero: everything shown, ordered, and the reader cuts.
  await expect(page.getByTestId("floor")).toHaveValue("0");
  expect(all).toHaveLength(committed.calculations.length);
  await expect(page.getByTestId("floor-cut")).toHaveCount(0);

  /** What the page printed as a percentage, read back as a ratio. */
  const ratio = (size: string): number | null => {
    const found = /^([\d.]+)%$/.exec(size.trim());
    return found === null ? null : Number(found[1]) / 100;
  };

  for (const floor of ["1", "0.01"]) {
    await page.getByTestId("floor").fill(floor);
    const shown = (await listed(page)).map((entry) => entry.node);
    const cut = Number(floor) / 100;
    // Exactly the entries carrying a measured ratio at or above the floor,
    // plus every entry that carries no ratio to be below one: a model change
    // is exact, a move out of zero was never divided, and "no move here" is
    // not a small move.
    // The floor is applied to every kind that carries a measurement — a data
    // entry is cut by a floor it is under exactly as a numbers entry is.
    const wanted = all
      .filter((entry) => {
        const size = ratio(entry.size);
        return entry.mark === "model" || size === null || size >= cut;
      })
      .map((entry) => entry.node);
    expect(shown).toEqual(wanted);
    await expect(page.getByTestId("floor-cut")).toHaveText(
      `${String(all.length - wanted.length)} below the floor`,
    );
  }
});

test("a model-changed column shows both formulas, before on the left", async ({ page }) => {
  await opened(page);
  await page.locator('[data-testid="changes"] li[data-node="maint_fee_pp@1"] button').click();

  const before = page.locator('.proof-one.before');
  const after = page.locator('.proof-one.after');
  await expect(before).toBeVisible();
  await expect(after).toBeVisible();

  // Each proof's formula is its own document's, quoted.
  const earlier = artifact("compare-before").nodes.find((node) => node.id === "maint_fee_pp@1");
  const later = artifact("compare-after").nodes.find((node) => node.id === "maint_fee_pp@1");
  await expect(before.locator('li[data-kind="formula"] .text')).toHaveText(String(earlier?.formula));
  await expect(after.locator('li[data-kind="formula"] .text')).toHaveText(String(later?.formula));
  expect(earlier?.formula).not.toBe(later?.formula);

  // And the footers stamp two different local fingerprints, which is what
  // "the model moved" means about this column.
  await expect(page.getByTestId("proof-footer-before")).toContainText(
    String(earlier?.local_fingerprint),
  );
  await expect(page.getByTestId("proof-footer")).toContainText(String(later?.local_fingerprint));
});

test("a numbers-changed column shows one formula and two sets of operands", async ({ page }) => {
  await opened(page);
  await page.locator('[data-testid="changes"] li[data-node="pols_lapse@1"] button').click();

  const before = page.locator('.proof-one.before');
  const after = page.locator('.proof-one.after');
  const earlier = artifact("compare-before").nodes.find((node) => node.id === "pols_lapse@1");
  const later = artifact("compare-after").nodes.find((node) => node.id === "pols_lapse@1");

  // One formula, written twice.
  expect(earlier?.formula).toBe(later?.formula);
  await expect(before.locator('li[data-kind="formula"] .text')).toHaveText(String(earlier?.formula));
  await expect(after.locator('li[data-kind="formula"] .text')).toHaveText(String(later?.formula));

  // And the substituted operands differ, which is the whole of the change.
  const terms = async (side: typeof before): Promise<string[]> =>
    side.locator('li[data-kind="substitution"] .term, li[data-kind="substitution"] .text').allInnerTexts();
  const was = await terms(before);
  const now = await terms(after);
  expect(was.length).toBeGreaterThan(0);
  expect(was).not.toEqual(now);
});

test("the grid marks the changed columns and the selected one carries both numbers", async ({
  page,
}) => {
  await opened(page);
  const entries = await listed(page);
  const byNode = new Map(entries.map((entry) => [entry.node, entry.mark]));

  // Every marked heading wears the mark the list gives that column, and no
  // heading the list does not name wears one.
  const headings = await page
    .locator(".grid thead tr.names th[data-mark]")
    .evaluateAll((cells) =>
      cells.map((cell) => ({
        column: cell.getAttribute("data-column") ?? "",
        mark: cell.getAttribute("data-mark") ?? "",
        says: cell.querySelector(".chip.mark")?.textContent ?? "",
      })),
    );
  expect(headings.length).toBeGreaterThan(0);
  for (const heading of headings) {
    expect(byNode.get(`${heading.column}@1`)).toBe(heading.mark);
    // Legible without colour: the chip says which kind it is, in a word.
    expect(heading.says).toBe(heading.mark);
  }

  // The selected column's cells carry both numbers; a cell whose value did not
  // move carries one.
  await page.locator('[data-testid="changes"] li[data-node="pols_lapse@1"] button').click();
  const before = artifact("compare-before").nodes.find((node) => node.id === "pols_lapse@1");
  const after = artifact("compare-after").nodes.find((node) => node.id === "pols_lapse@1");
  const cell = page.locator('.grid td.sel[data-period="0"]');
  await expect(cell).toHaveAttribute("data-before", /\d/);
  const text = (await cell.innerText()).replace(/\s+/g, " ");
  expect(text).toContain("→");
  expect((before?.value_sample as number[])[0]).not.toBe((after?.value_sample as number[])[0]);
});

test("the cone marks the same columns the same way", async ({ page }) => {
  await opened(page);
  await page.locator('[data-testid="changes"] li[data-node="maint_fee_pp@1"] button').click();
  const box = page.locator('.react-flow__node[data-id="maint_fee_pp@1"]');
  await expect(box).toBeVisible();
  await expect(box.getByTestId("cone-mark")).toHaveText("model");
});

test("the identity strip names both documents before anything says what changed", async ({
  page,
}) => {
  await opened(page);
  const before = artifact("compare-before");
  const after = artifact("compare-after");
  const strip = page.getByTestId("compared");
  await expect(strip).toBeVisible();
  await expect(page.getByTestId("seal-before")).toHaveAttribute(
    "title",
    String(before.document_digest),
  );
  await expect(page.getByTestId("seal-after")).toHaveAttribute("title", String(after.document_digest));
  expect(await strip.innerText()).toContain(before.created_at.slice(0, 10));
});

test("selecting an entry in the list selects that column everywhere", async ({ page }) => {
  await opened(page);
  await page.locator('[data-testid="changes"] li[data-node="pv_net_cf@1"] button').click();
  await expect(page.getByTestId("proof-idiom")).toBeVisible();
  await expect(page.locator('.proof-one.after .at')).toContainText("pv_net_cf");
  await expect(page.locator('[data-testid="changes"] li.change.sel')).toHaveAttribute(
    "data-node",
    "pv_net_cf@1",
  );
});

test("the earlier proof settles on rest and never shows another period's numbers", async ({
  page,
}) => {
  await opened(page);
  await page.locator('[data-testid="changes"] li[data-node="pols_lapse@1"] button').click();

  // At rest, both sides are worked out.
  await expect(page.locator(".proof-one.before .lines")).toBeVisible();
  await expect(page.getByTestId("proof-settling")).toHaveCount(0);

  // Scrubbing: the earlier side is not computed at all, and says so in a word.
  // Two worked examples per period step cost a frame, and the alternative — a
  // deferred render — would put period 40 on the left beside period 45 on the
  // right, which is the one thing the page must never draw.
  await page.getByTestId("grid").click();
  const from = Number(await page.getByTestId("cursor").inputValue());
  const steps = 20;
  // One read per step, in the page, because the assertion is about what is on
  // the screen *between* two key presses: a round trip per fact would put more
  // than the settling time between them and measure a page at rest.
  const duringTheScrub = [];
  for (let step = 0; step < steps; step += 1) {
    await page.keyboard.press("ArrowDown");
    duringTheScrub.push(
      await page.evaluate(() => ({
        settling: document.querySelectorAll('[data-testid="proof-settling"]').length,
        // The earlier side's period, where it is drawn at all. This is the
        // invariant, and it does not depend on how fast the keys arrive: if
        // the earlier document is on the screen, it is on the screen at the
        // period the cursor is standing on and at no other.
        before:
          document.querySelector(".proof-one.before .at")?.textContent?.match(/period (\d+)/)?.[1] ??
          null,
        cursor: (document.querySelector('[data-testid="cursor"]') as HTMLInputElement).value,
      })),
    );
  }
  // The word was on the screen while the cursor was moving — which is what
  // says the earlier proof is not being computed on every step.
  expect(duringTheScrub.filter((seen) => seen.settling === 1).length).toBeGreaterThan(0);
  // And wherever the earlier document *was* drawn, it was drawn at the
  // cursor's own period. A deferred render would fail this line, which is the
  // reason the panel withholds the proof rather than lagging it.
  for (const seen of duringTheScrub) {
    if (seen.before !== null) expect(seen.before).toBe(seen.cursor);
  }

  // At rest it fills in, at the cursor's period and at no other.
  await expect(page.locator(".proof-one.before .lines")).toBeVisible();
  await expect(page.getByTestId("proof-settling")).toHaveCount(0);
  const period = Number(await page.getByTestId("cursor").inputValue());
  expect(period).toBe(from + steps);
  await expect(page.locator(".proof-one.before .at")).toContainText(`period ${String(period)}`);

  // **And at no other period.** `pols_lapse` reads three columns, none of them
  // with an offset, so every substituted term must be indexed at the cursor's
  // own period — which is the assertion a deferred render would fail, because
  // it would have left the period before it on the screen.
  const terms = await page
    .locator('.proof-one.before li[data-kind="substitution"] .term')
    .allInnerTexts();
  expect(terms.length).toBeGreaterThan(0);
  for (const term of terms) {
    expect(term).toMatch(new RegExp(`\\[${String(period)}\\]`));
  }

  // The values are the earlier document's own, read out of the fixture rather
  // than off the panel opposite: the two sides differ, which is why this
  // column is in the list at all.
  const earlier = artifact("compare-before").nodes.find((node) => node.id === "lapse_rate_mth@1");
  const run = earlier?.value_sample as number[];
  const operand = terms.find((term) => term.startsWith("lapse_rate_mth"));
  expect(operand).toBe(`lapse_rate_mth[${String(period)}] = ${formatValue(run[period])}`);
  // And they are this period's rather than the step before it, which is only
  // a meaningful assertion where the two differ.
  expect(run[period]).not.toBe(run[period - 1]);
});

test("a page where only the book moved marks every moved column data, and nothing else", async ({
  page,
}) => {
  await page.goto(BOOK_PAGE);
  await expect(page.getByTestId("grid")).toBeVisible();
  const entries = await listed(page);

  // Asserted against the two fixtures' own samples and against nothing else.
  // `gspio diff` has no kind for this, which is the whole reason the mark is
  // derived in the page: its report over these two files is empty of
  // calculations and names the book underneath, and a reader who saw that
  // report alone would be told nothing moved.
  const before = artifact("compare-book-before");
  const after = artifact("compare-book-after");
  const sampleOf = (file: Artifact, id: string): unknown =>
    file.nodes.find((node: ArtifactNode) => node.id === id)?.value_sample;
  const unequal = after.nodes
    .filter(
      (node) => JSON.stringify(sampleOf(before, node.id)) !== JSON.stringify(sampleOf(after, node.id)),
    )
    .map((node) => node.id);

  expect(unequal.length).toBeGreaterThan(10);
  expect(entries.map((entry) => entry.node).sort()).toEqual([...unequal].sort());
  expect(entries.every((entry) => entry.mark === "data")).toBe(true);
  // Every fingerprint held, which is what makes this the case that matters: under
  // the old rule the list was empty and the grid showed two different numbers.
  expect(after.graph_fingerprint).toBe(before.graph_fingerprint);

  // Ranked with the rest, by the magnitude these two files give. Read off the
  // measurement the row carries rather than off the percentage it prints: a
  // very small move is printed in exponent form, and re-parsing a rendering is
  // a second implementation of the rendering.
  const sizes = await page
    .locator('[data-testid="changes"] li.change')
    .evaluateAll((rows) =>
      rows
        .map((row) => row.querySelector(".change-size")?.getAttribute("data-magnitude") ?? "")
        .filter((one) => one !== "")
        .map(Number),
    );
  expect(sizes.length).toBeGreaterThan(5);
  expect(sizes).toEqual([...sizes].sort((a, b) => b - a));

  // The book itself is named underneath the list, which is what moved, and
  // the page says so rather than that nothing explains the move.
  await expect(page.getByTestId("bases")).toContainText("model points");
  await expect(page.getByTestId("bases")).toContainText("model_points_2022Q4IF.parquet");
  await expect(page.getByTestId("data-note")).toHaveCount(0);
});

test("the book's mark is a word and an outline, and the grid and the cone wear it", async ({
  page,
}) => {
  await page.goto(BOOK_PAGE);
  await expect(page.getByTestId("grid")).toBeVisible();
  const entries = await listed(page);
  const first = entries.find((entry) => entry.node.endsWith("@1")) ?? entries[0]!;

  // Legible without colour: the chip says the kind in a word, and its title
  // says it in a sentence.
  const chip = page.locator(`[data-testid="changes"] li[data-node="${first.node}"] .chip.mark`);
  await expect(chip).toHaveText("data");
  await expect(chip).toHaveAttribute("title", "the book moved");
  // A third outline, not a third colour.
  expect(
    await chip.evaluate((one) => getComputedStyle(one).borderStyle),
  ).toBe("dotted");

  await page.locator(`[data-testid="changes"] li[data-node="${first.node}"] button`).click();
  const box = page.locator(`.react-flow__node[data-id="${first.node}"]`);
  await expect(box).toBeVisible();
  await expect(box.getByTestId("cone-mark")).toHaveText("data");

  // And the heading the reader finds the column under wears the same word.
  const column = first.node.replace(/@\d+$/, "");
  const heading = page.locator(`.grid thead tr.names th[data-column="${column}"]`);
  if ((await heading.count()) > 0) {
    await expect(heading).toHaveAttribute("data-mark", "data");
    await expect(heading.locator(".chip.mark")).toHaveText("data");
  }
});

test("a scenario export compared with itself matches every entry to its own cut", async ({
  page,
}) => {
  // Six entries: three per-scenario folds and three rows of policy 1, telling
  // each other apart by `filter` and by nothing else. Compared with itself,
  // each has one answer on the earlier axis and it is the entry the reader is
  // standing on — so nothing moved, for every one of them. Drop the cut from
  // the entry identity and each finds three answers instead, which the page
  // refuses in a sentence rather than resolving to the first.
  const self = artifact("scenarios");
  expect(self.policies).toHaveLength(6);
  expect(new Set(self.policies.map((entry) => entry.filter)).size).toBe(3);

  await page.goto(SELF_PAGE);
  await expect(page.getByTestId("grid")).toBeVisible();
  const switcher = page.getByTestId("policy-switcher");
  const labels = await switcher.locator("option").allInnerTexts();

  for (const [at, entry] of self.policies.entries()) {
    // The page names this entry, on the control the reader chooses it with.
    expect(labels[at]).toContain(String(entry.why));

    await switcher.selectOption(String(at));
    // Compared, not refused: exactly one entry of the earlier axis answers to
    // this one. The note is what stands here when none does or several do.
    await expect(page.getByTestId("policy-note")).toHaveCount(0);
    await expect(page.getByTestId("changes-count")).toHaveText("0 changes");
    await expect(page.getByTestId("bases")).toHaveCount(0);
  }

  // And the link written from one of the three rows called `1` is a link to
  // that row: the same round trip the one-artifact page is held to, on a page
  // carrying two documents.
  const up = self.policies.findIndex(
    (entry) => entry.aggregation === null && entry.filter === 'scenario_id == "UP"',
  );
  expect(up).toBeGreaterThanOrEqual(0);
  await switcher.selectOption(String(up));
  await page.getByTestId("search").fill("pv_net_cf");
  await page.getByTestId("search").press("Enter");
  const cut = new URLSearchParams({ filter: String(self.policies[up]?.filter) })
    .toString()
    .slice("filter=".length);
  await expect.poll(async () => page.evaluate(() => window.location.hash)).toContain(`filter=${cut}`);
  const fragment = await page.evaluate(() => window.location.hash);

  await page.goto(`${SELF_PAGE}${fragment}`);
  await expect(page.getByTestId("policy-switcher")).toHaveValue(String(up));
  await expect(page.getByTestId("link-note")).toHaveCount(0);
  await expect(page.getByTestId("policy-note")).toHaveCount(0);
});

test("a book neither document could digest is written as not compared, with the reason", async ({
  page,
}) => {
  // Two exports whose producers could not vouch for their books, from runs
  // that named no file for their policy data: nothing on either page says
  // whether the policies are the same. The page writes the book underneath
  // anyway, with the reason `gspio diff` gives in place of the two digests,
  // rather than an empty list that would read as "the same policies".
  const detail =
    "No book was handed to the export: the graph was written from its calculations alone, with no policy data beside it.";
  const unvouched = (name: string): Artifact => {
    const one = artifact(name);
    return {
      ...one,
      model: { ...one.model, model_points: null },
      book: { columns: ["point_id"], digest: { omitted: "unavailable", detail } },
    };
  };
  // Written beside the committed fixtures under names git ignores, each
  // renamed into place whole so a second browser's run never reads half.
  for (const [written, from] of [
    ["written-unvouched-before", "compare-before"],
    ["written-unvouched-after", "compare-after"],
  ] as const) {
    const out = resolve(`fixtures/${written}.json`);
    const partial = `${out}.${String(process.pid)}.part`;
    writeFileSync(partial, JSON.stringify(unvouched(from)));
    renameSync(partial, out);
  }
  execFileSync("node", ["pack.mjs", "written-unvouched-after", "--second", "written-unvouched-before"], {
    cwd: resolve("."),
    stdio: "pipe",
  });

  await page.goto(pathToFileURL(resolve("dist/written-unvouched-after.html")).href);
  await expect(page.getByTestId("grid")).toBeVisible();
  const reason = page.getByTestId("bases").getByTestId("base-reason");
  await expect(reason).toHaveCount(1);
  await expect(reason).toContainText("The two books could not be compared");
  await expect(reason).toContainText("No book was handed to the export");
  await expect(page.getByTestId("bases").locator('[data-base="model_points"]')).toHaveCount(1);
});

/** The two results files the committed results report was taken over. */
const RESULTS_Q1 = { path: "results_q1.parquet", fingerprint: `sha256:${"1".repeat(64)}` };
const RESULTS_Q2 = { path: "results_q2.parquet", fingerprint: `sha256:${"2".repeat(64)}` };

/** `compare-before`, as though its run had named `results` when it was exported. */
function namingResults(results: { path: string; fingerprint: string }): Artifact {
  const one = artifact("compare-before");
  return { ...one, model: { ...one.model, results } };
}

/**
 * One derived document, written beside the committed fixtures under a name git
 * ignores and renamed into place whole, so a second browser's run never reads
 * half of it. Returns its path.
 */
function written(name: string, document: Artifact): string {
  const out = resolve(`fixtures/${name}.json`);
  const partial = `${out}.${String(process.pid)}.part`;
  writeFileSync(partial, JSON.stringify(document));
  renameSync(partial, out);
  return out;
}

/** The comparison page `pack.mjs` writes from two fixtures, the later first. */
function packed(later: string, earlier: string): string {
  execFileSync("node", ["pack.mjs", later, "--second", earlier], { cwd: resolve("."), stdio: "pipe" });
  return pathToFileURL(resolve(`dist/${later}.html`)).href;
}

test("the committed results report is the report the command writes today", async () => {
  test.skip(!existsSync(GSPIO), "the repository's Python environment is not installed here");
  const earlier = written("written-results-before", namingResults(RESULTS_Q1));
  const later = written("written-results-after", namingResults(RESULTS_Q2));
  const fixed = JSON.parse(readFileSync(resolve("fixtures/compare-results-report.json"), "utf8")) as Report;
  const today = JSON.parse(reportFrom(GSPIO, earlier, later)) as Report;
  expect(today.calculations).toEqual(fixed.calculations);
  expect(today.data).toEqual(fixed.data);
});

test("a results file that moved is listed under its own heading, saying what its digest shows", async ({
  page,
}) => {
  // One document compared with itself, each side naming a different results
  // file: the file is the only thing that moved, which is the case `gspio diff`
  // used to call nothing moved.
  written("written-results-before", namingResults(RESULTS_Q1));
  written("written-results-after", namingResults(RESULTS_Q2));
  await page.goto(packed("written-results-after", "written-results-before"));
  await expect(page.getByTestId("grid")).toBeVisible();

  await expect(page.getByTestId("changes-count")).toHaveText("0 changes");
  await expect(page.getByTestId("bases")).toHaveCount(0);
  await expect(page.locator(".changes-sub", { hasText: "the results file" })).toBeVisible();
  const entry = page.getByTestId("results").locator('[data-base="results"]');
  await expect(entry).toHaveCount(1);
  await expect(entry).toHaveAttribute("data-name", "results_q2.parquet");
  await expect(entry.locator(".base-kind")).toHaveText("results");
  // Named as a file, and read as one: the digest moves with the writer, so the
  // row says so and points to the step that compares the numbers.
  await expect(entry.getByTestId("base-results")).toHaveText(RESULTS_FILE_MOVED);
  await expect(page.getByTestId("results-note")).toHaveCount(0);
});

test("a results file only one run named is not compared, and the page says which named none", async ({
  page,
}) => {
  written("written-results-named", namingResults(RESULTS_Q2));
  await page.goto(packed("written-results-named", "compare-before"));
  await expect(page.getByTestId("grid")).toBeVisible();

  await expect(page.getByTestId("results")).toHaveCount(0);
  await expect(page.locator(".changes-sub", { hasText: "the results file" })).toBeVisible();
  const note = page.getByTestId("results-note");
  await expect(note).toContainText("The results files were not compared");
  await expect(note).toContainText("the earlier run recorded no checksum of a results file");
  await expect(note).toContainText("to see whether the two results agree");
});

/** The columns the overwrite route moves on these pages: one line, and a line that reads it. */
const OVERWRITTEN = ["claims@1", "net_cf@1"];

/** A sample as a column rewritten to nine tenths of itself holds it. */
function scaled(sample: unknown): unknown {
  if (Array.isArray(sample)) return sample.map(scaled);
  return typeof sample === "number" ? sample * 0.9 : sample;
}

/**
 * A document as the overwrite route leaves its record: a recorded column
 * rewritten straight in the query plan moves the values the export sampled,
 * and nothing a fingerprint, the book or an assumption entry covers.
 */
function overwritten(document: Artifact, ids: string[] = OVERWRITTEN): Artifact {
  return {
    ...document,
    nodes: document.nodes.map((node) =>
      ids.includes(node.id) ? { ...node, value_sample: scaled(node.value_sample) } : node,
    ),
  };
}

/** What the page says of the columns it marks data, where nothing in the record explains them. */
async function saysNothingExplainsIt(page: Page): Promise<void> {
  const entries = await listed(page);
  expect(entries.filter((entry) => entry.mark === "data").map((entry) => entry.node).sort()).toEqual(
    [...OVERWRITTEN].sort(),
  );
  expect(entries.every((entry) => entry.mark === "data")).toBe(true);
  for (const id of OVERWRITTEN) {
    const chip = page.locator(`[data-testid="changes"] li[data-node="${id}"] .chip.mark`);
    await expect(chip).toHaveText("data");
    await expect(chip).toHaveAttribute("title", "nothing in the record explains this move");
  }
  const note = page.getByTestId("data-note");
  await expect(note).toContainText("Nothing in the record explains the moves marked data");
  await expect(note).toContainText("those lines' fingerprints, the book and the producer are the ones they were");
  await expect(note).toContainText("gspio run-artifact … --every-node");
  await expect(note).toContainText("using gspio compare");
  // The book did not move, and the page does not say it did.
  await expect(page.getByTestId("bases")).toHaveCount(0);
  await expect(page.locator('[title="the book moved"]')).toHaveCount(0);

  // The box in the cone and the column's heading say what the list says.
  const first = OVERWRITTEN[0]!;
  await page.locator(`[data-testid="changes"] li[data-node="${first}"] button`).click();
  const box = page.locator(`.react-flow__node[data-id="${first}"]`);
  await expect(box.getByTestId("cone-mark")).toHaveAttribute("title", "nothing in the record explains this move");
  const heading = page.locator(`.grid thead tr.names th[data-column="${first.replace(/@\d+$/, "")}"] .chip.mark`);
  if ((await heading.count()) > 0) {
    await expect(heading).toHaveAttribute("title", "nothing in the record explains this move");
  }
}

test("the overwrite route with both results files named says nothing in the record explains the move", async ({
  page,
}) => {
  written("written-overwrite-before", namingResults(RESULTS_Q1));
  written("written-overwrite-after", overwritten(namingResults(RESULTS_Q2)));
  await page.goto(packed("written-overwrite-after", "written-overwrite-before"));
  await expect(page.getByTestId("grid")).toBeVisible();

  await saysNothingExplainsIt(page);
  await expect(page.getByTestId("results").locator('[data-base="results"]')).toHaveCount(1);
  await expect(page.getByTestId("results-note")).toHaveCount(0);
});

test("the overwrite route with one results file named says the same, and that they were not compared", async ({
  page,
}) => {
  written("written-overwrite-named", overwritten(namingResults(RESULTS_Q2)));
  await page.goto(packed("written-overwrite-named", "compare-before"));
  await expect(page.getByTestId("grid")).toBeVisible();

  await saysNothingExplainsIt(page);
  await expect(page.getByTestId("results")).toHaveCount(0);
  await expect(page.getByTestId("results-note")).toContainText(
    "the earlier run recorded no checksum of a results file",
  );
});

test("a quarter that re-sourced a basis and carries an overwrite does not say the book moved", async ({
  page,
}) => {
  // `compare-after` re-sourced `lapse_rates`, so the lines reading it moved
  // their fingerprints and are marked numbers. These two read no lapse, kept
  // their fingerprints, and are overwritten: the basis explains nothing about
  // them, and neither does the book, which did not move.
  const untouched = ["mort_rate@1", "mort_rate_mth@1"];
  written("written-resourced-overwrite", overwritten(artifact("compare-after"), untouched));
  await page.goto(packed("written-resourced-overwrite", "compare-before"));
  await expect(page.getByTestId("grid")).toBeVisible();

  const entries = await listed(page);
  expect(entries.filter((entry) => entry.mark === "data").map((entry) => entry.node).sort()).toEqual(
    [...untouched].sort(),
  );
  expect(entries.some((entry) => entry.mark === "numbers")).toBe(true);
  for (const id of untouched) {
    const chip = page.locator(`[data-testid="changes"] li[data-node="${id}"] .chip.mark`);
    await expect(chip).toHaveAttribute("title", "nothing in the record explains this move");
  }
  await expect(page.locator('[title="the book moved"]')).toHaveCount(0);
  await expect(page.getByTestId("bases").locator('[data-base="table"]')).toHaveCount(1);
  await expect(page.getByTestId("data-note")).toContainText("Nothing in the record explains the moves marked data");
});

test("a line that moved within the specification's tolerance agrees, and nothing is asked of it", async ({
  page,
}) => {
  // One period of one line moved by nine tenths of what §11.1.12 allows two
  // runs of one model: the scale is the line's, taken over its own values and
  // those of every node it reads, in both documents.
  const line = "claims@1";
  const document = artifact("compare-before");
  const node = document.nodes.find((one) => one.id === line)!;
  let scale = 0;
  const visit = (value: unknown): void => {
    if (Array.isArray(value)) value.forEach(visit);
    else if (typeof value === "number" && Number.isFinite(value)) scale = Math.max(scale, Math.abs(value));
  };
  for (const id of [line, ...node.reads]) visit(document.nodes.find((one) => one.id === id)?.value_sample);
  const sample = node.value_sample as number[];
  const at = sample.findIndex((value) => value !== 0 && Math.abs(value) < scale);
  const nudged = sample.map((value, period) => (period === at ? value + 0.9 * 1e-12 * scale : value));
  written("written-within-tolerance", {
    ...document,
    nodes: document.nodes.map((one) => (one.id === line ? { ...one, value_sample: nudged } : one)),
  });
  await page.goto(packed("written-within-tolerance", "compare-before"));
  await expect(page.getByTestId("grid")).toBeVisible();

  const entries = await listed(page);
  expect(entries.map((entry) => entry.node)).toEqual([line]);
  const chip = page.locator(`[data-testid="changes"] li[data-node="${line}"] .chip.mark`);
  await expect(chip).toHaveText("data");
  await expect(chip).toHaveAttribute("title", "agrees within the specification's tolerance");
  await expect(page.getByTestId("data-note")).toHaveCount(0);
  await expect(page.locator('[title="nothing in the record explains this move"]')).toHaveCount(0);
});
