// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The cone, read off the page the exporter writes.
 *
 * Which nodes belong in the window is worked out here from the fixture, by the
 * same walk the page uses, for the reason the grid's cases give: a list of
 * node names typed into a test is a list somebody read off a screen once. What
 * is held to is that the drawing is the window — that the controls move it one
 * step at a time, that a read the file states an offset for is drawn as the
 * loop and labelled from the facet, that a superseded definition is folded
 * into the one that replaced it, and that a click here and a click in the grid
 * are the same click.
 *
 * The viewport is larger than a laptop's on purpose. The cone pane is a
 * quarter of the page, and a window of twenty-one nodes drawn at the body's
 * own 220 x 78 does not fit a quarter of a 1280-wide page above the pinned
 * `minZoom` of 0.3. Making the pane big enough is the difference between
 * testing the drawing and testing the zoom floor.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { buildIndex } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";
import { coneWindow } from "../src/reader/window";

test.use({ viewport: { width: 2560, height: 1440 } });

/** The fixture a packed page carries, read back to work out what to expect. */
function fixture(name: string) {
  const artifact = JSON.parse(
    readFileSync(resolve(`fixtures/${name}.json`), "utf8"),
  ) as Artifact;
  return buildIndex(artifact);
}

const level4 = fixture("level4");

