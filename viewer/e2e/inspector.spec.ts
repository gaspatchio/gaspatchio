// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The drawer's three tabs, read off the page the exporter writes.
 *
 * This is the answer to "where exactly is this defined?", and
 * what is held to here is that it is a flat rendering of the file rather than a
 * summary of it: every member of the selected node's record, under the name the
 * format gives it, in the order the file writes it. A tab that had picked the
 * interesting members would pass a test written against a list somebody chose,
 * and fail this one, which asks the fixture what its keys are.
 *
 * Two pages: `level4.html` for a real export, and `holes.html` for the envelope
 * a reviewer reads when the model does not account for every column it holds.
 */

import { execFileSync } from "node:child_process";
import { readFileSync, renameSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { shortFingerprint } from "../src/reader/format";
import { descendantsOf, endsReached } from "../src/reader/impact";
import { buildIndex } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";
import { coneWindow } from "../src/reader/window";

/** One fixture, indexed, read back here to work out what to expect. */
function fixture(name: string) {
  const artifact = JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact;
  return buildIndex(artifact);
}

const level4 = fixture("level4");
const holes = fixture("holes");

test("the tabs are the width of their names, at whatever width the drawer is", async ({
  page,
}) => {
  // At the 320 px the drawer opens at, four tabs sharing the bar and four tabs
  // the width of their own names look much the same. Dragged out towards the
  // 960 px stop — which is what the Source tab's model file wants, and why that stop was
  // raised from 640 — sharing the bar left four short names marooned in the
  // middle of four very wide tabs. They are labels, so they are the width of
  // the labels and they start at the left.
  //
  // The width is put where the reader's own drag puts it rather than dragged
  // here, for the reason `e2e/panes.spec.ts` stores one: a drag measured in
  // pixels is a test about a mouse, and what is under test is the bar.
  const page4 = pathToFileURL(resolve("dist/level4.html")).href;
  await page.goto(page4);
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.evaluate(() => {
    localStorage.setItem(
      "gaspatchio-viewer.panes",
      JSON.stringify({ top: 0.62, cone: 0.5, drawer: 960, railed: [] }),
    );
  });
  await page.reload();
  await expect(page.getByTestId("inspector")).toBeVisible();

  const bar = page.locator(".inspector .tabs");
  const first = page.locator('.inspector .tab[data-tab="node"]');
  const last = page.locator('.inspector .tab[data-tab="source"]');
  const barBox = (await bar.boundingBox()) ?? { x: 0, width: 0 };
  const firstBox = (await first.boundingBox()) ?? { x: 0, width: 0 };
  const lastBox = (await last.boundingBox()) ?? { x: 0, width: 0 };

  // The drawer really is wide, or the rest of this says nothing.
  expect(barBox.width).toBeGreaterThan(700);
  // Against the left edge of the bar.
  expect(firstBox.x).toBeCloseTo(barBox.x, 0);
  // And all four together take a small part of a bar this wide: four short
  // words are nowhere near a third of it.
  const spread = lastBox.x + lastBox.width - firstBox.x;
  expect(spread).toBeLessThan(barBox.width / 3);

  // Every tab still works from where it now stands.
  await last.click();
  await expect(last).toHaveAttribute("aria-selected", "true");
});

/** The page packed from one fixture, as a file on a disk. */
function pageFor(name: string): string {
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/** Open a packed page, and select one column where one is named. */
async function open(page: Page, name: string, column?: string): Promise<void> {
  await page.goto(pageFor(name));
  await expect(page.getByTestId("inspector")).toBeVisible();
  if (column === undefined) return;
  await page.getByTestId("search").fill(column);
  await page.getByTestId("search").press("Enter");
}

/** One of the three tabs, opened. */
async function tab(page: Page, which: "node" | "table" | "model") {
  await page.getByTestId("inspector").locator(`[data-tab="${which}"]`).click();
  return page.getByTestId("inspector").locator(`[data-panel="${which}"]`);
}

test("the Node tab lists every member of the record, in the file's order", async ({ page }) => {
  await open(page, "level4", "net_cf");
  const panel = await tab(page, "node");

  const record = level4.nodes.get("net_cf@1");
  if (record === undefined) throw new Error("the level-4 fixture carries no net_cf@1");
  const keys = Object.keys(record);
  // Every one of them, under the format's own name, in the file's own order.
  await expect(panel.locator("[data-member]")).toHaveCount(keys.length);
  expect(await panel.locator("[data-member] .member-name").allInnerTexts()).toEqual(keys);

  // A string member reads as the file writes it.
  await expect(panel.locator('[data-member="dtype"] .member-value')).toHaveText(record.dtype);
  // A structured one as compact JSON, not as prose about it.
  await expect(panel.locator('[data-member="reads"] .member-value')).toHaveText(
    JSON.stringify(record.reads),
  );
});

test("the two long members are folded away and open again, never dropped", async ({ page }) => {
  await open(page, "level4", "net_cf");
  const panel = await tab(page, "node");

  for (const member of ["value_sample", "trace"]) {
    const row = panel.locator(`[data-member="${member}"]`);
    await expect(row).toHaveCount(1);
    const control = row.locator("[data-testid='unfold']");
    await expect(row.locator(".member-value")).toHaveCount(0);
    await control.click();
    await expect(row.locator(".member-value")).toHaveCount(1);
    await expect(control).toHaveAttribute("aria-expanded", "true");
    await control.click();
    await expect(row.locator(".member-value")).toHaveCount(0);
    await expect(control).toHaveAttribute("aria-expanded", "false");
    await control.click();
  }

  const record = level4.nodes.get("net_cf@1");
  const sample = record?.value_sample;
  if (!Array.isArray(sample)) throw new Error("the level-4 fixture carries no sampled net_cf@1");
  await expect(panel.locator('[data-member="value_sample"] .member-value')).toContainText(
    JSON.stringify(sample[0]),
  );
});

test("direct inputs navigate to the recorded version", async ({ page }) => {
  await open(page, "level4", "net_cf");
  const panel = await tab(page, "node");
  const reads = level4.nodes.get("net_cf@1")!.reads;
  expect(reads.length).toBeGreaterThan(0);
  const links = panel.getByTestId("direct-inputs").locator("button");
  expect(await links.allInnerTexts()).toEqual(reads);
  await links.first().click();
  await expect(panel.locator('[data-member="id"] .member-value')).toHaveText(reads[0]!);
});

test("the Table tab shows the whole payload, the hit marked, and filters it", async ({ page }) => {
  // `base_mort_rate@1` is the level-4 node that reads an assumption:
  // `mortality_select`, nine thousand six hundred rows of it.
  await open(page, "level4", "base_mort_rate");
  const panel = await tab(page, "table");

  const entry = level4.tables.get("mortality_select") as {
    fingerprint: string;
    payload: { columns: { name: string }[]; rows: unknown[][] };
  };
  await expect(panel.getByTestId("table-name")).toHaveText("mortality_select");
  await expect(panel.getByTestId("table-rows")).toHaveText(String(entry.payload.rows.length));
  await expect(panel.getByTestId("table-fingerprint")).toHaveText(
    shortFingerprint(entry.fingerprint),
  );

  // The whole table is there, which means it is virtualised: far fewer rows are
  // drawn than the payload holds, and the hit is one of the ones drawn.
  const drawn = panel.locator("tbody tr");
  expect(await drawn.count()).toBeLessThan(entry.payload.rows.length);
  const hit = panel.locator("tbody tr[data-hit]");
  await expect(hit).toHaveCount(1);
  // The same row the proof names, at the same period.
  const proofHit = await page
    .getByTestId("proof")
    .locator(".excerpt-rows tbody tr[data-hit]")
    .innerText();
  expect((await hit.innerText()).split(/\s+/)).toEqual(proofHit.split(/\s+/));

  // And the search box narrows the payload by substring.
  await panel.getByTestId("table-search").fill("zzz-no-such-row");
  await expect(panel.locator("tbody tr")).toHaveCount(0);
  await expect(panel.getByTestId("table-matches")).toHaveText("0");
});

test("a column that reads no assumption says so on the Table tab", async ({ page }) => {
  await open(page, "level4", "net_cf");
  const panel = await tab(page, "table");
  expect(level4.nodes.get("net_cf@1")?.reads_assumptions).toEqual([]);
  await expect(panel).toContainText("reads no assumption");
  await expect(panel.locator("tbody tr")).toHaveCount(0);
});

test("the Model tab is the envelope, member by member", async ({ page }) => {
  await open(page, "level4");
  const panel = await tab(page, "model");
  const file = level4.artifact;

  await expect(panel.locator('[data-fact="model.source_path"]')).toContainText(
    String(file.model.source_path),
  );
  await expect(panel.locator('[data-fact="schema"]')).toContainText(file.schema);
  await expect(panel.locator('[data-fact="profile"]')).toContainText(file.profile);
  await expect(panel.locator('[data-fact="producer"]')).toContainText(
    JSON.stringify(file.producer),
  );
  // The values block is the selected entry of the policy axis, under its own
  // path in the file: one policy here, so it is `policies[0]` — which is the
  // same context `enrichment` restates.
  await expect(panel.locator('[data-fact="policies"]')).toContainText("1 policy");
  await expect(panel.locator('[data-fact="policies[0].policy_id"]')).toContainText(
    String(file.policies[0]?.policy_id),
  );
  await expect(panel.locator('[data-fact="policies[0].why"]')).toContainText(
    String(file.policies[0]?.why),
  );
  expect(file.policies[0]?.policy_id).toBe(file.enrichment?.policy_id);
  for (const fact of [
    "policies[0].aggregation",
    "policies[0].periods",
    "policies[0].filter",
  ]) {
    await expect(panel.locator(`[data-fact="${fact}"]`)).toHaveCount(1);
  }
  // The level-4 export carries neither a results file nor a git commit, and the
  // rows say that rather than going missing. A row that disappeared when the
  // file was silent would leave a reader unable to tell "not recorded" from
  // "not shown". Its `git` is null, which says why: it was exported outside a
  // working tree.
  expect(file.model.results).toBeUndefined();
  expect(file.model.git).toBeNull();
  await expect(panel.locator('[data-fact="model.results.path"]')).toContainText("no ");
  await expect(panel.locator('[data-fact="model.git.commit"] .fact-value')).toHaveText(
    "exported outside a git working tree",
  );
});

test("the Model tab says which book the file was built over, or that it does not say", async ({
  page,
}) => {
  // The committed level-4 export states its book: the digest and the columns it
  // was taken over, printed as the file states them.
  const stated = level4.artifact.book as { columns: string[]; digest: string };
  expect(typeof stated.digest).toBe("string");
  await open(page, "level4");
  const said = await tab(page, "model");
  await expect(said.locator('[data-fact="book.digest"] .fact-value')).toHaveText(stated.digest);
  await expect(said.locator('[data-fact="book.columns"] .fact-value')).toHaveText(stated.columns.join(", "));

  // A file whose producer could not vouch for its book says why, in the
  // file's own words.
  const unvouched = fixture("versions").artifact.book as {
    columns: string[];
    digest: { omitted: string; detail: string };
  };
  expect(unvouched.digest.omitted).toBe("unavailable");
  await open(page, "versions");
  const short = await tab(page, "model");
  await expect(short.locator('[data-fact="book.digest"] .fact-value')).toHaveText(
    `not vouched for: ${unvouched.digest.detail}`,
  );

  // And a file written before documents recorded their book says it records
  // none rather than going missing. Written beside the committed fixtures
  // under a name git ignores, and packed the way every other page here is.
  const { book: _book, ...before } = level4.artifact;
  const out = resolve("fixtures/written-book.json");
  const partial = `${out}.${String(process.pid)}.part`;
  writeFileSync(partial, JSON.stringify(before));
  renameSync(partial, out);
  execFileSync("node", ["pack.mjs", "written-book"], { cwd: resolve("."), stdio: "pipe" });
  await page.goto(pageFor("written-book"));
  await expect(page.getByTestId("inspector")).toBeVisible();
  const silent = await tab(page, "model");
  await expect(silent.locator('[data-fact="book.digest"] .fact-value')).toHaveText("no book recorded");
  await expect(silent.locator('[data-fact="book.columns"] .fact-value')).toHaveText("no book recorded");
});

test("the holes chip opens the drawer on the Model tab, with the reasons", async ({ page }) => {
  await open(page, "holes");
  // Not on the Model tab to begin with: the chip is what puts it there.
  await expect(page.getByTestId("inspector").locator('[data-panel="model"]')).toHaveCount(0);

  await page.getByTestId("holes-chip").click();
  const panel = page.getByTestId("inspector").locator('[data-panel="model"]');
  await expect(panel).toBeVisible();

  const listed = panel.locator("[data-hole]");
  await expect(listed).toHaveCount(holes.artifact.holes.length);
  for (const hole of holes.artifact.holes as { column: string; reason: string }[]) {
    await expect(panel.locator(`[data-hole="${hole.column}"]`)).toContainText(hole.reason);
  }
});

test("a file that records no holes says so rather than showing an empty list", async ({ page }) => {
  await open(page, "level4");
  const panel = await tab(page, "model");
  expect(level4.artifact.holes).toEqual([]);
  await expect(panel.locator("[data-hole]")).toHaveCount(0);
  await expect(panel.locator('[data-fact="holes"]')).toContainText("no ");
});

/**
 * The reviewer's question, answered in one place.
 *
 * "Change the lapse basis — what moves?" The cone answers it a step at a time;
 * this answers it once, under the file's own record and marked as the page's
 * reading of the edges rather than as something the producer wrote.
 */
test("the drawer says what moves if this column changes, and which ends it reaches", async ({
  page,
}) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill("lapse_rate_unfloored");
  await page.getByTestId("search").press("Enter");

  const impact = page.getByTestId("impact");
  await expect(impact).toContainText("what moves if this changes");

  // The count is the closure, not a step or two of it.
  const downstream = descendantsOf(level4, "lapse_rate_unfloored@1");
  await expect(page.getByTestId("impact-count")).toHaveText(String(downstream.length));

  // And the model's own ends among them are named, bottom line included.
  const reached = endsReached(level4, "lapse_rate_unfloored@1").map(
    (id) => level4.nodes.get(id)?.column ?? id,
  );
  for (const end of reached) {
    await expect(page.getByTestId("impact-ends").locator(`[data-end="${end}"]`)).toHaveCount(1);
  }
  expect(reached).toContain("pv_net_cf");

  // Each is a way there.
  await page.getByTestId("impact-ends").locator('[data-end="pv_net_cf"]').click();
  await expect(page.getByTestId("proof")).toContainText("pv_net_cf");
});

test("a column at the end of its own chain says nothing moves", async ({ page }) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();

  // The page opens on exactly such a column, which is the point of opening
  // there: it is where the model stopped.
  await expect(page.getByTestId("impact")).toContainText("a change here moves nothing else");
  await expect(page.getByTestId("impact-count")).toHaveCount(0);
});

test("one control opens everything a change here would travel to", async ({ page }) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill("lapse_rate_unfloored");
  await page.getByTestId("search").press("Enter");

  const before = Number(await page.getByTestId("cone-count").textContent());
  await page.getByTestId("cone-downstream").click();
  const after = Number(await page.getByTestId("cone-count").textContent());

  // Counted off the window rather than off the DOM: at this size React Flow
  // draws only what is in view, so a rendered box is evidence and a missing one
  // is not. The window is the union of what was there and everything a change
  // here would travel to.
  const union = new Set([
    ...coneWindow(level4, "lapse_rate_unfloored@1", 2, 2).nodes,
    ...descendantsOf(level4, "lapse_rate_unfloored@1"),
  ]);
  expect(after).toBeGreaterThan(before);
  expect(after).toBe(union.size);
});
