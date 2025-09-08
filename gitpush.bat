@echo off
REM Auto commit with timestamp (UnixTime + dd-mm-yyyy + hh:mm)

REM --- สร้างข้อความเวลา ---
for /f %%A in ('powershell -NoProfile -Command "[int][double]::Parse((Get-Date -UFormat %%s))"') do set unixtime=%%A
for /f "tokens=1-3 delims=/" %%a in ("%date%") do (
    set dd=%%a
    set mm=%%b
    set yyyy=%%c
)
set hh=%time:~0,2%
set mn=%time:~3,2%

REM --- ลบช่องว่างในชั่วโมง (กรณี <10) ---
if "%hh:~0,1%"==" " set hh=0%hh:~1,1%

set msg=%unixtime% %dd%-%mm%-%yyyy% %hh%:%mn%

echo Commit message: %msg%

REM --- รัน Git ---
git add -A
git commit -m "%msg%"
git push
