@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environnement Python introuvable. Lance d'abord setup.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m src.main
if errorlevel 1 pause
