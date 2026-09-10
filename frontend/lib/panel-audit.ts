// Reading the panel's change journal (T-89). One call, and there is no writing
// counterpart on purpose: the backend exposes no verb that could change a
// journal line, so neither does this.
import { panelRequest } from "./panel-client";

export type AuditEntry = {
  occurredAt: string;
  actorEmail: string;
  /** A key such as `document_published`, translated by the dictionary. */
  action: string;
  subjectType: string | null;
  subjectId: number | null;
  detail: string | null;
};

export type AuditFilters = {
  actorEmail?: string;
  /** Both are plain dates from a date input, "2026-09-01". */
  since?: string;
  until?: string;
};

type RawEntry = {
  occurred_at: string;
  actor_email: string;
  action: string;
  subject_type: string | null;
  subject_id: number | null;
  detail: string | null;
};

export async function listAuditEvents(
  filters: AuditFilters = {},
  signal?: AbortSignal,
): Promise<AuditEntry[]> {
  const query = new URLSearchParams();
  if (filters.actorEmail?.trim()) {
    query.set("actor_email", filters.actorEmail.trim());
  }
  if (filters.since) {
    query.set("since", `${filters.since}T00:00:00`);
  }
  if (filters.until) {
    // The whole of the last day, down to the microsecond. The backend compares
    // `<=` against a microsecond-precision column, so a plain `T23:59:59` still
    // dropped an event recorded at 23:59:59.412, one second of the same hiding
    // the day-wide version of this bug used to do.
    query.set("until", `${filters.until}T23:59:59.999999`);
  }

  const suffix = query.toString();
  const rows = await panelRequest<RawEntry[]>(
    `/api/panel/audit-events${suffix ? `?${suffix}` : ""}`,
    { signal },
  );
  return rows.map((row) => ({
    occurredAt: row.occurred_at,
    actorEmail: row.actor_email,
    action: row.action,
    subjectType: row.subject_type,
    subjectId: row.subject_id,
    detail: row.detail,
  }));
}
