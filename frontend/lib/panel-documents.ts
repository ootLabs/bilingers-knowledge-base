// Document calls, on top of the session handling in panel-client.ts. A second
// file rather than a bigger one: the client owns the token and the failure
// vocabulary, this owns one resource, and neither has to be read to change the
// other.
//
// The backend speaks snake_case (it is a Python API). Converting here, once,
// keeps that off every screen: a component reading `latest_version` would be a
// component that has to know what wrote it.
import { panelRequest } from "./panel-client";

export type DocumentStatus = "draft" | "in_review" | "published" | "withdrawn";

export type VersionSummary = {
  versionNumber: number;
  status: DocumentStatus;
  title: string;
  changeComment: string | null;
  authorEmail: string | null;
  createdAt: string;
  // Both null until the version is published. Separate from the author and the
  // creation date because a version written on Monday and published on Friday
  // by somebody else is the normal case.
  publishedAt: string | null;
  publishedByEmail: string | null;
};

export type VersionDetail = VersionSummary & { content: string };

export type DocumentSummary = {
  id: number;
  createdAt: string;
  latestVersion: VersionSummary;
  // What a parent is reading, which stops being the newest version the moment
  // anybody saves an edit. Null when nothing has ever been published, never
  // more than one: the database allows a single published version per document.
  publishedVersion: VersionSummary | null;
};

export type DocumentDetail = {
  id: number;
  createdAt: string;
  latestVersion: VersionDetail;
  publishedVersion: VersionSummary | null;
};

/**
 * The state of the DOCUMENT, which is not the state of its newest version.
 *
 * A document with a published version 1 and a draft version 2 is published:
 * that is what a parent gets when they ask. Reading the newest version's
 * status instead made the panel answer "szkic" for a document it was actively
 * serving, which is the one thing the status is on screen to prevent.
 */
export function documentState(document: DocumentSummary): DocumentStatus {
  return document.publishedVersion !== null ? "published" : document.latestVersion.status;
}

/** Whether newer, unpublished work is waiting behind what parents can see. */
export function hasUnpublishedChanges(document: DocumentSummary): boolean {
  return (
    document.publishedVersion !== null &&
    document.publishedVersion.versionNumber !== document.latestVersion.versionNumber
  );
}

/**
 * Whether a status filter should list this document.
 *
 * Either answer counts, and that is the point: a document with a published
 * version 1 behind a draft version 2 genuinely is both published and has a
 * draft. Matching only `documentState` made three of the four filter values
 * unable to reach any document that had ever been published, so "which
 * documents have work waiting to go live" became unanswerable on the one
 * screen built to answer it.
 */
export function matchesStatus(document: DocumentSummary, status: DocumentStatus): boolean {
  return documentState(document) === status || document.latestVersion.status === status;
}

/**
 * Every title this document is findable by.
 *
 * The published version's title too, because it can differ from the newest
 * one: retitle a published document and a colleague searching for the title
 * parents actually see would otherwise be told nothing matches.
 */
export function searchableTitles(document: DocumentSummary): string[] {
  const titles = [document.latestVersion.title];
  if (document.publishedVersion !== null) {
    titles.push(document.publishedVersion.title);
  }
  return titles;
}

/** What one save carries. `changeComment` is the editor's note, always optional. */
export type DocumentContent = {
  title: string;
  content: string;
  changeComment?: string | null;
};

type RawVersion = {
  version_number: number;
  status: DocumentStatus;
  title: string;
  change_comment: string | null;
  author_email: string | null;
  created_at: string;
  published_at: string | null;
  published_by_email: string | null;
  content?: string;
};

type RawDocument = {
  id: number;
  created_at: string;
  latest_version: RawVersion;
  published_version: RawVersion | null;
};

function toSummary(raw: RawVersion): VersionSummary {
  return {
    versionNumber: raw.version_number,
    status: raw.status,
    title: raw.title,
    changeComment: raw.change_comment,
    authorEmail: raw.author_email,
    createdAt: raw.created_at,
    publishedAt: raw.published_at,
    publishedByEmail: raw.published_by_email,
  };
}

