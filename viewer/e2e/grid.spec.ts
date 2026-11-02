// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The grid, read off the page the exporter writes.
 *
 * Every expected value in this file is computed from the fixture the page was
 * packed from, by the same two functions the page draws with. That is
 * deliberate and it is the only way an assertion about a cell can be worth
 * making: a number typed into a test is a number somebody read off a screen
 * once, and it stops being evidence the moment the fixture is regenerated.
 * What is being held to here is that the cell on the page is the element of
 * `value_sample` it claims to be, and that the outlines fall where the file's
 * own `offset` says they fall.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";

import { formatFormula, formatValue } from "../src/reader/format";
import type { Artifact, ArtifactNode } from "../src/reader/types";

const LEVEL4 = resolve("dist/level4.html");
const HOLES = resolve("dist/holes.html");

/** The fixture a packed page carries, read back here to compute what to expect. */
function fixture(name: string): Artifact {
  return JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact;
}

const level4 = fixture("level4");

/** One node of the level-4 fixture, by the id the file gives it. */
function node(id: string): ArtifactNode {
  const found = level4.nodes.find((n) => n.id === id);
  if (found === undefined) throw new Error(`the level-4 fixture carries no node ${id}`);
  return found;
}

/** The per-period columns, as the reader picks them: list nodes in the final schema. */
const perPeriod = level4.nodes.filter((n) => n.in_final_schema && n.shape === "list");
const scalars = level4.nodes.filter((n) => n.in_final_schema && n.shape === "scalar");

/** The cursor's period for every assertion below, and the one the mocks were drawn at. */
const CURSOR = 12;

/** Open the packed page and put the row cursor on `CURSOR` from the grid's own keys. */
async function atTheCursor(page: import("@playwright/test").Page): Promise<void> {
  await page.goto(pathToFileURL(LEVEL4).href);
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("grid").focus();
  for (let step = 0; step < CURSOR; step += 1) await page.keyboard.press("ArrowDown");
  await expect(page.locator(`tr[data-period="${CURSOR}"]`)).toHaveClass(/\bcursor\b/);
}

/**
 * How far the row of one period is outside the part of the grid a reader can
 * see: below the sticky header and above the bottom of the scroller's view,
 * which is above its horizontal scrollbar where the platform draws one. Zero or
 * less on each side is a row wholly in sight.
 */
async function outOfSight(
  page: import("@playwright/test").Page,
  period: number,
): Promise<{ above: number; below: number }> {
  return page.evaluate((at) => {
    const scroller = document.querySelector(".grid .scroll");
    const head = scroller?.querySelector("thead");
    const row = scroller?.querySelector(`tbody tr[data-period="${String(at)}"]`);
    if (!(scroller instanceof HTMLElement) || !head || !row) {
      return { above: Number.POSITIVE_INFINITY, below: Number.POSITIVE_INFINITY };
    }
    const box = row.getBoundingClientRect();
    const top = head.getBoundingClientRect().bottom;
    const bottom =
      scroller.getBoundingClientRect().top + scroller.clientTop + scroller.clientHeight;
    return { above: top - box.top, below: box.bottom - bottom };
  }, period);
}

/** Wait until the row of one period is wholly in sight, within a pixel's rounding. */
async function inSight(page: import("@playwright/test").Page, period: number): Promise<void> {
  await expect
    .poll(
      async () => {
        const { above, below } = await outOfSight(page, period);
        return Math.max(above, below) <= 1;
      },
      { message: `the cursor's row, period ${String(period)}, is not wholly in sight` },
    )
    .toBe(true);
}

