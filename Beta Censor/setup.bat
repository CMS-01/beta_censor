@echo off
cd /d "%~dp0"
echo Creation de l'environnement Beta Censor...
py -3.12 -m venv .venv
if errorlevel 1 (
  echo Python 3.12 introuvable. Installe-le avec: py install 3.12
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Pret. Lance run.bat pour ouvrir Beta Censor.
pause
