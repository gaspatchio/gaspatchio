// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * An integer a double cannot carry, on the page a reader opens.
 *
 * `test/exact.test.ts` holds the reader's own arithmetic without a browser.
 * What is under test here is the part only a browser answers: that the number
 * the exporter wrote reaches the grid, the drawer and the worked example with
 * every digit the file spelled, through the parse the page actually runs.
 *
 * The fixture is the producer's own export of the smallest model that shows
 * it — `result = number + 1` over the Int64 `9007199254740992` — which is the
 * document an external review found this with. §11.1.25 admits that
 * arithmetic across the signed range and §10 makes the format's integers
 * exact, so `9007199254740993` is a value a conforming file carries; before
 * this the page displayed `9,007,199,254,740,992` for it, in the grid, in the
 * trace and in any comparison, with nothing on the screen admitting it.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test } from "@playwright/test";

import type { Artifact } from "../src/reader/types";

const PAGE = pathToFileURL(resolve("dist/wide-integer.html")).href;

const file = JSON.parse(readFileSync(resolve("fixtures/wide-integer.json"), "utf8")) as Artifact;

/** The digits the exporter wrote, read out of the file's own text. */
const DIGITS = /"result@1"[\s\S]*?"value_sample": (\d+)/.exec(
  readFileSync(resolve("fixtures/wide-integer.json"), "utf8"),
)?.[1];

/** Those digits grouped the way every integer on this page is grouped. */
const WRITTEN = "9,007,199,254,740,993";

test("the file carries an i64 past what a double holds", async () => {
  // Stated first, because every assertion below is only worth making if the
  // document really carries it. The producer wrote the digits; a reader that
  // had already lost them would be comparing two rounded numbers.
  expect(DIGITS).toBe("9007199254740993");
  const node = file.nodes.find((one) => one.id === "result@1");
  expect(node?.dtype).toBe("i64");
  expect(Number.isSafeInteger(Number(DIGITS))).toBe(false);
});

test("the page writes every digit the file spelled, in the grid and in the drawer", async ({
  page,
}) => {
  await page.goto(PAGE);
  await expect(page.getByTestId("inspector")).toBeVisible();

  // `result` is a scalar — one value per policy and no row to put it on — so
  // the drawer's record is where its number is written.
  const record = page.getByTestId("inspector");
  await expect(record.locator('[data-member="column"] .member-value')).toHaveText("result");

  // The record prints the file's own notation, and `value_sample` is behind a
  // fold because eighty-three numbers open would be the whole drawer.
  await record.locator('[data-member="value_sample"] [data-testid="unfold"]').click();
  await expect(record.locator('[data-member="value_sample"] .member-value')).toHaveText(
    String(DIGITS),
  );
  // Bare, as the document writes it. A quoted `"9007199254740993"` here would
  // say the file carries a string where it carries an i64 — the page
  // inventing a dtype, which is the same wrong answer as rounding the digits.
  expect(
    await record.locator('[data-member="value_sample"] .member-value').innerText(),
  ).not.toContain('"');

  // And the proof, where a reader follows the number rather than the record.
  await expect(page.getByTestId("proof")).toContainText(WRITTEN);
});

test("the worked example substitutes the exact operand and closes on the exact result", async ({
  page,
}) => {
  await page.goto(PAGE);
  const proof = page.getByTestId("proof");
  await expect(proof).toBeVisible();
  // The input it read is 2⁵³ exactly, which a double holds and this page still
  // writes whole; the answer is one past it, which a double does not.
  await expect(proof).toContainText("9,007,199,254,740,992");
  await expect(proof).toContainText(WRITTEN);
  // No disagreement chip: the trace's answer and the sampled value are the
  // same number, and they are only the same number when both are exact.
  await expect(page.getByTestId("disagreement")).toHaveCount(0);
});
