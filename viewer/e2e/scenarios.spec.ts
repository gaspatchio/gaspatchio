// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * A scenario run's page, read off the artifact the exporter writes.
 *
 * `gspio calc-graph --scenarios run_scenarios.py` runs the plan the
 * modeller wrote and exports the cross-joined frame. Four things are held to
 * here, and each is a thing a reader of a sensitivity pack asks.
 *
 * **Every entry of the axis names its scenario.** A cross-join gives one
 * policy one row per scenario, so three entries can read `policy 1` and differ
 * in nothing a reader can see. The `filter` is what tells them apart, and the
 * switcher shows it on both halves of the axis — the per-scenario folds at the
 * head, and the policies beneath them.
 *
 * **The axis column reads as what it is.** `scenario_id` was not in the
 * model-points file; the framework put it there at a line of the run script,
 * and the input leaf's provenance chip says so rather than filing it under the
 * book. It is the one sentence on the page that used to be false.
 *
 * **The bases a discounted column read are named, all of them.** Level 5
 * dispatches three rate curves on `scenario_id`, so the file carries three
 * curve entries and the node reads all three. The panel names them with their
 * fingerprints instead of naming the first as though it were the one this row
 * took — which is a claim the file does not carry.
 *
 * **The fold entries carry the plan's own totals**, read out of the fixture by
 * the reader the page draws with.
 *
 * **And a link to one of them is a link to that one.** Three entries are
 * called `1` and three are called `fold · sum`; before 2026-09-20 all six wrote
 * one of two fragments and every one of them landed on BASE. The fragment now
 * carries the entry's own cut, and the case below walks the whole axis: stand
 * on an entry, take the link the page wrote, follow it, and arrive where you
 * were standing.
 *
 * The fixture is a producer's own export of level 5's base: eight policies
 * against BASE, UP and DOWN, with `--policies :3`.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { formatValue, isIntegerDtype } from "../src/reader/format";
import { buildIndex } from "../src/reader/index";
import type { Artifact } from "../src/reader/types";

const MODEL = "scenarios";

/** The fixture the packed page carries, read back to work out what to expect. */
const file = JSON.parse(readFileSync(resolve(`fixtures/${MODEL}.json`), "utf8")) as Artifact;

/** The axis column the cross-join put on the frame, and the column it steers. */
const AXIS_NODE = "scenario_id@1";
const DISCOUNTED = "disc_factors";
const DISCOUNTED_NODE = "disc_factors@1";
const FOLDED = "pv_net_cf";
const FOLDED_NODE = "pv_net_cf@1";

/** The entry that folds the DOWN cut of the book, and the policy row under DOWN. */
const DOWN_FOLD = file.policies.findIndex(
  (entry) => entry.aggregation !== null && entry.filter === 'scenario_id == "DOWN"',
);
const DOWN_POLICY = file.policies.findIndex(
  (entry) => entry.aggregation === null && entry.filter === 'scenario_id == "DOWN"',
);

/** The page packed from one fixture, as a file on a disk. */
function pageFor(name: string): string {
  return pathToFileURL(resolve(`dist/${name}.html`)).href;
}

/** What one entry holds for one column, written as the page writes it. */
function held(at: number, id: string, period: number): string {
  const index = buildIndex(file, at);
  const sample = index.sampleOf(id);
  return formatValue(Array.isArray(sample) ? sample[period] : sample, {
    integer: isIntegerDtype(String(index.nodes.get(id)?.dtype)),
  });
}

/** Move to one entry of the axis and select one column. */
async function reading(page: Page, at: number, column: string): Promise<void> {
  await page.goto(pageFor(MODEL));
  await expect(page.getByTestId("policy-switcher")).toBeVisible();
  await page.getByTestId("policy-switcher").selectOption(String(at));
  await page.getByTestId("search").fill(column);
  await page.getByTestId("search").press("Enter");
  await expect(page.getByTestId("cone-count")).toBeVisible();
}

test("every entry of the axis names the scenario its rows sit in", async ({ page }) => {
  // The file says it first, on both halves: the folds are one per cut, and a
  // policy entry states the cut its row is in.
  const cuts = file.policies.map((entry) => entry.filter);
  expect(cuts.every((cut) => typeof cut === "string" && cut.startsWith("scenario_id =="))).toBe(
    true,
  );
  expect(new Set(cuts).size).toBe(3);

  // And the page shows it: three entries read policy 1, and the sentence
  // beside each is what separates them.
  // The page mounts after its load event -- React schedules the first render
  // -- and allInnerTexts() reads whatever is there the moment it is called,
  // which on WebKit was often nothing. The switcher is drawn with all its
  // options at once, so the page is read once it is.
  await page.goto(pageFor(MODEL));
  const switcher = page.getByTestId("policy-switcher");
  await expect(switcher).toBeVisible();
  const labels = await switcher.locator("option").allInnerTexts();
  expect(labels).toHaveLength(file.policies.length);
  for (const [at, entry] of file.policies.entries()) {
    expect(labels[at]).toContain(String(entry.why));
  }
});

