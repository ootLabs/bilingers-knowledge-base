// Line comparison between two versions of a document, written here rather than
// installed. Adding a dependency is a decision worth recording in
// docs/architecture.md, and this is forty lines of standard longest-common-
// subsequence: buying a package for it would cost more to justify than to write.

export type DiffKind = "same" | "added" | "removed";

export type DiffLine = {
  kind: DiffKind;
  text: string;
};

// The table is one number per pair of lines, so cost grows with the product of
// the two lengths. Past this, comparing line by line stops being worth the
// memory and the wait, and the honest answer is "these two texts are different"
// rather than a browser tab locking up. 250k cells is roughly two 500-line
// documents.
const MAX_CELLS = 250_000;

function wholesale(left: string[], right: string[]): DiffLine[] {
  return [
    ...left.map((text): DiffLine => ({ kind: "removed", text })),
    ...right.map((text): DiffLine => ({ kind: "added", text })),
  ];
}

/**
 * What changed between two texts, line by line.
 *
 * Lines, not words: an editor comparing two versions of a knowledge base
 * article is looking for the paragraph that moved, and word-level highlighting
 * inside a rewritten paragraph is noise around that answer.
 */
export function diffLines(before: string, after: string): DiffLine[] {
  const left = before.split("\n");
  const right = after.split("\n");

  if (left.length * right.length > MAX_CELLS) {
    return wholesale(left, right);
  }

  // table[i][j] is the length of the longest common subsequence of left[i..]
  // and right[j..]. Filled backwards so the walk below can go forwards, which
  // is what keeps the output in reading order.
  const table: number[][] = Array.from({ length: left.length + 1 }, () =>
    new Array<number>(right.length + 1).fill(0),
  );
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      table[i][j] =
        left[i] === right[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }

  const lines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < left.length && j < right.length) {
    if (left[i] === right[j]) {
      lines.push({ kind: "same", text: left[i] });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      lines.push({ kind: "removed", text: left[i] });
      i += 1;
    } else {
      lines.push({ kind: "added", text: right[j] });
      j += 1;
    }
  }
  while (i < left.length) {
    lines.push({ kind: "removed", text: left[i] });
    i += 1;
  }
  while (j < right.length) {
    lines.push({ kind: "added", text: right[j] });
    j += 1;
  }
  return lines;
}
