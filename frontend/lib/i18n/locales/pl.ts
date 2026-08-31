// Polish dictionary, the only active locale (see docs/llm/i18n.md).
// A second locale file must export the same shape: translations.ts types
// its registry against this object, so a partial translation fails
// `npm run typecheck` instead of silently falling back to the key.
const pl = {
  common: {
    productName: "Bilingers",
    tagline: "Inteligentna baza wiedzy o dwujęzyczności",
  },
  nav: {
    ariaLabel: "Główna nawigacja",
    home: "Strona główna",
    chat: "Czat",
    quiz: "Quiz",
    account: "Konto",
  },
  landing: {
    heading: "Bilingers",
    description: "Inteligentna baza wiedzy o dwujęzyczności.",
    scaffoldNote: "Szkielet projektu. API:",
    cta: "Przejdź do czatu",
  },
  chat: {
    heading: "Czat",
    placeholder: "Rozmowa z asystentem pojawi się tutaj wkrótce.",
  },
  quiz: {
    heading: "Quiz",
    placeholder: "Quiz sprawdzający wiedzę pojawi się tutaj wkrótce.",
  },
  account: {
    heading: "Konto",
    placeholder: "Zarządzanie kontem pojawi się tutaj wkrótce.",
  },
} as const;

export default pl;
