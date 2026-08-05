const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  return (
    <main>
      <h1>Bilingers</h1>
      <p>Inteligentna baza wiedzy o dwujęzyczności.</p>
      <p style={{ color: "var(--muted)" }}>
        Szkielet projektu. API: <code>{API_URL}</code>
      </p>
    </main>
  );
}
