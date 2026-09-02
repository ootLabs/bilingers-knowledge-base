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
    inputLabel: "Twoje pytanie",
    inputPlaceholder: "Na przykład: od kiedy mówić do dziecka w dwóch językach?",
    submit: "Zapytaj",
    answerLabel: "Odpowiedź asystenta",
    typing: "Asystent pisze",
    empty: {
      // Deliberately just an empty state. The assistant's self-description
      // and the suggested opening questions Justyna asked for belong to the
      // entry screen designed in T-61, which is still awaiting review;
      // writing them here would be guessing at copy someone else owns.
      title: "Nie zadano jeszcze pytania",
      description:
        "Napisz pytanie o wychowanie dziecka w dwóch językach. Odpowiedź pojawi się tutaj.",
    },
    // snake_case against the camelCase used everywhere else in this file,
    // because these are not ours to name: the backend streams these exact
    // dot paths one per line (see `stream_placeholder_answer`) and the
    // frontend resolves them. Renaming one here silently drops a fragment
    // of the answer.
    placeholder_answer: {
      chunk_0: "To jest odpowiedź zastępcza. ",
      chunk_1: "Asystent nie korzysta jeszcze z bazy wiedzy fundacji ",
      chunk_2: "ani z żadnego modelu językowego. ",
      chunk_3: "Sprawdzamy tutaj wyłącznie to, ",
      chunk_4: "czy odpowiedź pojawia się poprawnie fragment po fragmencie. ",
      chunk_5: "Prawdziwe odpowiedzi przyjdą w kolejnym etapie pracy.",
    },
  },
  // Keyed by the failure vocabulary in lib/api-client.ts, which in turn
  // mirrors the backend's `detail` keys. Same snake_case reasoning as above:
  // these names come from the API contract, not from this file.
  errors: {
    retry: "Spróbuj ponownie",
    unreachable: {
      title: "Nie udało się połączyć",
      description:
        "Nie mogliśmy teraz połączyć się z asystentem. Sprawdź połączenie z internetem i spróbuj ponownie.",
    },
    database_unavailable: {
      title: "Asystent jest chwilowo niedostępny",
      description: "To krótka przerwa po naszej stronie. Spróbuj ponownie za moment.",
    },
    invalid_question: {
      title: "Nie możemy przyjąć tego pytania",
      description: "Wpisz je jeszcze raz, krótszym i prostszym zdaniem.",
    },
    // Not phrased as a fault and not phrased in the second person singular
    // with a gendered verb form: T-61 calls this the main conversion point
    // of the whole funnel, reached at peak interest, so it explains the
    // benefit instead of telling the parent off.
    limit_reached: {
      title: "To już wszystkie pytania na teraz",
      description:
        "Załóż darmowe konto, żeby pytać dalej i wracać do swoich rozmów. Zajmuje to chwilę i nic nie kosztuje.",
      action: "Załóż darmowe konto",
    },
  },
  notFound: {
    heading: "Nie ma takiej strony",
    title: "Sprawdź adres",
    description: "Strona, której szukasz, mogła zmienić adres albo nigdy jej tu nie było.",
    action: "Wróć na stronę główną",
  },
  serverError: {
    heading: "Coś poszło nie tak",
    title: "Nie udało się wyświetlić tej strony",
    description: "To błąd po naszej stronie, nie po twojej. Spróbuj otworzyć stronę ponownie.",
    retry: "Wyświetl ponownie",
    action: "Wróć na stronę główną",
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
