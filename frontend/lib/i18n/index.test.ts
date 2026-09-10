import { afterEach, describe, expect, it, vi } from "vitest";

import { fill, getTranslations } from "./index";

describe("getTranslations", () => {
  it("resolves a top-level dot-path key", () => {
    const t = getTranslations();
    expect(t("common.productName")).toBe("Bilingers");
  });

  it("resolves a key nested under a feature namespace", () => {
    const t = getTranslations();
    expect(t("nav.chat")).toBe("Czat");
  });
});

describe("getTranslations, missing key", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns the key itself instead of throwing", () => {
    const t = getTranslations();
    expect(t("nav.doesNotExist")).toBe("nav.doesNotExist");
  });

  it("warns in development when a key is missing", () => {
    vi.stubEnv("NODE_ENV", "development");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const t = getTranslations();

    t("nav.doesNotExist");

    expect(warn).toHaveBeenCalledWith(expect.stringContaining("nav.doesNotExist"));
    warn.mockRestore();
  });

  it("does not warn in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const t = getTranslations();

    t("nav.doesNotExist");

    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe("fill", () => {
  it("puts a value into a sentence instead of gluing the sentence together", () => {
    // Polish inflects, so a fragment that reads correctly in one sentence is
    // wrong in the next. The whole sentence stays in the dictionary.
    expect(fill("Zapisano jako wersja {version}.", { version: 4 })).toBe(
      "Zapisano jako wersja 4.",
    );
  });

  it("fills every placeholder in one string", () => {
    expect(fill("Wersja {version} z dnia {date}", { version: 2, date: "5 wrzesnia" })).toBe(
      "Wersja 2 z dnia 5 wrzesnia",
    );
  });

  it("leaves a placeholder nobody supplied visible rather than dropping it", () => {
    // A visible "{version}" gets reported and fixed; a silently dropped one
    // leaves a sentence that looks finished and says the wrong thing.
    expect(fill("Wersja {version}", {})).toBe("Wersja {version}");
  });
});
