// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The worked example, checked against the file it is assembled from.
 *
 * Every expectation below is read out of the fixture in this file rather than
 * typed in from a screen, for the reason the grid's and the cone's cases give.
 * What is held to here is the one property that makes the panel worth showing:
 * each line is a quotation. The lowered line is the producer's own step-2
 * string, character for character; each operand line is an element of that
 * operand's `value_sample`; the result is the element of this column's; the
 * lookup excerpt is a slice of the payload's own rows. None of it is computed
 * here and none of it is computed there.
 *
 * Three facts about the level-4 export were measured before these cases were
 * written, and the plan's own words corrected against them. `mort_rate@1` reads
 * no assumption — it is a conditional over `mort_scalar@1` and
 * `base_mort_rate@1` — so the lookup case is written over `base_mort_rate@1`,
 * which does read one. The trace's `result` is the value at period 0 and not at
 * the cursor, because `enrichment.periods` is null and every trace's own
 * comment says "``result`` is period 0 of 83". And of the twenty formulas that
 * open with `when(`, eighteen classify `conditional`: two of them read an
 * assumption as well, and the assumption is tested first.
 */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { formatFormula, formatValue, isIntegerDtype } from "../src/reader/format";
import { buildIndex } from "../src/reader/index";
import { parseExactly } from "../src/reader/exact";
import { classify, proofOf, tracePeriod } from "../src/reader/proof";
import type { Artifact, ArtifactNode } from "../src/reader/types";

/** One fixture, indexed. */
function fixture(name: string) {
  const artifact = JSON.parse(
    readFileSync(new URL(`../fixtures/${name}.json`, import.meta.url), "utf8"),
  ) as Artifact;
  return buildIndex(artifact);
}

const level4 = fixture("level4");
const branches = fixture("level4-branches");
const rollforward = fixture("rollforward");
const holes = fixture("holes");
const scenarios = fixture("scenarios");

/** The cursor every case below stands at. */
const CURSOR = 12;

/** One node of a fixture, by the id the file gives it. */
function node(index: ReturnType<typeof buildIndex>, id: string): ArtifactNode {
  const found = index.nodes.get(id);
  if (found === undefined) throw new Error(`the fixture carries no node ${id}`);
  return found;
}

/** A node's sampled timeline, refused rather than defaulted where there is none. */
function timeline(index: ReturnType<typeof buildIndex>, id: string): unknown[] {
  const sample = index.timeline(id);
  if (sample === null) throw new Error(`${id} carries no sampled timeline`);
  return sample;
}

/** One value written the way the grid writes it: the page's one convention. */
function written(index: ReturnType<typeof buildIndex>, id: string, value: unknown): string {
  return formatValue(value, { integer: isIntegerDtype(node(index, id).dtype) });
}

/** The first line of one kind, refused rather than defaulted where there is none. */
function lineOfKind(
  lines: { kind: string; text: string; flagged?: boolean }[],
  kind: string,
): { text: string; flagged?: boolean } {
  const found = lines.find((line) => line.kind === kind);
  if (found === undefined) throw new Error(`no ${kind} line in the proof`);
  return found;
}

describe("classify", () => {
  it("reads the file's own members, in a fixed order", () => {
    expect(classify(node(level4, "survival_prob@1"))).toBe("accumulation");
    expect(classify(node(level4, "base_mort_rate@1"))).toBe("lookup");
    expect(classify(node(level4, "pols_maturity@1"))).toBe("conditional");
    expect(classify(node(level4, "net_cf@1"))).toBe("arithmetic");
    expect(classify(node(level4, "point_id"))).toBe("leaf");
    expect(classify(node(rollforward, "rollforward:ff70eb792aee"))).toBe("rollforward");
    expect(classify(node(holes, "reserve_override"))).toBe("hole");
  });

  it("calls mort_rate a conditional, because it reads no assumption", () => {
    const mortRate = node(level4, "mort_rate@1");
    expect(mortRate.reads_assumptions).toEqual([]);
    expect(mortRate.reads).toContain("base_mort_rate@1");
    expect(mortRate.formula?.startsWith("when(")).toBe(true);
    expect(classify(mortRate)).toBe("conditional");
  });

  it("puts the assumption before the branch where a node has both", () => {
    // Twenty of level 4's formulas open with `when(`. Two of them are a `when`
    // around a table lookup, and the lookup is what the reader needs to see.
    const opensWithWhen = level4.artifact.nodes.filter((n) =>
      (n.formula ?? "").trimStart().startsWith("when("),
    );
    expect(opensWithWhen).toHaveLength(20);

    const conditional = level4.artifact.nodes.filter((n) => classify(n) === "conditional");
    expect(conditional).toHaveLength(18);
    expect(conditional.map((n) => n.id)).toContain("pols_maturity@1");

    for (const id of ["base_lapse_rate@1", "surr_charge_rate@1"]) {
      expect(classify(node(level4, id))).toBe("lookup");
    }
  });
});