test("the scenario axis reads as a column handed to the model, not as the book", async ({
  page,
}) => {
  const axis = file.nodes.find((node) => node.id === AXIS_NODE);
  expect(axis?.kind).toBe("input");
  expect(axis?.provenance).toBe("injected");
  expect(axis?.source_location).toContain("run_scenarios.py:");

  await reading(page, DOWN_POLICY, "scenario_id");
  // "handed to the model at <file>:<line>" — the line of the run script that
  // declares the plan, which is where the axis came from.
  await expect(page.getByTestId("proof")).toContainText(
    `handed to the model at ${String(axis?.source_location)}`,
  );
});

test("a column that read several rate curves names every one of them", async ({ page }) => {
  const node = file.nodes.find((entry) => entry.id === DISCOUNTED_NODE);
  const read = node?.reads_assumptions ?? [];
  expect(read.length).toBeGreaterThan(1);

  await reading(page, DOWN_POLICY, DISCOUNTED);
  const proof = page.getByTestId("proof");
  for (const name of read) {
    await expect(proof).toContainText(name);
    const entry = (file.assumptions as { name?: string; fingerprint?: string }[]).find(
      (table) => table.name === name,
    );
    // The chip's digest is the entry's, so a reader checking a curve against
    // the pack is checking the one the file carries.
    await expect(proof).toContainText(String(entry?.fingerprint));
  }
});

test("a link to one scenario entry lands on that entry and on no other", async ({ page }) => {
  // Every entry of the axis, both halves of it: the three per-scenario folds
  // and the three rows of policy 1. Each is selected, the link the page wrote
  // for it is read off the address bar, and the page is reopened from it.
  for (const [at, entry] of file.policies.entries()) {
    await page.goto(pageFor(MODEL));
    await expect(page.getByTestId("policy-switcher")).toBeVisible();
    await page.getByTestId("policy-switcher").selectOption(String(at));
    await page.getByTestId("search").fill(FOLDED);
    await page.getByTestId("search").press("Enter");

    // The fragment settles on a trailing timer, so it is polled rather than
    // read once — and what is polled for is the cut, which is the whole of
    // what separates this entry from the two beside it.
    // `URLSearchParams` is what wrote it, and it spells a space `+` where
    // `encodeURIComponent` spells it `%20`.
    const cut = new URLSearchParams({ filter: String(entry.filter) }).toString().slice("filter=".length);
    await expect
      .poll(async () => page.evaluate(() => window.location.hash))
      .toContain(`filter=${cut}`);
    const fragment = await page.evaluate(() => window.location.hash);

    await page.goto(`${pageFor(MODEL)}${fragment}`);
    await expect(page.getByTestId("policy-switcher")).toHaveValue(String(at));
    // Landed cleanly: nothing about this link was unanswerable, which is what
    // says the round trip is a round trip and not a near miss with a note.
    await expect(page.getByTestId("link-note")).toHaveCount(0);
  }
});

test("a link that names a policy three entries answer to lands on none of them", async ({
  page,
}) => {
  // A link written before the cut was in the grammar, or typed by hand. The
  // page opens where it opens and says what it could not answer, rather than
  // handing the reader BASE's numbers under a name UP and DOWN also answer to.
  await page.goto(`${pageFor(MODEL)}#policy=1&column=${FOLDED}`);
  await expect(page.getByTestId("grid")).toBeVisible();
  await expect(page.getByTestId("link-note")).toContainText(
    "policy 1, which this file carries under more than one filter",
  );
});

test("a per-scenario fold carries the plan's own total for that cut", async ({ page }) => {
  expect(DOWN_FOLD).toBeGreaterThanOrEqual(0);
  expect(file.policies[DOWN_FOLD]?.policy_id).toBeNull();

  await reading(page, DOWN_FOLD, FOLDED);
  await expect(page.getByTestId("proof")).toContainText(held(DOWN_FOLD, FOLDED_NODE, 0));
  await expect(page.getByTestId("proof").locator('[data-kind="fold"]')).toContainText(
    String(file.policies[DOWN_FOLD]?.why),
  );
});
