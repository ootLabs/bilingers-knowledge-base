import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PanelRequestError } from "@/lib/panel-client";
import { type DocumentSummary, listDocuments } from "@/lib/panel-documents";

import DocumentsList from "./DocumentsList";

const replace = vi.fn();
// A stable object, like the real Next router. The panel screens put
// `useSessionRecovery` in a dependency list, so a router whose identity changed
// on every render would make their load effect refire forever.
const router = { replace, push: vi.fn(), refresh: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/panel/documents",
}));

vi.mock("@/lib/panel-documents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/panel-documents")>();
  return { ...actual, listDocuments: vi.fn() };
});

const listDocumentsMock = vi.mocked(listDocuments);

function row(
  id: number,
  title: string,
  status: DocumentSummary["latestVersion"]["status"],
  createdAt: string,
): DocumentSummary {
  return {
    id,
    createdAt,
    latestVersion: {
      versionNumber: 1,
      status,
      title,
      changeComment: null,
      authorEmail: "redaktorka@fundacja.test",
      createdAt,
      publishedAt: status === "published" ? createdAt : null,
      publishedByEmail: status === "published" ? "redaktorka@fundacja.test" : null,
    },
  };
}

const DOCUMENTS = [
  row(1, "Dwujezycznosc w przedszkolu", "draft", "2026-09-01T10:00:00Z"),
  row(2, "Rozmowa z logopeda", "published", "2026-09-05T10:00:00Z"),
];

beforeEach(() => {
  listDocumentsMock.mockReset();
  replace.mockReset();
});

describe("DocumentsList", () => {
  it("offers exactly one way onward when the base is empty", async () => {
    listDocumentsMock.mockResolvedValue([]);
    render(<DocumentsList />);

    expect(await screen.findByText("Nie ma jeszcze żadnego dokumentu")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Nowy dokument" })).toHaveAttribute(
      "href",
      "/panel/documents/new",
    );
  });

  it("shows the state of each document without anyone clicking", async () => {
    // The main trust mechanism of the panel: what a parent is reading has to be
    // distinguishable from what is still a draft, at a glance.
    listDocumentsMock.mockResolvedValue(DOCUMENTS);
    render(<DocumentsList />);

    expect(await screen.findByText("Szkic")).toBeInTheDocument();
    expect(screen.getByText("Opublikowany")).toBeInTheDocument();
  });

  it("narrows the list by title", async () => {
    listDocumentsMock.mockResolvedValue(DOCUMENTS);
    render(<DocumentsList />);
    await screen.findByText("Dwujezycznosc w przedszkolu");

    fireEvent.change(screen.getByLabelText("Szukaj w tytułach"), {
      target: { value: "logoped" },
    });

    expect(screen.getByText("Rozmowa z logopeda")).toBeInTheDocument();
    expect(screen.queryByText("Dwujezycznosc w przedszkolu")).not.toBeInTheDocument();
  });

  it("narrows the list by status", async () => {
    listDocumentsMock.mockResolvedValue(DOCUMENTS);
    render(<DocumentsList />);
    await screen.findByText("Dwujezycznosc w przedszkolu");

    fireEvent.change(screen.getByLabelText("Stan dokumentu"), {
      target: { value: "published" },
    });

    expect(screen.getByText("Rozmowa z logopeda")).toBeInTheDocument();
    expect(screen.queryByText("Dwujezycznosc w przedszkolu")).not.toBeInTheDocument();
  });

  it("tells a filtered-away list apart from an empty base", async () => {
    listDocumentsMock.mockResolvedValue(DOCUMENTS);
    render(<DocumentsList />);
    await screen.findByText("Dwujezycznosc w przedszkolu");

    fireEvent.change(screen.getByLabelText("Szukaj w tytułach"), {
      target: { value: "czegos takiego nie ma" },
    });

    expect(screen.getByText("Nic nie pasuje do tych warunków")).toBeInTheDocument();
    expect(screen.queryByText("Nie ma jeszcze żadnego dokumentu")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Wyczyść filtry" }));

    expect(screen.getByText("Dwujezycznosc w przedszkolu")).toBeInTheDocument();
  });

  it("sends an expired session back to the login screen", async () => {
    listDocumentsMock.mockRejectedValue(new PanelRequestError("not_authenticated"));
    render(<DocumentsList />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/panel/login"));
  });

  it("offers a retry when the backend is down, and does not sign anybody out", async () => {
    listDocumentsMock.mockRejectedValueOnce(new PanelRequestError("database_unavailable"));
    listDocumentsMock.mockResolvedValueOnce(DOCUMENTS);
    render(<DocumentsList />);

    fireEvent.click(await screen.findByRole("button", { name: "Spróbuj ponownie" }));

    expect(await screen.findByText("Rozmowa z logopeda")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