describe("proofOf, arithmetic", () => {
  it("quotes the trace's step 2 verbatim, under its own kind", () => {
    const proof = proofOf(level4, "net_cf@1", CURSOR);
    const stepTwo = level4.traceOf("net_cf@1")?.find((s) => s.step === 2);
    expect(stepTwo?.expr).toBeTypeOf("string");

    // `lowered` and not `substitution`: the lowered expression the producer ran
    // is evidence, the operand lines are the worked example, and the two used to
    // share a label. Still character for character — folding it away in the
    // panel changes where a reader meets it, never what it says.
    expect(proof.lines.some((line) => line.kind === "lowered" && line.text === stepTwo?.expr)).toBe(
      true,
    );
    expect(proof.lines.some((line) => line.kind === "substitution")).toBe(true);
  });

  it("opens with the formula the producer recorded", () => {
    const proof = proofOf(level4, "net_cf@1", CURSOR);
    expect(lineOfKind(proof.lines, "formula").text).toBe(
      formatFormula(node(level4, "net_cf@1").formula),
    );
  });

  it("gives every operand its value at the period, from that operand's own timeline", () => {
    const proof = proofOf(level4, "net_cf@1", CURSOR);
    for (const source of node(level4, "net_cf@1").reads) {
      const line = proof.lines.find((l) => l.operand === source);
      expect(line, source).toBeDefined();
      expect(line?.text).toBe(
        `${String(node(level4, source).column)}[${CURSOR}] = ` +
          `${written(level4, source, timeline(level4, source)[CURSOR])}`,
      );
    }
  });

  it("writes the result as the element of value_sample the cursor sits on", () => {
    const proof = proofOf(level4, "net_cf@1", CURSOR);
    expect(lineOfKind(proof.lines, "result").text).toBe(
      written(level4, "net_cf@1", timeline(level4, "net_cf@1")[CURSOR]),
    );
  });

  it("carries the file's offset on the line the offset moved", () => {
    const proof = proofOf(level4, "shifted_growth@1", CURSOR);
    const line = proof.lines.find((l) => l.operand === "combined_growth_factor@1");
    expect(line?.offset).toBe(-1);
    expect(line?.text).toBe(
      `combined_growth_factor[${CURSOR - 1}] = ` +
        `${written(level4, "combined_growth_factor@1", timeline(level4, "combined_growth_factor@1")[CURSOR - 1])}`,
    );
  });
});

describe("proofOf, the trace against the sample", () => {
  it("stands the trace at period 0 where the export named no periods", () => {
    expect(level4.policy?.periods).toBeNull();
    expect(tracePeriod(level4)).toBe(0);
    const answer = level4.traceOf("net_cf@1")?.find((s) => s.step === 3);
    expect(answer?.result).toBe(timeline(level4, "net_cf@1")[0]);
  });

  it("flags nothing on a file whose traces and samples agree", () => {
    for (const id of ["net_cf@1", "survival_prob@1", "base_mort_rate@1", "pols_maturity@1"]) {
      expect(proofOf(level4, id, CURSOR).disagreement, id).toBe(false);
    }
  });

  it("flags a file whose trace disagrees with its own sample", () => {
    const artifact = JSON.parse(
      readFileSync(new URL("../fixtures/level4.json", import.meta.url), "utf8"),
    ) as Artifact;
    const target = artifact.nodes.find((n) => n.id === "net_cf@1");
    if (target === undefined) throw new Error("the fixture carries no net_cf@1");
    // The sample at the period the trace stands at, moved. The cursor's period
    // is left alone on purpose: the flag is about the trace's own claim.
    (target.value_sample as number[])[0] = 1;
    const mutated = buildIndex(artifact);
    expect(proofOf(mutated, "net_cf@1", CURSOR).disagreement).toBe(true);
  });
});

