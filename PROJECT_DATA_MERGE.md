# Merge projektow lokalnych na serwer

Projekty platformy sa zapisane w:

```text
data\inserter_platform.db
data\uploads\
```

Nie kopiujemy calego katalogu `data` na serwer, jesli na serwerze sa juz wazne projekty. Zamiast tego robimy merge: brakujace projekty z lokalnej bazy sa dodawane do bazy serwerowej.

## Plan bez zapisu

Z lokalnego komputera:

```powershell
cd C:\Users\tomas\Documents\Projekty\Inserter
.\merge_projects_to_server.ps1
```

To:

- wysle lokalny snapshot bazy do katalogu `_incoming_projects` na serwerze,
- uruchomi na serwerze plan importu,
- nic nie zapisze do serwerowej bazy.

## Wlasciwy merge

Po sprawdzeniu planu:

```powershell
cd C:\Users\tomas\Documents\Projekty\Inserter
.\merge_projects_to_server.ps1 -Apply
```

Skrypt:

- doda tylko projekty, ktorych nie ma na serwerze,
- pomija projekty o tym samym `id`,
- pomija projekty o tej samej nazwie, zeby nie zrobic duplikatu,
- przenosi kroki, punkty, polaryzacje, statusy operatora, feedback i historie,
- kopiuje folder uploadow danego projektu,
- robi backup serwerowej bazy przed zapisem w `data\backups`.

## Po merge

Po imporcie zrestartuj aplikacje:

```powershell
.\deploy_from_local_8780.ps1
```

## Gdy projekt ma taka sama nazwe, ale chcesz go mimo wszystko dodac

```powershell
.\merge_projects_to_server.ps1 -Apply -AllowNameDuplicates
```

Uzywaj tego tylko swiadomie, bo operator zobaczy dwa projekty o tej samej nazwie.
