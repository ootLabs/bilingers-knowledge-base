import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PanelRequestError } from "@/lib/panel-client";
import {
  type DocumentDetail,
  getDocument,
  publishVersion,
  saveVersion,
  type VersionDetail,
} from "@/lib/panel-documents";

import DocumentEditor from "./DocumentEditor";

const replace = vi.fn();
// A stable object, like the real Next router. The panel screens put
// `useSessionRecovery` in a dependency list, so a router whose identity changed
// on every render would make their load effect refire forever.
const router = { replace, push: vi.fn(), refresh: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/panel/documents/1",
}));

vi.mock("@/lib/panel-documents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/panel-documents")>();
  return {
    ...actual,
    getDocument: vi.fn(),
    saveVersion: vi.fn(),
    publishVersion: vi.fn(),
  };
});

const getDocumentMock = vi.mocked(getDocument);
const saveVersionMock = vi.mocked(saveVersion);
const publishVersionMock = vi.mocked(publishVersion);

function version(overrides: Partial<VersionDetail> = {}): VersionDetail {
  return {
    versionNumber: 3,
    status: "draft",
    title: "Dwujezycznosc w przedszkolu",
    content: "Tresc trzeciej wersji.",
    changeComment: null,
    authorEmail: "redaktorka@fundacja.test",
    createdAt: "2026-09-05T09:30:00Z",
    publishedAt: null,
    publishedByEmail: null,
    ...overrides,
  };
}

function document(
  latest: VersionDetail,
  publishedVersion: DocumentDetail["publishedVersion"] = null,
): DocumentDetail {
  return {
    id: 1,
    createdAt: "2026-09-01T09:00:00Z",
    latestVersion: latest,
    publishedVersion,
  };
}

beforeEach(() => {
  getDocumentMock.mockReset();
  saveVersionMock.mockReset();
  publishVersionMock.mockReset();
  replace.mockReset();
});

describe("DocumentEditor", () => {
  it("does not eat unsaved text when the document is published", async () => {
    // Publishing acts on the last saved version, so re-reading the document
    // afterwards must not overwrite the box. Whatever is typed there may be
    // the only copy of it, the same rule a refused save follows.
    const published = version({ status: "published" as const });
    getDocumentMock.mockResolvedValue(document(version()));
    publishVersionMock.mockResolvedValue(published);
    render(<DocumentEditor documentId={1} />);

    const content = await screen.findByLabelText("Treść");
    fireEvent.change(content, { target: { value: "Akapit, ktorego jeszcze nie zapisano." } });

    fireEvent.click(screen.getByRole("button", { name: "Opublikuj tę wersję" }));

    await waitFor(() => expect(publishVersionMock).toHaveBeenCalled());
    expect(await screen.findByDisplayValue("Akapit, ktorego jeszcze nie zapisano.")).toBeInTheDocument();
  });

  it("names the version parents are reading while a draft is on screen", async () => {
    const live = { ...version({ versionNumber: 1, status: "published" as const }) };
    getDocumentMock.mockResolvedValue(document(version({ versionNumber: 2 }), live));
    render(<DocumentEditor documentId={1} />);

    expect(
      await screen.findByText(/Rodzice czytają teraz wersję 1/),
    ).toBeInTheDocument();
  });

  it("says so plainly when no version has ever been published", async () => {
    getDocumentMock.mockResolvedValue(document(version(), null));
    render(<DocumentEditor documentId={1} />);

    expect(
      await screen.findByText(/rodzice go jeszcze nie widzą/),
    ).toBeInTheDocument();
  });

  it("says which version is on screen and when it was written", async () => {
    getDocumentMock.mockResolvedValue(document(version()));
    render(<DocumentEditor documentId={1} />);

    expect(await screen.findByText(/Edytujesz wersję 3/)).toBeInTheDocument();
    expect(screen.getByText("Szkic")).toBeInTheDocument();
  });

  it("warns in as many words when the text on screen is the published one", async () => {
    // Getting this wrong means changing what parents read without realising it.
    getDocumentMock.mockResolvedValue(document(version({ status: "published" })));
    render(<DocumentEditor documentId={1} />);

    expect(
      await screen.findByText(/to jest wersja opublikowana, rodzice czytają ją w tej chwili/i),
    ).toBeInTheDocument();
  });

  it("saves through the versions endpoint and says what happened", async () => {
    getDocumentMock.mockResolvedValue(document(version()));
    saveVersionMock.mockResolvedValue(version({ versionNumber: 4, content: "Nowa tresc." }));
    render(<DocumentEditor documentId={1} />);
    await screen.findByLabelText("Treść");

    fireEvent.change(screen.getByLabelText("Treść"), { target: { value: "Nowa tresc." } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz jako nową wersję" }));

    expect(await screen.findByText(/Zapisano jako wersja 4/)).toBeInTheDocument();
    expect(saveVersionMock).toHaveBeenCalledWith(1, {
      title: "Dwujezycznosc w przedszkolu",
      content: "Nowa tresc.",
      changeComment: null,
    });
  });

  it("keeps the typed text when somebody else saved first", async () => {
    // A 409 is the one failure where the text on screen is the only copy that
    // exists. Clearing or reloading it would destroy the editor's work.
    getDocumentMock.mockResolvedValue(document(version()));
    saveVersionMock.mockRejectedValue(new PanelRequestError("conflict"));
    render(<DocumentEditor documentId={1} />);
    await screen.findByLabelText("Treść");

    fireEvent.change(screen.getByLabelText("Treść"), {
      target: { value: "Tresc ktorej nie wolno zgubic." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz jako nową wersję" }));

    expect(await screen.findByText("Ktoś zapisał zmiany przed tobą")).toBeInTheDocument();
    expect(screen.getByLabelText("Treść")).toHaveValue("Tresc ktorej nie wolno zgubic.");
  });

  it("sends an expired session back to the login screen", async () => {
    getDocumentMock.mockRejectedValue(new PanelRequestError("not_authenticated"));
    render(<DocumentEditor documentId={1} />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/panel/login"));
  });
});