describe("proofOf, conditional", () => {
  it("says the export did not carry the dead branch, when it did not", () => {
    const proof = proofOf(level4, "pols_maturity@1", CURSOR);
    expect(level4.branchesOf("pols_maturity@1")).toBeUndefined();
    expect(proof.lines.some((line) => line.kind === "dead")).toBe(false);
    expect(lineOfKind(proof.lines, "note").text).toContain("--branches");
  });

  it("names the branch that fired and prices the one that did not", () => {
    const proof = proofOf(branches, "pols_maturity@1", CURSOR);
    const carried = branches.branchesOf("pols_maturity@1");
    if (carried === undefined) throw new Error("the branches fixture carries no branches");
    const fired = (carried.fired as string[])[CURSOR];
    const dead = fired === "then" ? "otherwise" : "then";
    expect(lineOfKind(proof.lines, "fired").text).toBe(
      `${fired} = ` +
        written(branches, "pols_maturity@1", (carried[fired as "then"] as unknown[])[CURSOR]),
    );
    expect(lineOfKind(proof.lines, "dead").text).toBe(
      `${dead} = ` +
        written(branches, "pols_maturity@1", (carried[dead as "then"] as unknown[])[CURSOR]),
    );
  });
});

describe("proofOf, lookup", () => {
  it("quotes the hit and two rows either side, in the payload's own order", () => {
    const proof = proofOf(level4, "base_mort_rate@1", CURSOR);
    const entry = level4.tables.get("mortality_select") as {
      fingerprint: string;
      payload: { columns: { name: string }[]; rows: unknown[][] };
    };
    expect(proof.table?.name).toBe("mortality_select");
    expect(proof.table?.fingerprint).toBe(entry.fingerprint);
    expect(proof.table?.header).toEqual(entry.payload.columns.map((c) => c.name));
    expect(proof.table?.rows).toHaveLength(5);
    expect(proof.table?.hitRow).toBe(2);

    // The hit is the row whose keys are the values the operands hold here.
    const hit = proof.table?.rows[2];
    expect(hit).toEqual([
      level4.nodes.get("mort_table_id@1")?.value_sample,
      timeline(level4, "age@1")[CURSOR],
      timeline(level4, "duration_capped@1")[CURSOR],
      timeline(level4, "base_mort_rate@1")[CURSOR],
    ]);

    // And the five are a contiguous slice of the payload, not a gathering.
    const at = entry.payload.rows.indexOf(hit as unknown[]);
    expect(entry.payload.rows.slice(at - 2, at + 3)).toEqual(proof.table?.rows);
  });

  it("gives the key operands their values at the period", () => {
    const proof = proofOf(level4, "base_mort_rate@1", CURSOR);
    const ageLine = proof.lines.find((line) => line.operand === "age@1");
    expect(ageLine?.text).toBe(
      `age[${CURSOR}] = ${written(level4, "age@1", timeline(level4, "age@1")[CURSOR])}`,
    );
    // A scalar key wears no subscript: it is one value for the policy, and a
    // `[12]` beside it would say the file carries a timeline it does not.
    const idLine = proof.lines.find((line) => line.operand === "mort_table_id@1");
    expect(idLine?.text).toBe(
      `mort_table_id = ${written(level4, "mort_table_id@1", node(level4, "mort_table_id@1").value_sample)}`,
    );
  });

  it("quotes no row where the file carries none, and says which kind of entry it is", () => {
    // `projection_date@1` names a schedule in `reads_assumptions`, so the
    // classifying order makes it a lookup. A schedule's payload carries the
    // grid's settings and no rows, so the panel shows the operands and says so.
    const projection = node(level4, "projection_date@1");
    expect(projection.reads_assumptions).toEqual(["schedule:fede58ef"]);
    expect(classify(projection)).toBe("lookup");
    const proof = proofOf(level4, "projection_date@1", CURSOR);
    expect(proof.table).toBeUndefined();
    expect(lineOfKind(proof.lines, "note").text).toContain("schedule");
    expect(lineOfKind(proof.lines, "result").text).toBe(
      written(level4, "projection_date@1", timeline(level4, "projection_date@1")[CURSOR]),
    );
  });

  it("quotes no row where the operands do not name one", () => {
    // `disc_rate@1` passes two of its three keys as literals — `currency="USD"`
    // and a scenario held in a Python variable — and the export records neither
    // as a read. There is no row the file lets the page name.
    const proof = proofOf(level4, "disc_rate@1", CURSOR);
    expect(proof.table).toBeUndefined();
    expect(lineOfKind(proof.lines, "note").text).toContain("no single row");
  });
});

