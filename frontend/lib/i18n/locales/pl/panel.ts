// The foundation's panel. Written for an editor, not for a systems
// administrator: no technical identifiers, no jargon, and every message says
// what happened and what to do about it.
//
// Split from the parent-facing half when the dictionary passed the size
// limit. Nothing here is ever read by a parent and nothing there by the
// foundation, which is why this is the seam.
import journal from "./journal";

const panel = {
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
  // Failure keys in snake_case, like `errors.*` in the parent half: they come
  // from the API contract (lib/panel-client.ts), not from our naming.
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
    // The size named in the copy is the default `DOCX_IMPORT_MAX_BYTES` (5 MB),
    // which `import.fileHint` now states up front as well. Without this entry
    // the import's 413 degraded to `unreachable`, so an oversized file told the
    // editor to check an internet connection that was working perfectly.
    file_too_large: {
      title: "Ten plik jest za duży",
      description:
        "Panel wczytuje pliki .docx do 5 MB. Podziel materiał na rozdziały albo usuń z pliku obrazy i wgraj go jeszcze raz.",
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
  // The document's state, legible without clicking anything. This is the
  // panel's main trust mechanism: an editor has to know what a parent sees and
  // what is still a draft. The keys come straight from the API.
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
    // A document's state is not its newest version's. After a save, parents
    // go on reading the older published version, and that has to be visible
    // without opening anything.
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
  // The braces are placeholders for numbers and dates, filled by `fill()` in
  // lib/i18n. The whole sentence stays here because Polish inflects, and
  // gluing one together from fragments in a component gets the grammar wrong.
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
    fileHint: "Tylko pliki .docx z Worda, do 5 MB. Tabele i obrazy nie są wczytywane.",
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
  // The journal's vocabulary is its own slice; see journal.ts.
  audit: journal,
  // The second factor, written for somebody hearing the term for the first
  // time: the words "TOTP" and "secret" appear nowhere. There is an app, there
  // is a key, and there are backup codes on paper.
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
} as const;

export default panel;
