@echo off
setlocal
cd /d %~dp0\..
set "PROJECT_CONFIG=%~1"
if "%PROJECT_CONFIG%"=="" set "PROJECT_CONFIG=config\project.yml"
if not exist .venv py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e .
python -m granjas_anomalias.cli run --config "%PROJECT_CONFIG%"
if errorlevel 1 exit /b 1
echo Pipeline finalizado. La salida anterior muestra el dashboard de la granja.
endlocal
