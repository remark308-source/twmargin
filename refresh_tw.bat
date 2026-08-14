@echo off
setlocal
set "PYEXE=C:\Users\alan\.workbuddy\binaries\python\versions\3.13.12.old.1464\python.exe"
set "WORKDIR=C:\Users\alan\WorkBuddy\2026-08-12-12-58-38"
cd /d "%WORKDIR%"
echo === Refreshing Taiwan margin MA20 chart data ===
echo [%date% %time%] build_tw.py ...
"%PYEXE%" build_tw.py
if errorlevel 1 (
  echo [ERROR] build_tw.py failed.
  pause
  exit /b 1
)
echo [%date% %time%] gen_html_tw.py ...
"%PYEXE%" gen_html_tw.py
if errorlevel 1 (
  echo [ERROR] gen_html_tw.py failed.
  pause
  exit /b 1
)
echo === Refresh OK ===
endlocal