describe("proofOf, accumulation", () => {
  it("prints the convention from settings, in words", () => {
    expect(node(level4, "survival_prob@1").settings).toEqual({ start_at: 1, from_survival: false });
    expect(lineOfKind(proofOf(level4, "survival_prob@1", CURSOR).lines, "convention").text).toBe(
      "beginning of period",
    );
  });

  it("writes one step of the recurrence with the numbers the two timelines hold", () => {
    const proof = proofOf(level4, "survival_prob@1", CURSOR);
    const self = timeline(level4, "survival_prob@1");
    const rate = timeline(level4, "combined_decrement@1");
    expect(
      proof.lines.some(
        (line) =>
          line.kind === "substitution" &&
          line.text ===
            `survival_prob[${CURSOR}] = survival_prob[${CURSOR - 1}] × ` +
              `(1 − combined_decrement[${CURSOR - 1}]) = ` +
              `${written(level4, "survival_prob@1", self[CURSOR - 1])} × ` +
              `(1 − ${written(level4, "combined_decrement@1", rate[CURSOR - 1])})`,
      ),
    ).toBe(true);
  });

  it("says the series opens where there is no earlier period to read", () => {
    const proof = proofOf(level4, "survival_prob@1", 0);
    expect(lineOfKind(proof.lines, "note").text).toContain("opens the series");
  });
});

