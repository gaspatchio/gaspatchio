// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The position a link carries, and everything it refuses to carry.
 *
 * Two properties are worth more here than any single case. **A link round-trips
 * against the file it was written from** — write where the reader is standing,
 * follow it back, land in the same place — and that is asserted over every
 * entry of a real axis rather than on one. And **a link that has gone stale
 * still opens the page**: every way a document can have moved on under a link
 * lands on the page's own opening position with one line saying what was asked
 * for, because a page that would not open is worse to its reader than a page
 * that opens and says what has moved.
 *
 * The fixtures are the producer's own exports, and the awkward one is
 * deliberate: `policy-axis` carries a policy called `3:40` and one called
 * `all`, and `portfolio` carries two entries the file gives no id at all.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { buildIndex } from "../src/reader/index";
import { policyName } from "../src/reader/policies";
import { fragmentFor, landingIn, locate, policyAt, wantedIn } from "../src/reader/position";
import type { Artifact } from "../src/reader/types";

function artifact(name: string): Artifact {
  return JSON.parse(readFileSync(resolve(`fixtures/${name}.json`), "utf8")) as Artifact;
}

function fixture(name: string, at = 0) {
  return buildIndex(artifact(name), at);
}

const level4 = fixture("level4");
const axis = artifact("policy-axis");
const portfolio = artifact("portfolio");
const scenarios = artifact("scenarios");

describe("reading a fragment", () => {
  it("reads the four keys and nothing else", () => {
    expect(wantedIn("#policy=1&column=net_cf&period=12")).toEqual({
      policy: { name: "1", filter: null },
      column: "net_cf",
      period: 12,
    });
  });

  it("reads the cut beside the policy, as one entry rather than two keys", () => {
    // An entry's identity is the name *and* the cut, and a caller handed the
    // name alone is exactly the defect this replaced: three scenarios, one link.
    expect(wantedIn('#policy=1&filter=scenario_id %3D%3D "UP"&period=0').policy).toEqual({
      name: "1",
      filter: 'scenario_id == "UP"',
    });
  });

  it("asks for nothing where there is no fragment", () => {
    expect(wantedIn("")).toEqual({ policy: null, column: null, period: null });
    expect(wantedIn("#")).toEqual({ policy: null, column: null, period: null });
  });

  it("decodes a policy id that needed encoding", () => {
    // `3:40` is a real id in the corpus and a colon is percent-encoded on the
    // way out, so the way back has to be the matching decode rather than a
    // split on punctuation.
    expect(wantedIn("#policy=3%3A40").policy?.name).toBe("3:40");
  });

  it("takes a period that is a whole number and nothing that is not", () => {
    expect(wantedIn("#period=0").period).toBe(0);
    expect(wantedIn("#period=banana").period).toBeNull();
    expect(wantedIn("#period=1.5").period).toBeNull();
  });

  it("ignores a fragment that is not this grammar", () => {
    // These links are the page's own output, so a fragment that does not parse
    // is a typo in one rather than a statement about the file — there is
    // nothing to say about it in the strip.
    const wanted = wantedIn("#section-4");
    expect(wanted).toEqual({ policy: null, column: null, period: null });
    expect(landingIn(level4, wanted).note).toBeNull();
  });
});

describe("naming an entry of the axis", () => {
  it("names a policy by its id and a fold by its fold", () => {
    expect(portfolio.policies.map(policyName)).toEqual(["fold · sum", "fold · period_sum", "1"]);
  });

  it("finds each entry of a real axis by that name", () => {
    for (const [at, entry] of axis.policies.entries()) {
      expect(policyAt(axis.policies, { name: policyName(entry) ?? "", filter: entry.filter })).toBe(
        at,
      );
    }
  });

  it("asks for no entry where the link named none", () => {
    expect(policyAt(axis.policies, null)).toBeNull();
  });

  it("finds each scenario entry by its own cut, and no other", () => {
    // The file the external review used: eight policies against BASE, UP and
    // DOWN, so three entries are called `1` and three folds are called
    // `fold · sum`. Every one of them is reachable, and only itself.
    for (const [at, entry] of scenarios.policies.entries()) {
      const wanted = { name: policyName(entry) ?? "", filter: entry.filter };
      expect(locate(scenarios.policies, wanted)).toBe(at);
    }
  });

  it("refuses a name three entries answer to rather than taking the first", () => {
    // The defect's own shape: a link written without the cut, on a cross-joined file.
    expect(locate(scenarios.policies, { name: "1", filter: null })).toBe("ambiguous");
    expect(locate(scenarios.policies, { name: "fold · sum", filter: null })).toBe("ambiguous");
    expect(policyAt(scenarios.policies, { name: "1", filter: null })).toBeNull();
  });

  it("says a name no entry answers to is absent, not ambiguous", () => {
    expect(locate(scenarios.policies, { name: "nobody", filter: null })).toBe("absent");
  });
});

