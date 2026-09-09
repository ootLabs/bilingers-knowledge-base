import PanelGuard from "./PanelGuard";
import PanelNav from "./PanelNav";

// Every /panel route, including the login screen, renders inside this. The
// guard itself decides which of them needs a token; see PanelGuard.tsx.
export default function PanelLayout({ children }: { children: React.ReactNode }) {
  return (
    <section className="panel">
      <PanelGuard>
        {/* Inside the guard, so it is never drawn for somebody on their way to
            the login screen, and it hides itself on that screen. */}
        <PanelNav />
        {children}
      </PanelGuard>
    </section>
  );
}
