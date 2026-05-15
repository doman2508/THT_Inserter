# Raporty operatora

Raporty sa zapisywane przez lokalny serwer raportow uruchamiany na komputerze operatora.

## Uruchomienie

1. Uruchom `start_report_server.bat`.
2. Zostaw okno serwera wlaczone podczas pracy operatora.
3. W wygenerowanym HTML kliknij `Raport`.

Domyslny katalog zapisu:

```text
\\DOKUMENTACJE\__NARZEDZIA__\Raporty_inserter
```

Serwer zapisuje dwa pliki:

- `.csv` - do szybkiego otwarcia w Excelu,
- `.json` - pelne dane raportu.

Pliki trafiaja do podfolderu z nazwa projektu.

## Zmiana katalogu

Przed uruchomieniem serwera mozna ustawic inny katalog:

```powershell
$env:INSERTER_REPORT_DIR="\\SERWER\UDZIAL\Raporty_inserter"
python report_server.py
```

## Fallback

Jesli serwer raportow nie dziala, przycisk `Raport` pobierze awaryjny plik CSV w przegladarce.
