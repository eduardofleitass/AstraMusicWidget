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
WM_APP_CANCEL_SCRUB = win32con.WM_APP + 3
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_CAPTURECHANGED = 0x0215
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = []


def check(name: str, ok: bool, detail: str = "", skipped: bool = False) -> bool:
    RESULTS.append((name, bool(ok), detail, bool(skipped)))
    tag = "SALTA" if skipped else ("PASA" if ok else "FALLA")
    print(f"{tag:5}  {name}" + (f"  -> {detail}" if detail else ""))
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


def franja_rgb(wr: tuple, y_rel: int, x0: int, x1: int) -> list:
    """Pixeles de una fila del widget, en coordenadas relativas."""
    from PIL import ImageGrab
    return list(ImageGrab.grab(bbox=(wr[0] + x0, wr[1] + y_rel, wr[0] + x1, wr[1] + y_rel + 1))
                .convert("RGB").getdata())


def region_rgb(wr: tuple, y0: int, y1: int, x0: int, x1: int) -> list:
    """Pixeles de una franja de varias filas (para medir TEXTO, que no se puede
    medir con una sola fila: los glifos empiezan unos pixeles mas abajo)."""
    from PIL import ImageGrab
    return list(ImageGrab.grab(bbox=(wr[0] + x0, wr[1] + y0, wr[0] + x1, wr[1] + y1))
                .convert("RGB").getdata())


def fila_dif(a: list, b: list, umbral: int = 25) -> tuple:
    """(cuanto cambia en promedio, x relativa del cambio mas a la derecha)."""
    n = min(len(a), len(b))
    d = [max(abs(a[i][c] - b[i][c]) for c in range(3)) for i in range(n)]
    ultimo = max((i for i, v in enumerate(d) if v > umbral), default=-1)
    return (sum(d) / max(1, len(d)), ultimo)


def log_lineas() -> list:
    try:
        with open(os.path.join(os.path.dirname(HERE), "widget.log"), encoding="utf-8") as fh:
            return fh.readlines()
    except Exception:
        return []


def scrub_sim(hwnd, wx: int, y: int, mover_a=None) -> tuple:
    """Arrastre simulado sobre la barra, SIN tocar la reproduccion ni el cursor.

    El mensaje va directo a la ventana (no hay raton real de por medio), asi que se
    ejercita el mismo procedimiento de la ventana. Al no soltar el boton, el salto
    no se manda nunca: la prueba mira la previsualizacion y aborta.
    """
    win32gui.PostMessage(hwnd, WM_LBUTTONDOWN, 1, wx | (y << 16))
    time.sleep(0.5)
    if mover_a is not None:
        win32gui.PostMessage(hwnd, WM_MOUSEMOVE, 1, mover_a | (y << 16))
        time.sleep(0.5)
    return rect(hwnd)


