// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Every member the record carries, on the page a reviewer opens.
 *
 * `gspio verify --model` and `--assumptions` hold a model's helper modules and
 * its tables' files against the files beside it, and the record names both; a
 * page that did not show them would show a reviewer less than the verifier
 * checks. So the drawer states the modules, the library that produced the
 * values, why there is no git revision where there is none, and where each
 * table was read from — and it states every digit of the value under the
 * cursor, which the grid writes rounded.
 *
 * The page is packed from `fixtures/record.json`, the producer's own export of
 * a model resting on a helper and three tables (`fixtures/record/export.py`).
 * The shapes an export of it cannot take on a desk — versions stated, which a
 * committed document withholds, and git unable to answer — are that document
 * with the one member set, written beside it under a name git ignores, as the
 * inspector's own cases write theirs. Every expected sentence and value is
 * read off the file or the reader, never typed from a screen.
 */

import { execFileSync } from "node:child_process";
import { readFileSync, renameSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { shortFingerprint } from "../src/reader/format";
import type { Artifact } from "../src/reader/types";

/** The record fixture's own text, which the expected digits are read out of. */
const TEXT = readFileSync(resolve("fixtures/record.json"), "utf8");
const record = JSON.parse(TEXT) as Artifact;

/** The page packed from one fixture, as a file on a disk. */
function pageFor(name: string): string {
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/** The record with some members replaced, packed under a name git ignores. */
function written(name: string, edit: (document: Artifact) => void): string {
  const document = JSON.parse(TEXT) as Artifact;
  edit(document);
  const out = resolve(`fixtures/written-${name}.json`);
  const partial = `${out}.${String(process.pid)}.part`;
  writeFileSync(partial, JSON.stringify(document));
  renameSync(partial, out);
  execFileSync("node", ["pack.mjs", `written-${name}`], { cwd: resolve("."), stdio: "pipe" });
  return pageFor(`written-${name}`);
}

/** Open a page and the drawer's Model tab. */
async function modelTab(page: Page, url: string) {
  await page.goto(url);
  await expect(page.getByTestId("inspector")).toBeVisible();
  await page.getByTestId("inspector").locator('[data-tab="model"]').click();
  return page.getByTestId("inspector").locator('[data-panel="model"]');
}

/** Select one column by the search box. */
async function select(page: Page, column: string): Promise<void> {
  await page.getByTestId("search").fill(column);
  await page.getByTestId("search").press("Enter");
}

/**
 * One timeline value's token, exactly as the file spells it.
 *
 * Read from the text rather than from the parse, because the parse is the
 * thing that would lose a digit: the claim on the page is "the file holds",
 * and this is what the file holds.
 */
function token(id: string, period: number): string {
  const at = TEXT.indexOf(`"id": "${id}"`);
  const sample = /"value_sample": \[([^\]]*)\]/.exec(TEXT.slice(at));
  const value = sample?.[1]?.split(",")[period]?.trim();
  if (value === undefined) throw new Error(`the record carries no ${id} at period ${String(period)}`);
  return value;
}

test("the Model tab names the model's own files beside it, each with its stamp", async ({ page }) => {
  const modules = record.model.modules ?? [];
  expect(modules.map((entry) => entry.path)).toEqual(["loadings.py"]);
  const panel = await modelTab(page, pageFor("record"));
  const row = panel.locator('[data-fact="model.modules[0]"]');
  await expect(row.locator(".fact-name")).toHaveText("loadings.py");
  await expect(row.locator(".fact-value")).toHaveText(shortFingerprint(modules[0]?.fingerprint ?? ""));
  await expect(row.locator(".fact-value")).toHaveAttribute("title", modules[0]?.fingerprint ?? "");

  // A model importing nothing from beside itself says so: the tiers export's
  // list is empty, and empty is a claim.
  const tiers = JSON.parse(readFileSync(resolve("fixtures/tiers.json"), "utf8")) as Artifact;
  expect(tiers.model.modules).toEqual([]);
  const none = await modelTab(page, pageFor("tiers"));
  await expect(none.locator('[data-fact="model.modules"] .fact-value')).toHaveText(
    "imports nothing from beside itself",
  );
});

test("the library is one fact per key, and a withheld one says it was withheld", async ({ page }) => {
  const withheld = await modelTab(page, pageFor("record"));
  expect(record.producer).toMatchObject({ versions: { omitted: "withheld" } });
  await expect(withheld.locator('[data-fact="producer.versions"] .fact-value')).toHaveText(
    "withheld: the exporter was asked not to state them",
  );
  // The producer row is the name and the version; the versions are not
  // printed a second time as a line of JSON.
  await expect(withheld.locator('[data-fact="producer"] .fact-value')).toHaveText(
    '{"name":"gaspatchio","version":"1.0.0"}',
  );

  const versions = {
    core_version: "1.0.0",
    extension_version: "1.0.0",
    extension_sha256: "sha256:a81975366bb2bf50a97601ea363dafe7f1595c7fc1b5754e8f1dda2e0b57ebde",
    polars_version: "1.42.1",
    python_version: "3.13.0",
    platform: "macOS-15.7.9-x86_64-i386-64bit-Mach-O",
    imports: { polars: "1.42.1" },
  };
  const stated = await modelTab(
    page,
    written("record-versions", (document) => {
      (document.producer as Record<string, unknown>)["versions"] = versions;
    }),
  );
  for (const key of ["core_version", "extension_version", "polars_version", "python_version", "platform"]) {
    await expect(stated.locator(`[data-fact="producer.versions.${key}"] .fact-name`)).toHaveText(key);
    await expect(stated.locator(`[data-fact="producer.versions.${key}"] .fact-value`)).toHaveText(
      versions[key as keyof typeof versions] as string,
    );
  }
  const sha = stated.locator('[data-fact="producer.versions.extension_sha256"] .fact-value');
  await expect(sha).toHaveText("a8197536");
  await expect(sha).toHaveAttribute("title", versions.extension_sha256);
  await expect(stated.locator('[data-fact="producer.versions.imports"] .fact-value')).toHaveText("polars 1.42.1");
  await expect(stated.locator('[data-fact="producer.versions"]')).toHaveCount(0);
});

test("the git rows say why a record states no revision, and never undefined", async ({ page }) => {
  // No working tree: the committed record was exported outside one.
  expect(record.model.git).toBeNull();
  const outside = await modelTab(page, pageFor("record"));
  await expect(outside.locator('[data-fact="model.git.commit"] .fact-value')).toHaveText(
    "exported outside a git working tree",
  );
  await expect(outside.locator('[data-fact="model.git.dirty"] .fact-value')).toHaveText(
    "no working tree, so no state to record",
  );

  // Git there and unable to answer: the detail is the producer's sentence,
  // printed as the file writes it. This is the case the dirty row used to
  // print as "undefined".
  const detail = "fatal: detected dubious ownership in repository at '..'";
  const refused = await modelTab(
    page,
    written("record-git", (document) => {
      document.model.git = { omitted: "unavailable", detail };
    }),
  );
  await expect(refused.locator('[data-fact="model.git.commit"] .fact-value')).toHaveText(
    `git could not answer: ${detail}`,
  );
  await expect(refused.locator('[data-fact="model.git.dirty"] .fact-value')).toHaveText(
    "not recorded, because git could not answer",
  );
  await expect(refused).not.toContainText("undefined");
});

test("the Table panel says where each table was read from, and what its recipe did", async ({ page }) => {
  await page.goto(pageFor("record"));
  await expect(page.getByTestId("inspector")).toBeVisible();

  // Read from a file through a recipe that renamed a column.
  await select(page, "qx_monthly");
  await page.getByTestId("inspector").locator('[data-tab="table"]').click();
  const panel = page.getByTestId("inspector").locator('[data-panel="table"]');
  await expect(panel.getByTestId("table-name")).toHaveText("record_mortality");
  await expect(panel.getByTestId("table-source")).toHaveText("read from mortality.csv");
  await expect(panel.getByTestId("table-shaped")).toHaveText(
    "age renamed from Age: verify cannot hold this table against its file.",
  );

  // Read from a file as it stands: the file, and nothing more.
  await select(page, "lapse_monthly");
  await expect(panel.getByTestId("table-name")).toHaveText("record_lapse");
  await expect(panel.getByTestId("table-source")).toHaveText("read from lapse.csv");
  await expect(panel.getByTestId("table-shaped")).toHaveCount(0);

  // Built from a frame in the model's own code.
  await select(page, "expense");
  await expect(panel.getByTestId("table-name")).toHaveText("record_expense");
  await expect(panel.getByTestId("table-source")).toHaveText("built from a frame in code");
});

test("a selected cell shows every digit the file holds, and says the grid rounds", async ({ page }) => {
  await page.goto(pageFor("record"));
  await expect(page.getByTestId("grid")).toBeVisible();
  const digits = token("expected_claims@1", 5);
  // The case is worth making only if the grid really rounds this value.
  expect(digits.length).toBeGreaterThan(12);

  const cell = page.locator('.grid td[data-column="expected_claims"][data-period="5"]');
  await cell.click();
  await expect(cell).not.toHaveText(digits);
  await expect(page.getByTestId("held-note")).toHaveText("shown rounded; the file holds every digit");
  await expect(page.getByTestId("held-value")).toHaveText(digits);
  await expect(page.getByTestId("held")).toContainText("expected_claims at period 5");
});

test("copying a cell copies the digits the file holds, not the rounded text", async ({
  page,
  context,
  browserName,
}) => {
  // The clipboard is read back only where the engine grants it from a file on
  // a disk, which is Chromium; `e2e/source.spec.ts` says why.
  if (browserName === "chromium") {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  }
  await page.goto(pageFor("record"));
  await expect(page.getByTestId("grid")).toBeVisible();
  const digits = token("expected_claims@1", 7);
  await page.locator('.grid td[data-column="expected_claims"][data-period="7"]').click();

  // What the grid hands a copy, in either engine: the event the browser
  // raises on a copy, with the clipboard it would write to.
  const handed = await page.getByTestId("grid").evaluate((grid) => {
    const clipboardData = new DataTransfer();
    grid.dispatchEvent(new ClipboardEvent("copy", { clipboardData, bubbles: true, cancelable: true }));
    return clipboardData.getData("text/plain");
  });
  expect(handed).toBe(digits);

  // And the drawer's control, which says what it did.
  await page.getByTestId("copy-held").click();
  if (browserName === "chromium") {
    await expect(page.getByTestId("copy-held")).toHaveText("value copied");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(digits);
    // The keyboard, on the grid a click on the cell focuses.
    await page.evaluate(() => navigator.clipboard.writeText(""));
    await page.locator('.grid td[data-column="expected_claims"][data-period="7"]').click();
    await page.keyboard.press("ControlOrMeta+C");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(digits);
  }
});

test("the disagreement chip prints both numbers whole, so two that differ read apart", async ({ page }) => {
  // The trace's answer moved by one unit in the last place: a disagreement the
  // reader computes on the numbers, and one the grid's rounding cannot see.
  const sample = token("expected_claims@1", 0);
  const moved = "11.916666666666668";
  expect(sample).toBe("11.916666666666666");
  await page.goto(
    written("record-disagrees", (document) => {
      const node = document.nodes.find((one) => one.id === "expected_claims@1");
      const last = node?.trace?.[node.trace.length - 1] as { result?: unknown } | undefined;
      if (last === undefined) throw new Error("the record carries no trace for expected_claims@1");
      last.result = Number(moved);
    }),
  );
  await expect(page.getByTestId("grid")).toBeVisible();
  await select(page, "expected_claims");
  await expect(page.getByTestId("disagreement")).toBeVisible();
  await expect(page.getByTestId("disagreement-trace")).toHaveText(moved);
  await expect(page.getByTestId("disagreement-sample")).toHaveText(sample);
});

test("the formulas figure stands beside the graph figure, each saying what it covers", async ({ page }) => {
  // The committed record predates the member, and says so rather than
  // printing nothing.
  expect(record.formulas_fingerprint).toBeUndefined();
  const older = await modelTab(page, pageFor("record"));
  await expect(older.locator('[data-fact="formulas_fingerprint"] .fact-value')).toHaveText(
    "not recorded — the file was written before the figure",
  );

  const figure = `sha256:${"d1".repeat(32)}`;
  const panel = await modelTab(
    page,
    written("formulas", (document) => {
      document.formulas_fingerprint = figure;
    }),
  );
  await expect(panel.locator('[data-fact="graph_fingerprint"] .fact-value')).toHaveText(record.graph_fingerprint);
  await expect(panel.locator('[data-fact="formulas_fingerprint"] .fact-name')).toHaveText("formulas");
  await expect(panel.locator('[data-fact="formulas_fingerprint"] .fact-value')).toHaveText(figure);
  await expect(panel.getByTestId("covers-graph")).toHaveText(
    "the model as run: its formulas and the tables, curves and schedules they read",
  );
  await expect(panel.getByTestId("covers-formulas")).toHaveText(
    "its formulas alone: a re-sourced table, curve or schedule leaves this where it was",
  );
});
