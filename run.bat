@echo off
REM Avvio del Simulatore Fido SIAD Romania (v3) su Windows: doppio clic su questo file.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
if not exist ".venv\Scripts\python.exe" (
    echo Prima configurazione: creo l'ambiente Python isolato...
    %PY% -m venv .venv
    if errorlevel 1 ( echo Creazione dell'ambiente non riuscita. Verifica che Python 3.10 o superiore sia installato ^(python.org^). & pause & exit /b 1 )
)
set VPY=.venv\Scripts\python.exe
"%VPY%" -m pip install -q --upgrade pip
"%VPY%" -m pip install -q -r requirements.txt
if errorlevel 1 ( echo Installazione delle librerie non riuscita. & pause & exit /b 1 )
"%VPY%" -m streamlit run app.py
pause
