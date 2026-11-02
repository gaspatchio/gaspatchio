// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The model beside the proof, over the sources section the file carries (§7.3).
 *
 * The page could name the line that computed a figure and could not show it.
 * These are the cases that say it can now, and — the half that is easy to
 * forget — that it says which of §6.1's three reasons it is when the file
 * carries no text.
 *
 * Two files, two claims. The level-4 export carries `model.py` whole, and its
 * digest is the `model.source_sha` the envelope already published, so the page
 * can say the source it is showing is the source that ran. The holes fixture
 * carries the section with a payload that says `withheld`: the path and the
 * digest travel and the text does not, which is a decision the document records
 * rather than a silence, and the tab has to say so rather than look empty.
 *
 * Every line quoted below is read out of the fixture, not typed in. A test that
 * asserted line 520 said what somebody once saw it say would stop being
 * evidence the day the tutorial model was edited.
 */

import { execFileSync } from "node:child_process";
import { readFileSync, renameSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";

import { buildIndex } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";

/** One committed fixture, indexed. */
function fixture(name: string) {
  return buildIndex(
    JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact,
  );
}

const level4 = fixture("level4");
const holes = fixture("holes");

/** The page packed from one fixture, as a file on a disk. */
function pageFor(name: string): string {
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/**
 * Write one artifact and pack the page the exporter would have written around it.
 *
 * The same shape `e2e/refusals.spec.ts` uses, and for its reason: this is a
 * document edited to provoke one answer rather than an export a producer wrote,
 * and one of those sitting in a fixtures directory is a thing somebody will one
 * day open by mistake. The `refusal-` prefix is what `.gitignore` ignores, and
 * this page does print a refusal — the source tab's, over a section that is not
 * there. Both Playwright projects run this file, so the write goes through a
 * temporary name and a rename and the bytes are a pure function of the fixture
 * they came from.
 *
 * @param name - The fixture's name, under the ignored prefix.
 * @param body - Its text.
 * @returns The packed page's `file://` URL.
 */
function packed(name: string, body: string): string {
  const out = resolve(`fixtures/${name}.json`);
  const partial = `${out}.${String(process.pid)}.part`;
  writeFileSync(partial, body);
  renameSync(partial, out);
  execFileSync("node", ["pack.mjs", name], { cwd: resolve("."), stdio: "pipe" });
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/** The model's text, as the level-4 file carries it, split into lines. */
const modelText = (() => {
  const entry = level4.sources.get(level4.artifact.model.source_path ?? "");
  if (entry === undefined || !("text" in entry.payload)) {
    throw new Error("fixtures/level4.json carries no model text — re-export it with --source");
  }
  return entry.payload.text.split("\n");
})();

test("the proof footer's location is a control, and it opens the file at that line", async ({
  page,
}) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill("maint_fee_pp");
  await page.getByTestId("search").press("Enter");

  const node = level4.nodes.get("maint_fee_pp@1");
  const location = String(node?.source_location);
  const line = Number(location.split(":").pop());

  const control = page.getByTestId("open-source");
  await expect(control).toHaveText(location);
  await control.click();

  // The drawer is on the fourth tab, at that file and that line.
  await expect(page.getByTestId("inspector").locator('[data-tab="source"]')).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByTestId("source-path")).toHaveText("model.py");
  const hit = page.locator('[data-panel="source"] [data-hit="true"]');
  await expect(hit).toHaveCount(1);
  await expect(hit).toHaveAttribute("data-line", String(line));
  // The line itself, off the file rather than out of this test.
  await expect(hit.locator(".source-code")).toHaveText(modelText[line - 1] ?? "");
});

test("the file's own path and digest are above it, and it is the source that ran", async ({
  page,
}) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill("maint_fee_pp");
  await page.getByTestId("search").press("Enter");
  await page.getByTestId("open-source").click();

  const entry = level4.sources.get("model.py");
  const eightHex = (entry?.fingerprint?.split(":").pop() ?? "").slice(0, 8);
  await expect(page.getByTestId("source-fingerprint")).toHaveText(eightHex);
  // §7.3's one stated guarantee, said on the page: the entry for the model's
  // own path carries exactly the digest the envelope publishes beside it.
  expect(entry?.fingerprint).toBe(level4.artifact.model.source_sha);
  await expect(page.getByTestId("source-ran")).toBeVisible();
  await expect(page.getByTestId("source-bytes")).toContainText("39,964");
});

test("the head's control copies the file's text, byte for byte", async ({
  page,
  context,
  browserName,
}) => {
  // Reading the clipboard back is the assertion worth making, and only one of
  // the two engines will grant it from a file on a disk — the same split the
  // fingerprint's control is held to in `e2e/shell.spec.ts`. In the other, the
  // control's own word for what it did is what there is.
  if (browserName === "chromium") {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  }
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill("maint_fee_pp");
  await page.getByTestId("search").press("Enter");
  await page.getByTestId("open-source").click();
  await expect(page.getByTestId("source-path")).toHaveText("model.py");

  await page.getByTestId("copy-source").click();
  await expect(page.getByTestId("copy-source")).toHaveText("file copied");

  if (browserName === "chromium") {
    const pasted = await page.evaluate(() => navigator.clipboard.readText());
    // The payload as the document carries it, and not the lines the tab drew:
    // a trailing newline is a byte of the file, the line numbers and the
    // margin are the page's, and the digest above the control can only be
    // checked against the first of those. Read out of the fixture rather than
    // typed, so it stays evidence when the tutorial model is next edited.
    const entry = level4.sources.get("model.py");
    const text = entry !== undefined && "text" in entry.payload ? entry.payload.text : "";
    expect(text).not.toBe("");
    expect(pasted).toBe(text);
    // 39,964 bytes of it, which is what the head beside the control says.
    expect(new TextEncoder().encode(pasted).length).toBe(39964);
  }

  // For a second, and then the control is its own name again.
  await expect(page.getByTestId("copy-source")).toHaveText("copy file");
});

