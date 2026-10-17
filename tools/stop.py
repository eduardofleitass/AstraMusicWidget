"""Detiene el widget de forma ordenada y devuelve el espacio a la barra.

    python tools/stop.py            # cierre ordenado (recomendado)
    python tools/stop.py --force    # si quedo zombi, matar y sanear la barra

El cierre ordenado le pide a la ventana controladora que termine, con lo que el
widget restaura el ancho natural de la lista de tareas antes de irse.

Sanea TODAS las barras de tareas, no solo la principal: el widget puede estar
viviendo en la barra de otro monitor (Shell_SecondaryTrayWnd), que tiene su propia
estructura (contenedor WorkerW y reloj como ancla).
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import win32con  # noqa: E402
import win32gui  # noqa: E402

from widget.taskbarwin import TaskbarHost, list_bars  # noqa: E402


def widget_pids() -> list[int]:
    try:
        out = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=25).stdout
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        if "main.py" in line:
            tail = line.rsplit(",", 1)[-1].strip()
            if tail.isdigit():
                pids.append(int(tail))
    return pids


def host_de(barra: dict) -> TaskbarHost:
    """Host apuntado a esa barra (resuelve su contenedor y su ancla)."""
    host = TaskbarHost()
    host.select(None if barra["primario"] else barra["monitor"])
    host.refresh()
    return host


def estado() -> list[tuple]:
    """(nombre, ancho del contenedor, ancho natural, hay widget) por barra."""
    filas = []
    for b in list_bars():
        host = host_de(b)
        cont = win32gui.GetWindowRect(host.container) if host.container else (0, 0, 0, 0)
        ancla = host._anchor_rect()
        hay = bool(win32gui.FindWindowEx(b["tray"], 0, "GorusTaskbarMusicWnd", None))
        filas.append((b["nombre"], cont[2] - cont[0], ancla[0] - cont[0], hay))
    return filas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    ctl = win32gui.FindWindow("GorusTaskbarMusicCtl", None)
    if ctl and not args.force:
        print(f"pidiendo cierre ordenado a {hex(ctl)}")
        win32gui.PostMessage(ctl, win32con.WM_CLOSE, 0, 0)
        for _ in range(20):
            time.sleep(0.25)
            if not win32gui.FindWindow("GorusTaskbarMusicCtl", None):
                break
    elif args.force:
        k = ctypes.windll.kernel32
        for pid in widget_pids():
            h = k.OpenProcess(0x0001, False, pid)
            if h:
                k.TerminateProcess(h, 1)
                k.CloseHandle(h)
                print(f"terminado PID {pid}")
        time.sleep(1.0)

    # Saneamiento: devolver el ancho natural a cada barra, por si una corrida
    # anterior murio sin limpiar (o si el widget vivia en una secundaria).
    #
    # Se espera a que el proceso termine DE VERDAD antes de reparar y se reintenta:
    # si se repara mientras el widget todavia existe, el propio widget vuelve a
    # reservar su espacio despues y el resultado queda a medias (visto: "REVISAR:
    # quedo espacio leakado" en la primera corrida y bien en la segunda).
    def cerrar_y_reparar(espera: float) -> bool:
        t0 = time.time()
        while time.time() - t0 < espera:
            if not win32gui.FindWindow("GorusTaskbarMusicCtl", None) and not any(
                    f[3] for f in estado()):
                break
            time.sleep(0.25)
        for b in list_bars():
            host_de(b).restore()
        time.sleep(0.3)
        return all((not hay) and abs(ancho - natural) <= 3
                   for _, ancho, natural, hay in estado())

    for intento in range(3):
        if cerrar_y_reparar(3.0 if intento == 0 else 1.5):
            break
    time.sleep(0.2)

    ok = True
    for nombre, ancho, natural, hay in estado():
        bien = not hay and abs(ancho - natural) <= 3
        ok = ok and bien
        print(f"barra {nombre:10}: widget {'todavia presente' if hay else 'detenido'}"
              f" | lista de tareas {ancho} px (natural {natural} px)"
              f" {'' if bien else '  <-- REVISAR'}")
    print("VEREDICTO       :", "barras restauradas" if ok else "REVISAR: quedo espacio leakado")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
