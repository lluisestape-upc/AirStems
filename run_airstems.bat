@echo off
REM ---- AirStems launcher -------------------------------------------------
REM Double-click to run. Prefers a local venv\, otherwise falls back to the
REM Aetheric venv (mediapipe 0.10.9, which still has mp.solutions).
cd /d "%~dp0"
set "PY=%~dp0venv\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\luigi\Desktop\Llluis\Gestural-Harmonic-Mapping\venv\Scripts\python.exe"
echo Launching AirStems with:
echo   %PY%
echo (click the AirStems window, then: space=play/pause  b=beat-sync  q=quit)
echo.
"%PY%" "%~dp0airstems.py"
echo.
echo (AirStems closed.)
pause
