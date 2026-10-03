@echo off
setlocal
rem 舊路徑 C:\Users\alan\.workbuddy\...\python.exe 已不存在，改用 PATH 上的 python
set "WORKDIR=%~dp0"
cd /d "%WORKDIR%"
echo === Refreshing Taiwan margin MA20 chart data ===
echo [%date% %time%] build_tw.py ...
python -X utf8 build_tw.py
if errorlevel 1 (
  echo [ERROR] build_tw.py failed.
  pause
  exit /b 1
)
echo [%date% %time%] gen_html_tw.py ...
python -X utf8 gen_html_tw.py
if errorlevel 1 (
  echo [ERROR] gen_html_tw.py failed.
  pause
  exit /b 1
)
echo === Refresh OK ===
endlocal
