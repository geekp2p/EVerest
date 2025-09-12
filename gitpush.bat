@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM === Build timestamped commit message: UnixTime + dd-mm-yyyy + hh:mm ===
for /f %%A in ('powershell -NoProfile -Command "[int][double]::Parse((Get-Date -UFormat %%s))"') do set "unixtime=%%A"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "Get-Date -Format 'dd-MM-yyyy HH:mm'"`) do set "stamp=%%A"
set "msg=%unixtime% %stamp%"

echo Commit message: %msg%

REM === Ensure we are in a Git repo ===
git rev-parse --is-inside-work-tree >NUL 2>&1
if errorlevel 1 (
  echo Not a Git repository here.
  exit /b 1
)

REM === Stage & commit (skip empty commit cleanly) ===
git add -A
git diff --cached --quiet
if %errorlevel% EQU 0 (
  echo Nothing to commit - index is clean.
) else (
  git commit -m "%msg%"
  if errorlevel 1 (
    echo Commit failed.
    exit /b 1
  )
)

REM === Fetch & rebase on current branch ===
git fetch origin
if errorlevel 1 (
  echo Fetch failed.
  exit /b 1
)

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "BR=%%b"

echo Rebase %BR% onto origin/%BR% ...
git pull --rebase --autostash origin %BR%
if errorlevel 1 (
  echo Rebase encountered conflicts. Resolve them, then:
  echo   git add ^<files^>
  echo   git rebase --continue
  echo When done: git push
  exit /b 1
)

REM === Push (normal or forced with /force) ===
if /I "%~1"=="/force" goto PUSH_FORCE

:PUSH_NORMAL
git push
if errorlevel 1 (
  echo Push failed. If you need to overwrite remote, run:
  echo   %~nx0 /force
  exit /b 1
)
goto DONE

:PUSH_FORCE
echo Forcing push with lease protection...
git push --force-with-lease
if errorlevel 1 exit /b 1

:DONE
echo Done.
endlocal
