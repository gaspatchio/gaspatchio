// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The rollforward model — one state, a fund — read through the page.
 *
 * The scripted form of the written read of this model taken on 2026-09-17
 * — the same walk, scripted so that it stays true, asking that read's questions in that read's order.
 * See `level3.spec.ts` for what is asserted as written and what is derived from
 * the fixture, and `walk.ts` for the mechanics the four share.
 *
 * This walk is shorter than the other three: one state, one compilation and
 * two computed columns, so there is no conditional, no lookup and no
 * accumulation to work through.
 *
 * **The compiled rollforward's own case has changed, and the change is the
 * movements arriving.** The record quotes the box saying *"the export does not yet carry
 * the movements inside a compiled rollforward — the opening balance, each
 * charge and each credit"* and stopping at the states. That sentence is gone
 * from the page, because the export carries them: the panel draws the
 * waterfall — opening, one line per step of the chain, closing — and states
 * `closing = opening + Σ movements` under it. So the case below asserts the
 * waterfall where the record's version asserted the admission. That is this
 * unit's doing and not a regression: the record was a faithful reading of a
 * page that could not answer the question a rollforward is audited by, and the
 * page answers it now. Every other case on this walk is the record's, unedited.
 */

import { expect, test } from "@playwright/test";

import { formatFormula, formatValue, shortFingerprint } from "../../src/reader/format";
import { coneWindow } from "../../src/reader/window";
import { fixture, held, modelTab, pageFor, reading, photograph, VIEWPORT } from "./walk";

test.use({ viewport: VIEWPORT });

const MODEL = "rollforward";
const index = fixture(MODEL);

/** The period the record stands at: six, halfway through a twelve-month fund. */
const CURSOR = 6;

/** The compiled rollforward, as the file names it. */
const COMPILED = "rollforward:ff70eb792aee";

/** A number written the way the waterfall writes it, off the same function. */
function fmt(value: number): string {
  return formatValue(value);
}

/** What one movement moved at the cursor, out of the fixture's own array. */
function at(moved: Map<string, unknown>, key: string): number {
  return (moved.get(key) as number[])[CURSOR];
}

test("who am I looking at", async ({ page }) => {
  await page.goto(pageFor(MODEL));
  await expect(page.getByTestId("grid")).toBeVisible();

  // "The header strip reads `policy RF001 model.py 3755dc9b`".
  const policy = String(index.artifact.enrichment?.policy_id);
  const file = String(index.artifact.model.source_path).split("/").pop();
  const eight = shortFingerprint(index.artifact.graph_fingerprint);
  const strip = (await page.locator(".identity").innerText()).replace(/\s+/g, " ").trim();
  expect(strip).toBe(`policy ${policy} ${String(file)} ${eight}`);
  await expect(page.getByTestId("fingerprint")).toHaveAttribute(
    "title",
    index.artifact.graph_fingerprint,
  );

  // "The holes chip is absent: the file records no hole."
  expect(index.artifact.holes).toEqual([]);
  await expect(page.getByTestId("holes-chip")).toHaveCount(0);
});

test("what is the fund's growth at period 6, and what went into it", async ({ page }) => {
  await reading(page, MODEL, "av_growth", CURSOR);

  // "the cell reads 6,465.29, the formula row under the name reads af.av - af.av_init"
  await expect(
    page.locator(`td[data-column="av_growth"][data-period="${String(CURSOR)}"]`),
  ).toHaveText(held(index, "av_growth@1", CURSOR));
  await expect(page.locator('td[data-formula-for="av_growth"]')).toHaveText(
    formatFormula(index.nodes.get("av_growth@1")?.formula ?? null),
  );

  // "the operand outlines on row 6 are av[6] = 106,465.29" — one, because the
  // other term is a scalar and a scalar has no row to outline; it is pinned.
  const cell = page.locator(`td[data-column="av"][data-period="${String(CURSOR)}"]`);
  await expect(cell).toHaveClass(/\boperand\b/);
  await expect(cell).toHaveText(held(index, "av@1", CURSOR));
  await page.getByTestId("search").fill("av_init");
  await expect(page.getByTestId("search-found")).not.toContainText("0 of");
  await page.getByTestId("search").fill("");

  // "The grid draws 5 per-period columns; its 5 scalars are
  // reached by the search box, which counts over every column in the final schema."
  await expect(page.locator("th[data-column]")).toHaveCount(index.perPeriodColumns.length);
  await page.getByTestId("search").fill("_");
  await expect(page.getByTestId("search-found")).toContainText(
    `of ${String(index.finalColumns.length)}`,
  );
  await page.getByTestId("search").fill("");
});

test("what fed it, and what does it feed", async ({ page }) => {
  await reading(page, MODEL, "av_growth", CURSOR);

  // "The cone at av_growth reports 4 nodes in the window two steps each way."
  const window = coneWindow(index, "av_growth@1", 2, 2);
  await expect(page.getByTestId("cone-count")).toHaveText(String(window.nodes.length));
  // "Offset loops in the window: none." Nothing in this model reads another
  // period through a facet — the state machine's own carry is inside the box.
  await expect(page.locator(".edge-offset")).toHaveCount(0);
});

