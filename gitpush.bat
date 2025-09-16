@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================
REM  Build commit message: <UnixTime> <dd-MM-yyyy HH:mm>
REM ============================================
for /f %%A in ('
  powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"
') do (
  set "unixtime=%%A"
)

for /f "usebackq delims=" %%A in (`
  powershell -NoProfile -Command "$([datetime]::Now.ToString('dd-MM-yyyy HH:mm'))"
`) do (
  set "stamp=%%A"
)

set "msg=%unixtime% %stamp%"
echo Commit message: %msg%

REM ============================================
REM  Ensure current folder is a Git repository
REM ============================================
git rev-parse --is-inside-work-tree >NUL 2>&1
if errorlevel 1 (
  echo Not a Git repository here.
  exit /b 1
)

REM ============================================
REM  Stage all changes and commit if needed
REM ============================================
git add -A

git diff --cached --quiet
if %errorlevel% EQU 0 (
  echo Nothing to commit - index is clean.
) else if %errorlevel% EQU 1 (
  git commit -m "%msg%"
  if errorlevel 1 (
    echo Commit failed.
    exit /b 1
  )
) else (
  echo "git diff --cached --quiet" failed.
  exit /b 1
)

REM ============================================
REM  Fetch & rebase onto upstream of current branch
REM ============================================
git fetch origin
if errorlevel 1 (
  echo Fetch failed.
  exit /b 1
)

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do (
  set "BR=%%b"
)

echo Rebase %BR% onto origin/%BR% ...
git pull --rebase --autostash origin %BR%
if errorlevel 1 (
  echo Rebase encountered conflicts. Resolve them, then:
  echo   git add ^<files^>
  echo   git rebase --continue
  echo When done: git push
  exit /b 1
)

REM ============================================
REM  Push (normal or forced with /force)
REM ============================================
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
if errorlevel 1 (
  echo Force push failed.
  exit /b 1
)

:DONE
echo Done.
endlocal
