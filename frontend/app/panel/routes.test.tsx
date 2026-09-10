import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PanelAuditPage from "./audit/page";
import DocumentEditorPage from "./documents/[id]/page";
import DocumentHistoryPage from "./documents/[id]/history/page";
import DocumentImportPage from "./documents/import/page";
import NewDocumentPage from "./documents/new/page";
import PanelDocumentsPage from "./documents/page";
import PanelLayout from "./layout";
import PanelLoginPage from "./login/page";
import PanelSecurityPage from "./security/page";

// One file for every panel route rather than eight files with one assertion
// each. They all have the same job and the same failure modes: a heading read
// from the dictionary and a client half that has to mount. Each screen's own
// behaviour is tested beside that screen.
//
// This is worth testing rather than counted as coverage filler. A route file is
// where a broken import or a translation key that never existed shows up, and
// the two dynamic routes carry the only real logic in the set: an address whose
// id is not a number must become the 404 screen and never a request the backend
// could only refuse.

const NOT_FOUND = "next/navigation notFound() called";

vi.mock("next/navigation", () => ({
  notFound: () => {
    // The real one throws to unwind the render, so the stub does too.
    throw new Error(NOT_FOUND);
  },
}));

// Each client half is stubbed: mounting the real one would pull in fetches and
// a router this test is not about.
vi.mock("./documents/DocumentsList", () => ({
  default: () => <div data-testid="documents-list" />,
}));
vi.mock("./documents/[id]/DocumentEditor", () => ({
  default: ({ documentId }: { documentId: number }) => (
    <div data-testid="document-editor">{documentId}</div>
  ),
}));
vi.mock("./documents/[id]/history/VersionHistory", () => ({
  default: ({ documentId }: { documentId: number }) => (
    <div data-testid="version-history">{documentId}</div>
  ),
}));
vi.mock("./documents/import/DocumentImport", () => ({
  default: () => <div data-testid="document-import" />,
}));
vi.mock("./documents/new/NewDocumentForm", () => ({
  default: () => <div data-testid="new-document-form" />,
}));
vi.mock("./login/LoginForm", () => ({
  default: () => <div data-testid="login-form" />,
}));
vi.mock("./security/TwoFactorSetup", () => ({
  default: () => <div data-testid="two-factor-setup" />,
}));
vi.mock("./audit/AuditLog", () => ({
  default: () => <div data-testid="audit-log" />,
}));
// A wrapper rather than a bare fragment, so the layout test can see what is
// inside the guard and what is beside it. That nesting is the load-bearing
// part: drawn outside the guard, the navigation would appear for somebody on
// their way to the login screen.
vi.mock("./PanelGuard", () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="panel-guard">{children}</div>
  ),
}));
vi.mock("./PanelNav", () => ({
  default: () => <nav data-testid="panel-nav" />,
}));

describe("panel routes", () => {
  it("renders the documents list behind its heading", () => {
    render(<PanelDocumentsPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Dokumenty");
    expect(screen.getByTestId("documents-list")).toBeInTheDocument();
  });

  it("renders the login screen", () => {
    render(<PanelLoginPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Panel fundacji");
    expect(screen.getByTestId("login-form")).toBeInTheDocument();
  });

  it("renders the second factor screen", () => {
    render(<PanelSecurityPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Dodatkowe zabezpieczenie logowania",
    );
    expect(screen.getByTestId("two-factor-setup")).toBeInTheDocument();
  });

  it("renders the change journal", () => {
    render(<PanelAuditPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Dziennik zmian");
    expect(screen.getByTestId("audit-log")).toBeInTheDocument();
  });

  it("renders the new document form", () => {
    render(<NewDocumentPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Nowy dokument");
    expect(screen.getByTestId("new-document-form")).toBeInTheDocument();
  });

  it("renders the import screen", () => {
    render(<DocumentImportPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Wgraj plik .docx");
    expect(screen.getByTestId("document-import")).toBeInTheDocument();
  });

  it("wraps every panel screen in the guard and the navigation", () => {
    render(
      <PanelLayout>
        <p>zawartosc ekranu</p>
      </PanelLayout>,
    );

    // Both inside the guard, not merely on the page: the navigation drawn
    // outside it would be offered to somebody on their way to the login form.
    const guard = screen.getByTestId("panel-guard");
    expect(guard).toContainElement(screen.getByTestId("panel-nav"));
    expect(guard).toContainElement(screen.getByText("zawartosc ekranu"));
  });
});

describe("panel routes that carry an id", () => {
  it("hands a numeric id to the editor", async () => {
    render(await DocumentEditorPage({ params: Promise.resolve({ id: "7" }) }));

    expect(screen.getByTestId("document-editor")).toHaveTextContent("7");
  });

  it("hands a numeric id to the history screen", async () => {
    render(await DocumentHistoryPage({ params: Promise.resolve({ id: "7" }) }));

    expect(screen.getByTestId("version-history")).toHaveTextContent("7");
  });

  it.each([
    ["not a number", "abc"],
    ["zero", "0"],
    ["negative", "-3"],
    // Everything `Number.parseInt` used to read as a valid 7 and render a real
    // document under a meaningless address.
    ["digits with a suffix", "7abc"],
    ["fractional", "7.9"],
    ["signed", "+7"],
    ["exponential", "1e5"],
    ["padded with a space", " 7"],
    ["empty", ""],
  ])("answers 404 for an id that is %s", async (_name, id) => {
    // Straight to the 404 screen rather than a request the backend could only
    // refuse, on both routes that take an id.
    await expect(DocumentEditorPage({ params: Promise.resolve({ id }) })).rejects.toThrow(
      NOT_FOUND,
    );
    await expect(DocumentHistoryPage({ params: Promise.resolve({ id }) })).rejects.toThrow(
      NOT_FOUND,
    );
  });
});