function toDetail(raw: RawVersion): VersionDetail {
  return { ...toSummary(raw), content: raw.content ?? "" };
}

/**
 * A version that may not be there at all.
 *
 * Absent and null both mean "nothing is published". Tolerating absence is not
 * defensive clutter: this is the only field on the response whose whole point
 * is that it is often missing, and reading it as a crash rather than as an
 * answer would take out the list screen instead of the one sentence on it.
 */
function toSummaryOrNull(raw: RawVersion | null | undefined): VersionSummary | null {
  return raw ? toSummary(raw) : null;
}

function toDocument(raw: RawDocument): DocumentDetail {
  return {
    id: raw.id,
    createdAt: raw.created_at,
    latestVersion: toDetail(raw.latest_version),
    publishedVersion: toSummaryOrNull(raw.published_version),
  };
}

function body(content: DocumentContent) {
  return {
    title: content.title,
    content: content.content,
    change_comment: content.changeComment ?? null,
  };
}

export async function listDocuments(signal?: AbortSignal): Promise<DocumentSummary[]> {
  const rows = await panelRequest<RawDocument[]>("/api/panel/documents", { signal });
  return rows.map((row) => ({
    id: row.id,
    createdAt: row.created_at,
    latestVersion: toSummary(row.latest_version),
    publishedVersion: toSummaryOrNull(row.published_version),
  }));
}

export async function getDocument(
  documentId: number,
  signal?: AbortSignal,
): Promise<DocumentDetail> {
  return toDocument(
    await panelRequest<RawDocument>(`/api/panel/documents/${documentId}`, { signal }),
  );
}

export async function createDocument(content: DocumentContent): Promise<DocumentDetail> {
  return toDocument(
    await panelRequest<RawDocument>("/api/panel/documents", {
      method: "POST",
      body: body(content),
    }),
  );
}

/**
 * Save an edit.
 *
 * POST, never PUT: the backend has no PUT on a version and never will. A save
 * adds the next snapshot and leaves the previous one exactly as it was, which
 * is the only reason a bad change can be undone at all.
 */
export async function saveVersion(
  documentId: number,
  content: DocumentContent,
): Promise<VersionDetail> {
  return toDetail(
    await panelRequest<RawVersion>(`/api/panel/documents/${documentId}/versions`, {
      method: "POST",
      body: body(content),
    }),
  );
}

export async function listVersions(
  documentId: number,
  signal?: AbortSignal,
): Promise<VersionSummary[]> {
  const rows = await panelRequest<RawVersion[]>(
    `/api/panel/documents/${documentId}/versions`,
    { signal },
  );
  return rows.map(toSummary);
}

export async function getVersion(
  documentId: number,
  versionNumber: number,
  signal?: AbortSignal,
): Promise<VersionDetail> {
  return toDetail(
    await panelRequest<RawVersion>(
      `/api/panel/documents/${documentId}/versions/${versionNumber}`,
      { signal },
    ),
  );
}

/**
 * Put one version in front of parents, or take it back out (T-88).
 *
 * Publishing the version that is already published answers 200 and changes
 * nothing, so a second click from someone who missed the first is harmless.
 */
export async function publishVersion(
  documentId: number,
  versionNumber: number,
): Promise<VersionDetail> {
  return toDetail(
    await panelRequest<RawVersion>(
      `/api/panel/documents/${documentId}/versions/${versionNumber}/publish`,
      { method: "POST" },
    ),
  );
}

export async function withdrawVersion(
  documentId: number,
  versionNumber: number,
): Promise<VersionDetail> {
  return toDetail(
    await panelRequest<RawVersion>(
      `/api/panel/documents/${documentId}/versions/${versionNumber}/withdraw`,
      { method: "POST" },
    ),
  );
}

/** Copy an old version forward as a new one. The history keeps growing. */
export async function restoreVersion(
  documentId: number,
  versionNumber: number,
  changeComment: string,
): Promise<VersionDetail> {
  return toDetail(
    await panelRequest<RawVersion>(
      `/api/panel/documents/${documentId}/versions/${versionNumber}/restore`,
      { method: "POST", body: { change_comment: changeComment } },
    ),
  );
}
