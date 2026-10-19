"""Volca el menu contextual que ofrece el widget ahora mismo (items, ids y submenus).

    python tools/menu_items.py              # abre el menu, lo lista y lo cierra
    python tools/menu_items.py --cerrar     # solo cierra un menu que quedo abierto

Sirve para contestar "¿el menu ofrece la opcion X?" sin leer el codigo: lista lo que
Windows tiene de verdad en el popup, con el id que va a devolver `TrackPopupMenu` (que
es el que atiende `_handle_menu`).

Dos cosas que no son obvias y costaron encontrar:

- En una ventana de menu, `GetMenu()` devuelve 0. El HMENU se pide con el mensaje
  `MN_GETHMENU` (0x01E1).
- Los ids de un SUBMENU no se pueden elegir mandandole `WM_COMMAND` al popup padre:
  Windows ignora los ids que no son del menu que esta siguiendo. Para probar el clic
  de verdad hay que abrir el submenu y clickear el item (o usar el gancho WM_APP_MONITOR).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ctypes
import ctypes.wintypes as wt

import win32api
import win32con
import win32gui

MN_GETHMENU = 0x01E1
user32 = ctypes.windll.user32
user32.GetMenuStringW.argtypes = [wt.HMENU, wt.UINT, wt.LPWSTR, ctypes.c_int, wt.UINT]


def texto_item(hmenu, i: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    n = user32.GetMenuStringW(hmenu, i, buf, 256, win32con.MF_BYPOSITION)
    return buf.value if n else ""


def popups() -> list[int]:
    vistos, h = [], 0
    while True:
        h = win32gui.FindWindowEx(0, h, "#32768", None)
        if not h:
            return vistos
        vistos.append(h)


def cerrar() -> None:
    for _ in range(4):
        p = popups()
        if not p:
            return
        for h in p:
            win32gui.PostMessage(h, win32con.WM_KEYDOWN, win32con.VK_ESCAPE, 0)
            win32gui.PostMessage(h, win32con.WM_KEYUP, win32con.VK_ESCAPE, 0)
        time.sleep(0.35)


def abrir(w: int) -> int:
    """Abre el menu con un clic derecho sintetico y devuelve el popup (0 si no abrio)."""
    r = win32gui.GetWindowRect(w)
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    win32api.SetCursorPos((int(cx), int(cy)))
    time.sleep(0.3)
    win32gui.PostMessage(w, win32con.WM_RBUTTONUP, 0, win32api.MAKELONG(cx - r[0], cy - r[1]))
    for _ in range(25):
        time.sleep(0.1)
        p = popups()
        if p:
            return p[0]
    return 0


def volcar(hmenu: int, prefijo: str = "") -> int:
    """Imprime el menu y sus submenus. Devuelve cuantos items mostro."""
    n = win32gui.GetMenuItemCount(hmenu)
    for i in range(n):
        texto = texto_item(hmenu, i)
        ident = win32gui.GetMenuItemID(hmenu, i)
        estado = win32gui.GetMenuState(hmenu, i, win32con.MF_BYPOSITION)
        if estado & win32con.MF_POPUP:
            marca = "SUBMENU"
        elif estado & win32con.MF_CHECKED:
            marca = "TILDADO"
        elif estado & win32con.MF_GRAYED:
            marca = "apagado"
        elif not texto:
            marca = "---------"
        else:
            marca = ""
        print("%s[%2d] id=%-5s %-8s %s"
              % (prefijo, i, "-" if ident in (-1, 0xFFFFFFFF) else ident, marca, texto))
        if estado & win32con.MF_POPUP:
            sub = win32gui.GetSubMenu(hmenu, i)
            if sub:
                volcar(sub, prefijo + "        ")
    return n


def main() -> int:
    if "--cerrar" in sys.argv:
        cerrar()
        print("menus cerrados")
        return 0
    w = win32gui.FindWindow("AstraMusicWnd", None)
    if not w:
        print("no hay widget corriendo (clase AstraMusicWnd)")
        return 1
    cerrar()
    menu = abrir(w)
    if not menu:
        print("el menu contextual no se abrio")
        return 1
    hmenu = win32gui.SendMessage(menu, MN_GETHMENU, 0, 0)
    print("popup %s  HMENU %s\n" % (hex(menu), hex(hmenu) if hmenu else 0))
    if hmenu:
        volcar(hmenu)
    cerrar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