describe("a link written and then followed", () => {
  it("round-trips every entry of a multi-policy axis", () => {
    for (let at = 0; at < axis.policies.length; at += 1) {
      const index = buildIndex(axis, at);
      const nodeId = index.perPeriodColumns[3] ?? "";
      const fragment = fragmentFor(index, nodeId, 5);
      const landing = landingIn(index, wantedIn(fragment));
      expect(landing).toEqual({ at, nodeId, period: 5, note: null });
    }
  });

  it("round-trips a fold entry, which has no id to be named by", () => {
    // `period_sum`: the book folded a period at a time, so it has a timeline.
    const index = buildIndex(portfolio, 1);
    const nodeId = index.perPeriodColumns[0] ?? "";
    const fragment = fragmentFor(index, nodeId, 2);
    expect(fragment).toContain("policy=fold+%C2%B7+period_sum");
    expect(landingIn(index, wantedIn(fragment))).toEqual({ at: 1, nodeId, period: 2, note: null });
  });

  it("round-trips a fold that folded the timeline away", () => {
    // `sum` over the whole book leaves one number per column and no periods at
    // all, so the link carries none and the round trip says nothing about it.
    const index = buildIndex(portfolio, 0);
    expect(index.periods).toBe(0);
    const nodeId = index.perPeriodColumns[0] ?? "";
    const fragment = fragmentFor(index, nodeId, 0);
    expect(fragment).not.toContain("period");
    expect(landingIn(index, wantedIn(fragment))).toEqual({ at: 0, nodeId, period: 0, note: null });
  });

  it("round-trips every entry of a cross-joined scenario axis", () => {
    // Six entries, three of them called `1` and three called `fold · sum`.
    // Each link lands on the entry it was written from and on no other, which
    // is what the cut in the fragment buys.
    for (let at = 0; at < scenarios.policies.length; at += 1) {
      const index = buildIndex(scenarios, at);
      const nodeId = index.finalColumns[0] ?? "";
      const fragment = fragmentFor(index, nodeId, 0);
      expect(fragment).toContain("filter=");
      expect(landingIn(index, wantedIn(fragment)).at).toBe(at);
    }
  });

  it("carries no cut on an entry the file gave none", () => {
    // Every ordinary export. The key is omitted rather than written empty,
    // because an empty cut and no cut are two different claims.
    const index = buildIndex(axis, 1);
    expect(index.policy?.filter).toBeNull();
    expect(fragmentFor(index, index.finalColumns[0] ?? "", 0)).not.toContain("filter");
  });

  it("names no policy on a single-policy file", () => {
    // There is nothing to choose between, and the file opens on it anyway.
    const fragment = fragmentFor(level4, "net_cf@1", 12);
    expect(fragment).toBe("#column=net_cf&period=12");
  });

  it("carries the column by its name and not by the node's id", () => {
    // The name is what an actuary typed into the model; the id is that name
    // with the producer's version on it.
    expect(fragmentFor(level4, "net_cf@1", 0)).toContain("column=net_cf");
    expect(fragmentFor(level4, "net_cf@1", 0)).not.toContain("@1");
  });

  it("carries no period where the file samples no timeline", () => {
    // Otherwise the round trip comes back as a period past a timeline of none,
    // and the page says one line about a link it wrote itself.
    const none = fixture("no-values");
    expect(none.periods).toBe(0);
    expect(fragmentFor(none, none.finalColumns[0] ?? null, 0)).not.toContain("period");
  });
});

describe("a link that has gone stale", () => {
  it("opens the page on a column this file does not carry, and says so", () => {
    const landing = landingIn(level4, wantedIn("#column=shortfall&period=4"));
    expect(landing.nodeId).toBeNull();
    expect(landing.period).toBe(4);
    expect(landing.note).toBe(
      "This link asked for column shortfall, which this file does not carry. " +
        "The page opened where it opens.",
    );
  });

  it("opens on the first entry where the policy is not on the axis", () => {
    const index = buildIndex(axis, 0);
    const landing = landingIn(index, wantedIn("#policy=POL-999999"));
    expect(landing.at).toBe(0);
    expect(landing.note).toContain("policy POL-999999, which is not on this file's axis");
  });

  it("opens where the page opens on a policy this file carries under three cuts", () => {
    // Not on the first of the three. A link that named `1` and not the cut did
    // not ask for BASE, and answering with BASE would put one scenario's
    // numbers under a name three of them answer to.
    const index = buildIndex(scenarios, 0);
    const landing = landingIn(index, wantedIn("#policy=1&column=pv_net_cf&period=0"));
    expect(landing.at).toBe(0);
    expect(landing.note).toContain(
      "policy 1, which this file carries under more than one filter",
    );
  });

  it("opens on the first period where the period is past the timeline", () => {
    const landing = landingIn(level4, wantedIn("#period=400"));
    expect(landing.period).toBe(0);
    expect(landing.note).toBe(
      `This link asked for period 400, past the ${String(level4.periods)} this file sampled. ` +
        "The page opened where it opens.",
    );
  });

  it("says a file that samples nothing samples nothing", () => {
    const none = fixture("no-values");
    expect(landingIn(none, wantedIn("#period=3")).note).toContain(
      "this file samples no timeline at all",
    );
  });

  it("says all three in one line when all three have moved", () => {
    const index = buildIndex(axis, 0);
    const landing = landingIn(index, wantedIn("#policy=nobody&column=nothing&period=9999"));
    expect(landing).toMatchObject({ at: 0, nodeId: null, period: 0 });
    expect(landing.note).toBe(
      "This link asked for policy nobody, which is not on this file's axis, " +
        "column nothing, which this file does not carry and " +
        `period 9999, past the ${String(index.periods)} this file sampled. ` +
        "The page opened where it opens.",
    );
  });

  it("says nothing at all where the link is good", () => {
    expect(landingIn(level4, wantedIn("#column=net_cf&period=12")).note).toBeNull();
  });
});
