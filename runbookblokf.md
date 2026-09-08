# Runbook: baza wiedzy bezpiecznie przechowywana i edytowalna

Zamknięcie BLOKU F (panel fundacji), karty T-82 do T-89.
Stan wyjściowy: gałąź `dev`, commit `6b86ad8` (PR #10), 2026-09-08.

Każdy rozdział to jeden prompt do wklejenia w świeżą sesję. Prompty są samowystarczalne:
nie zakładają, że agent pamięta cokolwiek z poprzedniej. Kolejność jest wymuszona zależnościami,
nie preferencją. Jeden prompt to jedna gałąź i jeden PR do `dev`.

---

## Stan przed startem

Zmergowane w `dev`, nie ruszać:

| Karta | Co stoi w kodzie |
|---|---|
| T-11 | 5 tabel, Alembic `0001`, kolumny danych osobowych oznaczone `info=PERSONAL_DATA` |
| T-12 | `POST /chat` ze streamingiem, placeholdery zamiast modelu |
| T-14 | App Router, warstwa i18n (`lib/i18n/`), tokeny w `globals.css` |
| T-41 | Log kosztów USD i PLN, cennik z pliku, widoki `query_costs*`, `scripts/cost_report.py` |
| T-63 | Stany UI czatu, `components/StatusMessage.tsx`, 404 i 500 |
| T-82 | `panel_users`, role, sesje bearer 12 h, audyt logowań, blokada konta, throttle per IP, `python -m app.cli create-admin` |
| T-84 | `documents` + `document_versions`, statusy, migracja `ebedc16a4160`, indeks „jedna opublikowana wersja” |

Do zrobienia: T-86, T-87, T-85, T-88, T-83, T-89 plus zamknięcie.

Zanim wystartujesz z czymkolwiek:

```bash
git switch dev && git pull --ff-only && docker compose up -d --build
```

```bash
docker compose exec backend alembic current
```

Ma pokazać `ebedc16a4160`. Jeśli pokazuje coś innego, nie zaczynaj, tylko wyjaśnij dlaczego.

### Porządek na Trello, do zrobienia raz, ręcznie

- T-84 przenieść z „W trakcie” do „Zrobione” (jest w PR #10)
- T-63, T-41, T-82 leżą w „Zrobione” z flagą complete = false, odhaczyć
- Po każdym zmergowanym PR z tego runbooka przesunąć odpowiednią kartę, nie na koniec bloku

---

## P1 · Backend dokumentów: serwis, schematy, router

Gałąź `feat/panel-documents-api` z `dev`. Karty T-86 i T-87 (część backendowa). Bez migracji.

```
Pracujesz w repozytorium bilingers-knowledge-base, gałąź dev. Przeczytaj najpierw AGENTS.md,
docs/map/backend.md i docs/conventions.md. Trzymaj się definicji ukończenia z AGENTS.md.

ZADANIE
Warstwa serwisowa i HTTP dla dokumentów bazy wiedzy. Model już istnieje
(backend/app/models/document.py, migracja ebedc16a4160) i nie wolno go zmieniać ani dodawać
nowej migracji.

CO ZBUDOWAĆ
1. backend/app/services/documents.py
   - list_documents(session): dokument plus jego NAJNOWSZA wersja, jednym zapytaniem
     (DISTINCT ON albo LATERAL). Nie pętla po dokumentach, bo lista redaktorki to N plus 1.
   - create_document(session, author, title, content, change_comment): Document plus wersja 1
     w statusie DRAFT.
   - add_version(session, document_id, author, title, content, change_comment): jedyna ścieżka
     edycji. Nowa wersja zawsze DRAFT, nawet gdy poprzednia była PUBLISHED.
   - list_versions(session, document_id), get_version(session, document_id, version_number)
   - restore_version(session, document_id, version_number, author): kopiuje treść starej wersji
     do NOWEJ wersji. Historia nigdy się nie skraca.
   - Wyjątki domenowe w tym samym pliku, wzorem app/services/panel_users.py:
     DocumentNotFound, VersionNotFound, ConcurrentEdit.
   - Każda funkcja wołana przez router dostaje dekorator unavailable_on_database_failure
     z app/services/panel_errors.py.

2. backend/app/schemas/documents.py
   Pydantic na granicy, wzorem schemas/panel.py. title max 500 znaków (tyle ma kolumna),
   content wymagany i niepusty po strip, change_comment opcjonalny.
   ConfigDict(str_strip_whitespace=True), żeby strip działał przed sprawdzeniem długości.
   Znak NUL i znaki sterujące odrzucane jako 422, tak jak adres e-mail w panelu, inaczej
   psycopg zrobi z tego nieuwierzytelnione 500.

3. backend/app/routers/panel_documents.py, prefiks /api/panel/documents,
   zależność current_panel_user (redaktor wystarczy, nie require_admin):
   GET    /api/panel/documents                                 lista z ostatnią wersją
   POST   /api/panel/documents                                 nowy dokument plus wersja 1 (201)
   GET    /api/panel/documents/{id}                            dokument z najnowszą wersją
   GET    /api/panel/documents/{id}/versions                   historia malejąco po numerze
   GET    /api/panel/documents/{id}/versions/{n}               jedna wersja z treścią
   POST   /api/panel/documents/{id}/versions                   zapis edycji jako nowa wersja (201)
   POST   /api/panel/documents/{id}/versions/{n}/restore       nowa wersja z treści starej (201)
   Brak PUT i DELETE na wersji, to nie przeoczenie tylko cała idea modelu.
   detail to klucz, nie zdanie: document_not_found, version_not_found, concurrent_edit.
   Polskie napisy żyją we froncie.
   Dopisz router do importu i include_router w main.py.

NIENARUSZALNE REGUŁY MODELU
- Serwis NIGDY nie wykonuje UPDATE na document_versions. Wersja jest niemutowalna, baza tego
  nie wymusza, trzyma się to wyłącznie na kodzie i na testach.
- Status nowej wersji to zawsze DRAFT. Przejście na PUBLISHED to karta T-88, nie ta.
- author_id bierzesz z current_panel_user, nigdy z ciała żądania.
- knowledge_base_version_id zostaje NULL do czasu publikacji.

NUMEROWANIE WERSJI, JEDYNE TRUDNE MIEJSCE
max(version_number) plus 1 pod SELECT ... FOR UPDATE na wierszu documents.
Przy ponownym odczycie w tej samej sesji użyj populate_existing, inaczej identity map odda stary
obiekt i blokada niczego nie zmieni (ta sama pułapka co przy liczniku logowań w T-82).
IntegrityError na document_versions_document_id_version_number_key tłumacz na ConcurrentEdit
i HTTP 409, nie na 503. Na SQLite (fixture panel_db) with_for_update jest ignorowane, więc test
wyścigu musi być w klasie oznaczonej @pytest.mark.integration.

TESTY, w backend/tests/test_panel_documents.py (test_documents.py ma już ~400 linii,
limit 300 linii na plik obowiązuje, dziel po klasach):
- zapis edycji tworzy drugi wiersz, a pierwszy zostaje bajt w bajt taki sam
- przywrócenie wersji 1 przy trzech istniejących daje wersję 4, historia ma dalej 4 pozycje
- nowa wersja zawsze DRAFT, także gdy poprzednia była PUBLISHED
- token redaktorki A nie potrafi zapisać wersji podpisanej redaktorką B
- brak tokenu to 401, obcy identyfikator to 404, nigdy 500
- lista 20 dokumentów robi stałą liczbę zapytań

DEFINICJA UKOŃCZENIA
docker compose exec backend pytest
docker compose exec backend alembic check   (ma nie zgłosić dryfu, nowej migracji nie ma)
python scripts/check_map.py  oraz  python scripts/check_text.py  zwracają 0
Wiersz w docs/map/backend.md dla KAŻDEGO nowego pliku, w tym samym commicie.
Jeden wpis w docs/log.md, format i limit 5 linii opisane na górze tego pliku.
Commit na gałęzi feat/panel-documents-api, PR do dev.
```

---

## P2 · Front panelu: logowanie i klient API

Gałąź `feat/panel-login-ui` z `dev` po zmergowaniu P1. Domyka T-82 od strony użytkownika.

```
Repozytorium bilingers-knowledge-base, gałąź dev. Przeczytaj AGENTS.md, docs/map/frontend.md
i docs/conventions.md.

ZADANIE
Ekran logowania do panelu fundacji i klient HTTP panelu. Backend jest gotowy
(app/routers/panel_auth.py, sesje bearer z 12-godzinnym wygaśnięciem), nie ma tylko klienta.

CO ZBUDOWAĆ
1. frontend/lib/panel-client.ts, NOWY plik obok api-client.ts, nie rozbudowa tamtego.
   ChatFailure jest domkniętą unią dla ścieżki rodzica, a panel ma inny słownik błędów:
   dochodzi 401, 403 i 409, znika 429. Wspólne zostaje tylko API_URL, importowane
   z api-client.ts, żeby nie było dwóch kopii tego samego fallbacku.
   Każda odpowiedź błędna sprowadzana do klucza ZANIM zobaczy ją komponent. Ciała odpowiedzi
   błędnej nie czytamy i nie pokazujemy.

2. frontend/app/panel/login/page.tsx
   Formularz e-mail plus hasło. Jeden komunikat na KAŻDĄ odmowę (nieznane konto, złe hasło,
   konto zablokowane, konto wyłączone), dokładnie tak jak backend: nie zdradzamy, czy konto
   istnieje. Po sukcesie przekierowanie na /panel/documents.

3. Strażnik trasy: wejście na /panel/* bez ważnego tokenu wraca na /panel/login.
   401 z dowolnego wywołania panelu czyści token i robi to samo.

DECYZJA DO ZAPISANIA
Token trzymamy w sessionStorage i wysyłamy jako Bearer. T-82 świadomie odłożył CSRF i SameSite
do czasu, aż powstanie klient panelu, a to jest ten klient. Ciasteczko HttpOnly jest bezpieczniejsze,
ale wymaga zmiany po stronie backendu. Dopisz wiersz do tabeli decyzji w docs/architecture.md
i zaznacz w docs/log.md, że przejście na ciasteczka jest osobną kartą razem z T-83.

ZASADY
Nazwy tras po angielsku, spójnie z /chat, /quiz, /account. CAŁY tekst na ekranie
w frontend/lib/i18n/locales/pl.ts, odczyt przez getTranslations(). Zero polskich zdań
w komponencie, TypeScript odrzuci niekompletny słownik.
Stany ładowania, błędu i pustki bierz z components/StatusMessage.tsx, nie pisz drugiego.
Tonację niosą obramowanie i pigułka, nie sam kolor tekstu: --color-primary nie przechodzi AA
na białym, to już wiadomo z T-63.

TESTY (plik obok komponentu jako <Name>.test.tsx)
- złe hasło pokazuje ten sam komunikat co nieznane konto
- 503 pokazuje stan awarii, nie stan błędnych danych logowania
- wejście na trasę panelu bez tokenu przekierowuje na logowanie

DEFINICJA UKOŃCZENIA
docker compose exec frontend npm test
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run build
check_map.py i check_text.py zwracają 0, wiersze w docs/map/frontend.md dla nowych plików,
wpis w docs/log.md, PR do dev z gałęzi feat/panel-login-ui.
```

---

## P3 · Lista dokumentów (T-86)

Gałąź `feat/panel-documents-list` z `dev` po P1 i P2.

```
Repozytorium bilingers-knowledge-base, gałąź dev. Przeczytaj AGENTS.md i docs/map/frontend.md.
Backend /api/panel/documents oraz klient lib/panel-client.ts już istnieją.

ZADANIE (karta T-86)
Ekran, na którym redaktorka fundacji ląduje po zalogowaniu: frontend/app/panel/documents/page.tsx.
Jeśli nie znajdzie tu w pięć sekund dokumentu, którego szuka, panel jest martwy i wróci do
wysyłania plików mailem.

ZAKRES
Lista dokumentów z widocznym STATUSEM (szkic, w recenzji, opublikowany, wycofany), datą
ostatniej zmiany i autorem. Wyszukiwanie po tytule, filtrowanie po statusie, sortowanie po dacie.
Akcje: nowy dokument, edytuj, podgląd historii.

CZEGO NIE ROBIMY
Przycisku „wgraj .docx” NIE MA, import to karta T-85 i jeszcze nie istnieje. Nie robimy edytora
(T-87). Nie robimy kolejki luk wiedzy (T-80). Nie robimy publikacji ani wycofania (T-88), więc
statusy inne niż szkic na razie po prostu się nie pojawią i to jest w porządku.

STATUS MA BYĆ WIDOCZNY BEZ KLIKANIA
To główny mechanizm zaufania do tego panelu: redaktorka musi wiedzieć, co widzi rodzic, a co
jeszcze leży w szkicach. Status jako pigułka z obramowaniem, nie jako kolor samego tekstu.

ODBIORCA
Prof. Magdalena i Justyna, nie administratorzy systemów. Zero żargonu, zero identyfikatorów
technicznych na ekranie, żadnego „embedding status: pending”.

Copy po polsku w lib/i18n/locales/pl.ts. Stan pusty, ładowania i błędu z components/StatusMessage.tsx.

TESTY
- pusta baza pokazuje stan pusty z jedną drogą naprzód (utwórz dokument)
- filtr statusu i szukanie po tytule zawężają listę
- 401 wyrzuca na /panel/login

DEFINICJA UKOŃCZENIA jak w poprzednich promptach: npm test, typecheck, build, check_map.py,
check_text.py, wiersze mapy, wpis w docs/log.md, PR do dev.
```

---

## P4 · Edytor i historia wersji (T-87)

Gałąź `feat/panel-documents-editor` z `dev` po P3. To domyka „tworzyć, edytować, wersjonować”.

```
Repozytorium bilingers-knowledge-base, gałąź dev. Przeczytaj AGENTS.md i docs/map/frontend.md.
Endpointy dokumentów i lista już istnieją.

ZADANIE (karta T-87, bez autozapisu)
Serce panelu. Tu fundacja realnie rozwija bazę wiedzy, zamiast wysyłać kolejne wersje pliku
i czekać, aż ktoś je wgra. Pętla z decyzji D2 (pytanie bez odpowiedzi, prof. Magdalena odpowiada,
baza rośnie) domyka się na tym ekranie.

CO ZBUDOWAĆ
- frontend/app/panel/documents/new/page.tsx: nowy dokument (tytuł, treść, komentarz do zmiany)
- frontend/app/panel/documents/[id]/page.tsx: edytor. Zapis tworzy NOWĄ WERSJĘ, nigdy nie
  nadpisuje. Jedno opcjonalne pole „komentarz do zmiany”.
- frontend/app/panel/documents/[id]/history/page.tsx: lista wersji, podgląd starszej,
  porównanie z bieżącą, przywrócenie.

CO MUSI BYĆ JASNE NA EKRANIE
- czy edytujesz SZKIC czy WERSJĘ OPUBLIKOWANĄ, którą właśnie czyta rodzic. Pomyłka tutaj to
  zmiana na produkcji bez świadomości, że się ją robi
- numer edytowanej wersji i data, żeby było widać, że nie patrzysz na cudzy zapis sprzed minuty
- po zapisie komunikat mówiący, co się STAŁO, na przykład: „Zapisano jako wersja 4. Szkic,
  asystent jeszcze z niej nie korzysta”
- 409 (ktoś zapisał w tym samym momencie) pokazuje komunikat i NIE GUBI wpisanej treści

CZEGO NIE ROBIMY
Nie ma publikacji ani reindeksu (T-88). Nie ma edycji współbieżnej wielu osób naraz, trzy konta
i jedna osoba pisząca w danej chwili. Nie ma autozapisu, jawny zapis wystarcza, autozapis wraca
osobną kartą, jeśli redaktorki go poproszą.

Copy po polsku w pl.ts. Porównanie wersji zrób najprościej jak się da (dwie kolumny albo
podświetlone różnice liniowo), bez instalowania biblioteki. Dołożenie zależności to decyzja
do zapisania w docs/architecture.md, nie drive-by npm install.

TESTY
- zapis wywołuje POST na /versions, nie PUT
- ekran historii pokazuje wszystkie wersje po przywróceniu starej, a nie mniej
- 409 zostawia treść w polu

DEFINICJA UKOŃCZENIA jak wyżej. Po zmergowaniu przenieś T-86 i T-87 na Trello do Zrobione
i dopisz w komentarzu, że import .docx i publikacja zostały wyłączone z zakresu.
```

Po P4 zakres „tworzyć, edytować, wersjonować” jest zamknięty. Reszta zamyka milestone.

---

## P5 · Import .docx (T-85)

Gałąź `feat/panel-docx-import` z `dev`. Nie wymaga NDA, testujemy na plikach zrobionych przez nas.

```
Repozytorium bilingers-knowledge-base, gałąź dev. Przeczytaj AGENTS.md, docs/map/backend.md
i docs/map/frontend.md.

ZADANIE (karta T-85)
Redaktorka fundacji pracuje w Wordzie i tak będzie pracować dalej. Materiały przyszły już
w kilku plikach i formatach, w kilku wersjach. Ręczne przeklejanie treści przy każdej
aktualizacji to gwarantowany błąd.

ZAKRES
Wgranie pliku .docx w panelu, wyciągnięcie struktury nagłówek plus tekst, utworzenie dokumentu
w statusie SZKIC. PODGLĄD tego, co system zrozumiał, PRZED zapisem: redaktorka ma zobaczyć wynik
i móc go odrzucić. Import do istniejącego dokumentu tworzy NOWĄ WERSJĘ, nie duplikat.

ODPORNOŚĆ
Zepsute formatowanie w jednym akapicie nie może wywalić całego importu. Raport na koniec:
ile sekcji wczytano, ile pominięto i dlaczego.

CZEGO NIE ROBIMY
Nie poprawiamy merytoryki (decyzja D9). Nie robimy chunkingu ani embeddingów, to karty T-21
i T-22, uruchamiane dopiero przy publikacji (T-88).

RELACJA DO T-20
T-20 to parser materiału źródłowego na potrzeby pierwszego zasilenia bazy, zablokowany przez T-01.
Ta karta to ścieżka STAŁA, używana przez fundację po wdrożeniu. Kod prawdopodobnie wspólny,
moment użycia inny. Jeśli wydzielasz parser do osobnego modułu, powiedz to wprost w docs/log.md.

UWAGI TECHNICZNE
Nowa zależność do czytania .docx idzie do backend/requirements.txt z przypiętą wersją i wierszem
w docs/map/backend.md. Limit rozmiaru pliku i whitelist rozszerzenia po stronie serwera, nie tylko
w formularzu. Nazwa pliku od użytkownika nigdy nie trafia do ścieżki na dysku.

DEFINICJA UKOŃCZENIA jak w poprzednich promptach, plus testy na pliku .docx z podpiętym
załącznikiem testowym (zrobionym przez nas, nie z materiałów fundacji, bo NDA z B-09 jest otwarte).
```

---

## P6 · Publikacja i wycofanie (T-88, część wykonalna)

Gałąź `feat/panel-publish` z `dev`. Uwaga: karta jest częściowo zablokowana.

```
Repozytorium bilingers-knowledge-base, gałąź dev. Przeczytaj AGENTS.md, docs/map/backend.md
i docs/llm/retrieval.md.

ZADANIE (karta T-88, WYŁĄCZNIE część niezależna od RAG)
Ta karta łączy panel z czatem. Do tego momentu panel to CMS bez konsekwencji.
Decyzja D1 mówi, że czat odpowiada wyłącznie z bazy fundacji, a ta karta definiuje, co dokładnie
znaczy „jest w bazie”.

CO ROBIMY TERAZ
- akcja PUBLIKUJ: zmiana statusu wersji na PUBLISHED, podbicie WersjaBazyWiedzy,
  zapisanie knowledge_base_version_id na publikowanej wersji
- akcja WYCOFAJ: zmiana statusu na WITHDRAWN
- publikacja jest ATOMOWA: albo cały dokument wchodzi, albo nie wchodzi wcale, nigdy połowa
- w bazie jest już częściowy indeks unikalny document_versions_one_published_per_document.
  Opublikowanie nowej wersji musi najpierw zdjąć status z poprzedniej, w JEDNEJ transakcji,
  inaczej dostaniesz IntegrityError. To jest główna pułapka tej karty.
- ekran: jedno zdanie po ludzku, „Dokument jest opublikowany, asystent już z niego korzysta”,
  plus data i kto opublikował. Cisza po kliknięciu oznacza, że redaktorka kliknie drugi raz.

CZEGO NIE ROBIMY, BO JEST ZABLOKOWANE
Chunkingu (T-21), embeddingów i wejścia do indeksu (T-22), usuwania chunków przy wycofaniu.
Te karty są zablokowane przez T-01 i B-09. Zamiast tego zostaw JEDEN punkt zaczepienia:
funkcję albo interfejs w app/services/, wołany przy publikacji i wycofaniu, dziś nie robiący nic
poza zapisem do logu. Nie buduj wokół tego abstrakcji na zapas.
Koszt embeddingów (log do T-41) dochodzi razem z T-22, nie teraz.

W docs/log.md napisz WPROST, że karta T-88 jest zamknięta częściowo i czego brakuje, żeby nikt
nie uznał jej za skończoną. Na Trello zostaw kartę otwartą z komentarzem, co zostało zrobione.

DEFINICJA UKOŃCZENIA jak w poprzednich promptach. Testy koniecznie na PostgreSQL
(@pytest.mark.integration) dla przełączania opublikowanej wersji, bo to indeks bazy jest tu regułą.
```

---

## P7 · Dziennik zmian w panelu (T-89)

Gałąź `feat/panel-audit-log` z `dev`. To jest połowa słowa „bezpiecznie” w nazwie milestone'u.

```
Repozytorium bilingers-knowledge-base, gałąź dev. Przeczytaj AGENTS.md i docs/map/backend.md.

ZADANIE (karta T-89)
Baza wiedzy fundacji jest objęta NDA (B-09) i stanowi jedyne realne aktywo fundacji w tym
projekcie. System, który daje do niej dostęp, musi umieć powiedzieć, kto co z nią zrobił.
To jest konkretna, sprawdzalna odpowiedź na pytanie Justyny o bezpieczeństwo z callu 11.08.

ZAKRES
Zapis operacji na dokumentach i kontach: logowanie i wylogowanie, utworzenie, edycja, publikacja,
wycofanie, import pliku, eksport, zmiana uprawnień. Każdy wpis: kto, co, kiedy, na czym.
Dziennik TYLKO DO ODCZYTU, także dla administratora. Prosty widok w panelu z filtrem
po użytkowniku i zakresie dat.

DLACZEGO OSOBNO OD WERSJONOWANIA
Wersje z T-84 mówią, jak zmieniała się TREŚĆ. Dziennik mówi, kto miał do niej DOSTĘP i co
próbował zrobić. To dwa różne pytania i dwie różne odpowiedzi w razie incydentu.

CZEGO NIE ROBIMY
Nie logujemy treści rozmów rodziców, retencja rozmów wisi na RODO (B-07, karta T-113).
Nie dublujemy panel_login_attempts, ta tabela już istnieje i już zapisuje próby logowania,
więc albo z niej czytasz, albo świadomie ją obejmujesz nowym widokiem. Napisz w log.md, co wybrałeś.

UWAGI
Nowa tabela to nowa migracja Alembic. Nie nadawaj revision id ręcznie, wygeneruj
(docker compose exec backend alembic revision -m "..."), potem dopisz operacje.
W historii repo była już kolizja identyfikatorów między gałęziami, sprawdź down_revision.
Zapis do dziennika nie może wywrócić operacji, którą opisuje: jeśli logowanie zdarzenia
zawiedzie, użytkownik ma dostać wynik swojej akcji, a awaria ma trafić do logu serwera.

DEFINICJA UKOŃCZENIA jak w poprzednich promptach, plus pełny cykl
upgrade, downgrade, upgrade w kontenerze.
```

---

## P8 · 2FA dla panelu (T-83)

Gałąź `feat/panel-2fa` z `dev`. Ostatnia karta bloku.

```
Repozytorium bilingers-knowledge-base, gałąź dev. Przeczytaj AGENTS.md, docs/map/backend.md
i app/services/panel_auth.py.

ZADANIE (karta T-83)
Przejęcie konta redaktora to wyciek całej bazy wiedzy fundacji. Nie ma drugiej linii obrony:
kto wejdzie do panelu, ten widzi wszystko.

ZAKRES
TOTP (Google Authenticator, Authy, dowolna aplikacja zgodna ze standardem). Włączenie przy
pierwszym logowaniu, kody zapasowe do wydrukowania, procedura odzyskania dostępu przez
administratora.

DLACZEGO TOTP, A NIE SMS
Zero kosztu, zero zależności od operatora, zero danych osobowych do przechowywania. SMS wymagałby
numeru telefonu redaktorki w naszej bazie, czyli więcej danych osobowych w projekcie, w którym
RODO jest jeszcze nietknięte (B-07).

CZEGO NIE ROBIMY
Nie robimy 2FA dla rodziców. Rodzic ma konto o niskiej wartości i wysokim koszcie tarcia,
2FA zabiłoby konwersję z decyzji D5.

ODBIORCA
Redaktorka fundacji, nie inżynier. Instrukcja włączenia 2FA ma być zrozumiała dla osoby, która
pierwszy raz słyszy słowo TOTP. Copy po polsku, w pl.ts.

UWAGI
Sekret TOTP i kody zapasowe trzymane tak jak hasła, nie jawnie. Kod zapasowy jest jednorazowy.
Próby weryfikacji drugiego składnika podlegają temu samemu limitowaniu co logowanie, inaczej
sześciocyfrowy kod jest do zgadnięcia. Nowa zależność do TOTP z przypiętą wersją.
Jeśli w P2 zapadła decyzja o przejściu z sessionStorage na ciasteczko HttpOnly, to jest moment,
żeby ją wykonać, albo świadomie przesunąć i to zapisać.

DEFINICJA UKOŃCZENIA jak w poprzednich promptach, plus migracja z pełnym cyklem
upgrade, downgrade, upgrade.
```

---

## P9 · Zamknięcie milestone'u

Nie kod, tylko domknięcie. Do zrobienia po zmergowaniu P1 do P8.

```
Repozytorium bilingers-knowledge-base, gałąź dev. Przeczytaj AGENTS.md i docs/log.md
(kilka górnych wpisów).

ZADANIE
Domknij kamień milowy „Baza wiedzy bezpiecznie przechowywana i edytowalna” (BLOK F).

1. Uruchom pełny zestaw bramek na czystym starcie:
   docker compose down -v && docker compose up -d --build
   docker compose exec backend pytest
   docker compose exec frontend npm test
   docker compose exec frontend npm run build
   python scripts/smoke_test.py
   python scripts/check_map.py
   python scripts/check_text.py

2. Zaktualizuj dokumentację, bo zmieniła się STRUKTURA systemu, nie tylko kod:
   - docs/architecture.md: panel jako moduł w tabeli modułów, decyzje z P2 i P6
   - docs/map/backend.md i docs/map/frontend.md: kompletne, sprawdzone skryptem
   - docs/llm/knowledge-base.md: opisz, co teraz ISTNIEJE (dokumenty, wersje, statusy),
     a nie co było planowane
   - docs/log.md: jeden wpis domykający blok, maks 5 linii

3. Napisz krótkie podsumowanie dla fundacji, po polsku, bez żargonu, na trzy pytania:
   co redaktorka może teraz zrobić sama, czego jeszcze nie może i dlaczego, co jest potrzebne
   od fundacji, żeby ruszyć dalej (T-01, B-09, B-07). Osobny plik, nie commit do repo.

4. Wypisz, co z BLOKU F zostało domknięte tylko częściowo (co najmniej T-88) i co dokładnie
   zostało, żeby nikt nie uznał milestone'u za pełniejszy niż jest.

Nie wypuszczaj release'u do main bez wyraźnej decyzji człowieka.
```

---

## Reguły wspólne dla wszystkich promptów

Powtarzane w każdym z osobna, bo sesje są niezależne, ale warto mieć je też w jednym miejscu:

- **Repozytorium po angielsku**, copy dla użytkownika po polsku, chat w dowolnym języku
- **Zero myślnika i półpauzy** gdziekolwiek, `scripts/check_text.py` blokuje commit
- **Mapa przed gruntowaniem:** nowy, przeniesiony lub usunięty plik zmienia wiersz w `docs/map/` w tym samym commicie
- **Brak autorstwa AI** w commitach, PR-ach, kodzie i dokumentach
- **Gałąź z `dev`, PR do `dev`.** `main` dostaje wyłącznie release albo `hotfix/`
- **Plik ponad ~300 linii albo robiący dwie rzeczy** dzieli się, refaktor idzie osobnym commitem
- Zablokowane karty (`T-21`, `T-22`, `T-01`, `B-09`, `B-07`) nie są do obejścia sprytem, tylko do nazwania
