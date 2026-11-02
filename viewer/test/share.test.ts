// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The one materiality question this artifact can answer, and every shape where
 * it must refuse to.
 *
 * A share printed against a formula that is not a signed sum would be a false
 * decomposition on a page whose whole claim is that its numbers are quotations,
 * so the refusals matter more here than the answer does. Each of these shapes
 * is taken from the corpus rather than invented.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { buildIndex } from "../src/reader/index";
import { sharesOf } from "../src/reader/share";
import type { Artifact } from "../src/reader/types";

function fixture(name: string) {
  return buildIndex(
    JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact,
  );
}

const level4 = fixture("level4");

describe("the share of the gross", () => {
  it("decomposes a signed sum of columns", () => {
    // pv_net_cf is its six present values added and subtracted, which is the
    // shape every headline result on these models has.
    const shares = sharesOf(level4, "pv_net_cf@1", 0);
    expect(shares).not.toBeNull();
    expect(shares?.length).toBe(6);

    // Every term is one of the operands the file says it reads.
    const reads = new Set(level4.readsOf.get("pv_net_cf@1") ?? []);
    for (const term of shares ?? []) expect(reads.has(term.id)).toBe(true);

    // The shares are of the gross, so they add to one.
    const total = (shares ?? []).reduce((sum, term) => sum + term.share, 0);
    expect(total).toBeCloseTo(1, 10);

    // Largest first, which is the order a reader wants and the order the panel
    // prints.
    const ordered = [...(shares ?? [])].sort((a, b) => b.share - a.share);
    expect(shares).toEqual(ordered);
  });

  it("is each term's own value over the sum of the absolute values", () => {
    const shares = sharesOf(level4, "pv_net_cf@1", 0) ?? [];
    const gross = shares.reduce((sum, term) => sum + Math.abs(term.value), 0);
    for (const term of shares) {
      expect(term.share).toBeCloseTo(Math.abs(term.value) / gross, 12);
      // The value is the operand's own, at that period, not a recomputation.
      const sample = level4.nodes.get(term.id)?.value_sample;
      expect(term.value).toBe(Array.isArray(sample) ? sample[0] : sample);
    }
  });

  it.each([
    // A product: `af.av_pp * af.pols_maturity` leaves a `*` behind.
    ["claims_maturity@1"],
    // A power over a bracketed expression, with literals in it.
    ["mort_rate_mth@1"],
    // A conditional.
    ["pols_maturity@1"],
  ])("refuses %s, because its formula is not a signed sum", (id) => {
    expect(sharesOf(level4, id, 0)).toBeNull();
  });

  it("refuses a column that arrived, which has no formula at all", () => {
    expect(sharesOf(level4, "sum_assured@1", 0)).toBeNull();
  });

  it("refuses a sum of one, which is not a decomposition of anything", () => {
    // Every single-operand formula in the corpus, whatever else it is.
    for (const id of level4.order) {
      if ((level4.readsOf.get(id) ?? []).length === 1) {
        expect(sharesOf(level4, id, 0)).toBeNull();
      }
    }
  });
});
