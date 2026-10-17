"""Activa o desactiva el arranque automatico del widget con Windows.

    python tools/startup.py --install
    python tools/startup.py --uninstall
    python tools/startup.py --status

Crea (o borra) un acceso directo en la carpeta Inicio del usuario que apunta a
run.vbs por medio de wscript.exe, para que arranque sin ventana de consola.
Usar esto en vez de PowerShell con comillas anidadas: los escapes de la linea de
comandos fallan de forma silenciosa y el acceso directo no queda creado.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
VBS = os.path.join(PROJECT, "run.vbs")
EXE = os.path.join(PROJECT, "dist", "WidgetMusica.exe")
NAME = "Widget Musica.lnk"


def startup_dir() -> str:
    return os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                        "Start Menu", "Programs", "Startup")


def lnk_path() -> str:
    return os.path.join(startup_dir(), NAME)


def install() -> int:
    import win32com.client
    # Si esta empaquetado, se arranca el .exe (no necesita Python ni el venv). Si no, el
    # .vbs con el pythonw del entorno virtual, para que no abra consola.
    if os.path.exists(EXE):
        objetivo, args, icono = EXE, "", EXE
    elif os.path.exists(VBS):
        objetivo, args = os.path.join(os.environ["WINDIR"], "System32", "wscript.exe"), f'"{VBS}"'
        icono = os.path.join(os.environ["WINDIR"], "System32", "wmploc.dll,0")
        ico = os.path.join(PROJECT, "assets", "icono.ico")
        if os.path.exists(ico):
            icono = ico
    else:
        print(f"ERROR: ni {EXE} ni {VBS}")
        return 1
    wsh = win32com.client.Dispatch("WScript.Shell")
    lnk = wsh.CreateShortcut(lnk_path())
    lnk.TargetPath = objetivo
    lnk.Arguments = args
    lnk.WorkingDirectory = PROJECT if os.path.exists(VBS) else os.path.dirname(EXE)
    lnk.Description = "Widget de musica en la barra de tareas"
    lnk.IconLocation = icono
    lnk.Save()
    print("Arranque automatico ACTIVADO")
    print(f"  {lnk_path()}")
    print(f"  -> {lnk.TargetPath} {lnk.Arguments}")
    return 0


def uninstall() -> int:
    p = lnk_path()
    if os.path.exists(p):
        os.remove(p)
        print("Arranque automatico DESACTIVADO (acceso directo eliminado)")
    else:
        print("No habia arranque automatico configurado")
    return 0


def status() -> int:
    p = lnk_path()
    if not os.path.exists(p):
        print("Arranque automatico: DESACTIVADO")
        return 1
    try:
        import win32com.client
        lnk = win32com.client.Dispatch("WScript.Shell").CreateShortcut(p)
        print("Arranque automatico: ACTIVADO")
        print(f"  objetivo: {lnk.TargetPath} {lnk.Arguments}")
        print(f"  carpeta : {lnk.WorkingDirectory}")
    except Exception as exc:
        print(f"Arranque automatico: el acceso directo existe pero no se pudo leer ({exc})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--install", action="store_true")
    g.add_argument("--uninstall", action="store_true")
    g.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.install:
        return install()
    if a.uninstall:
        return uninstall()
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