test("the cursor's row stays in sight as it moves past either edge of the grid", async ({
  page,
}) => {
  await page.goto(pathToFileURL(LEVEL4).href);
  await expect(page.getByTestId("grid")).toBeVisible();

  // Down past the bottom of the window a row at a time, from the grid's keys:
  // every row after the first few is reached by scrolling, and each has to
  // land above the bottom of the view rather than under it.
  await page.getByTestId("grid").focus();
  for (let period = 1; period <= 24; period += 1) {
    await page.keyboard.press("ArrowDown");
    await expect(page.locator(`tr[data-period="${String(period)}"]`)).toHaveClass(/\bcursor\b/);
    await inSight(page, period);
  }

  // A page at a time, and the slider stepped as a scrub steps it.
  await page.keyboard.press("PageDown");
  await inSight(page, 36);
  const slider = page.getByTestId("cursor");
  for (let period = 37; period <= 48; period += 1) {
    await slider.fill(String(period));
    await inSight(page, period);
  }

  // And back up past the top, where a row has to land under the sticky
  // header rather than behind it.
  await page.getByTestId("grid").focus();
  for (let period = 47; period >= 30; period -= 1) {
    await page.keyboard.press("ArrowUp");
    await inSight(page, period);
  }
});

test("the cursor's row stays in sight above a scrollbar that takes room", async ({ page }) => {
  // Windows and most Linux desktops draw a scrollbar that takes room from the
  // grid rather than one laid over it, and the bottom of what a reader can see
  // is then above it. Drawn that way here where the engine allows it; an
  // engine that keeps its scrollbars over the content has no room to lose, and
  // the case above already covers it.
  await page.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      const style = document.createElement("style");
      style.textContent = ".grid .scroll::-webkit-scrollbar { width: 15px; height: 15px; }";
      document.head.append(style);
    });
  });
  await page.goto(pathToFileURL(LEVEL4).href);
  await expect(page.getByTestId("grid")).toBeVisible();
  const room = await page
    .locator(".grid .scroll")
    .evaluate((scroller) => (scroller as HTMLElement).offsetHeight - scroller.clientHeight);
  test.skip(room === 0, "this engine lays its scrollbars over the content");

  await page.getByTestId("grid").focus();
  for (let period = 1; period <= 20; period += 1) {
    await page.keyboard.press("ArrowDown");
    await inSight(page, period);
  }
});

/**
 * Where the row labels the column draws sit, and where the rows they label sit.
 *
 * Read off the page in one pass, with the number of things in the body that
 * stick: the column is meant to be the only one.
 */
async function labelsAndRows(page: import("@playwright/test").Page) {
  const seen = await page.evaluate(() => {
    const scroller = document.querySelector(".grid .scroll");
    const body = scroller?.querySelector("tbody");
    if (!(scroller instanceof HTMLElement) || !body) return null;
    const edge = scroller.getBoundingClientRect().left + scroller.clientLeft;
    const at = (element: Element) => element.getBoundingClientRect();
    return {
      sticky: [...body.querySelectorAll("*")].filter(
        (element) => getComputedStyle(element).position === "sticky",
      ).length,
      rows: [...body.querySelectorAll("tr[data-period]")].map((row) => ({
        period: row.getAttribute("data-period"),
        top: at(row).top,
        bottom: at(row).bottom,
        cursor: row.classList.contains("cursor"),
      })),
      labels: [...body.querySelectorAll(".label-column .label")].map((label) => ({
        text: label.textContent,
        top: at(label).top,
        bottom: at(label).bottom,
        left: at(label).left - edge,
        cursor: label.classList.contains("cursor"),
      })),
    };
  });
  if (seen === null) throw new Error("the grid drew no scroller and body to read");
  return seen;
}

/** Two animation frames, so a scroll or a zoom has been laid out and drawn. */
async function drawn(page: import("@playwright/test").Page): Promise<void> {
  await page.evaluate(
    () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))),
  );
}

