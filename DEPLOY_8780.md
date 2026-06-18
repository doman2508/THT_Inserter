# Deploy testowy MSX THT Inserter na porcie 8780

Ten wariant jest odpowiednikiem deploya z innej aplikacji na porcie 3000, ale dopasowany do Insertera.

## Zasada

Serwer:

- pracuje w katalogu `C:\Users\Remote01\Desktop\Apki\THT_Inserter`,
- aktualizuje branch `main`,
- przerywa deploy, jezeli working tree na serwerze nie jest czysty,
- ubija proces sluchajacy na porcie `8780`,
- uruchamia aplikacje na `0.0.0.0:8780`,
- sprawdza `http://127.0.0.1:8780/api/health`.

Katalog `data\` jest ignorowany przez Git, wiec baza projektow i uploady na serwerze zostaja na serwerze.

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
