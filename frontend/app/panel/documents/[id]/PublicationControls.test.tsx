import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PanelRequestError } from "@/lib/panel-client";
import { publishVersion, type VersionDetail, withdrawVersion } from "@/lib/panel-documents";

import PublicationControls from "./PublicationControls";

// A stable object, like the real Next router: a router whose identity changed
// on every render would make the screens' load effect refire forever.
const router = { replace: vi.fn(), push: vi.fn(), refresh: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/panel/documents/1",
}));

vi.mock("@/lib/panel-documents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/panel-documents")>();
  return { ...actual, publishVersion: vi.fn(), withdrawVersion: vi.fn() };
});

const publishVersionMock = vi.mocked(publishVersion);
const withdrawVersionMock = vi.mocked(withdrawVersion);

function version(overrides: Partial<VersionDetail> = {}): VersionDetail {
  return {
    versionNumber: 2,
    status: "draft",
    title: "Dwujezycznosc w przedszkolu",
    content: "Tresc.",
    changeComment: null,
    authorEmail: "redaktorka@fundacja.test",
    createdAt: "2026-09-05T09:30:00Z",
    publishedAt: null,
    publishedByEmail: null,
    ...overrides,
  };
}

const PUBLISHED = version({
  status: "published",
  publishedAt: "2026-09-08T11:00:00Z",
  publishedByEmail: "justyna@fundacja.test",
});

beforeEach(() => {
  publishVersionMock.mockReset();
  withdrawVersionMock.mockReset();
});

describe("PublicationControls", () => {
  it("says in plain words that a draft is not what parents are reading", () => {
    render(<PublicationControls documentId={1} version={version()} onChanged={vi.fn()} />);

    expect(
      screen.getByText(/Ta wersja nie jest opublikowana/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Opublikuj tę wersję" })).toBeInTheDocument();
  });

  it("says who published it and when, not just that it is published", async () => {
    // A published status with no date and no name is a claim, not an answer.
    render(<PublicationControls documentId={1} version={PUBLISHED} onChanged={vi.fn()} />);

    expect(
      screen.getByText("Dokument jest opublikowany, asystent już z niego korzysta."),
    ).toBeInTheDocument();
    expect(screen.getByText(/justyna@fundacja.test/)).toBeInTheDocument();
  });

  it("hands the published version back so the screen stops offering to publish it", async () => {
    publishVersionMock.mockResolvedValue(PUBLISHED);
    const onChanged = vi.fn();
    render(<PublicationControls documentId={1} version={version()} onChanged={onChanged} />);

    fireEvent.click(screen.getByRole("button", { name: "Opublikuj tę wersję" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(PUBLISHED));
    expect(publishVersionMock).toHaveBeenCalledWith(1, 2);
  });

  it("offers withdrawal, not publication, once it is live", async () => {
    withdrawVersionMock.mockResolvedValue(version({ status: "withdrawn" }));
    const onChanged = vi.fn();
    render(<PublicationControls documentId={1} version={PUBLISHED} onChanged={onChanged} />);

    fireEvent.click(screen.getByRole("button", { name: "Wycofaj z publikacji" }));

    await waitFor(() => expect(withdrawVersionMock).toHaveBeenCalledWith(1, 2));
    expect(publishVersionMock).not.toHaveBeenCalled();
  });

  it("says what went wrong instead of leaving the click silent", async () => {
    publishVersionMock.mockRejectedValue(new PanelRequestError("conflict"));
    render(<PublicationControls documentId={1} version={version()} onChanged={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Opublikuj tę wersję" }));

    expect(await screen.findByText("Ktoś zapisał zmiany przed tobą")).toBeInTheDocument();
  });
});
