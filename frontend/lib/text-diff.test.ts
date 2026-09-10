import { describe, expect, it } from "vitest";

import { diffLines } from "./text-diff";

describe("diffLines", () => {
  it("marks nothing when the two texts are the same", () => {
    const lines = diffLines("Pierwszy\nDrugi", "Pierwszy\nDrugi");

    expect(lines.every((line) => line.kind === "same")).toBe(true);
  });

  it("keeps the unchanged lines around a rewritten one", () => {
    const lines = diffLines(
      "Wstep\nStara tresc akapitu\nZakonczenie",
      "Wstep\nNowa tresc akapitu\nZakonczenie",
    );

    expect(lines).toEqual([
      { kind: "same", text: "Wstep" },
      { kind: "removed", text: "Stara tresc akapitu" },
      { kind: "added", text: "Nowa tresc akapitu" },
      { kind: "same", text: "Zakonczenie" },
    ]);
  });

  it("reports an inserted paragraph as one addition, not as a rewrite", () => {
    const lines = diffLines("A\nB", "A\nNowy akapit\nB");

    expect(lines.filter((line) => line.kind !== "same")).toEqual([
      { kind: "added", text: "Nowy akapit" },
    ]);
  });

  it("reports a deleted paragraph as one removal", () => {
    const lines = diffLines("A\nStary akapit\nB", "A\nB");

    expect(lines.filter((line) => line.kind !== "same")).toEqual([
      { kind: "removed", text: "Stary akapit" },
    ]);
  });

  it("falls back to whole texts rather than locking the tab on huge documents", () => {
    // Past the cell budget the honest answer is "these differ", not a browser
    // spending seconds building a table nobody reads.
    const long = Array.from({ length: 600 }, (_, index) => `Linia ${index}`).join("\n");
    const other = Array.from({ length: 600 }, (_, index) => `Inna ${index}`).join("\n");

    const lines = diffLines(long, other);

    expect(lines.some((line) => line.kind === "same")).toBe(false);
    expect(lines).toHaveLength(1200);
  });
});
