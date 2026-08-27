import { afterEach, describe, expect, it, vi } from "vitest";

import { getTranslations } from "./index";

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
