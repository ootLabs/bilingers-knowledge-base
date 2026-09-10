import { beforeEach, describe, expect, it, vi } from "vitest";

import { listAuditEvents } from "./panel-audit";
import { panelRequest } from "./panel-client";

vi.mock("./panel-client", () => ({ panelRequest: vi.fn() }));

const request = vi.mocked(panelRequest);

beforeEach(() => {
  request.mockReset();
  request.mockResolvedValue([]);
});

describe("listAuditEvents", () => {
  it("asks for the whole journal when nothing is filtered", async () => {
    await listAuditEvents();

    expect(request).toHaveBeenCalledWith("/api/panel/audit-events", { signal: undefined });
  });

  it("covers the whole of the last day, down to its last microsecond", async () => {
    // "1 to 5 September" that silently excluded the 5th would hide exactly the
    // event somebody is looking for. The backend compares `<=` against a
    // microsecond-precision column, so stopping at whole seconds left the same
    // hole one second wide: an event at 23:59:59.412 fell outside it.
    await listAuditEvents({ since: "2026-09-01", until: "2026-09-05" });

    expect(request).toHaveBeenCalledWith(
      "/api/panel/audit-events?since=2026-09-01T00%3A00%3A00"
        + "&until=2026-09-05T23%3A59%3A59.999999",
      { signal: undefined },
    );
  });

  it("ignores an address that is only whitespace", async () => {
    await listAuditEvents({ actorEmail: "   " });

    expect(request).toHaveBeenCalledWith("/api/panel/audit-events", { signal: undefined });
  });

  it("turns the backend's shape into the one the screen reads", async () => {
    request.mockResolvedValue([
      {
        occurred_at: "2026-09-08T09:00:00Z",
        actor_email: "redaktorka@fundacja.test",
        action: "document_published",
        subject_type: "document",
        subject_id: 3,
        detail: "version 2",
      },
    ]);

    await expect(listAuditEvents()).resolves.toEqual([
      {
        occurredAt: "2026-09-08T09:00:00Z",
        actorEmail: "redaktorka@fundacja.test",
        action: "document_published",
        subjectType: "document",
        subjectId: 3,
        detail: "version 2",
      },
    ]);
  });
});
