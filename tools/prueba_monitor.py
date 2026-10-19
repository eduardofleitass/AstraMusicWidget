"""Prueba de la eleccion de monitor del host flotante (Windows 11).

No abre ventanas: mide el contrato geometrico del host (rect, franja, limites) y
comprueba que elegir un monitor lo mueve de verdad. Con --e2e manda WM_APP_MONITOR
al widget que este corriendo y mide donde quedo la ventana.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import win32gui  # noqa: E402

from widget.flotante import FloatingHost  # noqa: E402
from widget.taskbarwin import monitores  # noqa: E402
from widget.app import WM_APP_MONITOR  # noqa: E402

fallos = []


def check(nombre, ok, detalle=""):
    print("%-58s %s%s" % (nombre, "OK" if ok else "FALLA",
                          "" if ok else "  <- " + str(detalle)))
    if not ok:
        fallos.append(nombre)


def rect_de(hwnd):
    return win32gui.GetWindowRect(hwnd)


def monitor_de(hwnd):
    r = rect_de(hwnd)
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    for m in monitores():
        if m["rect"][0] <= cx < m["rect"][2] and m["rect"][1] <= cy < m["rect"][3]:
            return m
    return None


def menu():
    """El submenu *Monitor* se arma con la lista correcta en los DOS hosts.

    Incrustado (Windows 10) la lista son las barras de tarea, una por monitor; flotante
    (Windows 11) los monitores. Se comprueba sin abrir ventanas: el constructor de la
    app no crea ninguna.
    """
    from widget.app import WidgetApp
    from widget import config as cfgmod
    from widget.taskbarwin import TaskbarHost, list_bars

    print("\n-- submenu Monitor (los dos hosts) --")
    app = WidgetApp(cfgmod.load())
    mons = monitores()

    app.host = FloatingHost(log=app.log)
    op = app._monitor_opciones()
    check("flotante: el menu ofrece los monitores",
          [m["monitor"] for m in op] == [m["monitor"] for m in mons],
          [m["nombre"] for m in op])
    check("flotante: los ids 50+i caben en el rango que atiende _handle_menu",
          all(50 <= 50 + i <= 59 for i in range(len(op))))
    otro = next((m for m in op if not m["primario"]), None)
    if otro:
        app.host.select(otro["monitor"])
        check("flotante: _misma_barra reconoce el monitor donde ya esta",
              app._misma_barra(otro))
        principal = next(m for m in op if m["primario"])
        check("flotante: _misma_barra distingue el otro monitor",
              not app._misma_barra(principal))

    app.host = TaskbarHost(log=app.log)
    op2 = app._monitor_opciones()
    barras = list_bars()
    check("incrustado: el menu sigue saliendo de las barras",
          len(op2) == (len(barras) if len(barras) > 1 else 0),
          [b["nombre"] for b in op2])
    check("incrustado: con una sola barra el submenu no aparece",
          len(barras) > 1 or op2 == [], op2)
    check("incrustado: _misma_barra compara handles de barra",
          app._misma_barra({"tray": app.host.tray}))


def contrato():
    mons = monitores()
    print("-- monitores --")
    for m in mons:
        print("   %-10s %-16s rect=%s franja=%s alto=%d"
              % (m["nombre"], m["monitor"], m["rect"], m["franja"], m["alto"]))
    if len(mons) < 2:
        print("   (un solo monitor: no hay a donde mudarse)")
        return
    logs = []
    h = FloatingHost(log=lambda *a, **k: logs.append(a[0] % a[1:] if a else ""))
    principal = next(m for m in mons if m["primario"])
    otro = next(m for m in mons if not m["primario"])

    check("arranca en el principal", h.rect == principal["rect"], h.rect)
    check("la franja apoya en el borde de abajo del principal",
          h.strip_y() == principal["rect"][3] - principal["alto"], h.strip_y())

    h.select(otro["monitor"])
    check("elegir el otro monitor mueve el rect", h.rect == otro["rect"], h.rect)
    check("la franja apoya en el borde de abajo del otro monitor",
          h.strip_y() == otro["rect"][3] - otro["alto"], h.strip_y())
    lo, hi = h.x_limits(360)
    check("los limites quedan dentro del otro monitor",
          otro["rect"][0] <= lo and hi + 360 <= otro["rect"][2], (lo, hi))
    x = h.reserve(360, 420, frac=1.0)
    check("la posicion automatica cae dentro del otro monitor",
          otro["rect"][0] <= x <= otro["rect"][2] - 360, x)
    check("no invade el borde izquierdo del otro monitor", x >= otro["rect"][0] + 8, x)
    c = h.base_color(x, 360, h.alto)
    check("muestrea color valido en el otro monitor",
          all(0 <= v <= 255 for v in c) and c != (26, 28, 36), c)

    h.select(None)
    check("volver al principal restaura el rect", h.rect == principal["rect"], h.rect)
    h.select(otro["monitor"])
    check("el monitor elegido se recuerda", h.monitor == otro["monitor"], h.monitor)

    h.select("\\.\DISPLAY99")
    check("un monitor que no existe cae al principal", h.rect == principal["rect"], h.rect)
    check("y lo deja dicho en el log",
          any("no encuentro el monitor" in s for s in logs), logs)

    b = h.barra_en(otro["rect"][0] + 10)
    check("barra_en encuentra el monitor por la x", bool(b) and b["rect"] == otro["rect"], b)


def e2e(veces=2):
    w = win32gui.FindWindow("AstraMusicWnd", None)
    if not w:
        print("no hay widget corriendo (clase AstraMusicWnd)")
        return 1
    mons = monitores()
    if len(mons) < 2:
        print("un solo monitor")
        return 1
    print("-- cambio de monitor sobre el widget vivo --")
    for _ in range(veces):
        for i, m in enumerate(mons):
            win32gui.PostMessage(w, WM_APP_MONITOR, i, 0)   # lParam 0 = no guardar
            time.sleep(1.6)
            w = win32gui.FindWindow("AstraMusicWnd", None)
            en = monitor_de(w) if w else None
            r = rect_de(w) if w else (0, 0, 0, 0)
            print("   pedido %-10s -> ventana %s monitor %s franja_ok=%s"
                  % (m["nombre"], r, en["nombre"] if en else "?",
                     bool(en) and abs(r[3] - en["rect"][3]) <= 1))
            check("el widget queda en el monitor pedido (%s)" % m["nombre"],
                  bool(en) and en["rect"] == m["rect"], r)
            check("apoya en la franja de abajo (%s)" % m["nombre"],
                  bool(en) and abs(r[3] - en["rect"][3]) <= 1, r)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--e2e", action="store_true")
    a = ap.parse_args()
    if a.e2e:
        raise SystemExit(e2e())
    contrato()
    menu()
    print("\n%s" % ("TODO OK" if not fallos else "FALLARON: %s" % fallos))
    raise SystemExit(0 if not fallos else 1)