test("the row labels stick down the left as one column, level with their rows", async ({
  page,
}) => {
  // Every label used to stick on its own, and an element that sticks inside a
  // scroller is a compositing layer of its own: one layer per drawn row. One
  // column now draws them, and what is held here is that it draws them where
  // the cells did: the same number on the same row, at the left edge of the
  // grid while the values slide under it.
  await atTheCursor(page);
  await page.locator(".grid .scroll").evaluate((scroller) => {
    scroller.scrollLeft = 700;
    scroller.scrollTop = 120;
  });
  await drawn(page);

  const seen = await labelsAndRows(page);
  expect(seen.sticky).toBe(1);
  expect(seen.rows.length).toBeGreaterThan(0);
  expect(seen.labels.map((label) => label.text)).toEqual(seen.rows.map((row) => row.period));
  seen.rows.forEach((row, at) => {
    const label = seen.labels[at];
    expect(label?.top).toBeCloseTo(row.top, 1);
    expect(label?.bottom).toBeCloseTo(row.bottom, 1);
    expect(label?.left).toBeCloseTo(0, 1);
    expect(label?.cursor).toBe(row.cursor);
  });
  expect(seen.labels.filter((label) => label.cursor).map((label) => label.text)).toEqual([
    String(CURSOR),
  ]);
});

// The page zoomed out and in, the two ways a browser does it: the page's own
// zoom, and a screen of fewer or more device pixels to the CSS pixel. A row's
// height is a minimum, and away from 100% its rule rounds to a whole device
// pixel, so a row can come out taller than the 23 px it asks for. A label of a
// fixed height fell behind its row by that rounding on every row, and at the
// foot of the grid read the next period's number beside a row. Taken at the
// foot, where the most rows have been laid out above the one being read.
for (const [how, scale] of [
  ["zoomed", 0.5],
  ["zoomed", 0.67],
  ["zoomed", 0.9],
  ["zoomed", 1.5],
  ["scaled", 0.5],
  ["scaled", 0.67],
] as const) {
  test(`the row labels stay level with their rows with the page ${how} to ${String(Math.round(scale * 100))}%`, async ({
    browser,
  }) => {
    const context = await browser.newContext(
      how === "scaled"
        ? {
            viewport: { width: Math.round(1440 / scale), height: Math.round(900 / scale) },
            deviceScaleFactor: scale,
          }
        : { viewport: { width: 1440, height: 900 } },
    );
    const page = await context.newPage();
    await page.goto(pathToFileURL(LEVEL4).href);
    await expect(page.locator('tr[data-period="0"]')).toBeVisible();
    if (how === "zoomed") {
      await page.evaluate((zoom) => {
        document.documentElement.style.zoom = String(zoom);
      }, scale);
    }
    await page.locator(".grid .scroll").evaluate((scroller) => {
      scroller.scrollLeft = 700;
      scroller.scrollTop = scroller.scrollHeight;
    });
    await drawn(page);

    const seen = await labelsAndRows(page);
    await context.close();
    expect(seen.rows.length).toBeGreaterThan(16);
    expect(seen.labels.map((label) => label.text)).toEqual(seen.rows.map((row) => row.period));
    const furthest = Math.max(
      ...seen.rows.map((row, at) =>
        Math.max(
          Math.abs((seen.labels[at]?.top ?? Number.NaN) - row.top),
          Math.abs((seen.labels[at]?.bottom ?? Number.NaN) - row.bottom),
        ),
      ),
    );
    expect(furthest).toBeLessThan(0.5);
  });
}

test("the search box is what the page hands you", async ({ page }) => {
  await page.goto(pathToFileURL(LEVEL4).href);
  await expect(page.getByTestId("search")).toBeFocused();
});

test("every per-period column the file carries has a header", async ({ page }) => {
  await page.goto(pathToFileURL(LEVEL4).href);
  await expect(page.locator("th[data-column]")).toHaveCount(perPeriod.length);
  for (const column of perPeriod) {
    await expect(page.locator(`th[data-column="${column.column}"]`)).toHaveCount(1);
  }
});

