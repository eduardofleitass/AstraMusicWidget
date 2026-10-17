@echo off
rem Anade el widget al arranque automatico de Windows (carpeta Inicio).
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: falta el entorno virtual. Ejecuta primero setup.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tools\startup.py --install
echo.
pause
