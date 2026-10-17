"""Diagnostico de la barra de tareas: por que el widget se incrusta o pasa a flotante.

    python tools/diagnostico_barra.py

No toca nada: solo mira y cuenta. Existe para la maquina de OTRO usuario, que es donde
aparecen los casos raros (Windows 11 con la barra nueva, la barra movida de lugar, un shell
de terceros tipo ExplorerPatcher). Vuelca:

- la version de Windows,
- cada barra que encuentra (clase, monitor, rectangulo),
- el veredicto de `taskbarwin.motivo_no_incrustable()`, con el detalle de por que,
- el arbol de `Shell_TrayWnd` **en orden de z-order** (arriba primero), que es lo que
  explica el caso de Windows 11: la ventana del widget puede existir, contestar que esta
  visible y estar bien ubicada, y no dibujarse nunca porque queda debajo del puente de
  composicion XAML (`DesktopWindowXamlSource`), que cubre toda el area de la barra.

El mismo volcado sirve para comprobar, en cualquier Windows, si el widget quedo incrustado
(es hijo de la barra) o flotante (es una ventana de nivel superior).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import win32con  # noqa: E402
import win32gui  # noqa: E402

from widget import taskbarwin as tw  # noqa: E402

WIDGET_CLASS = "AstraMusicWnd"


def _hijos(ventana: int, tope: int = 40) -> list[tuple]:
    """(hwnd, clase, visible, rect, texto) de los hijos, del mas alto al mas bajo."""
    fuera = []
    h = win32gui.GetWindow(ventana, win32con.GW_CHILD)
    while h and len(fuera) < tope:
        try:
            fuera.append((h, win32gui.GetClassName(h), win32gui.IsWindowVisible(h),
                          win32gui.GetWindowRect(h), win32gui.GetWindowText(h)))
        except Exception:
            pass
        h = win32gui.GetWindow(h, win32con.GW_HWNDNEXT)
    return fuera


def _pistas_xaml(tray: int) -> list[str]:
    """Las dos senales que mira barra_xaml(), contadas una por una para el informe."""
    pistas = []
    puente = win32gui.FindWindowEx(tray, 0, tw.XAML_BRIDGE_CLASS, None)
    if puente:
        pistas.append("puente de composicion XAML (%s) vis=%s"
                      % (tw.XAML_BRIDGE_CLASS, bool(win32gui.IsWindowVisible(puente))))
    else:
        pistas.append("sin puente de composicion XAML")
    rebar = win32gui.FindWindowEx(tray, 0, "ReBarWindow32", None)
    if not rebar:
        pistas.append("sin ReBarWindow32")
    else:
        caja = win32gui.FindWindowEx(rebar, 0, "MSTaskSwWClass", None) or rebar
        lista = win32gui.FindWindowEx(caja, 0, "MSTaskListWClass", None)
        if not lista:
            pistas.append("ReBarWindow32 sin MSTaskListWClass")
        else:
            pistas.append("MSTaskListWClass vis=%s (la lista de tareas legacy)"
                          % bool(win32gui.IsWindowVisible(lista)))
    return pistas


def _widgets() -> list[tuple]:
    """(hwnd, clase, padre, rect, visible) de cada ventana del widget que exista."""
    fuera = []

    def anotar(h):
        try:
            fuera.append((h, win32gui.GetClassName(h), win32gui.GetParent(h),
                          win32gui.GetWindowRect(h), win32gui.IsWindowVisible(h)))
        except Exception:
            pass

    def cb(h, _):
        if win32gui.GetClassName(h) == WIDGET_CLASS:
            anotar(h)
        return True

    win32gui.EnumWindows(cb, None)
    for b in tw.list_bars():                    # las incrustadas cuelgan de la barra
        for h, _clase, _vis, _rect, _txt in _hijos(b["tray"]):
            if win32gui.GetClassName(h) == WIDGET_CLASS:
                anotar(h)
    return fuera


def main() -> int:
    v = sys.getwindowsversion()
    print("=== sistema ===")
    print("  Windows %d.%d build %d  (%s)"
          % (v.major, v.minor, v.build, "Windows 11" if v.build >= 22000 else "Windows 10"))

    print("\n=== barras de tareas (list_bars) ===")
    barras = tw.list_bars()
    if not barras:
        print("  no encontre ninguna barra")
    for b in barras:
        print("  %-10s %-24s rect=%s monitor=%s"
              % (b["nombre"], b["clase"], b["rect"], b["monitor"]))
        print("    barra abajo y horizontal (barra_en_posicion_util): %s"
              % tw.barra_en_posicion_util(b))
        print("    dibujada por XAML (barra_xaml): %s" % tw.barra_xaml(b["tray"]))
        for p in _pistas_xaml(b["tray"]):
            print("      - %s" % p)

    print("\n=== veredicto ===")
    motivo = tw.motivo_no_incrustable()
    print("  motivo_no_incrustable(): %r" % (motivo,))
    print("  el programa arranca en modo: %s"
          % ("FLOTANTE (ventana propia)" if motivo else "INCRUSTADO (hijo de la barra)"))

    print("\n=== arbol de las barras, en orden de z-order (arriba primero) ===")
    for b in barras:
        print("  %s  0x%X  %s" % (b["nombre"], b["tray"], b["rect"]))
        for h, clase, vis, rect, txt in _hijos(b["tray"]):
            marca = "  <-- widget" if clase == WIDGET_CLASS else ""
            print("    %-46s vis=%-5s %-28s %r%s" % (clase, vis, rect, txt[:20], marca))

    print("\n=== ventanas del widget ===")
    ws = _widgets()
    if not ws:
        print("  no hay ninguna: el programa no esta corriendo (o es otra clase)")
    for h, clase, padre, rect, vis in ws:
        donde = "flotante (nivel superior)" if not padre else "incrustado en 0x%X" % padre
        print("  0x%X %s padre=%s %s vis=%s" % (h, clase, donde, rect, vis))
    print("\n  (si una ventana incrustada aparece en el arbol DEBAJO del puente XAML,"
          "\n   Windows 11 no la va a dibujar nunca: ese es el caso que arregla el modo"
          "\n   flotante automatico)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
