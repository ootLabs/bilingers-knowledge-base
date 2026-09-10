// The change journal's own vocabulary (T-89), which is most of what the
// panel's copy weighs: an action name for every event the backend can
// record, a reason for every way a login can be refused, and the keys the
// detail column arrives as. Split out of `panel.ts` when that slice passed
// the size limit; it is nested back in there as `audit`, so the shape the
// registry types against is unchanged.
const journal = {
  heading: "Dziennik zmian",
  lead: "Kto i kiedy pracował przy bazie wiedzy. Dziennik jest tylko do odczytu, nikt nie może w nim niczego poprawić ani usunąć.",
  actorLabel: "Adres e-mail osoby",
  sinceLabel: "Od dnia",
  untilLabel: "Do dnia",
  apply: "Pokaż",
  applying: "Wczytujemy...",
  // Action keys come from the API (app/models/audit.py), hence snake_case.
  actions: {
    login_succeeded: "Zalogowanie do panelu",
    login_failed: "Nieudana próba zalogowania",
    logged_out: "Wylogowanie z panelu",
    document_created: "Utworzenie dokumentu",
    document_version_saved: "Zapisanie nowej wersji",
    document_version_restored: "Przywrócenie starszej wersji",
    document_imported: "Wczytanie pliku .docx",
    document_published: "Opublikowanie wersji",
    document_withdrawn: "Wycofanie wersji z publikacji",
    account_created: "Utworzenie konta w panelu",
    account_changed: "Zmiana uprawnień konta",
    password_reset_issued: "Wydanie kodu do ustawienia hasła",
    two_factor_enabled: "Włączenie dodatkowego zabezpieczenia",
    two_factor_disabled: "Wyłączenie dodatkowego zabezpieczenia",
    two_factor_reset: "Skasowanie dodatkowego zabezpieczenia przez administratora",
  },
  // Why a login was refused, straight from `LoginFailure` in
  // app/services/panel_login_audit.py. A closed set, so every one of them is
  // translated: without this the journal reads "bad_password" on the one
  // screen ruled to show no technical identifiers.
  reasons: {
    unknown_account: "nie ma takiego konta",
    bad_password: "błędne hasło",
    no_password_set: "konto nie ma jeszcze ustawionego hasła",
    inactive_account: "konto wyłączone",
    locked_account: "konto tymczasowo zablokowane",
    ip_throttled: "za dużo prób z tego miejsca",
    second_factor_required: "zabrakło kodu z aplikacji",
    bad_second_factor: "błędny kod z aplikacji",
  },
  // Event details arrive as `key=value` pairs (app/models/audit.py). The key
  // is translated; a number is language neutral and passes through.
  details: {
    version: "wersja",
    to: "na wersję",
    bytes: "bajtów",
    headings: "nagłówków",
    role: "rola",
    active: "konto czynne",
  },
  values: {
    admin: "administrator",
    editor: "redaktorka",
    true: "tak",
    false: "nie",
  },
  loading: {
    title: "Wczytujemy dziennik",
    description: "To potrwa moment.",
  },
  empty: {
    title: "Brak zdarzeń w tym zakresie",
    description: "Zmień zakres dat albo wyczyść adres e-mail, żeby zobaczyć więcej.",
  },
} as const;

export default journal;
