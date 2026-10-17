"""Detiene el widget de forma ordenada y devuelve el espacio a la barra.

    python tools/stop.py            # cierre ordenado (recomendado)
    python tools/stop.py --force    # si quedo zombi, matar y sanear la barra

El cierre ordenado le pide a la ventana controladora que termine, con lo que el
widget restaura el ancho natural de la lista de tareas antes de irse.
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

from widget.taskbarwin import TaskbarHost  # noqa: E402


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


def natural_width() -> int:
    tray = win32gui.FindWindow("Shell_TrayWnd", None)
    rb = win32gui.FindWindowEx(tray, 0, "ReBarWindow32", None)
    an = win32gui.FindWindowEx(tray, 0, "DynamicContent2", None) or \
        win32gui.FindWindowEx(tray, 0, "TrayNotifyWnd", None)
    r, a = win32gui.GetWindowRect(rb), win32gui.GetWindowRect(an)
    return a[0] - r[0]


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

    host = TaskbarHost()
    host.refresh()
    host.restore()
    tray = win32gui.FindWindow("Shell_TrayWnd", None)
    left = win32gui.FindWindowEx(tray, 0, "GorusTaskbarMusicWnd", None)
    rb = win32gui.FindWindowEx(tray, 0, "ReBarWindow32", None)
    r = win32gui.GetWindowRect(rb)
    nat = natural_width()
    print(f"widget          : {'todavia presente' if left else 'detenido'}")
    print(f"lista de tareas : {r[2] - r[0]} px  (natural {nat} px)")
    ok = not left and abs((r[2] - r[0]) - nat) <= 3
    print("VEREDICTO       :", "barra restaurada" if ok else "REVISAR: quedo espacio leakado")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