/** The page packed from one fixture, as a file on a disk. */
function pageFor(name: string): string {
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/** The cone pane's node for one id, whatever the id has in it. */
function coneNode(page: Page, id: string) {
  return page.locator(`.react-flow__node[data-id="${id}"]`);
}

/** Open a packed page and select one column through the search box. */
async function selecting(page: Page, name: string, column: string): Promise<void> {
  await page.goto(pageFor(name));
  await expect(page.getByTestId("grid")).toBeVisible();
  await page.getByTestId("search").fill(column);
  await page.getByTestId("search").press("Enter");
  await expect(page.getByTestId("cone-count")).toBeVisible();
}

/** Every node the walk reaches from `center` at exactly `depth` steps up. */
function atDepth(center: string, depth: number): string[] {
  const nearer = new Set(coneWindow(level4, center, depth - 1, 0).nodes);
  return coneWindow(level4, center, depth, 0).nodes.filter((id) => !nearer.has(id));
}

test("the cone draws the selected node and what it reads", async ({ page }) => {
  await selecting(page, "level4", "net_cf");

  await expect(coneNode(page, "net_cf@1")).toBeVisible();
  for (const read of level4.readsOf.get("net_cf@1") ?? []) {
    await expect(coneNode(page, read)).toBeVisible();
  }
});

test("the count beside the controls is the window's own size", async ({ page }) => {
  await selecting(page, "level4", "net_cf");

  const two = coneWindow(level4, "net_cf@1", 2, 2);
  await expect(page.getByTestId("cone-count")).toHaveText(String(two.nodes.length));

  await page.getByTestId("widen-up").click();
  const three = coneWindow(level4, "net_cf@1", 3, 2);
  await expect(page.getByTestId("cone-count")).toHaveText(String(three.nodes.length));
});

test("narrowing twice leaves the node and what reads it, and nothing above", async ({ page }) => {
  await selecting(page, "level4", "net_cf");

  await page.getByTestId("narrow-up").click();
  await page.getByTestId("narrow-up").click();

  const alone = coneWindow(level4, "net_cf@1", 0, 2);
  await expect(page.getByTestId("cone-count")).toHaveText(String(alone.nodes.length));
  await expect(coneNode(page, "net_cf@1")).toBeVisible();
  for (const read of level4.readsOf.get("net_cf@1") ?? []) {
    await expect(coneNode(page, read)).toHaveCount(0);
  }
});

test("widening one step brings the third step up onto the canvas", async ({ page }) => {
  await selecting(page, "level4", "net_cf");

  const third = atDepth("net_cf@1", 3);
  expect(third.length).toBeGreaterThan(0);
  const anyOfThem = page.locator(
    third.map((id) => `.react-flow__node[data-id="${id}"]`).join(", "),
  );
  await expect(anyOfThem).toHaveCount(0);

  await page.getByTestId("widen-up").click();
  await expect(anyOfThem.first()).toBeVisible();
});

test("the direction control swaps the two reaches", async ({ page }) => {
  await selecting(page, "level4", "premiums");

  await page.getByTestId("narrow-down").click();
  await page.getByTestId("narrow-down").click();
  const twoAbove = coneWindow(level4, "premiums@1", 2, 0);
  await expect(page.getByTestId("cone-count")).toHaveText(String(twoAbove.nodes.length));

  await page.getByTestId("direction").click();
  const twoBelow = coneWindow(level4, "premiums@1", 0, 2);
  await expect(page.getByTestId("cone-count")).toHaveText(String(twoBelow.nodes.length));
  for (const reader of level4.readBy.get("premiums@1") ?? []) {
    await expect(coneNode(page, reader)).toBeVisible();
  }
});

test("a read the file gives an offset is drawn as the loop, labelled from the facet", async ({
  page,
}) => {
  await selecting(page, "level4", "shifted_growth");

  // The facet states -1 on this read and nothing else on the page does. The
  // label is the file's number, written the way a reviewer writes it.
  expect(level4.offsetOf("shifted_growth@1", "combined_growth_factor@1")).toBe(-1);
  await expect(page.locator('.edge-offset[data-label="t−1"]')).toHaveCount(1);
});

test("an accumulation wears its convention in words", async ({ page }) => {
  await selecting(page, "level4", "survival_prob");

  await expect(coneNode(page, "survival_prob@1")).toContainText("beginning of period");
});

test("a compiled rollforward is one box listing its states", async ({ page }) => {
  await selecting(page, "rollforward", "av");

  const compiled = coneNode(page, "rollforward:ff70eb792aee");
  await expect(compiled).toBeVisible();
  for (const state of ["av"]) {
    await expect(compiled.locator(".states")).toContainText(state);
  }
});

test("a column the model does not account for is drawn as a hole", async ({ page }) => {
  await selecting(page, "holes", "reserve_override");

  await expect(coneNode(page, "reserve_override")).toHaveClass(/\bhole\b/);
});

test("a superseded definition is folded in, and the badge opens it again", async ({ page }) => {
  await selecting(page, "versions", "reserve");

  const surviving = coneNode(page, "reserve@2");
  await expect(surviving).toBeVisible();
  await expect(surviving.getByTestId("versions-badge")).toHaveText("2 versions");
  await expect(coneNode(page, "reserve@1")).toHaveCount(0);

  await surviving.getByTestId("versions-badge").click();
  await expect(coneNode(page, "reserve@1")).toBeVisible();
});

test("a click in the cone is a click in the grid", async ({ page }) => {
  await selecting(page, "level4", "net_cf");

  await coneNode(page, "premiums@1").click();
  await expect(page.locator('th[data-column="premiums"]')).toHaveClass(/\bsel\b/);
  await expect(page.locator('th[data-column="net_cf"]')).not.toHaveClass(/\bsel\b/);
});

test("the overview is there, and its rectangle moves when the window does", async ({ page }) => {
  await selecting(page, "level4", "net_cf");

  const minimap = page.getByTestId("minimap");
  await expect(minimap).toBeVisible();
  // Every node of the whole graph, not only the window's.
  await expect(minimap.locator("[data-node]")).toHaveCount(level4.order.length);

  const rectangle = page.getByTestId("minimap-window");
  const before = await rectangle.evaluate((r) => r.getAttribute("width"));
  await page.getByTestId("widen-up").click();
  await expect(rectangle).not.toHaveAttribute("width", before ?? "");
});

/**
 * Opening the graph up, which is what a click inside the cone does.
 *
 * The cone used to be a function of the selected node: clicking a box made it
 * the new centre and the whole window was recomputed around it, so every box on
 * the screen moved and the reader lost the drawing they were reading. These
 * hold the rule that replaced it — a click moves the focus and opens exactly
 * one step, and only where there is something closed to open.
 */
test("clicking a box whose neighbours are all drawn moves the focus and nothing else", async ({
  page,
}) => {
  await selecting(page, "level4", "maint_fee_pp");
  const before = await page.getByTestId("cone-count").textContent();
  const drawn = await page
    .locator(".react-flow__node")
    .evaluateAll((els) => els.map((el) => el.getAttribute("data-id")).sort());

  // An interior box, found from the file rather than named: one whose every
  // neighbour is already on the screen.
  const inside = new Set(drawn);
  const interior = drawn.find((id) =>
    [...(level4.readsOf.get(id ?? "") ?? []), ...(level4.readBy.get(id ?? "") ?? [])].every(
      (neighbour) => inside.has(neighbour),
    ),
  );
  if (interior == null) throw new Error("no interior node in this window");
  await page.locator(`[data-testid="rf__node-${interior}"]`).click();

  // The proof followed, so the click did select it.
  await expect(page.getByTestId("proof")).toContainText(
    level4.nodes.get(interior)?.column ?? interior,
  );
  // And the drawing did not change at all: the same count, the same boxes.
  await expect(page.getByTestId("cone-count")).toHaveText(before ?? "");
  expect(
    await page
      .locator(".react-flow__node")
      .evaluateAll((els) => els.map((el) => el.getAttribute("data-id")).sort()),
  ).toEqual(drawn);
});

test("clicking a box at the edge opens one step out of it, and only one", async ({ page }) => {
  await selecting(page, "level4", "maint_fee_pp");
  const drawn = new Set(
    await page
      .locator(".react-flow__node")
      .evaluateAll((els) => els.map((el) => el.getAttribute("data-id"))),
  );

  // A node at the edge of the window: pick one whose own neighbours are not all
  // drawn, read off the file rather than assumed.
  const edge = [...drawn].find((id) => {
    const reads = level4.readsOf.get(id ?? "") ?? [];
    const readBy = level4.readBy.get(id ?? "") ?? [];
    return [...reads, ...readBy].some((neighbour) => !drawn.has(neighbour));
  });
  if (edge == null) throw new Error("no node at the edge of this window");
  const opening = [...(level4.readsOf.get(edge) ?? []), ...(level4.readBy.get(edge) ?? [])].filter(
    (neighbour) => !drawn.has(neighbour),
  );

  await page.locator(`[data-testid="rf__node-${edge}"]`).click();
  await expect(page.getByTestId("cone-count")).toHaveText(String(drawn.size + opening.length));

  const after = new Set(
    await page
      .locator(".react-flow__node")
      .evaluateAll((els) => els.map((el) => el.getAttribute("data-id"))),
  );
  // Its neighbours arrived; nothing that was drawn left.
  for (const neighbour of opening) expect(after.has(neighbour)).toBe(true);
  for (const id of drawn) expect(after.has(id)).toBe(true);

  // And only one step: a neighbour of a neighbour did not come with it.
  const second = (level4.readsOf.get(opening[0] ?? "") ?? []).filter(
    (id) => !drawn.has(id) && !opening.includes(id),
  );
  for (const far of second) expect(after.has(far)).toBe(false);
});

test("choosing a column from the search starts a fresh window", async ({ page }) => {
  await selecting(page, "level4", "maint_fee_pp");
  const seed = await page.getByTestId("cone-count").textContent();

  // Open it up, then ask for the same column again: a new subject is a new
  // window, which is the one thing that takes an expansion back.
  const drawn = new Set(
    await page
      .locator(".react-flow__node")
      .evaluateAll((els) => els.map((el) => el.getAttribute("data-id"))),
  );
  const edge = [...drawn].find((id) =>
    [...(level4.readsOf.get(id ?? "") ?? []), ...(level4.readBy.get(id ?? "") ?? [])].some(
      (neighbour) => !drawn.has(neighbour),
    ),
  );
  if (edge == null) throw new Error("no node at the edge of this window");
  await page.locator(`[data-testid="rf__node-${edge}"]`).click();
  await expect(page.getByTestId("cone-count")).not.toHaveText(seed ?? "");

  await page.getByTestId("search").fill("maint_fee_pp");
  await page.getByTestId("search").press("Enter");
  await expect(page.getByTestId("cone-count")).toHaveText(seed ?? "");
});

test("a box under the overview is still clickable", async ({ page }) => {
  await selecting(page, "level4", "maint_fee_pp");

  // The overview is drawn over the canvas in the top-right corner. Its own
  // marks are controls; the space between them is not, and a box that happens
  // to be under it has to stay reachable.
  const overview = await page.getByTestId("minimap").boundingBox();
  if (overview === null) throw new Error("no overview drawn");
  const under = await page.locator(".react-flow__node").evaluateAll(
    (els, box) =>
      els
        .map((el) => ({ id: el.getAttribute("data-id"), rect: el.getBoundingClientRect() }))
        .filter(
          (one) =>
            one.rect.left < box.x + box.width &&
            one.rect.right > box.x &&
            one.rect.top < box.y + box.height &&
            one.rect.bottom > box.y,
        )
        .map((one) => one.id),
    overview,
  );
  test.skip(under.length === 0, "no box falls under the overview in this window");

  await page.locator(`[data-testid="rf__node-${String(under[0])}"]`).click();
  await expect(page.getByTestId("proof")).toBeVisible();
});
