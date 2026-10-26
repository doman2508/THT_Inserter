# Deploy MSX THT Inserter na porcie 8780

Ten wariant jest odpowiednikiem deploya z innej aplikacji na porcie 3000, ale dopasowany do Insertera.

## Zasada

Serwer:

- pracuje w katalogu `C:\Users\Remote01\Desktop\Apki\THT_Inserter`,
- aktualizuje branch `main`,
- przerywa deploy, jezeli working tree na serwerze nie jest czysty,
- konfiguruje zadanie bez limitu 72 godzin (`ExecutionTimeLimit = PT0S`),
- ponawia uruchomienie po awarii co minute; dodatkowy wyzwalacz co minute nie wygasa i nie uruchamia drugiej kopii dzialajacej aplikacji,
- rejestruje konfiguracje i sprawdza ACL przed zatrzymaniem aplikacji,
- uzupelnia brakujace standardowe prawa SYSTEM i Administratorow tylko do wskazanego zadania; nie zmienia folderu Harmonogramu, innych zadan ani polityk logowania,
- przed restartem sprawdza rzeczywisty proces zadania i odpowiedz HTTP; samo przyjecie polecenia startu nie oznacza sukcesu,
- wylacza ponawianie na czas deploya, zatrzymuje stare zadanie i proces na porcie `8780`,
- uruchamia aplikacje na `0.0.0.0:8780`,
- sprawdza `http://127.0.0.1:8780/api/health`.

Katalog `data\` jest ignorowany przez Git, wiec baza projektow i uploady na serwerze zostaja na serwerze.
Kopia poprzedniej definicji zadania trafia do `data\deploy-backups\` (bez hasla).
Przed naprawa ACL w tym samym katalogu powstaje osobna kopia `.sddl`.
Jawne odmowy dostepu lub nieoczekiwany zakres zadania przerywaja naprawe.

## Jednorazowy autostart bez zalogowanego uzytkownika

Zwykle konto SSH moze nie miec uprawnien do utworzenia zadania w tle.
Wtedy deploy zachowuje dotychczasowy tryb interaktywny i wyswietla ostrzezenie
`SESSION-DEPENDENT MODE`. Limit czasu i ponawianie sa naprawione, ale start po
restarcie komputera bez logowania wymaga ponizszego kroku.

Na serwerze uruchom PowerShell **jako administrator**, po aktualizacji repozytorium:

```powershell
cd C:\Users\Remote01\Desktop\Apki\THT_Inserter
$inserterCredential = Get-Credential -UserName 'WIN-OGJFAFPNMCU\Remote01' -Message 'Konto do uruchamiania Insertera w tle'
.\deploy_server_8780.ps1 -SkipGitPull -TaskCredential $inserterCredential
Remove-Variable inserterCredential
```

Haslo wpisuje sie tylko w oknie Windows, nie w kodzie ani w czacie. Harmonogram
przechowuje je systemowo. Aplikacja nadal pracuje jako `Remote01` z najnizszym
poziomem uprawnien, nie jako SYSTEM ani administrator. Administrator rejestruje
wyzwalacz startu systemu z opoznieniem 30 sekund oraz start niezalezny od sesji.
Konto musi miec prawo **Log on as a batch job**; jezeli polityka domeny go blokuje,
administrator musi to skorygowac. Nie zmieniamy automatycznie polityk systemu.

Jesli diagnostyka potwierdzila brak tego prawa dla `Remote01`, po osobnej zgodzie
na jego nadanie mozna uruchomic na serwerze jako administrator:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\grant_platform_batch_logon_8780.ps1
```

