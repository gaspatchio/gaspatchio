// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The mechanics four scripted reads share, and nothing either of them asks.
 *
 * The reads' evidence comes in two forms: a written read first, where a person
 * walks a fixed list of questions over one real model and quotes what the page
 * answered, and a scripted read after, so the answers stay true rather than
 * having been true on one afternoon. The four specs beside this file are the
 * second form of the four written reads taken on 2026-09-17.
 *
 * What lives here is opening a page, putting the cursor somewhere and taking
 * the photograph — the same in all four because it is the same page. What does
 * **not** live here is any part of a walk: the columns, the periods, the lines
 * and the values differ model by model, the order they are asked in is the
 * record's, and a shared function that asked them would turn four readings of
 * four models into one parameterised claim about none of them.
 *
 * Every number a spec expects is read out of the fixture its page was packed
 * from, by the same function the page writes with, for the reason the grid's
 * and the proof's cases give: a figure typed into a test is a figure somebody
 * read off a screen once, and it stops being evidence the moment the fixture is
 * regenerated. The written record is where the figures are quoted; the spec is
 * where they are derived again from the file and checked against the screen.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import { formatValue, isIntegerDtype } from "../../src/reader/format";
import { buildIndex } from "../../src/reader/index";
import type { Index } from "../../src/reader/index";
import type { Artifact } from "../../src/reader/types";

/**
 * The screen the written reads were taken on, and the one they are scripted at.
 *
 * Every one of those written reads says "Screenshots at 1,440 × 900", and the answers
 * two of them quote are answers about a screen of that size — how much of a
 * twenty-one node window is on the canvas before anybody pans. Reading them
 * back at another size would be reading a different page.
 */
export const VIEWPORT = { width: 1440, height: 900 };

/**
 * One committed fixture, indexed, read back here to work out what to expect.
 *
 * On the first entry of its policy axis, which is where the page opens: these
 * four fixtures carry one policy each, so it is the only entry there is.
 */
export function fixture(name: string): Index {
  const artifact = JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact;
  return buildIndex(artifact);
}

/** The page packed from one fixture, as a file on a disk, which is how it is opened. */
export function pageFor(name: string): string {
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/**
 * What one column held at one period, written the way the page writes it.
 *
 * @param index - The fixture's index.
 * @param id - The node, as the file spells it.
 * @param period - The period to read, which for a scalar is ignored.
 * @returns The value, through `formatValue`, integer-aware as the grid is.
 */
export function held(index: Index, id: string, period: number): string {
  const node = index.nodes.get(id);
  const sample = index.sampleOf(id);
  return formatValue(Array.isArray(sample) ? sample[period] : sample, {
    integer: node !== undefined && isIntegerDtype(node.dtype),
  });
}

/**
 * One cell of a table excerpt, in the payload's own notation.
 *
 * The panel writes an inline table's cells as the payload holds them — a string
 * as itself, anything else as compact JSON — because an assumption table's rows
 * are the thing a reviewer is checking and reformatting them would be the page
 * editing the evidence. The rule is restated here rather than imported because
 * a test that asked the panel's own function what the panel should print would
 * be asking the answer of the thing under test.
 *
 * @param value - One cell of the payload.
 * @returns What the excerpt draws in that cell.
 */
export function excerptCell(value: unknown): string {
  if (value === null || value === undefined) return "·";
  return typeof value === "string" ? value : JSON.stringify(value);
}

/**
 * Open the page, put the row cursor on a period, and select a column.
 *
 * Both moves are made the way a reader makes them — the grid's own arrow keys
 * and the search box — so what is under test is the page somebody was sent and
 * not a door a test opened for itself.
 *
 * @param page - The browser page.
 * @param model - The fixture's name, which is also the packed page's.
 * @param column - The column to search for and select.
 * @param period - Where to leave the row cursor.
 */
export async function reading(
  page: Page,
  model: string,
  column: string,
  period: number,
): Promise<void> {
  await page.goto(pageFor(model));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("grid").focus();
  for (let step = 0; step < period; step += 1) await page.keyboard.press("ArrowDown");
  await expect(page.locator(`tr[data-period="${String(period)}"]`)).toHaveClass(/\bcursor\b/);
  await page.getByTestId("search").fill(column);
  await page.getByTestId("search").press("Enter");
  await expect(page.getByTestId("cone-count")).toBeVisible();
}

/** The drawer's Model tab, opened, which is the last question every read asks. */
export async function modelTab(page: Page) {
  await page.getByTestId("inspector").locator('[data-tab="model"]').click();
  const panel = page.getByTestId("inspector").locator('[data-panel="model"]');
  await expect(panel).toBeVisible();
  return panel;
}

/**
 * Photograph the page as the read's last step, and file it beside the spec.
 *
 * The written reads kept their own screenshots; these are the durable form,
 * retaken every time the four specs run, so the evidence is a
 * thing the lane keeps producing rather than four files somebody saved once.
 *
 * Two differences from the written reads'. The drawer is on the Model tab, which is
 * where each read's last question was answered. And the cursor's row is
 * scrolled into the middle of the grid rather than left where the page put it:
 * `Grid`'s own scroll aligns "auto", which leaves a row arrived at from above
 * sitting on the bottom edge, and a photograph with the row under discussion
 * pressed against its frame is a worse photograph. Only the scroll offset
 * moves — the selection, the cursor and everything drawn from them are the
 * page's.
 *
 * @param page - The browser page, already in the state the read ended in.
 * @param model - The fixture's name, which the file is named after.
 * @param period - The cursor's period, whose row is centred.
 */
export async function photograph(page: Page, model: string, period: number): Promise<void> {
  await modelTab(page);
  const row = page.locator(`tr[data-period="${String(period)}"]`);
  await row.evaluate((element) => {
    // `inline: "nearest"` deliberately: the grid scrolls both ways and a row
    // spans every column, so centring it horizontally would scroll the page
    // sideways to the middle of a column nobody asked about.
    element.scrollIntoView({ block: "center", inline: "nearest" });
  });
  await expect(row).toHaveClass(/\bcursor\b/);

  // The picture is taken when it is asked for, and not on every run.
  //
  // **Nothing compares these four images.** They are written and never
  // asserted: what the reads test is every question above this line, and the
  // picture is a record for a person — the one each written read points at.
  // A routine test run rewriting a record is the wrong way round, and it had a
  // cost past the untidiness: `git status` was never clean after an end-to-end
  // run, which is the check every unit in this repository uses as evidence
  // that a commit's committed assets are the ones its build wrote.
  //
  // They cannot be made byte-stable anyway, and that was measured rather than
  // assumed. Across runs of the same page the viewport transform, the edge
  // paths, the node count and every node's position are **identical**; what
  // differs is the rasterisation of the text inside the boxes, which is the
  // browser's and not ours. Two captures of one box hold the same characters
  // at the same size and differ in sub-pixel antialiasing. Chromium's
  // deterministic-rendering flags (`--disable-gpu`, `--disable-lcd-text`,
  // `--font-render-hinting=none`, `--disable-font-subpixel-positioning`)
  // narrow it and do not close it: three runs went from three distinct images
  // to two.
  //
  // So the record is taken deliberately — `npm run reads:photograph` — and a
  // reader who wants the picture fresh asks for it on the day they are
  // reading.
  if (process.env["READS_PHOTOGRAPH"] === "1") {
    await page.screenshot({ path: resolve(`e2e/reads/screenshots/${model}.png`) });
  }
}