test("searching for a column selects it, and the header row shows its formula", async ({
  page,
}) => {
  await page.goto(pathToFileURL(LEVEL4).href);
  await page.getByTestId("search").fill("net_cf");
  await page.getByTestId("search").press("Enter");

  await expect(page.locator('th[data-column="net_cf"]')).toHaveClass(/\bsel\b/);
  // The formula as the producer recorded it, on one line and otherwise as
  // written — six terms over six source lines in the model.
  await expect(page.locator('td[data-formula-for="net_cf"]')).toHaveText(
    formatFormula(node("net_cf@1").formula),
  );
  // Enter hands the grid back whole: a filter still narrowing it would hide the
  // very columns the selection is about to outline.
  await expect(page.getByTestId("search")).toHaveValue("");
  await expect(page.locator("th[data-column]")).toHaveCount(perPeriod.length);
});

test("the cell under the cursor is the element of value_sample it claims to be", async ({
  page,
}) => {
  await atTheCursor(page);
  await page.getByTestId("search").fill("net_cf");
  await page.getByTestId("search").press("Enter");

  const sample = node("net_cf@1").value_sample as unknown[];
  await expect(page.locator(`td[data-column="net_cf"][data-period="${CURSOR}"]`)).toHaveText(
    formatValue(sample[CURSOR]),
  );
});

test("a selected column outlines the cells it reads, on the cursor's row", async ({ page }) => {
  await atTheCursor(page);
  await page.getByTestId("search").fill("net_cf");
  await page.getByTestId("search").press("Enter");

  for (const read of ["premiums", "claims", "expenses"]) {
    await expect(page.locator(`td[data-column="${read}"][data-period="${CURSOR}"]`)).toHaveClass(
      /\boperand\b/,
    );
  }
});

test("a read with an offset outlines the row the offset points at", async ({ page }) => {
  await atTheCursor(page);
  await page.getByTestId("search").fill("shifted_growth");
  await page.getByTestId("search").press("Enter");

  // `shifted_growth` is `combined_growth_factor.projection.previous_period()`,
  // and the narrowing facet states the offset as -1. With the cursor on 12 the
  // outline belongs on 11, and nowhere else: the page knows this only because
  // the file says it.
  const outlined = page.locator('td[data-column="combined_growth_factor"][data-period="11"]');
  await expect(outlined).toHaveClass(/\boperand\b/);
  await expect(outlined).toHaveAttribute("data-offset", "-1");
  await expect(
    page.locator(`td[data-column="combined_growth_factor"][data-period="${CURSOR}"]`),
  ).not.toHaveClass(/\boperand\b/);
});

test("a scalar is reached by the search box, and is never a column of the grid", async ({
  page,
}) => {
  await page.goto(pathToFileURL(LEVEL4).href);

  // The strip of pinned scalars is gone and this is the door that replaced it.
  // Every scalar the file carries is findable by name: the search counts over
  // every column in the final schema, not the per-period ones alone.
  // A computed one, so the proof panel has a worked example to stand on.
  const scalar = scalars.find(
    (one) => typeof one.formula === "string" && typeof one.column === "string",
  );
  const column = scalar?.column;
  if (column == null) throw new Error("the level-4 fixture carries no computed scalar");
  await page.getByTestId("search").fill(column);
  await page.getByTestId("search").press("Enter");

  // Selected, so the proof panel works it out — and the grid draws no column
  // for it, because a scalar has one value and no row to put it on.
  await expect(page.getByTestId("proof")).toContainText(column);
  await expect(page.locator(`th[data-column="${column}"]`)).toHaveCount(0);

  // And the count is over every column now, not the per-period ones alone.
  await page.getByTestId("search").fill("pv_");
  await expect(page.getByTestId("search-found")).toContainText(
    `of ${String(level4.nodes.filter((n) => n.in_final_schema).length)}`,
  );
});

test("a file with no holes wears no chip, and one with two says two", async ({ page }) => {
  await page.goto(pathToFileURL(LEVEL4).href);
  await expect(page.getByTestId("holes-chip")).toHaveCount(0);

  await page.goto(pathToFileURL(HOLES).href);
  await expect(page.getByTestId("holes-chip")).toHaveText("2 holes");
});
