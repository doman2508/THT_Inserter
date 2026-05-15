# MSX THT Inserter Platform

To jest poczatek docelowej platformy webowej dla insertera THT.

Obecny prototyp `main.py` i eksportowany HTML nadal zostaja w projekcie. Platforma jest dodana rownolegle, zeby przenosic funkcje krok po kroku.

## Uruchomienie

1. Uruchom:

```text
start_platform.bat
```

2. Otworz w przegladarce:

```text
http://127.0.0.1:8780
```

## Co dziala teraz

- centralna baza SQLite,
- lista projektow,
- tworzenie projektu,
- dodanie prostego kroku montazu,
- import gotowych plikow `BOM XLSX` i `P&P XLSX`,
- automatyczne tworzenie krokow montazu z BOM,
- zapis punktow P&P dla pojedynczych desygnatorow,
- podstawowa walidacja brakow, duplikatow i nadmiarowych punktow,
- start sesji operatora,
- zapis statusu kroku `OK` / `Problem`,
- zapis uwag operatora jako zdarzen w bazie.

## Panel Admin

Pierwszy ekran Admina to lista projektow. Pokazuje nazwe projektu, status, liczbe krokow, liczbe punktow, informacje o obrazie PCB oraz daty utworzenia i modyfikacji.

Z tego ekranu mozna:

- utworzyc szkic nowego projektu,
- zaimportowac projekt z BOM/P&P/PCB,
- otworzyc szczegoly projektu,
- wyszukac projekt po podstawowych danych.
- edytowac dane projektu i status,
- dodac albo podmienic obraz PCB w istniejacym projekcie,
- wykonac reimport Exceli do istniejacego projektu.
- usunac projekt z listy projektow po potwierdzeniu.

Po otwarciu projektu dostepne sa zakladki:

- `Podsumowanie`,
- `Przygotowanie`,
- `Linie montażowe`,
- `P&P / punkty`,
- `Obraz PCB`,
- `Operator`.

W zakladce `Podsumowanie` i w naglowku szczegolow projektu sa akcje zarzadzania:

```text
Edytuj projekt | Dodaj/Podmień PCB | Reimport Exceli
```

`Reimport Exceli` zastepuje aktualne linie montazowe i punkty P&P wybranego projektu nowym importem. Obraz PCB zostaje zachowany, chyba ze przy reimporcie zostanie wskazany nowy plik obrazu.

## Przygotowanie produkcji

Zakladka `Przygotowanie` wykrywa linie, ktore wygladaja jak listwy, piny albo zlacza wymagajace decyzji technologicznej. Rozbicie odbywa sie na poziomie fizycznych odcinkow listwy, a nie pojedynczych otworow PCB.

Przyklad:

```text
TP1,TP2,TP3,TP4,TP8,TP9,TP10 | 1PIN 1X40 H12 | M-ZLACZ-00015
```

Osoba z przygotowania produkcji wpisuje:

```text
TP1 = odcinek 1 PIN
TP2 = odcinek 1 PIN
TP3 = odcinek 1 PIN
TP4 = odcinek 1 PIN
TP8,TP9,TP10 = odcinek 3 PIN
```

Po zatwierdzeniu platforma zastepuje jedna linie liniami operatorskimi pogrupowanymi po typie odcinka. Odcinki sa zapisywane osobno, zeby operator widzial sztuki do przygotowania, a nie tylko dlugi ciag desygnatorow.

```text
TP1 | TP2 | TP3 | TP4
1 PIN (1PIN 1X40 H12) | ilosc 4 szt. po 1 PIN

TP8+TP9+TP10 | TP17+TP18+TP19 | TP20+TP21+TP22
3 PIN (1PIN 1X40 H12) | ilosc 3 szt. po 3 PIN
```

Jesli linia BOM ma juz wartosc `3PIN 1x40 H12`, platforma domyslnie ustawia kazdy desygnator jako odcinek 3-pinowy, np. `J1 | J2 | J17` daje `3 szt. po 3 PIN`. Indeks Medcom zostaje zachowany, a projekt dostaje status `Przygotowany`.

Po zatwierdzeniu linia nie znika definitywnie z przygotowania. Przechodzi do sekcji `Juz przygotowane / popraw`, gdzie mozna ponownie zmienic podzial odcinkow i zapisac korekte. Platforma ponownie waliduje, czy kazdy desygnator zostal przypisany dokladnie raz.

## Import przygotowanych Exceli

W panelu `Admin` uzyj akcji `Importuj projekt`.

Wymagany BOM XLSX:

```text
Desygnator | Wartość | Indeks Medcom
```

Wymagany P&P XLSX:

```text
Desygnator | X | Y | Rotacja
```

Platforma rozbija grupy desygnatorow z BOM, dopasowuje je do P&P, zapisuje punkty w bazie i tworzy kroki operatorskie pogrupowane po `Wartość + Indeks Medcom`.

Przy imporcie mozna tez dolaczyc obraz PCB: `PNG`, `JPG`, `JPEG` albo `WEBP`. Plik jest zapisywany lokalnie w:

```text
data\uploads\<project_id>\board.*
```

Sciezka obrazu jest przypieta do projektu w bazie, zeby operator view mogl pozniej uzyc jej jako tla dla markerow.

Po imporcie w podsumowaniu zobaczysz:

- liczbe utworzonych krokow,
- liczbe zapisanych punktow,
- ile desygnatorow BOM dopasowano do P&P,
- brakujace desygnatory z P&P,
- nadmiarowe punkty P&P, ktorych nie ma w przygotowanym BOM.

Po imporcie projekt jest automatycznie wybierany w panelu `Admin`, a nizej pojawia sie tabela linii montazowych z kolumnami:

```text
Lp. | Desygnator | Wartość | Indeks Medcom | Ilość | Uwagi | Sekundy
```

Ta tabela jest baza pod kolejne funkcje administracyjne: edycje pozycji, zmiane kolejnosci, laczenie/dzielenie grup i zatwierdzanie wersji dla operatora.

## Gdzie sa dane

Domyslna baza:

```text
data\inserter_platform.db
```

Mozna zmienic sciezke przez zmienna:

```powershell
$env:INSERTER_PLATFORM_DB="C:\MSXInserter\inserter_platform.db"
python -m inserter_platform.server
```

## Kolejne kroki

1. Edytor kolejnosci i grup montazowych.
2. Operator view z markerami PCB przeniesiony z obecnego HTML-a.
3. Raporty i historia sesji w panelu Admin.
4. Automatyczne obrabianie surowego BOM `.doc` i P&P `.rpt`.
5. Moduly PRO: kamera, kalibracja realnej plytki, dokumentacja zdjeciowa.
