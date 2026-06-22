# Prompt dla Codexa: deploy aplikacji na serwer przez SSH

Ten dokument mozna wkleic do innego watku Codexa albo dolaczyc do projektu jako wspolna instrukcje dla modulow aplikacji.

## Kontekst

Chce skonfigurowac deploy aplikacji na serwerze przez SSH, analogicznie jak w projekcie MSX THT Inserter.

Zalozenia:

- aplikacja dziala na serwerze Windows pod adresem `192.168.1.10`,
- port aplikacji: `3000`,
- SSH z mojego komputera do serwera dziala pod aliasem: `api-vendo-prod`,
- uzytkownik serwera: `Remote01`,
- docelowo chce odpalac deploy z lokalnego komputera jedna komenda, bez RDP i bez recznego `git pull` na serwerze.

## Prompt do wklejenia w innym watku

```text
Chce skonfigurowac deploy tej aplikacji na serwerze przez SSH.

Zalozenia:
- aplikacja dziala na serwerze Windows pod adresem 192.168.1.10,
- port aplikacji: 3000,
- SSH z mojego komputera do serwera dziala pod aliasem: api-vendo-prod,
- uzytkownik serwera: Remote01,
- docelowo chce odpalac deploy z lokalnego komputera jedna komenda, bez RDP i bez recznego git pull na serwerze.

Najpierw sprawdz repo:
- git remote -v,
- git status,
- dostepne branche,
- czy istnieje branch server/local-msx,
- jakie pliki startowe istnieja, szczegolnie start-local.ps1 albo podobny skrypt startowy,
- gdzie jest konfiguracja portu 3000,
- czy dane produkcyjne, baza, uploady, .env i logi sa poza gitem albo w .gitignore.

Chce mechanizm deploy:

1. Na serwerze skrypt deploy_server_3000.ps1:
   - przechodzi do katalogu aplikacji na serwerze,
   - sprawdza, czy working tree jest czysty; jesli nie, przerywa,
   - robi git fetch origin,
   - robi git checkout main,
   - robi git pull --ff-only origin main,
   - jesli istnieje branch server/local-msx, robi:
     git checkout server/local-msx
     git rebase main
     i uruchamia aplikacje z tego brancha,
   - jesli branch server/local-msx nie istnieje, zostaje na main i jasno napisz, czy warto go utworzyc,
   - ubija proces sluchajacy na porcie 3000,
   - uruchamia aplikacje ponownie przez start-local.ps1 albo wlasciwy lokalny skrypt startowy,
   - robi health-check, najlepiej http://127.0.0.1:3000/ albo /api/health jesli istnieje,
   - zapisuje logi do katalogu logs.

2. Na lokalnym komputerze skrypt deploy_from_local_3000.ps1:
   - przez SSH odpala deploy_server_3000.ps1 na serwerze:
     ssh api-vendo-prod "powershell -NoProfile -ExecutionPolicy Bypass -File <SCIEZKA_DO_APKI>\deploy_server_3000.ps1"

3. Dodaj krotka instrukcje DEPLOY_3000.md:
   - jak uruchomic pierwszy deploy na serwerze,
   - jak potem robic deploy z lokalnego komputera,
   - jak sprawdzic, czy dziala,
   - co zrobic, jesli port 3000 jest zajety albo working tree nie jest czysty.

Wazne:
- Nie wrzucaj do repo sekretow, .env, baz danych, uploadow ani logow.
- Nie rob git reset --hard.
- Jesli working tree jest brudny, zatrzymaj sie i pokaz mi, co jest zmienione.
- Dopasuj komendy do istniejacej technologii projektu, nie zakladaj z gory Node/Python, tylko sprawdz po plikach.
- Po zmianach sprawdz skladnie skryptow i pokaz mi dokladnie, jakie komendy bede odpalal.
```

## Docelowy model pracy

Po wdrozeniu mechanizmu proces powinien wygladac tak:

1. Codex robi zmiany w projekcie lokalnym.
2. Codex robi commit i push do GitHuba.
3. Uzytkownik albo Codex odpala lokalnie:

```powershell
.\deploy_from_local_3000.ps1
```

4. Skrypt przez SSH uruchamia deploy na serwerze.
5. Serwer sam robi `git pull`, restart aplikacji i health-check.

## Wazne pytania dla kazdego modulu

Przed wdrozeniem w konkretnym module trzeba ustalic:

- jaka jest sciezka projektu na serwerze,
- czy aplikacja faktycznie dziala na porcie `3000`,
- jak uruchamia sie aplikacje produkcyjnie,
- czy jest endpoint `/api/health`,
- czy `server/local-msx` jest potrzebny,
- gdzie sa dane produkcyjne i czy na pewno nie sa w Git,
- czy port `3000` nie jest wspoldzielony przez inna aplikacje.

## Przyklad oczekiwanych komend

Pierwszy deploy na serwerze:

```powershell
cd <SCIEZKA_DO_APKI_NA_SERWERZE>
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_server_3000.ps1
```

Kolejne deploye z lokalnego komputera:

```powershell
cd <SCIEZKA_DO_PROJEKTU_LOKALNIE>
.\deploy_from_local_3000.ps1
```
