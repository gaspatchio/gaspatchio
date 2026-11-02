// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Level 3, the mini variable annuity, read through the page.
 *
 * The scripted form of the written read of this model taken on 2026-09-17,
 * so that what it found stays true after that afternoon: this file asks the
 * read's questions in the read's order. A reviewing actuary opened `viewer/fixtures/level3.json` in
 * the page on 2026-09-17, asked who the values belonged to, what the net
 * cashflow at period 12 was and what went into it, what fed it, then one worked
 * example per idiom, then whether anything was unaccounted for, and quoted
 * every answer. Each of those questions is one case below.
 *
 * Where the record quotes a whole line — the note under a conditional, the two
 * lines the Model tab ends with — the line is asserted as written. Where it
 * quotes a number, the number is derived again from the fixture by the function
 * the page writes with, because a figure typed into a test is a figure somebody
 * read off a screen once.
 *
 * The written read kept its own screenshot. The one taken here is the durable
 * form of it, retaken whenever this file runs.
 */

import { expect, test } from "@playwright/test";

import { formatFormula, shortFingerprint } from "../../src/reader/format";
import { proofOf } from "../../src/reader/proof";
import { coneWindow } from "../../src/reader/window";
import { excerptCell, fixture, held, modelTab, pageFor, reading, photograph, VIEWPORT } from "./walk";

test.use({ viewport: VIEWPORT });

const MODEL = "level3";
const index = fixture(MODEL);

/** The period the record stands at, and every case below with it. */
const CURSOR = 12;

