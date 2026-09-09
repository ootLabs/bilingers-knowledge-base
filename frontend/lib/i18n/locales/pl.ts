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
      // Its own label rather than the shared "Spróbuj ponownie": the backend
      // refused this exact wording, so the only thing that helps is writing
      // it again, and the button has to say so.
      action: "Popraw pytanie",
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
  // Panel fundacji. Odbiorcą jest redaktorka, nie administrator systemu:
  // żadnych identyfikatorów technicznych, żadnego żargonu, każdy komunikat
  // mówi co się stało i co z tym zrobić.
  panel: {
    nav: {
      ariaLabel: "Nawigacja panelu",
      documents: "Dokumenty",
      security: "Bezpieczeństwo",
      audit: "Dziennik zmian",
      signOut: "Wyloguj się",
      signingOut: "Wylogowujemy...",
    },
    checking: {
      title: "Sprawdzamy dostęp",
      description: "Za chwilę otworzymy panel albo poprosimy o zalogowanie.",
    },
    // Klucze błędów w snake_case, tak jak w errors.* wyżej: przychodzą
    // z kontraktu API (lib/panel-client.ts), nie z naszego nazewnictwa.
    errors: {
      retry: "Spróbuj ponownie",
      invalid_credentials: {
        title: "Nie udało się zalogować",
        description:
          "Adres e-mail lub hasło się nie zgadzają. Jeśli nie pamiętasz hasła, poproś administratora o nowy jednorazowy kod dostępu.",
      },
      forbidden: {
        title: "To działanie wymaga innych uprawnień",
        description: "Poproś administratora panelu, żeby wykonał je za ciebie.",
      },
      not_found: {
        title: "Nie ma takiego dokumentu",
        description: "Mógł zostać usunięty albo adres jest nieaktualny. Wróć do listy dokumentów.",
      },
      conflict: {
        title: "Ktoś zapisał zmiany przed tobą",
        description:
          "Twój tekst jest bezpieczny i dalej jest w oknie edycji. Otwórz dokument w nowej karcie, zobacz co się zmieniło, a potem zapisz swoją wersję jeszcze raz.",
      },
      invalid_input: {
        title: "Nie możemy zapisać tego w tej postaci",
        description: "Sprawdź, czy tytuł i treść są wypełnione, a tytuł mieści się w jednej linii.",
      },
      too_many_attempts: {
        title: "Za dużo prób z tego miejsca",
        description: "Odczekaj kilka minut i spróbuj zalogować się ponownie.",
      },
      invalid_code: {
        title: "Ten kod się nie zgadza",
        description:
          "Sprawdź, czy przepisujesz aktualny kod z aplikacji: zmienia się co pół minuty. Możesz też użyć jednego z kodów zapasowych.",
      },
      second_factor_required: {
        title: "Potrzebujemy jeszcze kodu",
        description:
          "To konto ma włączone dodatkowe zabezpieczenie. Wpisz kod z aplikacji w telefonie albo jeden ze swoich kodów zapasowych.",
      },
      two_factor_not_configured: {
        title: "Nie możemy teraz sprawdzić kodu",
        description:
          "To usterka po naszej stronie, nie po twojej. Napisz do osoby, która opiekuje się systemem.",
      },
      database_unavailable: {
        title: "Panel jest chwilowo niedostępny",
        description: "To krótka przerwa po naszej stronie. Spróbuj ponownie za moment.",
      },
      unreachable: {
        title: "Nie udało się połączyć",
        description: "Sprawdź połączenie z internetem i spróbuj ponownie.",
      },
    },
    login: {
      heading: "Panel fundacji",
      lead: "Zaloguj się, żeby pracować nad bazą wiedzy.",
      emailLabel: "Adres e-mail",
      passwordLabel: "Hasło",
      submit: "Zaloguj się",
      submitting: "Logowanie...",
      codeLabel: "Kod z aplikacji",
      codeHint:
        "Sześciocyfrowy kod z aplikacji w telefonie. Jeśli nie masz telefonu pod ręką, wpisz jeden ze swoich kodów zapasowych.",
    },
    // Stan dokumentu widoczny bez klikania. To główny mechanizm zaufania do
    // panelu: redaktorka musi wiedzieć, co widzi rodzic, a co leży w szkicach.
    // Klucze po angielsku, bo przychodzą wprost z API.
    status: {
      draft: "Szkic",
      in_review: "W recenzji",
      published: "Opublikowany",
      withdrawn: "Wycofany",
    },
    documents: {
      heading: "Dokumenty",
      lead: "Tu powstaje baza wiedzy. Każdy zapis tworzy nową wersję, więc nic nie ginie, a asystent korzysta wyłącznie z dokumentów opublikowanych.",
      create: "Nowy dokument",
      import: "Wgraj plik .docx",
      edit: "Edytuj",
      history: "Historia zmian",
      searchLabel: "Szukaj w tytułach",
      searchPlaceholder: "Na przykład: przedszkole",
      statusLabel: "Stan dokumentu",
      statusAll: "Wszystkie",
      orderLabel: "Kolejność",
      orderNewest: "Od najnowszych zmian",
      orderOldest: "Od najstarszych zmian",
      changedOn: "Zmieniono",
      changedBy: "przez",
      // Stan dokumentu to nie stan najnowszej wersji. Po zapisie edycji
      // rodzice dalej czytają starszą, opublikowaną wersję, i to musi być
      // widoczne bez klikania.
      parentsRead: "Rodzice czytają wersję {version}.",
      draftWaiting: "Nowsze zmiany czekają w szkicu (wersja {version}).",
      parentsReadTitle: "Pod tytułem: {title}.",
      clearFilters: "Wyczyść filtry",
      loading: {
        title: "Wczytujemy dokumenty",
        description: "To potrwa moment.",
      },
      empty: {
        title: "Nie ma jeszcze żadnego dokumentu",
        description:
          "Baza wiedzy jest pusta. Zacznij od pierwszego dokumentu, na przykład od jednego rozdziału materiału, który już masz.",
      },
      noMatches: {
        title: "Nic nie pasuje do tych warunków",
        description: "Zmień szukane słowa albo pokaż dokumenty we wszystkich stanach.",
      },
    },
    // Nawiasy klamrowe to miejsca na liczby i daty, podstawia je fill()
    // z lib/i18n. Całe zdanie zostaje tutaj, bo polski się odmienia i sklejanie
    // go z kawałków w komponencie kończy się błędem gramatycznym.
    editor: {
      heading: "Edycja dokumentu",
      createHeading: "Nowy dokument",
      createLead:
        "Dokument zapisze się jako szkic. Asystent zacznie z niego korzystać dopiero po opublikowaniu.",
      backToList: "Wróć do listy dokumentów",
      openHistory: "Historia zmian",
      titleLabel: "Tytuł",
      contentLabel: "Treść",
      commentLabel: "Komentarz do zmiany (opcjonalnie)",
      commentHint: "Jedno zdanie o tym, co zmieniasz. Zobaczy je każdy, kto otworzy historię.",
      createSubmit: "Utwórz dokument",
      saveSubmit: "Zapisz jako nową wersję",
      saving: "Zapisujemy...",
      editing: "Edytujesz wersję {version} z dnia {date}",
      parentsReadOther:
        "Rodzice czytają teraz wersję {version}. Ten zapis jej nie zmieni, dopóki nie opublikujesz nowej.",
      nothingPublished:
        "Żadna wersja tego dokumentu nie jest opublikowana, więc rodzice go jeszcze nie widzą.",
      lastSavedBy: "Ostatni zapis: {author}",
      editingPublished:
        "Uwaga: to jest wersja opublikowana, rodzice czytają ją w tej chwili. Twój zapis utworzy nowy szkic i nie zmieni tego, co widzą, dopóki go nie opublikujesz.",
      saved: "Zapisano jako wersja {version}. To szkic, asystent jeszcze z niego nie korzysta.",
      loading: {
        title: "Otwieramy dokument",
        description: "To potrwa moment.",
      },
    },
    history: {
      heading: "Historia zmian",
      lead: "Każdy zapis to osobna wersja. Nic nie znika, a starszą treść można przywrócić.",
      backToEditor: "Wróć do edycji",
      versionLabel: "Wersja {version}",
      currentMarker: "Wersja bieżąca",
      preview: "Porównaj z bieżącą",
      restore: "Przywróć tę treść",
      restoreComment: "Przywrócono treść z wersji {version}",
      restored:
        "Przywrócono treść jako wersja {version}. Starsze wersje zostały na miejscu, nic nie zniknęło.",
      comparingHeading: "Wersja {version} w porównaniu z bieżącą wersją {current}",
      comparingHint:
        "Linie oznaczone plusem są w wersji bieżącej, linie z minusem były w wersji starszej.",
      diff: {
        added: "Dodano:",
        removed: "Usunięto:",
      },
      loading: {
        title: "Wczytujemy historię",
        description: "To potrwa moment.",
      },
    },
    import: {
      heading: "Wgraj plik .docx",
      lead: "Pokażemy, co system odczytał z pliku, zanim cokolwiek zapiszemy. Jeśli coś się nie zgadza, po prostu odrzuć wynik.",
      fileLabel: "Plik z materiałem",
      fileHint: "Tylko pliki .docx z Worda. Tabele i obrazy nie są wczytywane.",
      read: "Odczytaj plik",
      reading: "Czytamy plik...",
      previewHeading: "Co odczytaliśmy",
      report: "Nagłówki: {headings}. Akapity: {paragraphs}.",
      nothingSkipped: "Nic nie zostało pominięte.",
      skipped: {
        unreadable_paragraph: "Pominięto akapity, których nie dało się odczytać: {count}.",
        table_not_imported: "Pominięto tabele, ta wersja panelu ich nie wczytuje: {count}.",
      },
      titleLabel: "Tytuł dokumentu",
      targetLabel: "Gdzie zapisać",
      targetNew: "Jako nowy dokument",
      targetHint:
        "Wybranie istniejącego dokumentu dopisze treść jako jego kolejną wersję, nie utworzy kopii.",
      contentHeading: "Podgląd treści",
      accept: "Zapisz jako szkic",
      reject: "Odrzuć i zacznij od nowa",
      changeComment: "Treść wczytana z pliku .docx",
    },
    publish: {
      heading: "Publikacja",
      isPublished: "Dokument jest opublikowany, asystent już z niego korzysta.",
      isNotPublished:
        "Ta wersja nie jest opublikowana. Asystent na razie z niej nie korzysta i rodzice jej nie widzą.",
      otherIsPublished:
        "Opublikowana jest wersja {version}. To ją czytają rodzice, dopóki nie opublikujesz tej.",
      noneIsPublished: "Żadna wersja tego dokumentu nie jest opublikowana.",
      publishedOn: "Opublikowano {date}, zrobiła to osoba: {author}.",
      unknownPublisher: "konto już nieistniejące",
      publish: "Opublikuj tę wersję",
      withdraw: "Wycofaj z publikacji",
      working: "Chwileczkę...",
    },
    audit: {
      heading: "Dziennik zmian",
      lead: "Kto i kiedy pracował przy bazie wiedzy. Dziennik jest tylko do odczytu, nikt nie może w nim niczego poprawić ani usunąć.",
      actorLabel: "Adres e-mail osoby",
      sinceLabel: "Od dnia",
      untilLabel: "Do dnia",
      apply: "Pokaż",
      // Klucze zdarzeń przychodzą z API (app/models/audit.py), stąd snake_case.
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
      loading: {
        title: "Wczytujemy dziennik",
        description: "To potrwa moment.",
      },
      empty: {
        title: "Brak zdarzeń w tym zakresie",
        description: "Zmień zakres dat albo wyczyść adres e-mail, żeby zobaczyć więcej.",
      },
    },
    // Logowanie dwuskładnikowe. Odbiorcą jest osoba, która pierwszy raz słyszy
    // to określenie, więc nigdzie nie pada słowo "TOTP" ani "sekret": jest
    // aplikacja, jest klucz, są kody zapasowe na papierze.
    twoFactor: {
      heading: "Dodatkowe zabezpieczenie logowania",
      lead: "Poza hasłem panel może prosić o sześciocyfrowy kod z aplikacji w telefonie. Dzięki temu samo poznanie hasła nie wystarczy, żeby wejść do bazy wiedzy fundacji.",
      isOff: "Dodatkowe zabezpieczenie jest wyłączone. Do zalogowania wystarczy hasło.",
      isOn: "Dodatkowe zabezpieczenie jest włączone. Przy logowaniu poprosimy o kod z aplikacji.",
      step1:
        "Zainstaluj w telefonie darmową aplikację z kodami, na przykład Google Authenticator lub Authy.",
      step2: "Kliknij przycisk poniżej. Pokażemy klucz, który wpiszesz w aplikacji.",
      step3:
        "Aplikacja zacznie pokazywać sześciocyfrowy kod, który zmienia się co pół minuty. Przepisz go tutaj, żeby potwierdzić, że wszystko działa.",
      start: "Włącz dodatkowe zabezpieczenie",
      keyHeading: "Klucz do wpisania w aplikacji",
      keyLead:
        "W aplikacji wybierz dodanie konta i opcję wpisania klucza ręcznie, a potem przepisz poniższe znaki. Wielkość liter nie ma znaczenia.",
      confirmLabel: "Kod z aplikacji",
      confirm: "Potwierdź i włącz",
      codeLabel: "Kod z aplikacji lub kod zapasowy",
      turnOff: "Wyłącz dodatkowe zabezpieczenie",
      codesHeading: "Kody zapasowe do wydrukowania",
      codesLead:
        "Każdego z tych kodów można użyć raz, zamiast kodu z aplikacji. Wydrukuj je albo zapisz w bezpiecznym miejscu, osobno od telefonu.",
      codesWarning:
        "Pokazujemy je tylko teraz. Po zamknięciu tego ekranu nie da się ich odczytać ponownie, ale administrator może wyłączyć zabezpieczenie i włączyć je od nowa.",
      codesSaved: "Zapisałam kody, przejdź dalej",
      codesLeft: "Pozostało niewykorzystanych kodów zapasowych: {count}.",
      loading: {
        title: "Sprawdzamy ustawienia",
        description: "To potrwa moment.",
      },
    },
  },
} as const;

export default pl;
