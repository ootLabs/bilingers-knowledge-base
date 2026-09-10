import { beforeEach, describe, expect, it, vi } from "vitest";

import { panelRequest } from "./panel-client";
import { previewImport } from "./panel-imports";

vi.mock("./panel-client", () => ({ panelRequest: vi.fn() }));

const request = vi.mocked(panelRequest);

beforeEach(() => {
  request.mockReset();
  request.mockResolvedValue({
    title: "Dwujezycznosc w przedszkolu",
    content: "# Dwujezycznosc w przedszkolu",
    heading_count: 1,
    paragraph_count: 4,
    skipped: [{ reason: "table_not_imported", count: 2 }],
  });
});

describe("previewImport", () => {
  it("posts the file as it stands, so the browser keeps the multipart boundary", async () => {
    const file = new File(["udawany docx"], "rozdzial.docx");

    await previewImport(file);

    const [path, init] = request.mock.calls[0] as [string, { method: string; body: FormData }];
    expect(path).toBe("/api/panel/document-imports");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBe(file);
  });

  it("returns the report in the shape the screen reads", async () => {
    const preview = await previewImport(new File(["x"], "rozdzial.docx"));

    expect(preview).toEqual({
      title: "Dwujezycznosc w przedszkolu",
      content: "# Dwujezycznosc w przedszkolu",
      headingCount: 1,
      paragraphCount: 4,
      skipped: [{ reason: "table_not_imported", count: 2 }],
    });
  });
});
