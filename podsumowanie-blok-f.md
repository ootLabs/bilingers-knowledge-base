# Baza wiedzy: co już działa, a czego jeszcze nie ma

Podsumowanie dla Fundacji Dwujęzyczna Przyszłość, stan na 8 września 2026.
Bez żargonu, na trzy pytania.

> Ten plik jest poza repozytorium kodu (nie trafia do commita). Jest do przeczytania i przesłania dalej.

---

## 1. Co redaktorka może teraz zrobić sama

Wszystko poniżej dzieje się w panelu, przez przeglądarkę, bez udziału programisty.

**Zalogować się na własne konto.** Konto zakłada administrator i przekazuje jednorazowy kod, którym redaktorka sama ustawia hasło. Nikt poza nią tego hasła nie zna. Można też włączyć dodatkowe zabezpieczenie: przy logowaniu panel poprosi wtedy o sześciocyfrowy kod z darmowej aplikacji w telefonie. Do tego dostaje się komplet kodów zapasowych do wydrukowania, na wypadek zgubienia telefonu.

**Zobaczyć całą bazę wiedzy na jednym ekranie.** Lista dokumentów pokazuje przy każdym tytule, w jakim jest stanie (szkic, w recenzji, opublikowany, wycofany), kiedy był ostatnio zmieniany i przez kogo. Można szukać po tytule, filtrować po stanie i zmieniać kolejność. To, co czyta rodzic, widać bez otwierania czegokolwiek.

**Napisać nowy dokument i redagować istniejące.** Każdy zapis tworzy nową wersję. Poprzednia zostaje nietknięta, więc nic nie ginie i nic nie da się przypadkiem nadpisać. Przy zapisie można dopisać jedno zdanie o tym, co się zmieniło.

**Cofnąć się do starszej wersji.** Historia pokazuje wszystkie wersje z datą i autorem. Można obejrzeć starszą, porównać ją z bieżącą linia po linii i przywrócić jej treść. Przywrócenie tworzy kolejną wersję, więc historia nigdy się nie skraca: nawet po cofnięciu widać, co było wcześniej.

**Wgrać plik .docx z Worda.** System czyta z pliku nagłówki i tekst, a potem pokazuje, co z niego zrozumiał, ZANIM cokolwiek zapisze. Jeśli coś wygląda źle, wystarczy odrzucić wynik. Do raportu trafia informacja, ile sekcji wczytano i co zostało pominięte (na przykład tabele, których ta wersja jeszcze nie czyta). Wgranie do istniejącego dokumentu dopisuje kolejną wersję, a nie tworzy drugiej kopii pod podobnym tytułem.

**Opublikować dokument i wycofać go z publikacji.** Publikacja to osobna, świadoma decyzja: sam zapis nigdy nie zmienia tego, co widzi rodzic. Po opublikowaniu na ekranie jest zdanie po ludzku, plus data i nazwisko osoby, która to zrobiła.

**Sprawdzić, kto co robił.** Dziennik zmian zapisuje logowania, wylogowania, nieudane próby logowania, utworzenie i edycję dokumentu, wgranie pliku, publikację, wycofanie, zmiany uprawnień i włączenie lub wyłączenie dodatkowego zabezpieczenia. Można filtrować po osobie i po zakresie dat. Dziennika nie da się zmienić ani skasować, także administratorowi: to była konkretna odpowiedź na pytanie o bezpieczeństwo z rozmowy 11 sierpnia.

---

## 2. Czego jeszcze nie może i dlaczego

**Baza jest pusta.** System do redagowania jest gotowy, ale nie ma w nim jeszcze ani jednego dokumentu fundacji. Czekamy na materiał (zadanie T-01) i na podpisanie NDA (B-09).

**Opublikowany dokument nie trafia jeszcze do asystenta.** To najważniejsze zastrzeżenie w całym podsumowaniu. Publikacja dziś oznacza: dokument ma stan "opublikowany", jest widoczny w panelu i wiadomo, kto go opublikował. Nie oznacza jeszcze, że czat zacznie z niego odpowiadać. Brakującego elementu (podziału tekstu na fragmenty i wczytania ich do wyszukiwarki, zadania T-21 i T-22) nie da się zbudować, dopóki nie ma prawdziwej treści i podpisanego NDA. Czat nadal odpowiada tekstem zastępczym.

**Nie ma podziału uprawnień między redaktorkami.** Każde konto w panelu widzi i może edytować każdy dokument. Przy trzech osobach to świadoma decyzja, a nie przeoczenie. Gdyby kont miało być więcej, trzeba to zmienić.

**Nie ma eksportu bazy do pliku.** Nikt o niego nie prosił, a nie ma jeszcze czego eksportować.

**Nie ma kodu QR przy włączaniu dodatkowego zabezpieczenia.** Klucz do aplikacji trzeba raz przepisać ręcznie. Jeśli okaże się to uciążliwe, dołożymy kod QR.

**Nie ma automatycznego zapisu w edytorze.** Zapis trzeba kliknąć. Zrobiliśmy tak celowo: automatyczny zapis w systemie, który liczy wersje, tworzyłby nową wersję po każdej przerwie w pisaniu. Jeśli redaktorki uznają, że wolą inaczej, wrócimy do tego.

**Tabele i obrazy z plików .docx nie są wczytywane.** System mówi o tym wprost w raporcie po wgraniu pliku, żeby nikt nie odkrył braku po miesiącach.

---

## 3. Czego potrzebujemy od fundacji, żeby ruszyć dalej

Trzy rzeczy, w kolejności od najpilniejszej.

**1. Materiał do pierwszego zasilenia bazy (T-01).** Pliki .docx z treścią, w takiej formie, w jakiej są. Nie trzeba ich przygotowywać, poprawiać ani ujednolicać: system pokazuje, co zrozumiał, i pozwala poprawić przed zapisem. To odblokowuje wszystko pozostałe, łącznie z tym, żeby czat w ogóle zaczął odpowiadać merytorycznie.

**2. Podpisana umowa o poufności (B-09).** Baza wiedzy to jedyne realne aktywo fundacji w tym projekcie. Dopóki NDA jest otwarte, nie pracujemy na prawdziwej treści, także w testach.

**3. Decyzje dotyczące danych osobowych (B-07, RODO).** Trzy pytania, na które potrzebujemy odpowiedzi, żeby dokończyć część prawną:
- Jak długo przechowujemy rozmowy rodziców z asystentem?
- Jak długo przechowujemy dziennik zmian i próby logowania do panelu?
- Na jaki adres i w jakiej formie mają trafiać pytania, na które baza nie zna odpowiedzi?

Przydatna, choć nie blokująca, byłaby też jedna decyzja organizacyjna: **kto w fundacji publikuje zmianę i jak często**. System już zapisuje, kto to zrobił; brakuje ustalenia, kto ma to robić.

---

## Co można zobaczyć od razu

Panel jest gotowy do pokazania na pustej bazie: logowanie, tworzenie dokumentu, zapis kolejnych wersji, historia z porównaniem, wgranie przykładowego pliku .docx, publikacja i dziennik zmian. To dobry moment na to, żeby prof. Magdalena i Justyna go przeklikały i powiedziały, co jest niejasne, zanim trafi tam prawdziwa treść.
