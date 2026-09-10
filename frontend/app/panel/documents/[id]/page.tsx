import { notFound } from "next/navigation";

import { getTranslations } from "@/lib/i18n";

import DocumentEditor from "./DocumentEditor";

// `params` is a promise in the App Router as of Next 15, so this stays a server
// component and awaits it before handing the id to the client half.
export default async function DocumentEditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const t = getTranslations();
  const { id } = await params;

  // Digits only, tested before parsing. `Number.parseInt` stops at the first
  // character it cannot read, so "7abc", "7.9" and " 7" all came back as 7 and
  // rendered document 7 under an address that means nothing.
  if (!/^\d+$/.test(id)) {
    notFound();
  }
  const documentId = Number.parseInt(id, 10);
  // Zero and anything the database cannot hold as an id are the 404 screen
  // straight away, rather than a request the backend could only refuse.
  if (documentId < 1 || !Number.isSafeInteger(documentId)) {
    notFound();
  }

  return (
    <>
      <h1>{t("panel.editor.heading")}</h1>
      <DocumentEditor documentId={documentId} />
    </>
  );
}
