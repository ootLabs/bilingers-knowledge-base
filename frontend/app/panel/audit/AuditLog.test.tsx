import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type AuditEntry, listAuditEvents } from "@/lib/panel-audit";
import { PanelRequestError } from "@/lib/panel-client";

import AuditLog from "./AuditLog";

const replace = vi.fn();
// A stable object, like the real Next router. The panel screens put
// `useSessionRecovery` in a dependency list, so a router whose identity changed
// on every render would make their load effect refire forever.
const router = { replace, push: vi.fn(), refresh: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/panel/audit",
}));

vi.mock("@/lib/panel-audit", () => ({ listAuditEvents: vi.fn() }));

const listAuditEventsMock = vi.mocked(listAuditEvents);

function entry(action: string, actorEmail = "redaktorka@fundacja.test"): AuditEntry {
  return {
    occurredAt: "2026-09-08T09:00:00Z",
    actorEmail,
    action,
    subjectType: "document",
    subjectId: 3,
    detail: null,
  };
}

beforeEach(() => {
  listAuditEventsMock.mockReset();
  replace.mockReset();
});

describe("AuditLog", () => {
  it("says what happened in Polish, not as a key", async () => {
    listAuditEventsMock.mockResolvedValue([entry("document_published")]);
    render(<AuditLog />);

    expect(await screen.findByText("Opublikowanie wersji")).toBeInTheDocument();
    expect(screen.getByText(/redaktorka@fundacja.test/)).toBeInTheDocument();
  });

  it("prints an action it does not know rather than leaving the line blank", async () => {
    // A blank line in a journal hides that something happened at all, which is
    // worse than a technical word on screen.
    listAuditEventsMock.mockResolvedValue([entry("something_new")]);
    render(<AuditLog />);

    expect(await screen.findByText("something_new")).toBeInTheDocument();
  });

  it("passes the person and the date range to the backend", async () => {
    listAuditEventsMock.mockResolvedValue([]);
    render(<AuditLog />);
    await screen.findByText("Brak zdarzeń w tym zakresie");

    fireEvent.change(screen.getByLabelText("Adres e-mail osoby"), {
      target: { value: "justyna@fundacja.test" },
    });
    fireEvent.change(screen.getByLabelText("Od dnia"), { target: { value: "2026-09-01" } });
    fireEvent.change(screen.getByLabelText("Do dnia"), { target: { value: "2026-09-05" } });
    fireEvent.click(screen.getByRole("button", { name: "Pokaż" }));

    await waitFor(() =>
      expect(listAuditEventsMock).toHaveBeenLastCalledWith(
        {
          actorEmail: "justyna@fundacja.test",
          since: "2026-09-01",
          until: "2026-09-05",
        },
        expect.any(AbortSignal),
      ),
    );
  });

  it("spells out the detail column in Polish", async () => {
    // A journal that answers "bad_password" and "version=3" is a journal full
    // of the technical identifiers this screen is ruled to have none of.
    listAuditEventsMock.mockResolvedValueOnce([
      { ...entry("login_failed"), detail: "bad_password" },
      { ...entry("document_version_saved"), detail: "version=3" },
      { ...entry("document_imported"), detail: "bytes=4096 headings=2" },
      { ...entry("account_changed"), detail: "role=editor active=false" },
    ]);
    render(<AuditLog />);

    expect(await screen.findByText(/błędne hasło/)).toBeInTheDocument();
    expect(screen.getByText(/wersja: 3/)).toBeInTheDocument();
    expect(screen.getByText(/bajtów: 4096, nagłówków: 2/)).toBeInTheDocument();
    expect(screen.getByText(/rola: redaktorka, konto czynne: nie/)).toBeInTheDocument();
  });

  it("prints a detail nobody has translated rather than nothing", async () => {
    // Same reasoning as an unknown action: a blank where something happened
    // hides that it happened at all.
    listAuditEventsMock.mockResolvedValueOnce([
      { ...entry("document_created"), detail: "czegos_takiego_nie_znamy" },
    ]);
    render(<AuditLog />);

    expect(await screen.findByText(/czegos_takiego_nie_znamy/)).toBeInTheDocument();
  });

  it("does not let a second read start while one is running", async () => {
    // The race closed at its source. Two clicks on "Pokaż" one gesture apart
    // used to leave two reads in flight, with the older one able to answer
    // second and show entries that did not match the filters above them.
    let releaseFirst: (entries: AuditEntry[]) => void = () => {};
    listAuditEventsMock.mockReturnValueOnce(
      new Promise<AuditEntry[]>((resolve) => {
        releaseFirst = resolve;
      }),
    );
    render(<AuditLog />);
    await waitFor(() => expect(listAuditEventsMock).toHaveBeenCalledTimes(1));

    expect(screen.getByRole("button", { name: "Wczytujemy..." })).toBeDisabled();

    releaseFirst([entry("document_published", "justyna@fundacja.test")]);

    const apply = await screen.findByRole("button", { name: "Pokaż" });
    expect(apply).toBeEnabled();
    expect(listAuditEventsMock).toHaveBeenCalledTimes(1);
  });

  it("cancels the read when the screen goes away", async () => {
    // What disabling cannot cover: a request answering into a screen nobody is
    // looking at any more.
    listAuditEventsMock.mockReturnValueOnce(new Promise<AuditEntry[]>(() => {}));
    const { unmount } = render(<AuditLog />);
    await waitFor(() => expect(listAuditEventsMock).toHaveBeenCalledTimes(1));

    expect(listAuditEventsMock.mock.calls[0][1]?.aborted).toBe(false);

    unmount();

    expect(listAuditEventsMock.mock.calls[0][1]?.aborted).toBe(true);
  });

  it("says nothing when a read was superseded rather than failed", async () => {
    // An abort is this screen cancelling itself. Reported as a failure it would
    // read "check your internet connection" on a screen whose network is fine.
    const aborted = new Error("aborted");
    aborted.name = "AbortError";
    listAuditEventsMock.mockRejectedValue(aborted);
    render(<AuditLog />);

    await waitFor(() => expect(listAuditEventsMock).toHaveBeenCalled());
    expect(screen.queryByText("Nie udało się połączyć")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("offers no way to change a line", async () => {
    listAuditEventsMock.mockResolvedValue([entry("document_published")]);
    render(<AuditLog />);
    await screen.findByText("Opublikowanie wersji");

    // Only the filter form's own button exists; a journal row carries no action.
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("sends an expired session back to the login screen", async () => {
    listAuditEventsMock.mockRejectedValue(new PanelRequestError("not_authenticated"));
    render(<AuditLog />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/panel/login"));
  });

  it("says an editor may not read it, rather than showing an empty journal", async () => {
    listAuditEventsMock.mockRejectedValue(new PanelRequestError("forbidden"));
    render(<AuditLog />);

    expect(
      await screen.findByText("To działanie wymaga innych uprawnień"),
    ).toBeInTheDocument();
  });
});