def scrub_abortar(hwnd) -> tuple:
    """Aborta el arrastre como lo haria el widget mismo: suelta la captura de raton
    en su propio hilo. Con un WM_CAPTURECHANGED simulado la captura quedaba puesta y
    el siguiente clic real se perdia (el sistema la reseteaba en el mousedown)."""
    win32gui.PostMessage(hwnd, WM_APP_CANCEL_SCRUB, 0, 0)
    time.sleep(0.7)
    return rect(hwnd)


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

    # --- barra de progreso: zona clicable y previsualizacion ---------------
    print("\n-- barra de progreso: zona clicable y previsualizacion --")
    try:
        w_now = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
        wr = rect(w_now)
        ww2, wh2 = wr[2] - wr[0], wr[3] - wr[1]
        pr = draw.progress_rect(ww2, k, cfg)
        ctl = draw.control_rects(ww2, k, cfg)
        check("la barra de progreso tiene zona clicable",
              bool(pr) and (pr[2] - pr[0]) >= 40, f"{pr}")
        check("la zona clicable de la barra no pisa los botones",
              bool(pr) and (not ctl or pr[2] <= ctl[0][0]),
              f"barra hasta x={pr[2] if pr else '?'} / botones desde "
              f"x={ctl[0][0] if ctl else '-'}")
        check("la franja clicable entra dentro del widget",
              bool(pr) and pr[0] >= 0 and pr[2] < ww2 and pr[3] <= wh2,
              f"franja {pr} dentro de {ww2}x{wh2}")
        if pr:
            medio = draw.progress_frac_at((pr[0] + pr[2]) / 2.0, ww2, k, cfg)
            check("la mitad de la barra corresponde a la mitad del tema",
                  abs(medio - 0.5) <= 0.06, f"fraccion {medio:.3f}")
            check("los extremos de la barra dan 0 y 1",
                  draw.progress_frac_at(pr[0], ww2, k, cfg) <= 0.01
                  and draw.progress_frac_at(pr[2], ww2, k, cfg) >= 0.99,
                  f"{draw.progress_frac_at(pr[0], ww2, k, cfg):.2f} / "
                  f"{draw.progress_frac_at(pr[2], ww2, k, cfg):.2f}")

            from widget.media import MediaPoller
            probe = MediaPoller(interval=0.3)
            probe.start()
            probe.wait_ready(6)
            time.sleep(0.9)
            seekable = probe.state().can_seek
            probe.stop()

            destino = 0.88
            x_dest = int(pr[0] + (pr[2] - pr[0]) * destino)
            x_ini = int(pr[0] + (pr[2] - pr[0]) * 0.5)
            y_barra = int(35.5 * k)
            # El texto del renglon del artista va de ARTIST_Y hacia abajo; con una
            # sola fila se mide el borde de los glifos y parece que no cambio nada.
            y_txt0, y_txt1 = int(draw.ARTIST_Y * k) + 3, int(draw.ARTIST_Y * k) + 11
            x_txt, x_txt1 = int(draw.TEXT_X * k), int(ww2 * 0.75)
            barra_antes = franja_rgb(wr, y_barra, 0, ww2)
            texto_antes = region_rgb(wr, y_txt0, y_txt1, x_txt, x_txt1)
            n_log = len(log_lineas())

            wr2 = scrub_sim(w_now, x_ini, y_barra, mover_a=x_dest)
            barra_scrub = franja_rgb(wr, y_barra, 0, ww2)
            texto_scrub = region_rgb(wr, y_txt0, y_txt1, x_txt, x_txt1)
            check("el arrastre sobre la barra no mueve el widget", wr2 == wr,
                  f"{wr} -> {wr2}")
            if not seekable:
                check("durante el arrastre la barra llega al destino", False,
                      "este reproductor no admite saltos", skipped=True)
                check("durante el arrastre se ve la hora destino", False,
                      "no aplica", skipped=True)
            else:
                m, ultimo = fila_dif(barra_antes, barra_scrub)
                check("durante el arrastre la barra llega al destino",
                      ultimo >= x_dest - max(8, int(6 * k)),
                      f"el cambio mas a la derecha esta en x={ultimo}, destino x={x_dest}"
                      f" (diferencia media {m:.1f})")
                check("la barra no se dibuja por debajo de los botones",
                      ultimo <= pr[2] + 8,
                      f"cambio hasta x={ultimo}, la barra termina en x={pr[2]}")
                mt, _ = fila_dif(texto_antes, texto_scrub, umbral=10)
                check("durante el arrastre se ve la hora destino", mt >= 3.0,
                      f"diferencia media en el renglon del artista {mt:.1f}")

            scrub_abortar(w_now)
            barra_final = franja_rgb(wr, y_barra, 0, ww2)
            saltos = [l for l in log_lineas()[n_log:] if "salto" in l]
            check("al abortar el arrastre no se manda ningun salto", not saltos,
                  f"{len(saltos)} lineas de salto en el log")
            i_dest = min(max(0, x_dest - 3), len(barra_final) - 1)
            dif_dest = max(abs(barra_final[i_dest][c] - barra_antes[i_dest][c]) for c in range(3))
            check("al abortar, la barra vuelve al progreso real", dif_dest <= 60,
                  f"diferencia en el destino {dif_dest} (era el indicador de arrastre)")
    except Exception as exc:
        check("medicion de la barra de progreso", False, repr(exc))

    # --- superficie sensible al mouse ---------------------------------------
    print("\n-- superficie sensible al mouse (con el fondo transparente) --")
    try:
        import ctypes
        import ctypes.wintypes as wt
        u32 = ctypes.windll.user32
        u32.WindowFromPoint.restype = wt.HWND
        u32.WindowFromPoint.argtypes = [wt.POINT]
        w_now = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
        # Sin fondo es el caso que fallaba: el alpha 0 por pixel hace que Windows
        # le entregue el mouse a la barra de tareas en las zonas vacias.
        posicion(w_now, 0xFFFF, 0)
        wr = rect(w_now)
        puntos = {
            "centro": ((wr[0] + wr[2]) // 2, (wr[1] + wr[3]) // 2),
            "hueco del boton play/pausa": (wr[0] + 263, (wr[1] + wr[3]) // 2),
            "zona vacia arriba al medio": (wr[0] + 150, wr[1] + 8),
            "esquina inferior derecha": (wr[2] - 8, wr[3] - 8),
        }
        malos = [n for n, (x, y) in puntos.items()
                 if u32.WindowFromPoint(wt.POINT(int(x), int(y))) != w_now]
        check("el widget recibe el mouse en toda su superficie (fondo transparente)",
              not malos, f"puntos que se lleva la barra: {malos or 'ninguno'}")
        posicion(w_now, 0xFFFF, int(cfg.get("chip_alpha", 232)))
    except Exception as exc:
        check("superficie sensible al mouse", False, repr(exc))

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

    fails = [r for r in RESULTS if not r[1] and not r[3]]
    skips = [r for r in RESULTS if r[3]]
    print(f"\n{len(RESULTS) - len(fails) - len(skips)}/{len(RESULTS)} pruebas pasaron"
          + (f", {len(skips)} saltadas" if skips else ""))
    out = os.path.join(HERE, "_selftest.json")
    try:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump([{"prueba": n, "pasa": o, "detalle": d, "salta": s}
                       for n, o, d, s in RESULTS], fh, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
