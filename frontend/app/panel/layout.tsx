import PanelGuard from "./PanelGuard";

// Every /panel route, including the login screen, renders inside this. The
// guard itself decides which of them needs a token; see PanelGuard.tsx.
export default function PanelLayout({ children }: { children: React.ReactNode }) {
  return (
    <section className="panel">
      <PanelGuard>{children}</PanelGuard>
    </section>
  );
}
