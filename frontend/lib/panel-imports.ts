// Reading a .docx (T-85). One call, and it writes nothing: what comes back is
// a proposal the editor accepts or throws away, and accepting it is an ordinary
// save through panel-documents.ts.
import { panelRequest } from "./panel-client";

/** One thing the reader left out. `reason` is a key the dictionary explains. */
export type ImportSkipped = {
  reason: string;
  count: number;
};

export type ImportPreview = {
  title: string;
  content: string;
  headingCount: number;
  paragraphCount: number;
  skipped: ImportSkipped[];
};

type RawPreview = {
  title: string;
  content: string;
  heading_count: number;
  paragraph_count: number;
  skipped: ImportSkipped[];
};

/**
 * Send one .docx and get back what the system understood.
 *
 * The file is posted as it stands; nothing about its name is used beyond the
 * server checking the extension, and nothing is stored anywhere until the
 * editor accepts the result.
 */
export async function previewImport(file: File): Promise<ImportPreview> {
  const form = new FormData();
  form.append("file", file);
  const raw = await panelRequest<RawPreview>("/api/panel/document-imports", {
    method: "POST",
    body: form,
  });
  return {
    title: raw.title,
    content: raw.content,
    headingCount: raw.heading_count,
    paragraphCount: raw.paragraph_count,
    skipped: raw.skipped,
  };
}
