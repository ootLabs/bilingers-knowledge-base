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
  const documentId = Number.parseInt(id, 10);

  // An address that is not a number never reaches the backend as a request that
  // could only answer 404 anyway; it is the 404 screen straight away.
  if (!Number.isInteger(documentId) || documentId < 1) {
    notFound();
  }

  return (
    <>
      <h1>{t("panel.editor.heading")}</h1>
      <DocumentEditor documentId={documentId} />
    </>
  );
}
