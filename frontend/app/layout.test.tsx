import { describe, expect, it } from "vitest";

import RootLayout, { metadata } from "./layout";

// The layout renders <html> and <body>, which cannot be mounted inside a test
// container, so the returned element tree is inspected directly instead.
describe("root layout", () => {
  it("declares Polish as the document language", () => {
    const element = RootLayout({ children: null }) as React.ReactElement<{
      lang: string;
    }>;
    expect(element.props.lang).toBe("pl");
  });

  it("renders the site header before the page content in the body", () => {
    const child = "content";
    const element = RootLayout({ children: child }) as React.ReactElement<{
      children: React.ReactElement<{ children: React.ReactNode[] }>;
    }>;
    const bodyChildren = element.props.children.props.children;
    expect(bodyChildren[1]).toBe(child);
  });

  it("sets metadata used for the browser tab and link previews", () => {
    expect(metadata.title).toBe("Bilingers");
    expect(metadata.description).toMatch(/dwuj/i);
  });
});
