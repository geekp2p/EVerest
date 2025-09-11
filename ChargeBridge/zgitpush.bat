@echo off
setlocal enabledelayedexpansion

REM === Build timestamped commit message: UnixTime + dd-mm-yyyy + hh:mm ===
for /f %%A in ('powershell -NoProfile -Command "[int][double]::Parse((Get-Date -UFormat %%s))"') do set unixtime=%%A
for /f "tokens=1-3 delims=/" %%a in ("%date%") do ( set dd=%%a & set mm=%%b & set yyyy=%%c )
set hh=%time:~0,2%
set mn=%time:~3,2%
if "%hh:~0,1%"==" " set hh=0%hh:~1,1%
set msg=%unixtime% %dd%-%mm%-%yyyy% %hh%:%mn%

echo Commit message: %msg%

REM === Ensure we’re in a Git repo ===
git rev-parse --is-inside-work-tree >NUL 2>&1 || (
  echo Not a Git repository here.
  exit /b 1
)

REM === Stage & commit ===
git add -A
git commit -m "%msg%" || (
  echo Nothing to commit or commit failed.
)

REM === Fetch and rebase ===
git fetch origin || ( echo Fetch failed & exit /b 1 )

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set BR=%%b

echo Rebase %BR% onto origin/%BR% ...
git pull --rebase origin %BR%
if errorlevel 1 (
  echo.
  echo Rebase encountered conflicts. Fix them, then run:
  echo     git add <files>
  echo     git rebase --continue
  echo When done, run: git push
  exit /b 1
)

REM === Push (normal or forced) ===
if /I "%~1"=="/force" (
  echo Forcing push with lease protection...
  git push --force-with-lease || exit /b 1
) else (
  git push || (
    echo Push failed. If you really need to overwrite remote:
    echo     %~nx0 /force
    exit /b 1
  )
)

echo Done.
endlocal
