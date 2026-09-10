import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    // A row whose newest version is the published one: the simple case, where
    // both answers agree. The interesting case is built by `withLiveVersion`.
    publishedVersion:
      status === "published"
        ? {
            versionNumber: 1,
            status,
            title,
            changeComment: null,
            authorEmail: "redaktorka@fundacja.test",
            createdAt,
            publishedAt: createdAt,
            publishedByEmail: "redaktorka@fundacja.test",
          }
        : null,
  };
}

/** A document parents are reading at version 1 while version 2 is a draft. */
function withLiveVersion(document: DocumentSummary): DocumentSummary {
  return {
    ...document,
    latestVersion: { ...document.latestVersion, versionNumber: 2, status: "draft" },
    publishedVersion: {
      ...document.latestVersion,
      versionNumber: 1,
      status: "published",
      publishedAt: document.createdAt,
      publishedByEmail: "redaktorka@fundacja.test",
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

    // Scoped to the list, because the status filter offers every state as an
    // option and an unscoped query for "Szkic" matches the dropdown too.
    const list = await screen.findByRole("list");
    expect(within(list).getByText("Szkic")).toBeInTheDocument();
    expect(within(list).getByText("Opublikowany")).toBeInTheDocument();
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

  it("keeps saying published while a newer draft waits behind it", async () => {
    // The bug this replaces: one save flipped the pill to "Szkic" and the
    // screen stopped mentioning the version parents were still being served.
    listDocumentsMock.mockResolvedValue([
      withLiveVersion(row(2, "Rozmowa z logopeda", "published", "2026-09-05T10:00:00Z")),
    ]);
    render(<DocumentsList />);

    const list = await screen.findByRole("list");
    expect(within(list).getByText("Opublikowany")).toBeInTheDocument();
    expect(within(list).queryByText("Szkic")).not.toBeInTheDocument();
    expect(screen.getByText(/Rodzice czytają wersję 1/)).toBeInTheDocument();
    expect(screen.getByText(/wersja 2/)).toBeInTheDocument();
  });

  it("finds that document under the published filter, not under drafts", async () => {
    listDocumentsMock.mockResolvedValue([
      withLiveVersion(row(2, "Rozmowa z logopeda", "published", "2026-09-05T10:00:00Z")),
    ]);
    render(<DocumentsList />);
    await screen.findByText("Rozmowa z logopeda");

    fireEvent.change(screen.getByLabelText("Stan dokumentu"), {
      target: { value: "published" },
    });
    expect(screen.getByText("Rozmowa z logopeda")).toBeInTheDocument();

    // And under drafts as well: it genuinely is both, and this is the only way
    // to ask "what has work waiting to go live".
    fireEvent.change(screen.getByLabelText("Stan dokumentu"), {
      target: { value: "draft" },
    });
    expect(screen.getByText("Rozmowa z logopeda")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Stan dokumentu"), {
      target: { value: "withdrawn" },
    });
    expect(screen.queryByText("Rozmowa z logopeda")).not.toBeInTheDocument();
  });

  it("does not call a withdrawn newer version a draft", async () => {
    // Publish v2, withdraw it, publish v1: the newest version is a deliberate
    // withdrawal, not work in progress, and calling it a draft would hide that.
    const document = withLiveVersion(
      row(3, "Wycofany rozdzial", "published", "2026-09-05T10:00:00Z"),
    );
    listDocumentsMock.mockResolvedValue([
      { ...document, latestVersion: { ...document.latestVersion, status: "withdrawn" } },
    ]);
    render(<DocumentsList />);

    expect(await screen.findByText(/Rodzice czytają wersję 1/)).toBeInTheDocument();
    expect(screen.queryByText(/czekają w szkicu/)).not.toBeInTheDocument();
  });

  it("finds a retitled document by the title parents still see", async () => {
    const document = withLiveVersion(
      row(4, "Dwujezycznosc w przedszkolu", "published", "2026-09-05T10:00:00Z"),
    );
    listDocumentsMock.mockResolvedValue([
      {
        ...document,
        latestVersion: { ...document.latestVersion, title: "Dwujezycznosc w zlobku" },
      },
    ]);
    render(<DocumentsList />);
    await screen.findByText("Dwujezycznosc w zlobku");

    fireEvent.change(screen.getByLabelText("Szukaj w tytułach"), {
      target: { value: "przedszkolu" },
    });

    expect(screen.getByText("Dwujezycznosc w zlobku")).toBeInTheDocument();
    expect(screen.getByText(/Dwujezycznosc w przedszkolu/)).toBeInTheDocument();
  });

  it("cancels the read when the screen goes away", async () => {
    // The plumbing was carried unused until now. A read nobody is waiting for
    // must not be able to land on top of a newer one.
    listDocumentsMock.mockResolvedValue([]);
    const { unmount } = render(<DocumentsList />);
    await screen.findByText("Nie ma jeszcze żadnego dokumentu");

    const signal = listDocumentsMock.mock.calls[0][0];
    expect(signal?.aborted).toBe(false);

    unmount();

    expect(signal?.aborted).toBe(true);
  });

  it("says nothing when a read was superseded rather than failed", async () => {
    // An abort is the screen cancelling itself, so there is nothing to tell
    // anybody. Reported as a failure it would read "check your internet
    // connection" on a screen whose network is fine.
    const aborted = new Error("aborted");
    aborted.name = "AbortError";
    listDocumentsMock.mockRejectedValue(aborted);
    render(<DocumentsList />);

    await waitFor(() => expect(listDocumentsMock).toHaveBeenCalled());
    expect(screen.queryByText("Nie udało się połączyć")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
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
