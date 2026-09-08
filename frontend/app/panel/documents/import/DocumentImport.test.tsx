import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PanelRequestError } from "@/lib/panel-client";
import { createDocument, listDocuments, saveVersion } from "@/lib/panel-documents";
import { previewImport } from "@/lib/panel-imports";

import DocumentImport from "./DocumentImport";

const replace = vi.fn();
// A stable object, like the real Next router. The panel screens put
// `useSessionRecovery` in a dependency list, so a router whose identity changed
// on every render would make their load effect refire forever.
const router = { replace, push: vi.fn(), refresh: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/panel/documents/import",
}));

vi.mock("@/lib/panel-imports", () => ({ previewImport: vi.fn() }));

vi.mock("@/lib/panel-documents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/panel-documents")>();
  return { ...actual, listDocuments: vi.fn(), createDocument: vi.fn(), saveVersion: vi.fn() };
});

const previewImportMock = vi.mocked(previewImport);
const listDocumentsMock = vi.mocked(listDocuments);
const createDocumentMock = vi.mocked(createDocument);
const saveVersionMock = vi.mocked(saveVersion);

const PREVIEW = {
  title: "Dwujezycznosc w przedszkolu",
  content: "# Dwujezycznosc w przedszkolu\n\nAkapit.",
  headingCount: 1,
  paragraphCount: 1,
  skipped: [{ reason: "table_not_imported", count: 2 }],
};

function upload() {
  const input = screen.getByLabelText("Plik z materiałem") as HTMLInputElement;
  const file = new File(["udawany docx"], "rozdzial.docx", {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Odczytaj plik" }));
}

beforeEach(() => {
  previewImportMock.mockReset();
  listDocumentsMock.mockReset();
  createDocumentMock.mockReset();
  saveVersionMock.mockReset();
  replace.mockReset();
  listDocumentsMock.mockResolvedValue([]);
});

describe("DocumentImport", () => {
  it("shows what was read, and what was left out, before anything is saved", async () => {
    previewImportMock.mockResolvedValue(PREVIEW);
    render(<DocumentImport />);

    upload();

    expect(await screen.findByText("Co odczytaliśmy")).toBeInTheDocument();
    expect(screen.getByText("Nagłówki: 1. Akapity: 1.")).toBeInTheDocument();
    expect(
      screen.getByText("Pominięto tabele, ta wersja panelu ich nie wczytuje: 2."),
    ).toBeInTheDocument();
    expect(createDocumentMock).not.toHaveBeenCalled();
    expect(saveVersionMock).not.toHaveBeenCalled();
  });

  it("lets the editor throw the result away without saving it", async () => {
    previewImportMock.mockResolvedValue(PREVIEW);
    render(<DocumentImport />);
    upload();
    await screen.findByText("Co odczytaliśmy");

    fireEvent.click(screen.getByRole("button", { name: "Odrzuć i zacznij od nowa" }));

    expect(screen.queryByText("Co odczytaliśmy")).not.toBeInTheDocument();
    expect(createDocumentMock).not.toHaveBeenCalled();
  });

  it("saves an accepted import as a new draft document", async () => {
    previewImportMock.mockResolvedValue(PREVIEW);
    createDocumentMock.mockResolvedValue({
      id: 12,
      createdAt: "2026-09-08T10:00:00Z",
      latestVersion: {
        versionNumber: 1,
        status: "draft",
        title: PREVIEW.title,
        content: PREVIEW.content,
        changeComment: null,
        authorEmail: "redaktorka@fundacja.test",
        createdAt: "2026-09-08T10:00:00Z",
        publishedAt: null,
        publishedByEmail: null,
      },
    });
    render(<DocumentImport />);
    upload();
    await screen.findByText("Co odczytaliśmy");

    fireEvent.click(screen.getByRole("button", { name: "Zapisz jako szkic" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/panel/documents/12"));
    expect(createDocumentMock).toHaveBeenCalledWith({
      title: PREVIEW.title,
      content: PREVIEW.content,
      changeComment: "Treść wczytana z pliku .docx",
    });
  });

  it("imports into an existing document as its next version, not as a copy", async () => {
    listDocumentsMock.mockResolvedValue([
      {
        id: 5,
        createdAt: "2026-09-01T10:00:00Z",
        latestVersion: {
          versionNumber: 2,
          status: "draft",
          title: "Istniejacy dokument",
          changeComment: null,
          authorEmail: null,
          createdAt: "2026-09-01T10:00:00Z",
          publishedAt: null,
          publishedByEmail: null,
        },
      },
    ]);
    previewImportMock.mockResolvedValue(PREVIEW);
    saveVersionMock.mockResolvedValue({
      versionNumber: 3,
      status: "draft",
      title: PREVIEW.title,
      content: PREVIEW.content,
      changeComment: null,
      authorEmail: null,
      createdAt: "2026-09-08T10:00:00Z",
      publishedAt: null,
      publishedByEmail: null,
    });
    render(<DocumentImport />);
    upload();
    await screen.findByText("Co odczytaliśmy");

    fireEvent.change(screen.getByLabelText("Gdzie zapisać"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz jako szkic" }));

    await waitFor(() => expect(saveVersionMock).toHaveBeenCalledWith(5, expect.anything()));
    expect(createDocumentMock).not.toHaveBeenCalled();
  });

  it("says a rejected file was rejected instead of showing a broken preview", async () => {
    previewImportMock.mockRejectedValue(new PanelRequestError("invalid_input"));
    render(<DocumentImport />);

    upload();

    expect(
      await screen.findByText("Nie możemy zapisać tego w tej postaci"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Co odczytaliśmy")).not.toBeInTheDocument();
  });
});
