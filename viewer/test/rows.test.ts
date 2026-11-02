// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The grid draws its rows in whole blocks, and never fewer than it was asked for.
 *
 * `views/rows.ts` widens the virtualizer's window so that a scroll of a row or
 * two changes nothing in the table. What it must not do is draw less: a row the
 * virtualizer asked for and the grid left out would be a gap on the screen. So
 * the check is the virtualizer's own window, from its own default extractor,
 * held against what the grid draws for every range of every timeline length
 * below — the level-4 export's eighty-three periods among them.
 */

import { defaultRangeExtractor, Virtualizer } from "@tanstack/react-virtual";
import type { Range } from "@tanstack/react-virtual";
import { describe, expect, it } from "vitest";

import { followOffset, ROW_BLOCK, rowsInBlocks } from "../src/views/rows";

/** Every range a timeline of `count` rows can put in sight, `visible` rows at a time. */
function ranges(count: number, visible: number): Range[] {
  const out: Range[] = [];
  for (let start = 0; start < count; start += 1) {
    out.push({ startIndex: start, endIndex: Math.min(count - 1, start + visible - 1), overscan: 12, count });
  }
  return out;
}

describe("the grid's rows, in blocks", () => {
  it("draws every row the virtualizer asks for, and whole blocks around them", () => {
    const wrong: string[] = [];
    for (const count of [1, 12, 16, 17, 83, 1200]) {
      for (const visible of [1, 17, 37]) {
        for (const range of ranges(count, visible)) {
          const asked = defaultRangeExtractor(range);
          const drawn = rowsInBlocks(range);
          const at = `${String(range.startIndex)}-${String(range.endIndex)} of ${String(count)}`;
          const first = drawn[0] ?? -1;
          const last = drawn[drawn.length - 1] ?? -1;
          if (drawn.some((row, k) => row !== first + k)) wrong.push(`${at}: not one run`);
          if (asked.some((row) => row < first || row > last)) wrong.push(`${at}: drops a row`);
          if (first % ROW_BLOCK !== 0) wrong.push(`${at}: starts mid-block`);
          if (last !== count - 1 && (last + 1) % ROW_BLOCK !== 0) wrong.push(`${at}: ends mid-block`);
          if (last - first + 1 > asked.length + 2 * (ROW_BLOCK - 1)) wrong.push(`${at}: too wide`);
        }
      }
    }
    expect(wrong).toEqual([]);
  });

  it("leaves the rows alone while a scroll stays inside a block", () => {
    // 17 rows in sight, as the grid shows on the level-4 export. Scrolling from
    // row 20 to row 21 moves the virtualizer's window by a row — rows 8 to 48,
    // then 9 to 49 — and the table's not at all: blocks 0 to 63 both times.
    const before = rowsInBlocks({ startIndex: 20, endIndex: 36, overscan: 12, count: 83 });
    const after = rowsInBlocks({ startIndex: 21, endIndex: 37, overscan: 12, count: 83 });
    expect(after).toEqual(before);
    expect(before).toEqual(Array.from({ length: 64 }, (_, k) => k));
  });

  it("draws nothing for a file with no timeline", () => {
    expect(rowsInBlocks({ startIndex: 0, endIndex: 0, overscan: 12, count: 0 })).toEqual([]);
  });
});

/**
 * The virtualizer's own follow — `scrollToIndex(period, { align: "auto" })` —
 * asked where it would put the grid's scroller.
 *
 * Its rows are the grid's — every one `rowHeight` tall, no padding — and its
 * scroller is a stand-in that says how tall it is and how tall its contents
 * are: the header and the rows, as the grid's table lays them out. The
 * virtualizer reads nothing else to decide.
 */
function virtualizersFollow(
  count: number,
  rowHeight: number,
  size: number,
  head: number,
  scrollbar: number,
): (period: number, offset: number) => number {
  const scroller = { scrollHeight: head + count * rowHeight, clientHeight: size - scrollbar } as unknown as Element;
  const virtualizer = new Virtualizer<Element, Element>({
    count,
    getScrollElement: () => scroller,
    estimateSize: () => rowHeight,
    scrollToFn: () => undefined,
    observeElementRect: () => undefined,
    observeElementOffset: () => undefined,
    scrollPaddingEnd: head + scrollbar,
  });
  virtualizer.scrollElement = scroller;
  virtualizer.scrollRect = { width: 800, height: size };
  virtualizer.getTotalSize();
  return (period, offset) => {
    virtualizer.scrollOffset = offset;
    const answer = virtualizer.getOffsetForIndex(period, "auto");
    if (answer === undefined) throw new Error(`no offset for period ${String(period)}`);
    return answer[0];
  };
}

describe("the grid's follow", () => {
  it("scrolls where the virtualizer's own follow scrolled, and only where it moves", () => {
    const rowHeight = 23;
    const wrong: string[] = [];
    let checked = 0;
    for (const count of [1, 2, 17, 83]) {
      for (const [size, head, scrollbar] of [
        [366, 52, 0],
        [387, 52, 15],
        [120, 67, 0],
        [900, 52, 0],
      ] as const) {
        const max = Math.max(0, head + count * rowHeight - (size - scrollbar));
        const follows = virtualizersFollow(count, rowHeight, size, head, scrollbar);
        for (let offset = 0; offset <= max; offset += 7) {
          for (let period = 0; period < count; period += 1) {
            const asked = follows(period, offset);
            const to = followOffset({ period, count, rowHeight, offset, size, obscured: head + scrollbar });
            // What the scroller would stand at: the browser clamps a write
            // into [0, max], and "bottom" is the furthest it goes.
            const lands = to === null ? offset : to === "bottom" ? max : Math.max(0, Math.min(max, to));
            checked += 1;
            if (lands !== asked) {
              wrong.push(`count ${String(count)} size ${String(size)} offset ${String(offset)} period ${String(period)}: ${String(lands)} vs ${String(asked)}`);
            }
          }
        }
      }
    }
    expect(wrong.slice(0, 10)).toEqual([]);
    expect(checked).toBeGreaterThan(10_000);
  });

  it("leaves the scroller alone while the cursor's row is in sight", () => {
    // Level 4's grid at the window perf/measure.mjs opens: 366 px tall, a
    // 52 px header, the scroller at the top. Rows 0 to 12 are wholly in sight.
    const sight = { count: 83, rowHeight: 23, offset: 0, size: 366, obscured: 52 };
    for (let period = 1; period <= 12; period += 1) {
      expect(followOffset({ ...sight, period })).toBeNull();
    }
    // Row 13 reaches past the bottom, and is brought up a row's worth and the
    // pixels it was past by: its lower edge, 322, onto the view's, 314.
    expect(followOffset({ ...sight, period: 13 })).toBe(8);
    // The last row asks for the furthest the scroller goes.
    expect(followOffset({ ...sight, period: 82 })).toBe("bottom");
    // From further down, a row above the top is brought down to it.
    expect(followOffset({ ...sight, offset: 230, period: 9 })).toBe(207);
  });
});