test("who am I looking at", async ({ page }) => {
  await page.goto(pageFor(MODEL));
  await expect(page.getByTestId("grid")).toBeVisible();

  // "The header strip reads `policy 1 model.py 9e5bfb4b`" — the policy, the
  // model file and the first eight hex of the graph fingerprint, all three the
  // envelope's own.
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

test("what is the net cashflow at period 12, and what went into it", async ({ page }) => {
  await reading(page, MODEL, "net_cf", CURSOR);

  // "the cell reads 5,895.80"
  await expect(page.locator(`td[data-column="net_cf"][data-period="${String(CURSOR)}"]`)).toHaveText(
    held(index, "net_cf@1", CURSOR),
  );
  // "the formula row under the name reads af.premiums + af.inv_income - …"
  await expect(page.locator('td[data-formula-for="net_cf"]')).toHaveText(
    formatFormula(index.nodes.get("net_cf@1")?.formula ?? null),
  );

  // "the operand outlines on row 12 are claims[12] = 37,971.81, premiums[12] =
  // 0.00, …" — every one of the six, outlined, holding what the file sampled.
  for (const operand of [
    "claims",
    "premiums",
    "expenses",
    "commissions",
    "inv_income",
    "av_change",
  ]) {
    const cell = page.locator(`td[data-column="${operand}"][data-period="${String(CURSOR)}"]`);
    await expect(cell).toHaveClass(/\boperand\b/);
    await expect(cell).toHaveText(held(index, `${operand}@1`, CURSOR));
  }

  // "The grid draws 40 per-period columns; its 29 scalars are
  // reached by the search box, which counts over every column in the final schema."
  await expect(page.locator("th[data-column]")).toHaveCount(index.perPeriodColumns.length);
  await page.getByTestId("search").fill("_");
  await expect(page.getByTestId("search-found")).toContainText(
    `of ${String(index.finalColumns.length)}`,
  );
  await page.getByTestId("search").fill("");
});

test("what fed it, and what does it feed", async ({ page }) => {
  await reading(page, MODEL, "net_cf", CURSOR);

  // "The cone at net_cf reports 21 nodes in the window two steps each way."
  const window = coneWindow(index, "net_cf@1", 2, 2);
  await expect(page.getByTestId("cone-count")).toHaveText(String(window.nodes.length));
  // "Offset loops in the window: ['t+1', 't+1']." Two reads in this window look
  // a period forward, and the page draws each as a loop labelled from the facet.
  await expect(page.locator('.edge-offset[data-label="t+1"]')).toHaveCount(2);
  await expect(page.locator('.edge-offset[data-label="t−1"]')).toHaveCount(0);
});

test("arithmetic — net_cf at 12", async ({ page }) => {
  await reading(page, MODEL, "net_cf", CURSOR);
  const proof = page.getByTestId("proof");
  await expect(page.getByTestId("proof-idiom")).toHaveText("arithmetic");

  // The formula, then the producer's own lowered expression — the whole timelines,
  // first three and last — quoted as step 2 of the file's trace and not redrawn.
  const node = index.nodes.get("net_cf@1");
  await expect(proof.locator('[data-kind="formula"] .text')).toHaveText(
    formatFormula(node?.formula ?? null),
  );
  const substituted = index.traceOf(String(node?.id))?.find((step) => step.step === 2)?.expr;
  expect(typeof substituted).toBe("string");
  await expect(proof.locator('[data-kind="lowered"] .text').first()).toHaveText(
    String(substituted),
  );

  // Then one line per operand at the period, in the file's own order, each
  // carrying the value that operand's timeline holds.
  for (const operand of [
    "premiums",
    "inv_income",
    "claims",
    "expenses",
    "commissions",
    "av_change",
  ]) {
    await expect(proof.locator(`[data-operand="${operand}@1"]`)).toHaveText(
      `${operand}[${String(CURSOR)}] = ${held(index, `${operand}@1`, CURSOR)}`,
    );
  }
  await expect(proof.locator('[data-kind="result"] .text')).toHaveText(
    held(index, "net_cf@1", CURSOR),
  );

  // "disagreement flag: absent; footer: model.py:435 local sha256:… graph sha256:…"
  await expect(page.getByTestId("disagreement")).toHaveCount(0);
  const footer = page.getByTestId("proof-footer");
  await expect(footer).toContainText(String(node?.source_location));
  await expect(footer).toContainText(String(node?.local_fingerprint));
  await expect(footer).toContainText(String(node?.fingerprint));
});

test("conditional — pols_maturity at 12", async ({ page }) => {
  await reading(page, MODEL, "pols_maturity", CURSOR);
  const proof = page.getByTestId("proof");
  await expect(page.getByTestId("proof-idiom")).toHaveText("conditional");

  await expect(proof.locator('[data-kind="formula"] .text')).toHaveText(
    formatFormula(index.nodes.get("pols_maturity@1")?.formula ?? null),
  );
  // The test and both its terms: a list column subscripted, a scalar bare.
  for (const [operand, text] of [
    ["duration_mth_t@1", `duration_mth_t[${String(CURSOR)}]`],
    ["maturity_month@1", "maturity_month"],
    ["survival_prob@1", `survival_prob[${String(CURSOR)}]`],
    ["policy_count", "policy_count"],
  ]) {
    await expect(proof.locator(`[data-operand="${String(operand)}"]`)).toHaveText(
      `${String(text)} = ${held(index, String(operand), CURSOR)}`,
    );
  }

  // "Which branch fired, and what would the other have held?" — this export was
  // made without --branches, so the panel says so and prices neither. The
  // sentence, whole, because it is the page's answer to the question asked.
  expect(index.branchesOf("pols_maturity@1")).toBeUndefined();
  await expect(proof.locator('[data-kind="note"] .text')).toHaveText(
    "the export states only the branch that fired. Run calc-graph with --branches " +
      "and this panel names it and shows what the other branch would have held.",
  );
  await expect(proof.locator('[data-kind="dead"]')).toHaveCount(0);
  await expect(proof.locator('[data-kind="fired"]')).toHaveCount(0);
  await expect(proof.locator('[data-kind="result"] .text')).toHaveText(
    held(index, "pols_maturity@1", CURSOR),
  );
});

test("lookup — mort_rate at 12", async ({ page }) => {
  await reading(page, MODEL, "mort_rate", CURSOR);
  const proof = page.getByTestId("proof");
  await expect(page.getByTestId("proof-idiom")).toHaveText("lookup");

  await expect(proof.locator('[data-kind="formula"] .text')).toHaveText(
    formatFormula(index.nodes.get("mort_rate@1")?.formula ?? null),
  );
  // "Which row of which table" — the one key this lookup reads, at the period.
  await expect(proof.locator('[data-operand="age@1"]')).toHaveText(
    `age[${String(CURSOR)}] = ${held(index, "age@1", CURSOR)}`,
  );
  await expect(proof.locator('[data-kind="excerpt"] .text')).toHaveText(
    "mortality — the row those keys name, with 2 rows either side",
  );

  // "5 rows shown, header `age | mort_rate`, the hit `60 | 0.0344`".
  const table = proofOf(index, "mort_rate@1", CURSOR).table;
  if (table === undefined) throw new Error("the level-3 fixture quotes no row for mort_rate@1");
  const rows = proof.locator(".excerpt-rows tbody tr");
  await expect(rows).toHaveCount(table.rows.length);
  expect(await proof.locator(".excerpt-rows thead th").allInnerTexts()).toEqual(table.header);
  await expect(rows.nth(table.hitRow)).toHaveAttribute("data-hit", "true");
  const hit = proof.locator(".excerpt-rows tbody tr[data-hit]");
  await expect(hit).toHaveCount(1);
  expect((await hit.innerText()).split(/\s+/)).toEqual(
    (table.rows[table.hitRow] ?? []).map(excerptCell),
  );

  // "and is it the table the model says?" — the stamp, truncated on the chip
  // and whole in its title, as a reviewer quotes it.
  const entry = index.tables.get("mortality") as { fingerprint: string };
  await expect(page.getByTestId("table-chip")).toHaveText(shortFingerprint(entry.fingerprint));
  await expect(page.getByTestId("table-chip")).toHaveAttribute("title", entry.fingerprint);
  await expect(proof.locator('[data-kind="result"] .text')).toHaveText(
    held(index, "mort_rate@1", CURSOR),
  );
});

test("accumulation — survival_prob at 12", async ({ page }) => {
  await reading(page, MODEL, "survival_prob", CURSOR);
  const proof = page.getByTestId("proof");
  await expect(page.getByTestId("proof-idiom")).toHaveText("accumulation");

  await expect(proof.locator('[data-kind="formula"] .text')).toHaveText(
    formatFormula(index.nodes.get("survival_prob@1")?.formula ?? null),
  );
  await expect(proof.locator('[data-operand="combined_decrement@1"]')).toHaveText(
    `combined_decrement[${String(CURSOR)}] = ${held(index, "combined_decrement@1", CURSOR)}`,
  );

  // "Which convention, and does the step reproduce?" — the settings in the
  // words an actuary uses, and the recurrence with the two numbers in it.
  await expect(proof.locator('[data-kind="convention"] .text')).toHaveText("beginning of period");
  await expect(
    proof.locator('[data-kind="substitution"] .text', { hasText: "survival_prob[12]" }),
  ).toHaveText(
    "survival_prob[12] = survival_prob[11] × (1 − combined_decrement[11]) = " +
      `${held(index, "survival_prob@1", CURSOR - 1)} × ` +
      `(1 − ${held(index, "combined_decrement@1", CURSOR - 1)})`,
  );
  await expect(proof.locator('[data-kind="result"] .text')).toHaveText(
    held(index, "survival_prob@1", CURSOR),
  );
});

test("a read across periods — prev_cumulative_growth", async ({ page }) => {
  await reading(page, MODEL, "prev_cumulative_growth", CURSOR);
  const proof = page.getByTestId("proof");

  await expect(proof.locator('[data-kind="formula"] .text')).toHaveText(
    formatFormula(index.nodes.get("prev_cumulative_growth@1")?.formula ?? null),
  );
  // "Which period did it read?" — eleven, and the line says so because the
  // narrowing facet states the offset, not because the page worked it out.
  expect(index.offsetOf("prev_cumulative_growth@1", "cumulative_growth@1")).toBe(-1);
  const term = proof.locator('[data-operand="cumulative_growth@1"]');
  await expect(term).toHaveAttribute("data-offset", "-1");
  await expect(term).toHaveText(
    `cumulative_growth[${String(CURSOR - 1)}] = ${held(index, "cumulative_growth@1", CURSOR - 1)}`,
  );
  await expect(proof.locator('[data-kind="result"] .text')).toHaveText(
    held(index, "prev_cumulative_growth@1", CURSOR),
  );

  // "the cone at prev_cumulative_growth: 10 nodes, offset loops ['t−1']"
  const window = coneWindow(index, "prev_cumulative_growth@1", 2, 2);
  await expect(page.getByTestId("cone-count")).toHaveText(String(window.nodes.length));
  await expect(page.locator('.edge-offset[data-label="t−1"]')).toHaveCount(1);
});

test("is anything unaccounted for", async ({ page }) => {
  await reading(page, MODEL, "net_cf", CURSOR);
  const panel = await modelTab(page);

  // "The file records no hole (the Model tab's line below)."
  await expect(panel.locator('[data-fact="holes"] .fact-value')).toHaveText(
    "no holes — every column is accounted for",
  );
  await expect(panel.locator("[data-hole]")).toHaveCount(0);
  // And the line the record's "what the file could not answer" rests on: this
  // export was made without --output-file, and the tab says that rather than
  // leaving the row out.
  expect(index.artifact.model.results).toBeUndefined();
  await expect(panel.locator('[data-fact="model.results.path"] .fact-value')).toHaveText(
    "no results file recorded — export with --results",
  );
});

test("the page as it was read", async ({ page, browserName }) => {
  // One photograph, not two. The two engines draw type and shadows differently
  // and both write the same path, so the file would be whichever finished last;
  // Chromium is the engine the record's own screenshots and the frame-time
  // measurement were taken in.
  test.skip(browserName !== "chromium", "one engine writes the evidence");
  await reading(page, MODEL, "net_cf", CURSOR);
  await photograph(page, MODEL, CURSOR);
});