describe("proofOf, a compiled rollforward's waterfall", () => {
  const COMPILATION = "rollforward:ff70eb792aee";
  /** Halfway through a twelve-month fund, which is where the read stands. */
  const MIDWAY = 6;

  it("names the states, then walks from opening to closing", () => {
    const proof = proofOf(rollforward, COMPILATION, MIDWAY);
    expect(proof.idiom).toBe("rollforward");
    expect(proof.lines[0]?.text).toBe("the states it runs: av");
    expect(proof.lines[1]?.text).toBe(`av@eop, period ${MIDWAY}`);
    const balance = rollforward.sampleOf("state:av@eop") as number[];
    const moved = rollforward.movementsOf(COMPILATION);
    const at = (key: string) => formatValue((moved.get(key) as number[])[MIDWAY]);
    const steps = proof.lines.filter((line) => line.kind === "substitution");
    // One line per step of the chain, in chain order, each carrying the
    // signed amount the file holds for it — and the floor's row is zero in
    // every period, because on this model it never bites.
    expect(steps.map((line) => line.text)).toEqual([
      `opening   ${formatValue(balance[MIDWAY - 1])}`,
      `fund_return   ${at("fund_return")}`,
      `me_charge   ${at("me_charge")}`,
      `floor@3   ${at("floor@3")}`,
    ]);
    expect((moved.get("floor@3") as number[])[MIDWAY]).toBe(0);
    expect(lineOfKind(proof.lines, "result").text).toBe(
      `closing   ${formatValue(balance[MIDWAY])}`,
    );
  });

  it("states the one arithmetic it may, and does not flag it when it closes", () => {
    const check = lineOfKind(proofOf(rollforward, COMPILATION, MIDWAY).lines, "check");
    expect(check.flagged).toBeUndefined();
    expect(check.text).toContain("closing = opening + Σ movements");
  });

  /** A wide integer: an i64 a double rounds to the one below it. */
  const WIDE = "9007199254740993";

  /**
   * The fixture as the producer wrote it, with one movement's amount at the
   * read an integer a double cannot carry.
   *
   * Written as text and read back through the page's own parser, because that
   * is the only way a document carries one: `JSON.stringify` of a number this
   * wide writes the double out again, which is the rounding under test. So the
   * amount goes in as a placeholder string and the digits take its place
   * before the parse.
   */
  function withAWideMovement(): ReturnType<typeof buildIndex> {
    const placeholder = "__the wide movement__";
    const doc = JSON.parse(
      readFileSync(new URL("../fixtures/rollforward.json", import.meta.url), "utf8"),
    ) as Artifact;
    const moved = doc.nodes.find((entry) => entry.id === COMPILATION)?.movements?.["fund_return"];
    if (!Array.isArray(moved)) throw new Error("the fixture carries no fund_return movement");
    moved[MIDWAY] = placeholder;
    const text = JSON.stringify(doc).replace(`"${placeholder}"`, WIDE);
    return buildIndex(parseExactly(text) as Artifact);
  }

  it("says why there is no check line where a movement is an integer it keeps as digits", () => {
    // This was the weakest point: the sum is withheld, rightly —
    // adding the double beside the digits would print a figure the file does
    // not hold — but it was withheld in silence, on the one arithmetic a
    // rollforward is audited by. The movement is still drawn, whole; what the
    // sentence accounts for is the line that is missing under it.
    const index = withAWideMovement();
    const proof = proofOf(index, COMPILATION, MIDWAY);
    const amount = (index.movementsOf(COMPILATION).get("fund_return") as unknown[])[MIDWAY];
    expect(proof.lines.map((line) => line.text)).toContain(
      `fund_return   ${formatValue(amount)}`,
    );
    expect(proof.lines.some((line) => line.kind === "check")).toBe(false);
    expect(proof.lines[proof.lines.length - 1]?.text).toBe(
      "no check line: fund_return is an integer the page keeps as digits and does not add, " +
        "so closing = opening + Σ movements is not stated for this period.",
    );
  });

  it("names the opening at period 0 rather than printing a number it has not got", () => {
    const proof = proofOf(rollforward, COMPILATION, 0);
    const steps = proof.lines.filter((line) => line.kind === "substitution");
    expect(steps[0]?.text).toContain("the state's own initial value");
    // And no check line: a term of that identity is not on the file at period
    // 0, and the page states it only where every term in it was quoted.
    expect(proof.lines.some((line) => line.kind === "check")).toBe(false);
  });

  it("says a hole is unaccounted for, with the reason the envelope gives", () => {
    const proof = proofOf(holes, "reserve_override", CURSOR);
    expect(proof.idiom).toBe("hole");
    expect(proof.lines).toHaveLength(1);
    expect(proof.lines[0]?.text).toContain("unaccounted for");
    expect(proof.lines[0]?.text).toContain("unrecorded");
  });

  it("gives an input its value and the provenance the file states", () => {
    const proof = proofOf(level4, "policy_term", CURSOR);
    expect(proof.idiom).toBe("leaf");
    expect(lineOfKind(proof.lines, "result").text).toBe(
      written(level4, "policy_term", node(level4, "policy_term").value_sample),
    );
    expect(lineOfKind(proof.lines, "note").text).toContain("model_points");
  });

  it("says where a column handed to the model was handed over", () => {
    // `injected` is the one arrival that knows a place, and the sentence is
    // the place rather than the word: a scenario axis is a column the
    // framework put on the frame at a line of the modeller's own script, and
    // "provenance injected" would leave a reader no better off than before.
    const axis = node(scenarios, "scenario_id@1");
    expect(axis.provenance).toBe("injected");
    const proof = proofOf(scenarios, "scenario_id@1", 0);
    expect(proof.idiom).toBe("leaf");
    expect(lineOfKind(proof.lines, "note").text).toBe(
      `a whole column handed to the model at ${String(axis.source_location)}.`,
    );
  });
});

describe("proofOf, a column that read more than one assumption base", () => {
  it("names every base with its own fingerprint, and picks none", () => {
    // Level 5 dispatches three rate curves on `scenario_id`, so naming
    // `reads_assumptions[0]` would be right one row in three. Which one this
    // row took is not in the file, and the panel says so rather than choosing.
    const discounted = node(scenarios, "disc_factors@1");
    expect(discounted.reads_assumptions.length).toBeGreaterThan(1);

    const proof = proofOf(scenarios, "disc_factors@1", 0);
    const note = lineOfKind(proof.lines, "note").text;
    for (const name of discounted.reads_assumptions) {
      const entry = scenarios.tables.get(name) as { fingerprint?: string } | undefined;
      expect(note).toContain(name);
      expect(note).toContain(String(entry?.fingerprint));
    }
    expect(note).toContain("chooses between them row by row");
    expect(proof.table).toBeUndefined();
  });
});