test("a line a node accounts for carries that column's name, and selects it", async ({ page }) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill("maint_fee_pp");
  await page.getByTestId("search").press("Enter");
  await page.getByTestId("open-source").click();

  // The line below the maintenance fee defines the next column, and the file
  // says which: this is the second reading the tab offers, from a line back to
  // the column it defines.
  const next = level4.nodes.get("av_pp_bef_inv@1");
  const line = Number(String(next?.source_location).split(":").pop());
  const margin = page.locator(`[data-panel="source"] [data-line="${String(line)}"] .source-account`);
  await expect(margin).toHaveText("av_pp_bef_inv");

  await margin.click();
  // The click reached the graph: the proof panel is now on that column.
  await expect(page.getByTestId("proof")).toContainText("av_pp_bef_inv");
});

test("clicking the line itself selects the column that line defines", async ({ page }) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill("maint_fee_pp");
  await page.getByTestId("search").press("Enter");
  await page.getByTestId("open-source").click();

  // The line is the target, not only the chip in its margin: a line that
  // defines a column does what that column's heading in the grid does. Clicked
  // on the code itself, well away from the margin.
  const next = level4.nodes.get("av_pp_bef_inv@1");
  const line = Number(String(next?.source_location).split(":").pop());
  const row = page.locator(`[data-panel="source"] [data-line="${String(line)}"]`);
  await row.locator(".source-code").click();
  await expect(page.getByTestId("proof")).toContainText("av_pp_bef_inv");
});

test("a line no node claims stays plain", async ({ page }) => {
  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill("maint_fee_pp");
  await page.getByTestId("search").press("Enter");
  await page.getByTestId("open-source").click();

  const claimed = level4.accountedLines.get("model.py");
  const node = level4.nodes.get("maint_fee_pp@1");
  const line = Number(String(node?.source_location).split(":").pop());
  // The comment above it. The file accounts for no column there, and that is
  // worth seeing: it is code the record does not account for.
  expect(claimed?.has(line - 1)).toBe(false);
  const plain = page.locator(`[data-panel="source"] [data-line="${String(line - 1)}"]`);
  await expect(plain).toBeVisible();
  await expect(plain.locator(".source-account")).toHaveCount(0);
  await expect(plain.locator(".source-code")).toHaveText(modelText[line - 2] ?? "");
});

test("a file whose text was withheld says so, and says what would bring it", async ({ page }) => {
  await page.goto(pageFor("holes"));
  await expect(page.getByTestId("cone")).toBeVisible();
  // This file carries no values, so the proof pane prints that refusal and has
  // no footer to open the source from; the drawer's own tab is the other door
  // and opens on the selected column's location.
  await page.getByTestId("search").fill("select_loaded_claims");
  await page.getByTestId("search").press("Enter");
  await page.getByTestId("inspector").locator('[data-tab="source"]').click();

  const entry = [...holes.sources.values()][0];
  expect(entry?.payload).toEqual({ omitted: "withheld" });

  const said = page.getByTestId("source-missing");
  await expect(said).toHaveAttribute("data-missing", "withheld");
  // §4's form: what the file claimed, what is missing, and the one move.
  await expect(said).toContainText(String(entry?.path));
  await expect(said).toContainText("withheld");
  await expect(said).toContainText("--source");
  // Not a summary of all three reasons: the file said one of them.
  await expect(said).not.toContainText("unavailable");
  await expect(page.locator('[data-panel="source"] .source-row')).toHaveCount(0);
});

test("a file carrying no section at all says that, not that it was withheld", async ({ page }) => {
  // Absent and withheld are different claims and the page must not collapse
  // them. `sources` is the one optional array in the envelope (§7), so a
  // conforming document may carry none — and every export this repository
  // writes carries one, which is why the case is made here rather than kept as
  // a fixture. Nothing else about the file is touched.
  const edited = JSON.parse(readFileSync(resolve("fixtures/level3.json"), "utf8")) as Artifact;
  delete edited.sources;
  await page.goto(packed("refusal-no-sources", JSON.stringify(edited)));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill("pols_death");
  await page.getByTestId("search").press("Enter");
  await page.getByTestId("open-source").click();

  const said = page.getByTestId("source-missing");
  await expect(said).toHaveAttribute("data-missing", "no-section");
  await expect(said).toContainText("no sources section");
});

test("the page fetches nothing to show the source", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (request) => {
    if (!request.url().startsWith("file:")) asked.push(request.url());
  });

  await page.goto(pageFor("level4"));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill("maint_fee_pp");
  await page.getByTestId("search").press("Enter");
  await page.getByTestId("open-source").click();
  await expect(page.getByTestId("source-path")).toHaveText("model.py");

  // The page reads the document it is part of and nothing else. A source view
  // that reached for a path on the reader's machine would be showing a file
  // nothing in the document identifies.
  expect(asked).toEqual([]);
});
