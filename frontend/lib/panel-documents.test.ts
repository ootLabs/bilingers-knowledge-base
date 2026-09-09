import { beforeEach, describe, expect, it, vi } from "vitest";

import { panelRequest } from "./panel-client";
import {
  createDocument,
  getDocument,
  getVersion,
  listDocuments,
  listVersions,
  publishVersion,
  restoreVersion,
  saveVersion,
  withdrawVersion,
} from "./panel-documents";

vi.mock("./panel-client", () => ({ panelRequest: vi.fn() }));

const request = vi.mocked(panelRequest);

const RAW_VERSION = {
  version_number: 2,
  status: "draft" as const,
  title: "Dwujezycznosc w przedszkolu",
  change_comment: "Poprawka",
  author_email: "redaktorka@fundacja.test",
  created_at: "2026-09-08T10:00:00Z",
  published_at: null,
  published_by_email: null,
  content: "Tresc.",
};

const RAW_LIVE_VERSION = {
  ...RAW_VERSION,
  version_number: 1,
  status: "published" as const,
  change_comment: null,
  published_at: "2026-09-02T08:00:00Z",
  published_by_email: "justyna@fundacja.test",
};

const RAW_DOCUMENT = {
  id: 3,
  created_at: "2026-09-01T10:00:00Z",
  latest_version: RAW_VERSION,
  published_version: RAW_LIVE_VERSION,
};

beforeEach(() => {
  request.mockReset();
});

describe("panel-documents", () => {
  it("turns the backend's snake_case into camelCase once, here", async () => {
    // A component reading `latest_version` would be a component that has to
    // know what wrote it.
    request.mockResolvedValue([RAW_DOCUMENT]);

    const [row] = await listDocuments();

    expect(row).toEqual({
      id: 3,
      createdAt: "2026-09-01T10:00:00Z",
      latestVersion: {
        versionNumber: 2,
        status: "draft",
        title: "Dwujezycznosc w przedszkolu",
        changeComment: "Poprawka",
        authorEmail: "redaktorka@fundacja.test",
        createdAt: "2026-09-08T10:00:00Z",
        publishedAt: null,
        publishedByEmail: null,
      },
      // The other half of the row, and the reason it exists: version 2 is the
      // draft an editor would open, version 1 is what a parent gets served.
      publishedVersion: {
        versionNumber: 1,
        status: "published",
        title: "Dwujezycznosc w przedszkolu",
        changeComment: null,
        authorEmail: "redaktorka@fundacja.test",
        createdAt: "2026-09-08T10:00:00Z",
        publishedAt: "2026-09-02T08:00:00Z",
        publishedByEmail: "justyna@fundacja.test",
      },
    });
  });

  it("reads a document with nothing published as having nothing published", async () => {
    request.mockResolvedValue({ ...RAW_DOCUMENT, published_version: null });

    const document = await getDocument(3);

    expect(document.publishedVersion).toBeNull();
  });

  it("survives a response that leaves the field out entirely", async () => {
    // Absent and null mean the same thing here. Crashing on the difference
    // would take out the whole screen over one sentence on it.
    const { published_version: _omitted, ...withoutTheField } = RAW_DOCUMENT;
    request.mockResolvedValue(withoutTheField);

    const document = await getDocument(3);

    expect(document.publishedVersion).toBeNull();
  });

  it("reads one document with the text of its newest version", async () => {
    request.mockResolvedValue(RAW_DOCUMENT);

    const document = await getDocument(3);

    expect(document.latestVersion.content).toBe("Tresc.");
    expect(request).toHaveBeenCalledWith("/api/panel/documents/3", { signal: undefined });
  });

  it("treats a version with no content as empty rather than undefined", async () => {
    request.mockResolvedValue([{ ...RAW_VERSION, content: undefined }]);

    const [version] = await listVersions(3);

    expect(version.versionNumber).toBe(2);
  });

  it("saves an edit with POST, never PUT", async () => {
    // The backend has no PUT on a version and never will: a save adds the next
    // snapshot and leaves the previous one exactly as it was.
    request.mockResolvedValue(RAW_VERSION);

    await saveVersion(3, { title: "Tytul", content: "Tresc", changeComment: "Uwaga" });

    expect(request).toHaveBeenCalledWith("/api/panel/documents/3/versions", {
      method: "POST",
      body: { title: "Tytul", content: "Tresc", change_comment: "Uwaga" },
    });
  });

  it("sends a missing comment as null rather than leaving the field out", async () => {
    request.mockResolvedValue(RAW_DOCUMENT);

    await createDocument({ title: "Tytul", content: "Tresc" });

    expect(request).toHaveBeenCalledWith("/api/panel/documents", {
      method: "POST",
      body: { title: "Tytul", content: "Tresc", change_comment: null },
    });
  });

  it("posts a restore to the version being restored, with its note", async () => {
    request.mockResolvedValue(RAW_VERSION);

    await restoreVersion(3, 1, "Przywrocono tresc z wersji 1");

    expect(request).toHaveBeenCalledWith("/api/panel/documents/3/versions/1/restore", {
      method: "POST",
      body: { change_comment: "Przywrocono tresc z wersji 1" },
    });
  });

  it("reads one version by its number", async () => {
    request.mockResolvedValue(RAW_VERSION);

    await getVersion(3, 2);

    expect(request).toHaveBeenCalledWith("/api/panel/documents/3/versions/2", {
      signal: undefined,
    });
  });

  it("publishes and withdraws through their own endpoints", async () => {
    request.mockResolvedValue(RAW_VERSION);

    await publishVersion(3, 2);
    await withdrawVersion(3, 2);

    expect(request).toHaveBeenNthCalledWith(1, "/api/panel/documents/3/versions/2/publish", {
      method: "POST",
    });
    expect(request).toHaveBeenNthCalledWith(2, "/api/panel/documents/3/versions/2/withdraw", {
      method: "POST",
    });
  });
});