test("arithmetic — av_growth at 6", async ({ page }) => {
  await reading(page, MODEL, "av_growth", CURSOR);
  const proof = page.getByTestId("proof");
  await expect(page.getByTestId("proof-idiom")).toHaveText("arithmetic");

  const node = index.nodes.get("av_growth@1");
  await expect(proof.locator('[data-kind="formula"] .text')).toHaveText(
    formatFormula(node?.formula ?? null),
  );
  const substituted = index.traceOf(String(node?.id))?.find((step) => step.step === 2)?.expr;
  expect(typeof substituted).toBe("string");
  await expect(proof.locator('[data-kind="lowered"] .text').first()).toHaveText(
    String(substituted),
  );

  // "av[6] = 106,465.29" and "av_init = 100,000.00" — the list subscripted, the
  // scalar bare.
  await expect(proof.locator('[data-operand="av@1"]')).toHaveText(
    `av[${String(CURSOR)}] = ${held(index, "av@1", CURSOR)}`,
  );
  await expect(proof.locator('[data-operand="av_init"]')).toHaveText(
    `av_init = ${held(index, "av_init", CURSOR)}`,
  );
  await expect(proof.locator('[data-kind="result"] .text')).toHaveText(
    held(index, "av_growth@1", CURSOR),
  );

  // "disagreement flag: absent; footer: model.py:49 local sha256:… graph sha256:…"
  await expect(page.getByTestId("disagreement")).toHaveCount(0);
  const footer = page.getByTestId("proof-footer");
  await expect(footer).toContainText(String(node?.source_location));
  await expect(footer).toContainText(String(node?.local_fingerprint));
  await expect(footer).toContainText(String(node?.fingerprint));
});

test("the compiled rollforward, clicked in the cone", async ({ page }) => {
  await reading(page, MODEL, "av_growth", CURSOR);
  // The box is on the canvas from `av_growth`'s own window, which is how the
  // record reached it: a click in the cone is a click in the grid.
  await page.locator(`.react-flow__node[data-id="${COMPILED}"]`).click();
  const proof = page.getByTestId("proof");
  await expect(page.getByTestId("proof-idiom")).toHaveText("rollforward");

  // "the states it runs: av" — the record's sentence, and now the only note.
  const states = index.nodes.get(COMPILED)?.states ?? [];
  expect(states).toEqual(["av"]);
  const notes = proof.locator('[data-kind="note"] .text');
  await expect(notes).toHaveCount(1);
  await expect(notes.nth(0)).toHaveText(`the states it runs: ${states.join(", ")}`);
  // The movements the record found missing. One line per step of the
  // chain, in chain order, each equal to the fixture's own array at the
  // cursor, and the floor's row at zero because on this model it cannot bite.
  const increments = index.nodes.get(COMPILED)?.increments ?? [];
  expect(increments.map((one) => one.operation)).toEqual(["Grow", "Charge", "Floor"]);
  const moved = index.movementsOf(COMPILED);
  expect([...moved.keys()]).toEqual(["fund_return", "me_charge", "floor@3"]);
  const balance = index.sampleOf("state:av@eop") as number[];
  const rows = proof.locator('[data-kind="substitution"] .text');
  await expect(rows.nth(0)).toHaveText(`opening   ${fmt(balance[CURSOR - 1])}`);
  await expect(rows.nth(1)).toHaveText(`fund_return   ${fmt(at(moved, "fund_return"))}`);
  await expect(rows.nth(2)).toHaveText(`me_charge   ${fmt(at(moved, "me_charge"))}`);
  await expect(rows.nth(3)).toHaveText(`floor@3   ${fmt(at(moved, "floor@3"))}`);
  expect(at(moved, "floor@3")).toBe(0);
  await expect(proof.locator('[data-kind="result"] .text')).toHaveText(
    `closing   ${fmt(balance[CURSOR])}`,
  );

  // The one arithmetic the page states, and it closes: no amber on the line.
  const opening = balance[CURSOR - 1];
  const total =
    at(moved, "fund_return") + at(moved, "me_charge") + at(moved, "floor@3");
  await expect(proof.locator('[data-kind="check"] .text')).toHaveText(
    `closing = opening + Σ movements   ${fmt(balance[CURSOR])} = ${fmt(opening)} ` +
      `+ ${fmt(total)}`,
  );
  await expect(proof.locator('[data-kind="check"][data-flagged]')).toHaveCount(0);
  // And it is true of the numbers, not only of the sentence, within the budget
  // the page allows a document whose five terms were rounded to six decimals.
  expect(Math.abs(balance[CURSOR] - (opening + total))).toBeLessThanOrEqual(5 * 5e-7);

  // "the cone at the rollforward: 7 nodes"
  const window = coneWindow(index, COMPILED, 2, 2);
  await expect(page.getByTestId("cone-count")).toHaveText(String(window.nodes.length));
  // The box says how many steps it folds: every one of them, since every one
  // is a movement the file now carries an amount for.
  await expect(
    page.locator(`.react-flow__node[data-id="${COMPILED}"] [data-testid="steps-chip"]`),
  ).toHaveText(`${String(increments.length)} steps`);
});

test("is anything unaccounted for", async ({ page }) => {
  await reading(page, MODEL, "av_growth", CURSOR);
  const panel = await modelTab(page);

  await expect(panel.locator('[data-fact="holes"] .fact-value')).toHaveText(
    "no holes — every column is accounted for",
  );
  await expect(panel.locator("[data-hole]")).toHaveCount(0);
  expect(index.artifact.model.results).toBeUndefined();
  await expect(panel.locator('[data-fact="model.results.path"] .fact-value')).toHaveText(
    "no results file recorded — export with --results",
  );
});

test("the page as it was read", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "one engine writes the evidence");
  await reading(page, MODEL, "av_growth", CURSOR);
  await photograph(page, MODEL, CURSOR);
});
