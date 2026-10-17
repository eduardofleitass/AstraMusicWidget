"""Auto-verificacion contra un widget ya en ejecucion.

Comprueba lo que de verdad importa: que este anclado donde debe, que se
reconstruya si algo lo tumba, que recupere su espacio si la barra se reacomoda,
que los pixeles realmente pintados sean los esperados, que el fondo sea de verdad
transparente cuando se lo pide, y que se pueda mover por la barra sin quedar
tapado por la lista de tareas.

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

WM_APP_MOVE = win32con.WM_APP + 1
WM_APP_ALPHA = win32con.WM_APP + 2
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


def rect(h) -> tuple:
    return win32gui.GetWindowRect(h)


def franja(x0: int, x1: int, y: int) -> list:
    from PIL import ImageGrab
    return list(ImageGrab.grab(bbox=(x0, y, x1, y + 1)).convert("RGB").getdata())


def difusa(a: list, b: list) -> tuple:
    d = [max(abs(a[i][c] - b[i][c]) for c in range(3)) for i in range(min(len(a), len(b)))]
    return sum(d) / max(1, len(d)), max(d)


def posicion(widget, frac, alpha=None, espera=0.9):
    win32gui.SendMessage(widget, WM_APP_MOVE, frac, 0)
    if alpha is not None:
        win32gui.SendMessage(widget, WM_APP_ALPHA, alpha, 0)
    time.sleep(espera)
    return rect(widget)


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
        # La caratula se mide por REGION, no por un pixel suelto: con un solo pixel
        # el resultado depende de que color tenga la tapa justo ahi (con una tapa
        # oscura la prueba fallaba sin que hubiera nada roto), y ademas no distingue
        # "hay una imagen" de "hay un color plano".
        caja = (max(1, int(5 * k)), max(1, int(5 * k)),
                max(2, int(35 * k)), max(2, int(35 * k)))
        gris = list(shot.crop(caja).convert("L").getdata())
        media = sum(gris) / max(1, len(gris))
        desv = (sum((v - media) ** 2 for v in gris) / max(1, len(gris))) ** 0.5
        chip = px[ww - 12, max(2, int(6 * k))]
        check("la caratula ocupa la esquina izquierda (imagen, no color plano)",
              desv >= 5 or abs(media - sum(chip) / 3.0) >= 8,
              f"media {media:.0f} desvio {desv:.1f} vs chip {chip}")
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

    # --- transparencia real -------------------------------------------------
    print("\n-- fondos: transparencia real medida contra la barra --")
    try:
        w_now = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
        tt = rect(p["tray"])[1]
        wr = posicion(w_now, 0xFFFF, 232)          # extremo derecho, chip solido
        an = rect(win32gui.FindWindowEx(p["tray"], 0, "DynamicContent2", None)
                  or p["anchor"])
        zona = (max(wr[0] + 40, 1250), min(wr[2] - 10, an[0] - 10))
        y = tt + 6                                  # dentro del chip
        muestras = {}
        for a in (0, 100, 170, 232):
            posicion(w_now, 0xFFFF, a)
            muestras[a] = franja(zona[0], zona[1], y)
        wr2 = posicion(w_now, 300, 232)             # a la izquierda: zona pelada
        pelado = franja(zona[0], zona[1], y)
        if wr2[2] >= zona[0]:
            check("franja de prueba libre para medir el fondo", False,
                  f"el widget en {wr2} tapa la franja {zona}")
        else:
            m0, mx0 = difusa(muestras[0], pelado)
            m100, _ = difusa(muestras[100], pelado)
            m232, _ = difusa(muestras[232], pelado)
            print(f"   franja {zona[0]}..{zona[1]} y={y - tt}: "
                  f"alpha0={m0:.2f}  alpha100={m100:.2f}  alpha232={m232:.2f}")
            check("sin fondo: se ve el fondo de la barra tal cual",
                  m0 <= 3, f"diferencia media {m0:.2f} (max {mx0})")
            check("fondo solido: el chip tapa el fondo", m232 >= 10,
                  f"diferencia media {m232:.2f}")
            check("los niveles de fondo son progresivos", m0 < m100 < m232,
                  f"{m0:.1f} < {m100:.1f} < {m232:.1f}")
    except Exception as exc:
        check("medicion de transparencia", False, repr(exc))

    # --- movimiento por la barra -------------------------------------------
    print("\n-- movimiento por la barra --")
    try:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        user32.WindowFromPoint.restype = wt.HWND
        user32.WindowFromPoint.argtypes = [wt.POINT]

        def quien(x, y):
            h = user32.WindowFromPoint(wt.POINT(int(x), int(y)))
            return win32gui.GetClassName(h) if h else "ninguna"

        w_now = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
        filas = []
        for f in range(0, 11, 2):
            frac = f / 10.0
            wr2 = posicion(w_now, int(frac * 1000), 232)
            rb2 = rect(win32gui.FindWindowEx(p["tray"], 0, "ReBarWindow32", None))
            ar2 = rect(win32gui.FindWindowEx(p["tray"], 0, "DynamicContent2", None)
                       or p["anchor"])
            arriba = quien((wr2[0] + wr2[2]) // 2, (wr2[1] + wr2[3]) // 2)
            filas.append((frac, wr2, rb2, ar2, arriba))
            print(f"   frac {frac:.1f}  widget.left={wr2[0]:5}  lista={rb2[2]-rb2[0]:4} px"
                  f"  tapado={'SI' if rb2[2] > wr2[0] + 1 else 'no'}  z={arriba}")
        check("el widget se mueve a lo largo de la barra",
              len({f[1][0] for f in filas}) >= 3,
              f"{len({f[1][0] for f in filas})} posiciones distintas")
        check("nunca queda tapado por la lista de tareas",
              all(f[2][2] <= f[1][0] + 1 for f in filas),
              f"peor: {max(f[2][2] - f[1][0] for f in filas)} px de invasión")
        check("nadie mas lo tapa en su zona",
              all(f[4] == "GorusTaskbarMusicWnd" for f in filas),
              str({f[4] for f in filas}))
        check("nunca invade el bloque de la bandeja",
              all(f[1][2] <= f[3][0] for f in filas),
              f"peor: {max(f[1][2] - f[3][0] for f in filas)} px")
        check("al extremo derecho queda pegado al ancla",
              abs(filas[-1][1][2] - filas[-1][3][0]) <= 3,
              f"right={filas[-1][1][2]} ancla={filas[-1][3][0]}")
        check("la lista de tareas conserva espacio usable en todo el recorrido",
              min(f[2][2] - f[2][0] for f in filas) >= 300,
              f"minimo {min(f[2][2] - f[2][0] for f in filas)} px")
    except Exception as exc:
        check("medicion del movimiento", False, repr(exc))

    # --- vigilancia del pintado --------------------------------------------
    print("\n-- vigilancia del pintado (30 muestras, ~9 s) --")
    try:
        w_now = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
        posicion(w_now, 0xFFFF, 232)
        tt = rect(p["tray"])[1]
        malos = 0
        total = 0
        for _ in range(30):
            time.sleep(0.3)
            wr3 = rect(w_now)
            fondo = franja(wr3[0] - 2, wr3[0] - 1, tt + 3)[0]
            borde = franja(wr3[2] - 12, wr3[2] - 11, tt + 3)[0]
            total += 1
            if max(abs(fondo[i] - borde[i]) for i in range(3)) <= 3:
                malos += 1
        check(f"el widget no queda borrado por la barra", malos <= 1,
              f"{total - malos}/{total} cuadros correctos")
    except Exception as exc:
        check("vigilancia del pintado", False, repr(exc))

    try:
        w_now = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
        posicion(w_now, 0xFFFF, int(cfg.get("chip_alpha", 232)))  # dejar como estaba
    except Exception:
        pass

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
