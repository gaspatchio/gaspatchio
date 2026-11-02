// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Level 4, the lifelib-reconciled model at 1,000 policies, read through the page.
 *
 * The scripted form of the written read of this model taken on 2026-09-17
 * — the same walk, scripted so that it stays true, asking that read's questions in that read's order.
 * See `level3.spec.ts` for what is asserted as written and what is derived from
 * the fixture, and `walk.ts` for the mechanics the four share.
 *
 * This is the largest of the four exports — 128 nodes, 184 edges, 83 periods —
 * and the one the frame-time measurement and the bundle ratchet are taken over.
 */

import { expect, test } from "@playwright/test";

import { formatFormula, shortFingerprint } from "../../src/reader/format";
import { proofOf } from "../../src/reader/proof";
import { coneWindow } from "../../src/reader/window";
import { excerptCell, fixture, held, modelTab, pageFor, reading, photograph, VIEWPORT } from "./walk";

test.use({ viewport: VIEWPORT });

const MODEL = "level4";
const index = fixture(MODEL);

/** The period the record stands at, and every case below with it. */
const CURSOR = 12;

test("who am I looking at", async ({ page }) => {
  await page.goto(pageFor(MODEL));
  await expect(page.getByTestId("grid")).toBeVisible();

  // "The header strip reads `policy 1 model.py 5d28b0c1`".
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

  // "the cell reads 41,096.45"
  await expect(page.locator(`td[data-column="net_cf"][data-period="${String(CURSOR)}"]`)).toHaveText(
    held(index, "net_cf@1", CURSOR),
  );
  await expect(page.locator('td[data-formula-for="net_cf"]')).toHaveText(
    formatFormula(index.nodes.get("net_cf@1")?.formula ?? null),
  );

  // "the operand outlines on row 12 are premiums[12] = 0.00, expenses[12] =
  // 3,811.40, …, av_change[12] = -1.13m" — the record's own order.
  for (const operand of [
    "premiums",
    "expenses",
    "commissions",
    "av_change",
    "inv_income",
    "claims",
  ]) {
    const cell = page.locator(`td[data-column="${operand}"][data-period="${String(CURSOR)}"]`);
    await expect(cell).toHaveClass(/\boperand\b/);
    await expect(cell).toHaveText(held(index, `${operand}@1`, CURSOR));
  }

  // "The grid draws 70 per-period columns; its 58 scalars are
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
  // "Offset loops in the window: ['t+1']."
  await expect(page.locator('.edge-offset[data-label="t+1"]')).toHaveCount(1);
  await expect(page.locator('.edge-offset[data-label="t−1"]')).toHaveCount(0);
});

