"""Prueba de clic real sobre el widget: verifica el circuito completo.

Mueve el cursor de verdad sobre cada boton, comprueba que el resaltado de hover
aparezca y que el clic efectivamente cambie el estado del reproductor. Deja el
reproductor como estaba al terminar.

    python tools/clicktest.py
    python tools/clicktest.py --hover-only

Importante: si estas usando el mouse mientras corre, tus movimientos compiten con
los que inyecta la prueba y el cursor no queda donde se lo pone. En ese caso la
prueba lo detecta, lo reporta como INTERFERENCIA y no como fallo, en vez de
inventar un bug que no existe. Solta el mouse y volve a correrla.

La prueba de play/pausa SI cambia lo que suena por un instante, y lo restaura.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import win32gui  # noqa: E402

from widget import config as cfgmod, draw  # noqa: E402
from widget.media import MediaPoller  # noqa: E402

user32 = ctypes.windll.user32
PASS, FAIL, SKIP = "PASA", "FALLA", "SALTA"
results = []
interfered = []


def check(name, ok, detail="", skipped=False):
    tag = SKIP if skipped else (PASS if ok else FAIL)
    results.append((name, bool(ok), tag, detail))
    print(f"{tag:5}  {name}" + (f"  -> {detail}" if detail else ""))
    return ok


def cursor_pos():
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def place_cursor(x, y, tries=10) -> bool:
    """Deja el cursor en (x,y). Devuelve False si algo lo mueve (mouse humano)."""
    for _ in range(tries):
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.13)
        p = cursor_pos()
        if abs(p[0] - x) <= 2 and abs(p[1] - y) <= 2:
            return True
    return False


def park_away(wrect, tries=10) -> bool:
    """Aparca el cursor lejos del widget y confirma que ahi se queda."""
    x, y = wrect[0] - 300, 560
    for _ in range(tries):
        user32.SetCursorPos(x, y)
        time.sleep(0.15)
        p = cursor_pos()
        if abs(p[0] - x) <= 2 and abs(p[1] - y) <= 2:
            p2 = cursor_pos()
            time.sleep(0.2)
            if abs(p2[0] - x) <= 2 and abs(p2[1] - y) <= 2:
                return True
    return False


def find_widget():
    tray = win32gui.FindWindow("Shell_TrayWnd", None)
    return tray, win32gui.FindWindowEx(tray, 0, "GorusTaskbarMusicWnd", None)


def button_centers(wrect, k, cfg):
    x0, y0, x1, y1 = wrect
    mid_y = (y0 + y1) // 2
    return [(x0 + (rx0 + rx1) // 2, mid_y)
            for rx0, ry0, rx1, ry1 in draw.control_rects(x1 - x0, k, cfg)]


def click(x, y) -> bool:
    if not place_cursor(x, y):
        return False
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    time.sleep(0.06)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
    time.sleep(0.35)
    return True


def grab(wrect):
    from PIL import ImageGrab
    return ImageGrab.grab(bbox=wrect).convert("L")


def mean_lum(img, box):
    """Luminancia media.

    No sirve contar pixeles sobre un umbral: el resaltado de hover sube el fondo
    del chip de ~28 a ~51, mientras el icono ya supera cualquier umbral alto, asi
    que el cambio quedaria invisible.
    """
    crop = img.crop(box)
    data = list(crop.getdata())
    return sum(data) / max(1, len(data))


def sample(poller, timeout=2.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = poller.state()
        if st.has_session:
            return st
        time.sleep(0.15)
    return poller.state()


def cell_box(wrect, cx, k):
    wl = cx - wrect[0]
    return (wl - 11, int(6 * k), wl + 11, int(34 * k))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hover-only", action="store_true")
    args = ap.parse_args()

    cfg = cfgmod.load()
    tray, w = find_widget()
    if not w:
        print("el widget no esta corriendo")
        return 1
    wrect = win32gui.GetWindowRect(w)
    k = (wrect[3] - wrect[1]) / 40.0
    centers = button_centers(wrect, k, cfg)
    print(f"widget en pantalla: {wrect}")
    print(f"centros de botones: {centers}\n")

    poller = MediaPoller(interval=0.3)
    poller.start()
    poller.wait_ready(6)
    before = sample(poller)
    print(f"estado inicial: {before.title!r} sonando={before.playing}\n")
    if not check("hay una sesion de medios activa", before.has_session):
        poller.stop()
        return 1

    # --- 0. el cursor se deja mover? -----------------------------------------
    libre = park_away(wrect)
    check("el cursor se puede posicionar (no hay interferencia)",
          libre, "si falla: hay un mouse humano moviendose" if not libre
          else "mouse libre", skipped=not libre)
    if not libre:
        interfered.append("posicionamiento del cursor")

    # --- 1. hover sobre cada boton (sin efectos secundarios) -----------------
    print("\n-- hover sobre los botones (sin efectos secundarios) --")
    hover_ok = []
    if not libre:
        for idx in range(len(centers)):
            hover_ok.append(None)
        check("el hover ilumina los tres botones", False,
              "no se pudo posicionar el cursor (interferencia del mouse)", skipped=True)
    else:
        park_away(wrect)
        reference = grab(wrect)
        for idx, (cx, cy) in enumerate(centers):
            if not place_cursor(cx, cy):
                interfered.append(f"boton {idx}")
                hover_ok.append(None)
                print(f"   boton {idx}: no se pudo posicionar el cursor (interferencia)")
                continue
            time.sleep(0.2)
            if not place_cursor(cx, cy):  # confirmar que sigue ahi
                interfered.append(f"boton {idx}")
                hover_ok.append(None)
                print(f"   boton {idx}: el cursor se movio antes de capturar")
                continue
            img = grab(wrect)
            box = cell_box(wrect, cx, k)
            s_on = mean_lum(img, box)
            s_off = mean_lum(reference, box)
            hover_ok.append(s_on > s_off + 0.5)
            print(f"   boton {idx}: luminancia {s_off:.2f} -> {s_on:.2f}  (+{s_on - s_off:.2f})")
        if all(v is not None for v in hover_ok):
            check("el hover ilumina los tres botones", all(hover_ok),
                  f"{sum(bool(v) for v in hover_ok)}/3 botones")
        else:
            check("el hover ilumina los tres botones", False,
                  f"no se pudo medir botones {[i for i, v in enumerate(hover_ok) if v is None]}",
                  skipped=True)
    check("el hover no cambia el estado de la musica",
          poller.state().playing == before.playing)

    if args.hover_only:
        user32.SetCursorPos(wrect[0] - 300, 560)
        poller.stop()
        return _summary()

    # --- 2. clic real en play/pausa, y restauracion --------------------------
    print("\n-- clic real en play/pausa (se restaura al final) --")
    toggle = centers[1]
    if not click(*toggle):
        check("el clic cambia el estado de reproduccion", False,
              "cursor inalcanzable por interferencia", skipped=True)
        check("el segundo clic restaura el estado original", False,
              "no aplica", skipped=True)
    else:
        time.sleep(1.6)
        mid = sample(poller)
        check("el clic cambia el estado de reproduccion", mid.playing != before.playing,
              f"{before.playing} -> {mid.playing}")
        if not click(*toggle):
            check("el segundo clic restaura el estado original", False,
                  "cursor inalcanzable por interferencia", skipped=True)
        else:
            time.sleep(1.8)
            after = sample(poller)
            check("el segundo clic restaura el estado original",
                  after.playing == before.playing, f"{mid.playing} -> {after.playing}")

    # --- 3. clic sobre el area de la caratula: no debe hacer nada ------------
    print("\n-- clic sobre el area de la caratula (no debe disparar nada) --")
    ref = sample(poller)
    art_x = wrect[0] + int(20 * k)
    if click(art_x, (wrect[1] + wrect[3]) // 2):
        time.sleep(1.2)
        st = sample(poller)
        check("un clic fuera de los botones no cambia nada",
              st.playing == ref.playing and st.title == ref.title,
              f"sonando={st.playing}")
    else:
        check("un clic fuera de los botones no cambia nada", False,
              "cursor inalcanzable por interferencia", skipped=True)

    user32.SetCursorPos(wrect[0] - 300, 560)
    poller.stop()
    return _summary()


def _summary() -> int:
    fails = [r for r in results if r[2] == FAIL]
    skips = [r for r in results if r[2] == SKIP]
    print(f"\n{len(results) - len(fails) - len(skips)}/{len(results)} pruebas pasaron"
          + (f", {len(skips)} saltadas" if skips else ""))
    if skips:
        print("Saltadas por interferencia del mouse: soltá el mouse y volvé a correr "
              "la prueba para un resultado completo.")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
