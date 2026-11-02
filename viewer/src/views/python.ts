// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The model's text, coloured the way the documentation site colours it.
 *
 * A reader arriving at `model.py:520` from a number has just been told this is
 * the line that computed it. Handed a wall of one grey, they have to find the
 * line's shape before they can read it; coloured, the string is a string and
 * the comment above it is a comment, and it reads like every other piece of
 * gaspatchio code they have seen. The palette is not invented here — it is
 * Material for MkDocs' own code colours with the one override
 * `gaspatchio-docs/docs/stylesheets/extra.css` makes, so the model file in this
 * tab and the same code on gaspatchio.dev are the same colours.
 *
 * **Why a tokeniser of our own and not a highlighting library.** One language
 * is in scope — the model is Python and the `sources` section carries the files
 * the nodes were written in. A library that can colour a hundred languages
 * costs a dependency, a lock-file move and its own share of the size ratchet to
 * do the one we need; this is a few hundred lines with no dependency, and the
 * colours are ours to match rather than a theme's to approximate.
 *
 * **The invariant, and it is the only one that matters.** The text is under a
 * digest. This function may only decide the colour of a character, never change
 * one: the tokens it returns, concatenated in order, must equal the file it was
 * given, byte for byte, with the newlines back in. `test/python.test.ts` asserts
 * exactly that over the tutorial's own model, so a tokeniser bug is a colouring
 * bug and can never be a text bug.
 *
 * Deliberately not exhaustive. An f-string's interior is one string rather than
 * an expression coloured inside a string, and a decorator's name is a name. Both
 * are places Pygments goes further; neither is a place where being plainer
 * misleads a reader about what they are looking at.
 */

/** What a run of characters is, for colour. One class per kind, in `Source.css`. */
export type TokenKind =
  | "keyword"
  | "string"
  | "number"
  | "comment"
  | "name"
  | "punct"
  | "plain";

/** One run of characters that shares a colour. */
export interface Token {
  text: string;
  kind: TokenKind;
}

/**
 * The words Python reserves, and the three constants it colours with them.
 *
 * `match`, `case` and `type` are soft keywords — a variable may be called any
 * of them — so they are deliberately absent. Colouring a variable called `case`
 * as a keyword is the kind of small lie that makes a reader distrust the rest.
 */
const KEYWORDS = new Set([
  "and", "as", "assert", "async", "await", "break", "class", "continue", "def",
  "del", "elif", "else", "except", "finally", "for", "from", "global", "if",
  "import", "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise",
  "return", "try", "while", "with", "yield",
  "None", "True", "False",
]);

const WHITESPACE = /[ \t\f]+/y;
const IDENTIFIER = /[A-Za-z_][A-Za-z0-9_]*/y;
const NUMBER =
  /0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|(?:\d[\d_]*)(?:\.[\d_]*)?(?:[eE][+-]?\d[\d_]*)?[jJ]?|\.\d[\d_]*(?:[eE][+-]?\d[\d_]*)?[jJ]?/y;
/** A string's opening: up to two prefix letters, then one quote or three. */
const STRING_OPEN = /(?:[rRbBuUfF]{1,2})?(?:"""|'''|"|')/y;

/** Where a sticky pattern matches at `at`, the text it matched; otherwise null. */
function matchAt(pattern: RegExp, text: string, at: number): string | null {
  pattern.lastIndex = at;
  const found = pattern.exec(text);
  return found === null ? null : found[0];
}

/**
 * The end of a string literal that opened at `from` with `quote`.
 *
 * A backslash escapes the next character, whatever it is. A single-quoted
 * string that reaches a newline without closing is unterminated — Python would
 * refuse the file, but this one has to draw it, so the string ends at the line
 * end and the next line starts again in code. Running to the end of the file
 * instead would colour a whole model as one string because of one stray quote.
 *
 * @returns The index one past the literal's last character.
 */
function endOfString(text: string, from: number, quote: string, triple: boolean): number {
  const closing = triple ? quote.repeat(3) : quote;
  let at = from;
  while (at < text.length) {
    if (text[at] === "\\") {
      at += 2;
      continue;
    }
    if (!triple && text[at] === "\n") return at;
    if (text.startsWith(closing, at)) return at + closing.length;
    at += 1;
  }
  return text.length;
}

/**
 * One file of Python, as runs of characters that share a colour.
 *
 * @param text - The file, exactly as the document carries it.
 * @returns Every character of `text`, in order, in tokens.
 */
export function tokenize(text: string): Token[] {
  const tokens: Token[] = [];
  /** Append, merging into the previous token where the kind is the same. */
  const push = (piece: string, kind: TokenKind): void => {
    const last = tokens[tokens.length - 1];
    if (last !== undefined && last.kind === kind) last.text += piece;
    else tokens.push({ text: piece, kind });
  };

  let at = 0;
  while (at < text.length) {
    const here = text[at];

    if (here === "\n") {
      push("\n", "plain");
      at += 1;
      continue;
    }

    const space = matchAt(WHITESPACE, text, at);
    if (space !== null) {
      push(space, "plain");
      at += space.length;
      continue;
    }

    if (here === "#") {
      const end = text.indexOf("\n", at);
      const comment = end < 0 ? text.slice(at) : text.slice(at, end);
      push(comment, "comment");
      at += comment.length;
      continue;
    }

    // A string before an identifier, so that the `f` of an f-string is part of
    // the literal rather than a name sitting in front of one.
    const open = matchAt(STRING_OPEN, text, at);
    if (open !== null) {
      const quote = open.endsWith('"') ? '"' : "'";
      const triple = open.endsWith('"""') || open.endsWith("'''");
      const end = endOfString(text, at + open.length, quote, triple);
      push(text.slice(at, end), "string");
      at = end;
      continue;
    }

    // A number before an identifier too: `0x1f` starts with a digit, and an
    // identifier can never start with one, so there is no ambiguity to lose.
    if (/[0-9]/.test(here ?? "") || (here === "." && /[0-9]/.test(text[at + 1] ?? ""))) {
      const number = matchAt(NUMBER, text, at);
      if (number !== null) {
        push(number, "number");
        at += number.length;
        continue;
      }
    }

    const word = matchAt(IDENTIFIER, text, at);
    if (word !== null) {
      push(word, KEYWORDS.has(word) ? "keyword" : "name");
      at += word.length;
      continue;
    }

    push(here ?? "", "punct");
    at += 1;
  }

  return tokens;
}

/**
 * One file of Python, as one array of tokens per line.
 *
 * The newlines are the split and are not in the result, so a caller drawing one
 * row per line draws every character exactly once. A triple-quoted string
 * crossing lines arrives as one string token on each of them, which is what a
 * row-at-a-time renderer needs.
 *
 * @param text - The file, exactly as the document carries it.
 * @returns One array of tokens per line, in order.
 */
export function highlight(text: string): Token[][] {
  const lines: Token[][] = [[]];
  for (const token of tokenize(text)) {
    const pieces = token.text.split("\n");
    pieces.forEach((piece, i) => {
      if (i > 0) lines.push([]);
      if (piece !== "") (lines[lines.length - 1] as Token[]).push({ text: piece, kind: token.kind });
    });
  }
  return lines;
}