test("arithmetic — net_cf at 12", async ({ page }) => {
  await reading(page, MODEL, "net_cf", CURSOR);
  const proof = page.getByTestId("proof");
  await expect(page.getByTestId("proof-idiom")).toHaveText("arithmetic");

  const node = index.nodes.get("net_cf@1");
  await expect(proof.locator('[data-kind="formula"] .text')).toHaveText(
    formatFormula(node?.formula ?? null),
  );
  const substituted = index.traceOf(String(node?.id))?.find((step) => step.step === 2)?.expr;
  expect(typeof substituted).toBe("string");
  await expect(proof.locator('[data-kind="lowered"] .text').first()).toHaveText(
    String(substituted),
  );

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

  // "disagreement flag: absent; footer: model.py:864 local sha256:… graph sha256:…"
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
  for (const [operand, text] of [
    ["duration_mth_t@1", `duration_mth_t[${String(CURSOR)}]`],
    ["maturity_month@1", "maturity_month"],
    ["pols_if_bef_mat@1", `pols_if_bef_mat[${String(CURSOR)}]`],
  ]) {
    await expect(proof.locator(`[data-operand="${String(operand)}"]`)).toHaveText(
      `${String(text)} = ${held(index, String(operand), CURSOR)}`,
    );
  }

  // Made without --branches: the panel says so and prices neither branch.
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

test("lookup — base_mort_rate at 12", async ({ page }) => {
  await reading(page, MODEL, "base_mort_rate", CURSOR);
  const proof = page.getByTestId("proof");
  await expect(page.getByTestId("proof-idiom")).toHaveText("lookup");

  await expect(proof.locator('[data-kind="formula"] .text')).toHaveText(
    formatFormula(index.nodes.get("base_mort_rate@1")?.formula ?? null),
  );
  // "Which row of which table" — three keys, one of them a scalar and written
  // without a subscript because the file sampled one value for it.
  for (const [operand, text] of [
    ["mort_table_id@1", "mort_table_id"],
    ["age@1", `age[${String(CURSOR)}]`],
    ["duration_capped@1", `duration_capped[${String(CURSOR)}]`],
  ]) {
    await expect(proof.locator(`[data-operand="${String(operand)}"]`)).toHaveText(
      `${String(text)} = ${held(index, String(operand), CURSOR)}`,
    );
  }
  await expect(proof.locator('[data-kind="excerpt"] .text')).toHaveText(
    "mortality_select — the row those keys name, with 2 rows either side",
  );

  // "5 rows shown, header `table_id | attained_age | duration | mort_rate`,
  // the hit `T3275 | 79 | 4 | 0.02055`".
  const table = proofOf(index, "base_mort_rate@1", CURSOR).table;
  if (table === undefined) throw new Error("the level-4 fixture quotes no row for base_mort_rate@1");
  const rows = proof.locator(".excerpt-rows tbody tr");
  await expect(rows).toHaveCount(table.rows.length);
  expect(await proof.locator(".excerpt-rows thead th").allInnerTexts()).toEqual(table.header);
  await expect(rows.nth(table.hitRow)).toHaveAttribute("data-hit", "true");
  const hit = proof.locator(".excerpt-rows tbody tr[data-hit]");
  await expect(hit).toHaveCount(1);
  expect((await hit.innerText()).split(/\s+/)).toEqual(
    (table.rows[table.hitRow] ?? []).map(excerptCell),
  );

  // "and is it the table the model says?" — table chip 4942028b.
  const entry = index.tables.get("mortality_select") as { fingerprint: string };
  await expect(page.getByTestId("table-chip")).toHaveText(shortFingerprint(entry.fingerprint));
  await expect(page.getByTestId("table-chip")).toHaveAttribute("title", entry.fingerprint);
  await expect(proof.locator('[data-kind="result"] .text')).toHaveText(
    held(index, "base_mort_rate@1", CURSOR),
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

  // "Which convention, and does the step reproduce?"
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

test("a read across periods — shifted_growth", async ({ page }) => {
  await reading(page, MODEL, "shifted_growth", CURSOR);
  const proof = page.getByTestId("proof");

  await expect(proof.locator('[data-kind="formula"] .text')).toHaveText(
    formatFormula(index.nodes.get("shifted_growth@1")?.formula ?? null),
  );
  // "Which period did it read?" — eleven, off the facet's own offset.
  expect(index.offsetOf("shifted_growth@1", "combined_growth_factor@1")).toBe(-1);
  const term = proof.locator('[data-operand="combined_growth_factor@1"]');
  await expect(term).toHaveAttribute("data-offset", "-1");
  await expect(term).toHaveText(
    `combined_growth_factor[${String(CURSOR - 1)}] = ` +
      held(index, "combined_growth_factor@1", CURSOR - 1),
  );
  await expect(proof.locator('[data-kind="result"] .text')).toHaveText(
    held(index, "shifted_growth@1", CURSOR),
  );

  // "the cone at shifted_growth: 8 nodes, offset loops ['t−1']"
  const window = coneWindow(index, "shifted_growth@1", 2, 2);
  await expect(page.getByTestId("cone-count")).toHaveText(String(window.nodes.length));
  await expect(page.locator('.edge-offset[data-label="t−1"]')).toHaveCount(1);
});

test("is anything unaccounted for", async ({ page }) => {
  await reading(page, MODEL, "net_cf", CURSOR);
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
  await reading(page, MODEL, "net_cf", CURSOR);
  await photograph(page, MODEL, CURSOR);
});
