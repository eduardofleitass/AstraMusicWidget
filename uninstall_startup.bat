@echo off
rem Quita el widget del arranque automatico y lo detiene.
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tools\startup.py --uninstall
    echo Deteniendo el widget y devolviendo el espacio a la barra...
    ".venv\Scripts\python.exe" tools\stop.py
) else (
    echo ERROR: falta el entorno virtual.
)
echo.
pause
