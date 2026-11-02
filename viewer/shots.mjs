// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * A photograph of every page the dev server is holding.
 *
 * The other half of the loop `dev-server.mjs` opens. That server makes a change
 * visible in a browser in about a second; this takes the picture, so a change
 * can be checked before anyone is asked to look at it. It is deliberately not
 * `e2e/reads/walk.ts`: those four screenshots are a record, taken through a
 * scripted read at a fixed selection and compared byte for byte. These are
 * working pictures of whatever the pages currently show, and nothing compares
 * them to anything.
 *
 * Usage, from `viewer/`, with the dev server already running:
 *
 *     node shots.mjs --out /tmp/shots
 *     node shots.mjs --out /tmp/shots --at http://100.x.y.z:8817
 *     node shots.mjs --out /tmp/shots --only level4,rollforward
 *     node shots.mjs --out /tmp/shots --width 1680 --height 1050
 *
 * A page that does not reach its grid inside the timeout is photographed
 * anyway and named in the output. A blank picture is a finding, not a reason to
 * stop taking the rest.
 */

import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { chromium } from "@playwright/test";

/** `--name value` from the command line, or the fallback. */
function option(name, fallback) {
  const at = process.argv.indexOf(`--${name}`);
  return at < 0 ? fallback : (process.argv[at + 1] ?? fallback);
}

const at = option("at", "http://127.0.0.1:8817");
const out = option("out", "shots");
const width = Number(option("width", "1440"));
const height = Number(option("height", "900"));
const only = option("only", undefined);

/** The pages the server is serving, read off its index rather than guessed. */
async function pages() {
  const response = await fetch(`${at}/`);
  const html = await response.text();
  const names = [...html.matchAll(/href="\/([^"]+)"/g)].map((match) => match[1]);
  return only === undefined ? names : names.filter((name) => only.split(",").includes(name));
}

mkdirSync(out, { recursive: true });
const names = await pages();
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width, height } });

for (const name of names) {
  const started = Date.now();
  let reached = true;
  await page.goto(`${at}/${name}`, { waitUntil: "load" });
  try {
    await page.waitForSelector('[data-testid="grid"], [data-testid="rail-grid"]', {
      timeout: 20_000,
    });
    // The cone lays out on an animation frame after the grid is up, so a
    // picture taken the moment the grid exists is a picture of half a page.
    await page.waitForTimeout(1_200);
  } catch {
    reached = false;
  }
  const file = join(out, `${name}.png`);
  await page.screenshot({ path: file });
  console.log(
    `${name.padEnd(14)} ${String(Date.now() - started).padStart(6)} ms  ${file}` +
      (reached ? "" : "   NO GRID — photographed anyway"),
  );
}

await browser.close();
