@echo off
setlocal
cd /d %~dp0\..
if not exist .venv py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e .
python -m granjas_anomalias.cli run --config config/project.yml
if errorlevel 1 exit /b 1
start "" reports\dashboard.html
endlocal
