"""Auto-verificacion contra un widget ya en ejecucion.

Comprueba lo que de verdad importa: que este anclado donde debe, que se
reconstruya si algo lo tumba, que recupere su espacio si la barra se reacomoda y
que los pixeles realmente pintados sean los esperados.

    python tools/selftest.py
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import win32con  # noqa: E402
import win32gui  # noqa: E402

from widget import config as cfgmod  # noqa: E402
from widget import draw  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"{'PASA' if ok else 'FALLA':5}  {name}" + (f"  -> {detail}" if detail else ""))
    return ok


def tray_parts():
    tray = win32gui.FindWindow("Shell_TrayWnd", None)
    return {
        "tray": tray,
        "rebar": win32gui.FindWindowEx(tray, 0, "ReBarWindow32", None),
        "anchor": win32gui.FindWindowEx(tray, 0, "DynamicContent2", None)
        or win32gui.FindWindowEx(tray, 0, "TrayNotifyWnd", None),
        "widget": win32gui.FindWindowEx(tray, 0, "GorusTaskbarMusicWnd", None),
    }


def main() -> int:
    cfg = cfgmod.load()
    p = tray_parts()
    if not check("la barra de tareas existe", bool(p["tray"])):
        return 1
    if not check("el widget esta incrustado", bool(p["widget"]) and
                 win32gui.GetParent(p["widget"]) == p["tray"]):
        print("  (arrancá el widget antes de correr esto)")
        return 1
    check("el widget esta visible", bool(win32gui.IsWindowVisible(p["widget"])),
          "se crea oculto y se muestra recien tras el primer render")

    tl, tt, tr, tb = win32gui.GetWindowRect(p["tray"])
    k = (tb - tt) / 40.0
    want_w = int(round(cfg.get("width", 260) * k))

    w_rect = win32gui.GetWindowRect(p["widget"])
    a_rect = win32gui.GetWindowRect(p["anchor"])
    r_rect = win32gui.GetWindowRect(p["rebar"])
    ww, wh = w_rect[2] - w_rect[0], w_rect[3] - w_rect[1]

    check("ancho del widget segun configuracion", abs(ww - want_w) <= 1,
          f"{ww} px (esperado {want_w})")
    check("alto igual a la barra", wh == tb - tt, f"{wh} vs {tb - tt}")
    check("apoyado contra el bloque de la bandeja", abs(w_rect[2] - a_rect[0]) <= 3,
          f"widget.right={w_rect[2]} vs ancla.left={a_rect[0]}")
    check("la lista de tareas cedio el espacio", r_rect[2] <= w_rect[0] + 2,
          f"rebar.right={r_rect[2]} < widget.left={w_rect[0]}")
    check("la lista conserva el minimo configurado",
          (r_rect[2] - r_rect[0]) >= cfg.get("min_tasklist_width", 420) - 4,
          f"{r_rect[2] - r_rect[0]} px")

    # --- pixeles realmente pintados -------------------------------------
    try:
        from PIL import ImageGrab
        shot = ImageGrab.grab(bbox=w_rect).convert("RGB")
        px = shot.load()
        art = px[max(2, int(8 * k)), max(2, int(10 * k))]
        chip = px[ww - 12, max(2, int(6 * k))]
        check("la caratula ocupa la esquina izquierda", sum(art) > 90,
              f"color {art}")
        check("el fondo del chip es oscuro", sum(chip) < 200, f"color {chip}")
        # Iconos de control: comparar contra el color del chip en vez de usar un
        # umbral fijo. Con umbral alto la comprobacion fallaba en pausa, porque el
        # icono atenuado queda por debajo, y no medía lo que se queria medir.
        rects = draw.control_rects(ww, k, cfg)
        if rects:
            base = shot.getpixel((max(2, ww - 12), max(2, int(6 * k))))
            base_lum = sum(base) / 3.0
            bright = sum(1 for x in range(rects[0][0], ww - 2)
                         for y in range(int(6 * k), int(34 * k))
                         if sum(shot.getpixel((x, y))) / 3.0 > base_lum + 40)
            check("los iconos de control estan dibujados", bright > 15,
                  f"{bright} px mas claros que el chip {base}")
    except Exception as exc:
        check("captura de pantalla", False, repr(exc))

    # --- recuperacion: tumbamos la ventana y debe renacer ------------------
    print("\n-- prueba de recuperacion: destruir la ventana del widget --")
    win32gui.PostMessage(p["widget"], win32con.WM_CLOSE, 0, 0)
    time.sleep(0.4)
    gone = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
    reborn = 0
    for _ in range(30):
        time.sleep(0.2)
        reborn = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
        if reborn:
            break
    check("el widget se reconstruye solo", bool(reborn),
          f"hwnd {hex(reborn) if reborn else 'ninguno'} (antes {hex(gone)})")
    if reborn:
        time.sleep(0.6)
        rb = win32gui.GetWindowRect(reborn)
        r2 = win32gui.GetWindowRect(win32gui.FindWindowEx(p["tray"], 0, "ReBarWindow32", None))
        a2 = win32gui.GetWindowRect(win32gui.FindWindowEx(p["tray"], 0, "DynamicContent2", None)
                                    or p["anchor"])
        check("renace en la posicion correcta", abs(rb[2] - a2[0]) <= 3,
              f"right={rb[2]} ancla={a2[0]}")
        check("renace visible", bool(win32gui.IsWindowVisible(reborn)))
        check("vuelve a reservar su espacio", r2[2] <= rb[0] + 2,
              f"rebar.right={r2[2]} widget.left={rb[0]}")

    # --- recuperacion: la barra se reacomoda a lo ancho --------------------
    print("\n-- prueba de recuperacion: la barra recupera su ancho natural --")
    reb = win32gui.FindWindowEx(p["tray"], 0, "ReBarWindow32", None)
    rr = win32gui.GetWindowRect(reb)
    an = win32gui.GetWindowRect(win32gui.FindWindowEx(p["tray"], 0, "DynamicContent2", None)
                                or p["anchor"])
    win32gui.SetWindowPos(reb, 0, 0, 0, an[0] - rr[0], rr[3] - rr[1],
                          win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
    print(f"  la lista de tareas vuelve a ocupar todo: right={an[0]}")
    ok = False
    for _ in range(25):
        time.sleep(0.2)
        rr2 = win32gui.GetWindowRect(win32gui.FindWindowEx(p["tray"], 0, "ReBarWindow32", None))
        wg = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
        if wg and rr2[2] <= win32gui.GetWindowRect(wg)[0] + 2:
            ok = True
            break
    check("el widget recupera su espacio solo", ok,
          f"rebar.right={rr2[2]}")

    fails = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} pruebas pasaron")
    out = os.path.join(HERE, "_selftest.json")
    try:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump([{"prueba": n, "pasa": o, "detalle": d} for n, o, d in RESULTS],
                      fh, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
