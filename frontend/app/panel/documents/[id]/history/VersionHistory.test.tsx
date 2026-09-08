import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  type DocumentDetail,
  getDocument,
  getVersion,
  listVersions,
  restoreVersion,
  type VersionDetail,
  type VersionSummary,
} from "@/lib/panel-documents";

import VersionHistory from "./VersionHistory";

// A stable object, like the real Next router: a router whose identity changed
// on every render would make the screens' load effect refire forever.
const router = { replace: vi.fn(), push: vi.fn(), refresh: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/panel/documents/1/history",
}));

vi.mock("@/lib/panel-documents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/panel-documents")>();
  return {
    ...actual,
    getDocument: vi.fn(),
    getVersion: vi.fn(),
    listVersions: vi.fn(),
    restoreVersion: vi.fn(),
  };
});

const getDocumentMock = vi.mocked(getDocument);
const getVersionMock = vi.mocked(getVersion);
const listVersionsMock = vi.mocked(listVersions);
const restoreVersionMock = vi.mocked(restoreVersion);

function summary(versionNumber: number): VersionSummary {
  return {
    versionNumber,
    status: "draft",
    title: "Dwujezycznosc w przedszkolu",
    changeComment: null,
    authorEmail: "redaktorka@fundacja.test",
    createdAt: `2026-09-0${versionNumber}T09:00:00Z`,
    publishedAt: null,
    publishedByEmail: null,
  };
}

function detail(versionNumber: number, content: string): VersionDetail {
  return { ...summary(versionNumber), content };
}

function document(latest: VersionDetail): DocumentDetail {
  return { id: 1, createdAt: "2026-09-01T09:00:00Z", latestVersion: latest };
}

const CURRENT = detail(3, "Wstep\nTresc trzeciej wersji\nKoniec");

beforeEach(() => {
  getDocumentMock.mockReset();
  getVersionMock.mockReset();
  listVersionsMock.mockReset();
  restoreVersionMock.mockReset();
  listVersionsMock.mockResolvedValue([summary(3), summary(2), summary(1)]);
  getDocumentMock.mockResolvedValue(document(CURRENT));
});

describe("VersionHistory", () => {
  it("lists every version, newest first", async () => {
    render(<VersionHistory documentId={1} />);

    expect(await screen.findByText("Wersja 3")).toBeInTheDocument();
    expect(screen.getByText("Wersja 2")).toBeInTheDocument();
    expect(screen.getByText("Wersja 1")).toBeInTheDocument();
  });

  it("shows more versions after a restore, never fewer", async () => {
    // Restoring copies forward. A history that shrank would mean the model had
    // quietly stopped being a history.
    render(<VersionHistory documentId={1} />);
    await screen.findByText("Wersja 3");

    restoreVersionMock.mockResolvedValue(detail(4, "Wstep\nTresc pierwszej wersji\nKoniec"));
    listVersionsMock.mockResolvedValue([summary(4), summary(3), summary(2), summary(1)]);
    getDocumentMock.mockResolvedValue(
      document(detail(4, "Wstep\nTresc pierwszej wersji\nKoniec")),
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Przywróć tę treść" })[1]);

    expect(await screen.findByText("Wersja 4")).toBeInTheDocument();
    expect(screen.getByText("Wersja 1")).toBeInTheDocument();
    expect(screen.getByText(/Przywrócono treść jako wersja 4/)).toBeInTheDocument();
  });

  it("passes a Polish note with the restore rather than leaving the backend to write one", async () => {
    render(<VersionHistory documentId={1} />);
    await screen.findByText("Wersja 3");
    restoreVersionMock.mockResolvedValue(detail(4, "cokolwiek"));

    fireEvent.click(screen.getAllByRole("button", { name: "Przywróć tę treść" })[1]);

    await waitFor(() =>
      expect(restoreVersionMock).toHaveBeenCalledWith(1, 1, "Przywrócono treść z wersji 1"),
    );
  });

  it("compares an older version with the current one line by line", async () => {
    getVersionMock.mockResolvedValue(detail(1, "Wstep\nTresc pierwszej wersji\nKoniec"));
    render(<VersionHistory documentId={1} />);
    await screen.findByText("Wersja 3");

    fireEvent.click(screen.getAllByRole("button", { name: "Porównaj z bieżącą" })[2]);

    expect(await screen.findByText("Tresc pierwszej wersji")).toBeInTheDocument();
    expect(screen.getByText("Tresc trzeciej wersji")).toBeInTheDocument();
    // The unchanged lines stay, so it reads as a change rather than as a rewrite.
    expect(screen.getByText("Wstep")).toBeInTheDocument();
  });

  it("offers no restore for the version that is already current", async () => {
    render(<VersionHistory documentId={1} />);
    await screen.findByText("Wersja 3");

    expect(screen.getByText("Wersja bieżąca")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Przywróć tę treść" })).toHaveLength(2);
  });
});
