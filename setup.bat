@echo off
rem Crea el entorno virtual e instala las dependencias.
setlocal
cd /d "%~dp0"
echo === Widget de musica para la barra de tareas: instalacion ===
echo.

where uv >nul 2>nul
if %errorlevel%==0 (
    echo [1/2] Creando entorno virtual con uv...
    uv venv --python 3.11 .venv
    echo [2/2] Instalando dependencias...
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
) else (
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo ERROR: no encuentro ni uv ni python en el PATH.
        echo Instala Python 3.11 o uv y volve a intentar.
        pause
        exit /b 1
    )
    echo [1/2] Creando entorno virtual con python -m venv...
    python -m venv .venv
    echo [2/2] Instalando dependencias...
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)
if %errorlevel% neq 0 (
    echo.
    echo La instalacion fallo. Revisa los mensajes de arriba.
    pause
    exit /b 1
)
echo.
echo Listo. Para arrancar el widget: doble clic en run.vbs
echo Para que arranque solo con Windows: install_startup.bat
pause
