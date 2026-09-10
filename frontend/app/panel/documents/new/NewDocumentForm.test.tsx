import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PanelRequestError } from "@/lib/panel-client";
import { createDocument } from "@/lib/panel-documents";

import NewDocumentForm from "./NewDocumentForm";

const replace = vi.fn();
// A stable object, like the real Next router. The panel screens put
// `useSessionRecovery` in a dependency list, so a router whose identity changed
// on every render would make their load effect refire forever.
const router = { replace, push: vi.fn(), refresh: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/panel/documents/new",
}));

vi.mock("@/lib/panel-documents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/panel-documents")>();
  return { ...actual, createDocument: vi.fn() };
});

const createDocumentMock = vi.mocked(createDocument);

function fillIn(title = "Nowy rozdzial", content = "Tresc rozdzialu.") {
  fireEvent.change(screen.getByLabelText("Tytuł"), { target: { value: title } });
  fireEvent.change(screen.getByLabelText("Treść"), { target: { value: content } });
}

beforeEach(() => {
  createDocumentMock.mockReset();
  replace.mockReset();
});

describe("NewDocumentForm", () => {
  it("will not submit without a title and a body", () => {
    render(<NewDocumentForm />);

    expect(screen.getByRole("button", { name: "Utwórz dokument" })).toBeDisabled();
  });

  it("opens the editor for the document it just created", async () => {
    createDocumentMock.mockResolvedValue({
      id: 7,
      createdAt: "2026-09-08T10:00:00Z",
      latestVersion: {
        versionNumber: 1,
        status: "draft",
        title: "Nowy rozdzial",
        content: "Tresc rozdzialu.",
        changeComment: null,
        authorEmail: "redaktorka@fundacja.test",
        createdAt: "2026-09-08T10:00:00Z",
        publishedAt: null,
        publishedByEmail: null,
      },
      publishedVersion: null,
    });
    render(<NewDocumentForm />);

    fillIn();
    fireEvent.click(screen.getByRole("button", { name: "Utwórz dokument" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/panel/documents/7"));
  });

  it("keeps the text on screen when the save is refused", async () => {
    createDocumentMock.mockRejectedValue(new PanelRequestError("database_unavailable"));
    render(<NewDocumentForm />);

    fillIn("Nowy rozdzial", "Tresc, ktorej nie wolno zgubic.");
    fireEvent.click(screen.getByRole("button", { name: "Utwórz dokument" }));

    expect(await screen.findByText("Panel jest chwilowo niedostępny")).toBeInTheDocument();
    expect(screen.getByLabelText("Treść")).toHaveValue("Tresc, ktorej nie wolno zgubic.");
  });
});