To osobny, jednorazowy krok, nigdy automatyczna czesc deploya. Skrypt sprawdza
konkretny serwer, zadanie i SID konta `Remote01`, zapisuje poprzednie przypisania
do `data\deploy-backups\` i przez `LsaAddAccountRights` dodaje tylko
`SeBatchLogonRight`. Nie zastepuje list praw, nie dodaje konta do Administratorow,
nie zmienia hasla, nie restartuje aplikacji i nie zmienia odmow logowania.
Ponowne wykonanie nie dodaje duplikatow. Po kroku administratora wykonaj zwykly
deploy, aby sprawdzic start z zapisanymi poswiadczeniami. Polityka domenowa moze
nadpisac lokalne przypisanie; w takim przypadku wymagana jest korekta przez administratora domeny.

Kolejne deploye zachowuja gotowe zadanie i zapisane poswiadczenia, jesli jego
konfiguracja sie nie zmienila. Zmiana ustawien zadania w tle wymaga ponownego
podania `-TaskCredential` przez administratora; skrypt zatrzyma sie przed restartem.
Zmiana hasla konta wymaga tez aktualizacji poswiadczen zadania.
Jawne podanie `-TaskCredential` zawsze odswieza zapisane poswiadczenia, takze
gdy XML zadania sie nie zmienil. Haslo nie trafia do logow ani kopii definicji.

### Start przyjety, ale proces nie powstaje

Odczyt diagnostyczny w PowerShellu administratora (bez zatrzymania aplikacji,
proby logowania, zmiany uprawnien lub wlaczania historii):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\diagnose_platform_task_8780.ps1
```

Skrypt odczytuje bezposrednio z LSA przypisania `SeBatchLogonRight` oraz
`SeDenyBatchLogonRight`, konto zadania i jego grupy lokalne, stan historii i HTTP.
Rozroznia brak przypisan od odmowy dostepu. Nie odczytuje hasel ani sekretow.

Skrypt czeka do 15 sekund na dzialajace wystapienie zadania. W razie niepowodzenia
sprawdz jako administrator dziennik `Microsoft-Windows-TaskScheduler/Operational`
dla `\MSX THT Inserter 8780`, zapisane poswiadczenia oraz prawo logowania wsadowego.
`LastTaskResult` moze pochodzic z poprzedniego uruchomienia, wiec nie wystarcza do diagnozy.
Nie zmieniaj globalnych ACL ani nie uruchamiaj aplikacji jako SYSTEM.

Gdy zadanie juz dziala, `IgnoreNew` zachowuje ten proces. Taki test nie potwierdza
poprawnosci hasla do kolejnego startu. Awaryjne uruchomienie `RunEx(..., TASK_RUN_AS_SELF, ...)`
nie jest potwierdzeniem autostartu po restarcie systemu. Deploy nie stosuje tego
obejscia automatycznie i nie przelacza zadania na tryb interaktywny.

## Logi i kontrola

- `logs\inserter_platform_8780.lifecycle.log`: start, PID, kod zakonczenia.
- `logs\inserter_platform_8780.<czas>-<PID>.stdout.log` i `.stderr.log`: osobne logi
  kazdego uruchomienia; Python zapisuje je bez buforowania, poprzednie logi zostaja.
- Kazde nieoczekiwane zakonczenie Pythona, takze kodem 0, daje kod 1 runnera,
  aby Harmonogram ponowil start. Zwykle komunikaty stderr nie przerywaja runnera.
- Celowe dluzsze wylaczenie: **najpierw wylacz zadanie w Harmonogramie**, a potem
  je zatrzymaj. Samo zatrzymanie procesu uruchomi automatyczne odzyskiwanie.
- Test konfiguracji (bez tworzenia zadan): `powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\test_platform_task.ps1`.
- Testy naprawy ACL i kontroli startu (bez tworzenia zadan): `powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\test_platform_task_permissions.ps1`.
- Testy aplikacji i runnera: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.
- Test faktycznego restartu Harmonogramu (okolo minuty, tworzy i usuwa osobne zadanie,
  nie przerywa aplikacji): `powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\test_platform_recovery.ps1`.

## Pierwsze uruchomienie na serwerze

W PowerShell na serwerze:

```powershell
cd C:\Users\Remote01\Desktop\Apki\THT_Inserter
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy_server_8780.ps1 -InstallRequirements
```

Adres w sieci:

```text
http://192.168.1.10:8780/
```

## Kolejne deploye z lokalnego komputera

Zakladajac, ze masz skonfigurowany SSH host `api-vendo-prod`:

```powershell
cd C:\Users\tomas\Documents\Projekty\Inserter
.\deploy_from_local_8780.ps1
```

To uruchamia na serwerze:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\Remote01\Desktop\Apki\THT_Inserter\deploy_server_8780.ps1
```

## Wazne

Przed deployem lokalnie trzeba wypchnac zmiany do repozytorium, z ktorego korzysta serwer:

```powershell
git push
```

Jezeli serwer ma remote ustawiony na inne repo niz lokalne `origin`, to push musi trafic wlasnie do tego repo.
