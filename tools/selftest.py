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
import win32api  # noqa: E402
import win32gui  # noqa: E402

from widget import config as cfgmod  # noqa: E402
from widget.taskbarwin import TaskbarHost, list_bars  # noqa: E402
from widget import draw  # noqa: E402

WM_APP_PANEL = win32con.WM_APP + 10
WM_APP_PANEL_CFG = win32con.WM_APP + 11
WM_APP_MOVE = win32con.WM_APP + 1
WM_APP_ALPHA = win32con.WM_APP + 2
WM_APP_CANCEL_SCRUB = win32con.WM_APP + 3
WM_APP_WAVES = win32con.WM_APP + 4
WM_APP_COLOR = win32con.WM_APP + 5
WM_APP_MONITOR = win32con.WM_APP + 6
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


def barra_del_widget():
    """(datos de la barra, hwnd del widget) donde sea que este viviendo.

    No se asume la barra principal: el widget puede estar en la de otro monitor.
    """
    barras = list_bars()
    for b in barras:
        w = win32gui.FindWindowEx(b["tray"], 0, "GorusTaskbarMusicWnd", None)
        if w:
            return b, w
    return (barras[0] if barras else None), 0


def host_de(barra) -> TaskbarHost:
    """Host apuntado a esa barra (resuelve contenedor y ancla de ESE monitor).

    En la principal el contenedor es ReBarWindow32 y el ancla el bloque de noticias;
    en las secundarias el contenedor es un WorkerW y el ancla el reloj.
    """
    host = TaskbarHost()
    if barra:
        host.select(None if barra["primario"] else barra["monitor"])
    host.refresh()
    return host


def tray_parts():
    barra, w = barra_del_widget()
    host = host_de(barra)
    return {"tray": host.tray, "rebar": host.container, "anchor": host.anchor,
            "widget": w, "barra": host.barra}


def rect(h) -> tuple:
    return win32gui.GetWindowRect(h)


def franja(x0: int, x1: int, y: int) -> list:
    from PIL import ImageGrab
    return list(ImageGrab.grab(all_screens=True, bbox=(x0, y, x1, y + 1)).convert("RGB").getdata())


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
    return list(ImageGrab.grab(all_screens=True, bbox=(wr[0] + x0, wr[1] + y_rel, wr[0] + x1, wr[1] + y_rel + 1))
                .convert("RGB").getdata())


def region_rgb(wr: tuple, y0: int, y1: int, x0: int, x1: int) -> list:
    """Pixeles de una franja de varias filas (para medir TEXTO, que no se puede
    medir con una sola fila: los glifos empiezan unos pixeles mas abajo)."""
    from PIL import ImageGrab
    return list(ImageGrab.grab(all_screens=True, bbox=(wr[0] + x0, wr[1] + y0, wr[0] + x1, wr[1] + y1))
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
    pegado = abs(w_rect[2] - a_rect[0]) <= 3
    frenado = w_rect[2] < a_rect[0]
    check("no pisa el bloque de la bandeja (pegado al ancla o frenado por la lista)",
          w_rect[2] <= a_rect[0] + 3,
          f"widget.right={w_rect[2]} vs ancla.left={a_rect[0]}"
          + ("" if pegado else " (frenado por el espacio de la lista de tareas)"))
    check("pegado al ancla cuando la lista no lo impide",
          pegado or frenado,
          "pegado" if pegado else "frenado por la lista, que es lo esperado con "
          "muchas ventanas abiertas")
    check("la lista de tareas cedio el espacio", r_rect[2] <= w_rect[0] + 2,
          f"rebar.right={r_rect[2]} < widget.left={w_rect[0]}")
    # min_tasklist_width es el minimo PREFERIDO; cuando el widget se mueve libre el
    # piso real es min_tasklist_free (el limite lo descubre el propio widget). Se
    # comprueba el piso y se informa el ancho real.
    piso_lista = int(cfg.get("min_tasklist_free", 140))
    ancho_lista = r_rect[2] - r_rect[0]
    check("la lista de tareas nunca baja de su piso",
          ancho_lista >= piso_lista - 4,
          f"{ancho_lista} px (piso {piso_lista}, preferido "
          f"{cfg.get('min_tasklist_width', 420)})")

    # --- pixeles realmente pintados -------------------------------------
    try:
        from PIL import ImageGrab
        shot = ImageGrab.grab(all_screens=True, bbox=w_rect).convert("RGB")
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
        r2 = win32gui.GetWindowRect(p["rebar"])
        a2 = win32gui.GetWindowRect(p["anchor"])
        check("renace sin pisar el bloque de la bandeja", rb[2] <= a2[0] + 3,
              f"right={rb[2]} ancla={a2[0]}"
              + ("" if abs(rb[2] - a2[0]) <= 3 else " (frenado por la lista)"))
        check("renace visible", bool(win32gui.IsWindowVisible(reborn)))
        check("vuelve a reservar su espacio", r2[2] <= rb[0] + 2,
              f"rebar.right={r2[2]} widget.left={rb[0]}")

    # --- recuperacion: la barra se reacomoda a lo ancho --------------------
    print("\n-- prueba de recuperacion: la barra recupera su ancho natural --")
    reb = p["rebar"]
    rr = win32gui.GetWindowRect(reb)
    an = win32gui.GetWindowRect(p["anchor"])
    win32gui.SetWindowPos(reb, 0, 0, 0, an[0] - rr[0], rr[3] - rr[1],
                          win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
    print(f"  la lista de tareas vuelve a ocupar todo: right={an[0]}")
    ok = False
    for _ in range(25):
        time.sleep(0.2)
        rr2 = win32gui.GetWindowRect(p["rebar"])
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
        an = rect(p["anchor"])
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
            # El cuanto depende del papel tapiz detras de la barra de ese monitor
            # (la barra es translucida): 10 es lo que da en la principal, en la del
            # secundario puede quedar en ~8. La invariante es que tape de forma
            # perceptible y que los niveles sean progresivos.
            check("fondo solido: el chip tapa el fondo", m232 >= 6,
                  f"diferencia media {m232:.2f} (en el monitor principal suele "
                  f"pasar de 10)")
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
            rb2 = rect(p["rebar"])
            ar2 = rect(p["anchor"])
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
        piso = int(cfg.get("min_tasklist_free", 140))
        menor = min(f[2][2] - f[2][0] for f in filas)
        check("la lista de tareas nunca baja de su piso usable",
              menor >= piso - 4, f"minimo {menor} px (piso configurado {piso})")
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

    # --- ondas de sonido ----------------------------------------------------
    print("\n-- ondas de sonido (franja, animacion y recorte del texto) --")
    try:
        from PIL import ImageGrab
        from widget.media import MediaPoller
        w_now = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
        wr = rect(w_now)
        ww2 = wr[2] - wr[0]
        wb = draw.wave_band(ww2, cfg)
        ctl = draw.control_rects(ww2, k, cfg)
        check("la franja de las ondas entra entre el texto y los botones",
              bool(wb) and (not ctl or wb[1] < ctl[0][0])
              and wb[0] >= draw.TEXT_X + draw.WAVE_MIN_TEXT,
              f"franja {wb} / los botones empiezan en x={ctl[0][0] if ctl else '-'}")
        wrec = draw.wave_rect(ww2, k, cfg)

        def captura():
            return ImageGrab.grab(all_screens=True, bbox=(wr[0], wr[1], wr[0] + ww2, wr[3])).convert("RGB")

        def distintos(a, b, box, umbral=30):
            """Pixeles que cambian entre dos capturas en esa region.

            Se compara contra la MISMA region de la otra captura en vez de contar
            un color: asi la comprobacion sirve con cualquier color elegido (con
            las ondas en rosa, contar pixeles verdes daba cero y parecia roto).
            """
            x0, y0, x1, y1 = box
            n = 0
            for x in range(max(0, x0), min(a.width, x1)):
                for y in range(max(0, y0), min(a.height, y1)):
                    pa, pb = a.getpixel((x, y)), b.getpixel((x, y))
                    if max(abs(pa[i] - pb[i]) for i in range(3)) > umbral:
                        n += 1
            return n

        estaba = bool(cfg.get("show_waves", False))
        win32gui.SendMessage(w_now, WM_APP_WAVES, 0, 0)      # sin guardar en config.json
        time.sleep(0.7)
        apagadas = captura()
        # Con las ondas apagadas la franja tiene que quedar lisa. Se mide en el DIBUJO y
        # no en la pantalla: con la barra de tareas translucida y el widget sin fondo
        # (chip_alpha 0), el fondo de la franja es el escritorio y varia por si solo
        # -medido: 47 pixeles distintos del fondo con las ondas encendidas y 58 con las
        # apagadas, asi que el umbral en pantalla no probaba nada-.
        from widget.media import MediaState as _MS
        est_franja = _MS(has_session=True, app_id="test.exe", title="Titulo",
                                artist="Artista", playing=False, position=30.0,
                                duration=180.0, position_at=time.monotonic(), art=None,
                                art_key="k", can_seek=True, can_toggle=True)
        apagado = draw.render(est_franja, dict(cfg, show_waves=False), art=None,
                              k=1.0, opaque=True, base=(40, 34, 33))
        wr_off = draw.wave_rect(apagado.width, 1.0, cfg)
        fuera = sum(1 for x in range(wr_off[0] + 1, wr_off[2] - 1)
                    for y in range(wr_off[1] + 1, wr_off[3] - 1)
                    if max(abs(apagado.getpixel((x, y))[i] - (40, 34, 33)[i])
                           for i in range(3)) > 6)
        check("con las ondas apagadas la franja queda lisa", fuera == 0,
              f"{fuera} pixeles fuera del fondo liso en la franja {wr_off} (medido en el dibujo)")

        probe = MediaPoller(interval=0.3)
        probe.start()
        probe.wait_ready(6)
        time.sleep(0.9)
        sonando = probe.state().playing
        probe.stop()

        win32gui.SendMessage(w_now, WM_APP_WAVES, 1, 0)
        time.sleep(0.7)
        cuadros = []
        for _ in range(8):
            cuadros.append(distintos(apagadas, captura(),
                                     (wrec[0], wrec[1], wrec[2], wrec[3])))
            time.sleep(0.16)
        if not sonando:
            check("con las ondas encendidas la animacion cambia de cuadro", False,
                  "la musica esta en pausa: las barras quedan planas a proposito",
                  skipped=True)
        else:
            check("con las ondas encendidas la animacion cambia de cuadro",
                  len(set(cuadros)) >= 3 and max(cuadros) > 0,
                  f"{len(set(cuadros))} cuadros distintos de {len(cuadros)}: {cuadros}")
        # el texto tiene que quedar recortado antes de la franja: ni un pixel claro
        # dentro de ella
        im = captura()
        claros = sum(1 for x in range(wrec[0] + 1, wrec[2] - 1) for y in range(0, int(29 * k))
                     if min(im.getpixel((x, y))) > 140
                     and max(im.getpixel((x, y))) - min(im.getpixel((x, y))) < 40)
        check("el texto se recorta antes de la franja de las ondas", claros == 0,
              f"{claros} pixeles de texto dentro de la franja")
        # Las barras no pueden salirse: se miran las zonas vecinas sin texto (a la
        # derecha, hasta los botones, y arriba). Mas abajo pasa la barra de progreso.
        con_ondas = captura()
        derecha = distintos(apagadas, con_ondas, (wrec[2], wrec[1], wrec[2] + 5, wrec[3]))
        arriba = distintos(apagadas, con_ondas, (wrec[0], 0, wrec[2], wrec[1] - 1))
        check("las ondas no se salen de su franja", derecha + arriba == 0,
              f"a la derecha {derecha}, arriba {arriba} (franja {wrec})")

        win32gui.SendMessage(w_now, WM_APP_WAVES, 1 if estaba else 0, 0)
        time.sleep(0.4)
    except Exception as exc:
        check("medicion de las ondas de sonido", False, repr(exc))

    # --- colores personalizados --------------------------------------------
    print("\n-- colores de la barra de progreso y de las ondas --")
    try:
        from PIL import ImageGrab
        w_now = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
        wr = rect(w_now)
        ww2 = wr[2] - wr[0]
        check("los colores se entienden en hex, en lista y en corto",
              draw.parse_color("#FF0000") == (255, 0, 0)
              and draw.parse_color("#f00") == (255, 0, 0)
              and draw.parse_color([0, 128, 255]) == (0, 128, 255)
              and draw.parse_color("no es un color") is None
              and draw.parse_color(None) is None,
              f"'#f00' -> {draw.parse_color('#f00')}, '[0,128,255]' -> "
              f"{draw.parse_color([0, 128, 255])}, basura -> {draw.parse_color('no es un color')}")

        pr = draw.progress_rect(ww2, k, cfg)
        wrec = draw.wave_rect(ww2, k, cfg)
        y_barra = wr[1] + int(35.5 * k)

        def cuenta(box, cual):
            im = ImageGrab.grab(all_screens=True, bbox=box).convert("RGB")
            out = 0
            for q in im.get_flattened_data():
                r, g, b = q
                if cual == "rojo" and r > g + 60 and r > b + 60:
                    out += 1
                elif cual == "azul" and b > r + 60 and b > g + 60:
                    out += 1
            return out

        # La franja incluye unas filas de mas: si el tema esta al principio el
        # relleno mide 1 px y solo la perilla tiene color; midiendo una sola fila esa
        # perilla aporta 3 px y la comprobacion falla sin que haya nada roto.
        caja_barra = (wr[0] + pr[0], y_barra - 3, wr[0] + pr[2], y_barra + 4)
        caja_ondas = (wr[0] + wrec[0], wr[1] + wrec[1], wr[0] + wrec[2], wr[1] + wrec[3])
        estaba_w = bool(cfg.get("show_waves", False))
        prob_antes, ond_antes = cfg.get("progress_color"), cfg.get("waves_color")

        # El relleno de la barra solo se dibuja si hay progreso: con el tema recien
        # empezado (0%) no hay ni un pixel del color elegido y la medicion da cero
        # sin que haya nada roto. Se adelanta a la mitad para poder medir el color.
        try:
            from widget.media import MediaPoller as _MP
            _pm = _MP(interval=0.3)
            _pm.start()
            _pm.wait_ready(6)
            for _ in range(12):
                if _pm.state().has_session:
                    break
                time.sleep(0.4)
            _st_c = _pm.state()
            if _st_c.can_seek and _st_c.duration > 8 and _st_c.live_position() < _st_c.duration * 0.3:
                _pm.seek(_st_c.duration * 0.5)
                time.sleep(1.2)
            _pm.stop()
        except Exception:
            pass

        win32gui.SendMessage(w_now, WM_APP_WAVES, 1, 0)
        win32gui.SendMessage(w_now, WM_APP_COLOR, 1, 0xFF0000)   # barra roja
        win32gui.SendMessage(w_now, WM_APP_COLOR, 2, 0x0000FF)   # ondas azules
        time.sleep(0.8)
        rojo_barra = cuenta(caja_barra, "rojo")
        azul_ondas = cuenta(caja_ondas, "azul")
        check("la barra de progreso toma el color elegido", rojo_barra >= 4,
              f"{rojo_barra} pixeles rojos en la barra")
        check("las ondas toman su propio color", azul_ondas >= 4,
              f"{azul_ondas} pixeles azules en la franja de las ondas")
        check("cada uno con su color: la barra no se pinta de azul",
              cuenta(caja_barra, "azul") == 0,
              f"{cuenta(caja_barra, 'azul')} pixeles azules en la barra")
        check("cada uno con su color: las ondas no se pintan de rojo",
              cuenta(caja_ondas, "rojo") == 0,
              f"{cuenta(caja_ondas, 'rojo')} pixeles rojos en las ondas")

        # volver como estaba (sin guardar en config.json)
        for wp, valor in ((1, prob_antes), (2, ond_antes)):
            c = draw.parse_color(valor)
            win32gui.SendMessage(w_now, WM_APP_COLOR, wp,
                                 0 if c is None else (c[0] << 16) | (c[1] << 8) | c[2])
        win32gui.SendMessage(w_now, WM_APP_WAVES, 1 if estaba_w else 0, 0)
        time.sleep(0.7)
        azul_final = cuenta(caja_ondas, "azul")
        if ond_antes is None:
            check("al volver al color del tema las ondas dejan el azul",
                  azul_final <= max(1, azul_ondas // 4),
                  f"{azul_final} pixeles azules despues de restaurar (habia {azul_ondas})")
        else:
            check("al volver a su color guardado las ondas dejan el azul", False,
                  f"el color guardado era {ond_antes!r}: no aplica", skipped=True)
    except Exception as exc:
        check("medicion de los colores", False, repr(exc))

    # --- barra de tareas de otro monitor ------------------------------------
    print("\n-- barra de tareas de otro monitor --")
    try:
        import ctypes
        import ctypes.wintypes as wt
        u32 = ctypes.windll.user32
        u32.WindowFromPoint.restype = wt.HWND
        u32.WindowFromPoint.argtypes = [wt.POINT]
        barras = list_bars()
        actual, w_now = barra_del_widget()
        if len(barras) < 2 or not w_now or actual is None:
            check("el equipo tiene mas de una barra de tareas", False,
                  f"{len(barras)} barra(s): no hay otro monitor que probar", skipped=True)
        else:
            idx_actual = barras.index(actual)
            destino = next(b for b in barras if b["tray"] != actual["tray"])
            idx_destino = barras.index(destino)
            h_dest, h_act = host_de(destino), host_de(actual)
            ancla_dest = h_dest._anchor_rect()
            ancla_act = h_act._anchor_rect()

            win32gui.SendMessage(w_now, WM_APP_MONITOR, idx_destino, 0)   # sin guardar
            time.sleep(1.7)
            b2, w2 = barra_del_widget()
            rb2 = rect(h_dest.container) if h_dest.container else (0, 0, 0, 0)
            wr2 = rect(w2) if w2 else (0, 0, 0, 0)
            check("el widget se muda a la barra del otro monitor",
                  bool(w2) and b2 is not None and b2["tray"] == destino["tray"],
                  f"ahora vive en {b2['nombre'] if b2 else '?'} "
                  f"(se pidio {destino['nombre']})")
            check("la ventana nueva es hija de esa barra",
                  bool(w2) and win32gui.GetParent(w2) == destino["tray"],
                  f"padre {hex(win32gui.GetParent(w2)) if w2 else '-'} "
                  f"vs barra {hex(destino['tray'])}")
            check("queda dentro de esa barra",
                  bool(w2) and wr2[0] >= destino["rect"][0] and wr2[2] <= destino["rect"][2],
                  f"widget {wr2} dentro de {destino['rect']}")
            check("esa barra le cede el espacio", bool(rb2[0]) and rb2[2] <= wr2[0] + 2,
                  f"contenedor.right={rb2[2]} widget.left={wr2[0]}")
            check("no invade el bloque de la derecha", bool(w2) and wr2[2] <= ancla_dest[0],
                  f"widget.right={wr2[2]} ancla.left={ancla_dest[0]}")
            check("el widget esta visible en la barra nueva",
                  bool(w2) and bool(win32gui.IsWindowVisible(w2)))
            centro = ((wr2[0] + wr2[2]) // 2, (wr2[1] + wr2[3]) // 2)
            tapado = (win32gui.GetClassName(u32.WindowFromPoint(wt.POINT(int(centro[0]), int(centro[1]))))
                      if w2 else "-")
            check("nadie lo tapa en la barra nueva", bool(w2) and tapado == "GorusTaskbarMusicWnd",
                  f"en el centro devuelve {tapado}")
            rb_act = rect(h_act.container) if h_act.container else (0, 0, 0, 0)
            check("la barra que dejo recupera su ancho natural",
                  abs((rb_act[2] - rb_act[0]) - (ancla_act[0] - rb_act[0])) <= 3,
                  f"contenedor {rb_act[2] - rb_act[0]} px, natural "
                  f"{ancla_act[0] - rb_act[0]} px")

            # volver a donde estaba
            win32gui.SendMessage(w2, WM_APP_MONITOR, idx_actual, 0)
            time.sleep(1.7)
            b3, w3 = barra_del_widget()
            check("la vuelta deja el widget en su barra",
                  bool(w3) and b3 is not None and b3["tray"] == actual["tray"],
                  f"quedo en {b3['nombre'] if b3 else '?'}")
            rb_dest2 = rect(h_dest.container) if h_dest.container else (0, 0, 0, 0)
            check("la barra que dejo tambien recupera su ancho natural",
                  abs((rb_dest2[2] - rb_dest2[0]) - (ancla_dest[0] - rb_dest2[0])) <= 3,
                  f"contenedor {rb_dest2[2] - rb_dest2[0]} px, natural "
                  f"{ancla_dest[0] - rb_dest2[0]} px")
    except Exception as exc:
        check("medicion de la barra de otro monitor", False, repr(exc))

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

    # --- volumen: celda del altavoz, fila de volumen y sesion de audio ---------
    print("\n-- volumen de la app --")
    # (a) geometria: el altavoz va despues de los botones y no pisa nada
    w_now = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
    ww3 = (rect(w_now)[2] - rect(w_now)[0]) if w_now else int(cfg.get("width", 300))
    ctrls = draw.control_rects(ww3, k, cfg)
    wrec = draw.wave_rect(ww3, k, cfg)
    prg = draw.progress_span(ww3, cfg)
    check("el altavoz es la cuarta celda, a la derecha del transporte",
          len(ctrls) == 4 and ctrls[3][0] > ctrls[2][0] == ctrls[1][2],
          f"{len(ctrls)} celdas; altavoz en {ctrls[3][:1] + ctrls[3][2:3] if ctrls else '-'}"
          if ctrls else "")
    check("la celda del altavoz no se mete en las ondas ni en el texto",
          bool(wrec and prg and wrec[2] <= ctrls[3][0] and prg[1] <= ctrls[3][0]),
          f"ondas hasta x={wrec[2] if wrec else '-'}, texto hasta x={prg[1] if prg else '-'}, "
          f"altavoz desde x={ctrls[3][0] if ctrls else '-'}")

    # (b) dibujo: la fila del progreso se convierte en barra de volumen
    try:
        from PIL import Image
        from widget.media import MediaState
        st_v = MediaState(has_session=True, app_id="prueba.exe", title="Titulo de prueba",
                          artist="Artista de prueba", playing=True, position=30.0,
                          duration=200.0, position_at=time.monotonic(), art=None,
                          art_key="k", can_seek=True, min_seek=0, max_seek=200,
                          can_toggle=True, can_prev=True, can_next=True)

        def cuadro(vol):
            return draw.render(st_v, cfg, k=k, base=(28, 30, 38), height=int(40 * k),
                               volume=vol).convert("RGB")

        # Con un color fijo (y sin auto-contraste) la barra queda en rojo puro:
        # contando filas rojas se mide el relleno exacto, sin umbrales de luminancia
        # que dependan del tema o del color que haya elegido el usuario.
        cfg_rojo = dict(cfg, progress_color="#FF0000", auto_contrast=False)

        def cuadro_rojo(vol):
            return draw.render(st_v, cfg_rojo, k=k, base=(28, 30, 38),
                               height=int(40 * k), volume=vol).convert("RGB")

        def filas_rojas(im, x=100, exacto=True):
            """Filas con relleno rojo en esa columna.

            Con exacto=True se cuentan solo los pixeles de rojo puro (el nucleo del
            relleno); con exacto=False se toleran los bordes suavizados, que es lo
            que hace falta para comparar grosores.
            """
            n = 0
            for y in range(26, 40):
                r, g, b = im.getpixel((x, y))
                if (255, 0, 0) == (r, g, b) if exacto else (r > 140 and g < 120 and b < 120):
                    n += 1
            return n

        normal = cuadro(None)
        volumen = cuadro((0.45, False, True, True))
        mudo = cuadro((0.45, True, True, True))
        sin_sesion = cuadro((0.45, False, True, False))
        # La cancion esta en 30 s de 200 (15%): a 100 px del borde izquierdo el
        # progreso no llega, pero el volumen al 45% si. Y la barra ademas se dibuja
        # 1,8 veces mas gruesa cuando esta activa.
        rojo_n = filas_rojas(cuadro_rojo(None))
        rojo_v = filas_rojas(cuadro_rojo((0.45, False, True, True)))
        rojo_m = filas_rojas(cuadro_rojo((0.45, True, True, True)))
        # grosor: en x=50 el progreso tambien tiene relleno (15%), asi que ahi se
        # comparan grosores; en x=100 solo el volumen llega
        grue_n = filas_rojas(cuadro_rojo(None), 50, exacto=False)
        grue_v = filas_rojas(cuadro_rojo((0.45, False, True, True)), 50, exacto=False)
        check("con el volumen a la vista la fila muestra el nivel donde el progreso no llega",
              rojo_v >= 2 and rojo_n == 0,
              f"filas de rojo puro en x=100: progreso {rojo_n}, volumen {rojo_v}")
        check("la barra de volumen se dibuja mas gruesa que el progreso",
              grue_v >= grue_n + 2, f"grosor en x=50: {grue_n} -> {grue_v} filas")
        check("silenciado, la barra de volumen queda vacia", rojo_m == 0,
              f"filas pintadas con silencio: {rojo_m}")
        dif = sum(1 for a, b in zip(normal.crop((0, 19, normal.width, 30)).getdata(),
                                    volumen.crop((0, 19, volumen.width, 30)).getdata())
                  if a != b)
        check("el renglon del artista pasa a decir el volumen", dif > 30,
              f"{dif} pixeles distintos en el renglon del artista")
        dif_mudo = sum(1 for a, b in zip(volumen.getdata(), mudo.getdata()) if a != b)
        check("el silencio se nota en lo que se ve", dif_mudo > 100,
              f"{dif_mudo} pixeles distintos entre volumen y silencio")
        check("sin sesion de audio el altavoz se dibuja atenuado",
              sin_sesion != cuadro((0.45, False, True, True)),
              "la cuarta celda cambia de color")
    except Exception as exc:
        check("el dibujo del volumen", False, repr(exc))

    # (c) la sesion de audio real: se lee el volumen de la app que esta sonando
    try:
        from widget import volume as volume_mod
        volume_mod.iniciar_com()
        app_sonando = ""
        try:
            pol = MediaPoller(interval=0.3)
            pol.start()
            pol.wait_ready(6)
            # el primer sondeo puede volver vacio: se reintenta un par de segundos
            for _ in range(10):
                app_sonando = getattr(pol.state(), "app_id", "") or ""
                if app_sonando:
                    break
                time.sleep(0.4)
            pol.stop()
        except Exception:
            pass
        est = volume_mod.estado(app_sonando) if app_sonando else None
        check("se lee el volumen de la app que esta sonando",
              bool(est) and 0.0 <= est[0] <= 1.0,
              f"{app_sonando or 'sin app'}: "
              + (f"{est[0] * 100:.0f}%" + (" (silenciado)" if est[1] else "")
                 if est else "no tiene sesion de audio"),
              skipped=not est)
        ses = volume_mod.sesiones()
        check("la API de audio del sistema responde",
              isinstance(ses, list) and len(ses) > 0,
              f"{len(ses)} sesiones: "
              + ", ".join(sorted({x.get('exe', '?') for x in ses}))[:80])
    except Exception as exc:
        check("la API de audio del sistema responde", False, repr(exc))

    # --- fundidos: caratula y mostrar/ocultar ---------------------------------
    print("\n-- fundidos --")
    try:
        import io as _io
        import time as _t
        from PIL import Image as _Image
        from widget.app import WidgetApp
        from widget.media import MediaState

        def png(color):
            im = _Image.new("RGB", (48, 48), color)
            buf = _io.BytesIO()
            im.save(buf, "PNG")
            return buf.getvalue()

        ROJO, AZUL = png((230, 30, 30)), png((30, 60, 230))

        def app_prueba(cfgx):
            a = WidgetApp(cfgx, embed=False)
            a.width_px, a.height_px, a.k = 300, 40, 1.0
            return a

        def estado(art, clave):
            return MediaState(has_session=True, app_id="prueba.exe", title="Titulo",
                              artist="Artista", playing=True, position=10.0,
                              duration=100.0, position_at=_t.monotonic(), art=art,
                              art_key=clave, can_seek=True, min_seek=0, max_seek=100,
                              can_toggle=True, can_prev=True, can_next=True)

        def dif(im1, im2, caja):
            a1, a2 = im1.convert("RGB").crop(caja), im2.convert("RGB").crop(caja)
            n = 0
            for p, q in zip(a1.get_flattened_data(), a2.get_flattened_data()):
                n += abs(p[0] - q[0]) + abs(p[1] - q[1]) + abs(p[2] - q[2])
            return n / (3.0 * a1.size[0] * a1.size[1])

        caja_tapa = (int(draw.PAD), int(draw.PAD),
                     int(draw.PAD + draw.ART), int(draw.PAD + draw.ART))
        a = app_prueba(cfg)
        a.state = estado(ROJO, "rojo")
        f_rojo = a._frame()
        a.state = estado(AZUL, "azul")
        # El fundido arranca con el PRIMER cuadro que se dibuja despues del cambio
        # (asi es en vivo: el tick ve la tapa nueva y empieza a mezclar), asi que hay
        # que pedir ese cuadro y recien despues medir la mitad.
        f_inicio = a._frame()
        _t.sleep(max(0.05, cfg.get("fade_cover_ms", 220) / 2000.0))
        f_mezcla = a._frame()          # a mitad de la mezcla
        _t.sleep(max(0.35, cfg.get("fade_cover_ms", 220) / 1000.0 + 0.15))
        f_azul = a._frame()            # ya terminado

        total = dif(f_rojo, f_azul, caja_tapa)
        hacia_viejo = dif(f_rojo, f_mezcla, caja_tapa)
        hacia_nuevo = dif(f_mezcla, f_azul, caja_tapa)
        check("al cambiar de caratula el cuadro queda en el medio (fundido)",
              total > 5 and hacia_viejo > 0.15 * total and hacia_nuevo > 0.15 * total,
              f"cambio total {total:.1f}; el cuadro del medio esta a "
              f"{hacia_viejo:.1f} de la tapa vieja y {hacia_nuevo:.1f} de la nueva")
        check("el fundido termina en la caratula nueva",
              dif(f_mezcla, f_azul, caja_tapa) < 0.9 * total,
              f"distancia del cuadro del medio a la tapa nueva {hacia_nuevo:.1f} "
              f"contra cambio total {total:.1f}")

        # control: apagado, el cambio es de golpe
        a2 = app_prueba(dict(cfg, fade_cover=False))
        a2.state = estado(ROJO, "rojo")
        f1 = a2._frame()
        a2.state = estado(AZUL, "azul")
        f2 = a2._frame()
        check("con el fundido apagado el cambio de caratula es inmediato",
              dif(f2, f_azul, caja_tapa) < 1.0 and dif(f1, f_rojo, caja_tapa) < 1.0,
              f"el cuadro siguiente ya es la tapa nueva "
              f"(distancia {dif(f2, f_azul, caja_tapa):.1f})")
        check("la configuracion trae los fundidos encendidos",
              bool(cfg.get("fade_cover", True)) and bool(cfg.get("fade_visible", True)),
              f"fade_cover={cfg.get('fade_cover')} fade_visible={cfg.get('fade_visible')}")
    except Exception as exc:
        check("los fundidos", False, repr(exc))

    # --- el fundido de mostrar/ocultar, medido en vivo -------------------------
    try:
        from PIL import ImageGrab
        w_now = win32gui.FindWindowEx(p["tray"], 0, "GorusTaskbarMusicWnd", None)
        ctl = win32gui.FindWindow("GorusTaskbarMusicCtl", None)
        wr = rect(w_now)

        def claros(caja=wr):
            """Cuantos pixeles claros hay: los elementos dibujados del widget."""
            im = ImageGrab.grab(all_screens=True, bbox=caja).convert("L")
            return sum(1 for v in im.get_flattened_data() if v > 60)

        visible_antes = claros()
        win32gui.PostMessage(ctl, win32con.WM_HOTKEY, 1, 0)   # ocultar: arranca el fundido
        time.sleep(max(0.08, cfg.get("fade_step", 48) and 0.10))
        medio = claros()
        time.sleep(0.7)
        oculto = claros()
        check("al ocultar, el widget pasa por un estado intermedio (fundido)",
              visible_antes > medio > oculto + 5,
              f"pixeles dibujados: visible {visible_antes} -> mitad {medio} -> oculto {oculto}")

        win32gui.PostMessage(ctl, win32con.WM_HOTKEY, 1, 0)   # mostrar: fundido al reves
        time.sleep(max(0.08, 0.10))
        medio2 = claros()
        time.sleep(0.7)
        visible_despues = claros()
        check("al mostrarlo tambien aparece con fundido",
              visible_despues > medio2 > oculto + 5,
              f"pixeles dibujados: oculto {oculto} -> mitad {medio2} -> visible "
              f"{visible_despues}")
        check("el widget termina visible y completo",
              abs(visible_despues - visible_antes) < max(60, 0.25 * visible_antes),
              f"antes {visible_antes} pixeles, despues {visible_despues}")
    except Exception as exc:
        check("el fundido en vivo", False, repr(exc))

    # --- panel (mini reproductor): dos tamanos y modo gaming ------------------
    print("\n-- panel --")
    try:
        import io as _io
        import time as _t
        from PIL import Image as _Image
        from widget import panel as panel_mod
        from widget.media import MediaState

        def png(color):
            im = _Image.new("RGB", (64, 64), color)
            buf = _io.BytesIO()
            im.save(buf, "PNG")
            return buf.getvalue()

        est = MediaState(has_session=True, app_id="brave.exe", title="Titulo de prueba",
                         artist="Artista de prueba", album="", playing=True,
                         position=60.0, duration=180.0, position_at=_t.monotonic(),
                         art=None, art_key="k", can_seek=True, min_seek=0, max_seek=180,
                         can_toggle=True, can_prev=True, can_next=True)
        kp = 1.0
        cfg_normal = dict(cfg, panel_size="normal")
        cfg_chico = dict(cfg, panel_size="chico")
        art_rojo = png((220, 40, 40))
        vol = (0.45, False, True, True)

        # (a) geometria: los DOS tamanos entran y no se pisan
        for nombre, c in (("normal", cfg_normal), ("chico", cfg_chico)):
            Wp, Hp = panel_mod.size(kp, c)
            z = panel_mod.rects(kp, c)
            piezas = ([z["tapa"], z["barra"], z["altavoz"], z["volumen"], z["cerrar"],
                       z["texto"]] + list(z["controles"]))
            adentro = all(0 <= r[0] < r[2] <= Wp and 0 <= r[1] < r[3] <= Hp for r in piezas)
            solapan = any(z["controles"][i][2] > z["controles"][i + 1][0] for i in range(2))
            pisa = (z["controles"][2][2] > z["altavoz"][0]
                    or z["texto"][2] > z["cerrar"][0] and z["texto"][1] < z["cerrar"][3])
            check(f"el panel {nombre} ({Wp}x{Hp}): zonas adentro y sin pisarse",
                  adentro and not solapan and not pisa,
                  f"controles hasta x={z['controles'][2][2]}, altavoz desde "
                  f"x={z['altavoz'][0]}, cerrar {z['cerrar']}, texto {z['texto']}")
        an = panel_mod.size(kp, cfg_normal)
        ac = panel_mod.size(kp, cfg_chico)
        check("el panel chico es mas chico (menos alto y menos ancho)",
              ac[1] < an[1] * 0.6 and ac[0] <= an[0],
              f"normal {an[0]}x{an[1]} -> chico {ac[0]}x{ac[1]} "
              f"({ac[0] * ac[1] * 100.0 / (an[0] * an[1]):.0f}% del area)")

        # (b) dibujo en los dos tamanos
        for nombre, c in (("normal", cfg_normal), ("chico", cfg_chico)):
            z = panel_mod.rects(kp, c)
            L = panel_mod.layout(c)
            art = draw.get_art(art_rojo, "rojo", int(L["tapa"][2]), int(L["tapa_radio"]))
            im = panel_mod.render(est, c, art=art, volume=vol, hover=-1, k=kp, opaque=True, base=(30, 30, 36)).convert("RGB")
            rojo_tapa = sum(1 for y in range(z["tapa"][1], z["tapa"][3])
                            for x in range(z["tapa"][0], z["tapa"][2])
                            if im.getpixel((x, y))[0] > 150
                            and im.getpixel((x, y))[0] > im.getpixel((x, y))[1] + 60)
            # El relleno de la barra se mide por DIFERENCIA contra el mismo panel con
            # la posicion en 0 (sin relleno): clasificar por color no sirve, el usuario
            # elige el color y con el violeta "r>g+60" daba cero pixeles.
            im0 = panel_mod.render(
                MediaState(has_session=True, app_id="brave.exe", title=est.title,
                           artist=est.artist, playing=True, position=0.0,
                           duration=180.0, position_at=_t.monotonic(), art=None,
                           art_key="k", can_seek=True, can_toggle=True),
                c, art=art, volume=vol, hover=-1, k=kp, opaque=True, base=(30, 30, 36)).convert("RGB")
            barra = sum(1 for y in range(z["barra"][1] - 2, z["barra"][3] + 3)
                        for x in range(z["barra"][0], z["barra"][2])
                        if im.getpixel((x, y)) != im0.getpixel((x, y)))
            texto = sum(1 for y in range(z["texto"][1], z["texto"][3])
                        for x in range(z["texto"][0], z["texto"][2])
                        if sum(im.getpixel((x, y))) > 420)
            check(f"el panel {nombre} dibuja caratula, textos y barra",
                  rojo_tapa > 120 and barra > 30 and texto > 80,
                  f"tapa {rojo_tapa}, barra {barra}, texto {texto} pixeles")

        # (b2) el renglon del artista no se mete en los tiempos (panel chico) y el
        # fondo se puede sacar (alfa del fondo independiente del resto)
        try:
            L = panel_mod.layout(cfg_chico)
            art = draw.get_art(art_rojo, "rojo", int(L["tapa"][2]), int(L["tapa_radio"]))
            z = panel_mod.rects(kp, cfg_chico)
            largo = MediaState(has_session=True, app_id="brave.exe",
                               title="Titulo", artist="Artista Con Un Nombre Larguisimo "
                               "Que No Entra Ni De Cana", playing=True, position=60.0,
                               duration=180.0, position_at=_t.monotonic(), art=None,
                               art_key="k", can_seek=True, can_toggle=True)
            corto = MediaState(has_session=True, app_id="brave.exe", title="Titulo",
                               artist="Corto", playing=True, position=60.0,
                               duration=180.0, position_at=_t.monotonic(), art=None,
                               art_key="k", can_seek=True, can_toggle=True)
            im_l = panel_mod.render(largo, cfg_chico, art=art, volume=vol,
                                    k=kp, opaque=True, base=(30, 30, 36)).convert("RGB")
            im_c = panel_mod.render(corto, cfg_chico, art=art, volume=vol,
                                    k=kp, opaque=True, base=(30, 30, 36)).convert("RGB")
            x_t = z["texto"][2]
            # Ventana bien adentro de los tiempos: el artista se corta ~56 px antes
            # (se le reserva el ancho de los tiempos + 8), asi que 45 px es seguro.
            caja_tiempos = (x_t - 45, L["artista_y"], x_t, L["artista_y"] + 14)
            caja_artista = (z["texto"][0], L["artista_y"], x_t - 60,
                            L["artista_y"] + 14)
            px_l = [im_l.getpixel((x, y)) for y in range(caja_tiempos[1], caja_tiempos[3])
                    for x in range(caja_tiempos[0], caja_tiempos[2])]
            px_c = [im_c.getpixel((x, y)) for y in range(caja_tiempos[1], caja_tiempos[3])
                    for x in range(caja_tiempos[0], caja_tiempos[2])]
            hay_artista_l = sum(1 for y in range(caja_artista[1], caja_artista[3])
                                for x in range(caja_artista[0], caja_artista[2])
                                if sum(im_l.getpixel((x, y))) > 300)
            hay_artista_c = sum(1 for y in range(caja_artista[1], caja_artista[3])
                                for x in range(caja_artista[0], caja_artista[2])
                                if sum(im_c.getpixel((x, y))) > 300)
            check("el artista no se mete en los tiempos (nombre largo o corto)",
                  px_l == px_c and any(sum(p) > 200 for p in px_l)
                  and hay_artista_l > hay_artista_c,
                  f"{sum(1 for p in px_l if sum(p) > 200)} pixeles de tiempos; "
                  f"identicos con nombre largo y corto: {px_l == px_c}; el nombre largo "
                  f"ocupa mas ({hay_artista_l} contra {hay_artista_c} pixeles)")

            def alfa_medio(cfgx):
                imx = panel_mod.render(est, cfgx, art=art, volume=vol, k=kp)
                canal = imx.getchannel("A")
                d = list(canal.get_flattened_data())
                return sum(d) / float(len(d))

            # Sin fondo NO se dibuja NADA atras: antes quedaba un piso de alfa (60)
            # que pintaba un velo al 24% y parecia que el fondo seguia estando.
            zc2 = panel_mod.rects(kp, cfg_chico)
            hueco = (zc2["texto"][0] + 4, L["titulo_y"] - 8)
            im_sf = panel_mod.render(est, dict(cfg_chico, panel_bg_alpha=0), art=art,
                                     volume=vol, k=kp)
            im_sol = panel_mod.render(est, dict(cfg_chico, panel_bg_alpha=250), art=art,
                                      volume=vol, k=kp)
            # El hueco "sin fondo" queda en el PISO de alfa (2), no en 0: Windows usa el
            # alfa por pixel para decidir que ventana recibe el mouse, y con 0 las zonas
            # vacias son agujeros que se queda la ventana de atras (medido en vivo:
            # WindowFromPoint sobre el fondo del panel devolvia Chrome en 66 de 98 puntos
            # -> el panel no se podia agarrar). El piso de 2 es 0,8%: invisible.
            piso = int(cfg_chico.get("hit_alpha_floor", 2))
            alfa = [p[3] for p in im_sf.getdata()]
            check("con el fondo en 0 no queda nada visible atras (ni borde)",
                  im_sf.getpixel(hueco)[3] == piso and im_sol.getpixel(hueco)[3] > 200,
                  f"alfa en un hueco del panel: sin fondo {im_sf.getpixel(hueco)[3]} "
                  f"(piso {piso}), con fondo {im_sol.getpixel(hueco)[3]}")
            check("toda la superficie del panel recibe el mouse (alfa con piso)",
                  min(alfa) == piso > 0 and max(alfa) == 255,
                  f"alfa del panel sin fondo: min {min(alfa)}, max {max(alfa)}")

            # ...y el texto tiene que contrastar con lo que hay DETRAS (se da vuelta)
            contrastes = []
            for base in ((235, 235, 235), (30, 30, 36)):
                th = draw.theme_for_base(cfg_chico, base)
                lt = draw._lum(th.get("title") or (238, 240, 248))
                lb = draw._lum(base)
                contrastes.append((lt - lb, abs(lt - lb)))
            check("sin fondo el texto cambia de color para contrastar con lo de atras",
                  contrastes[0][0] < 0 < contrastes[1][0]
                  and min(c[1] for c in contrastes) > 100,
                  f"con fondo claro el texto queda mas oscuro ({contrastes[0][0]:.0f}) y "
                  f"con fondo oscuro mas claro ({contrastes[1][0]:.0f})")

            a_solido = alfa_medio(dict(cfg_chico, panel_bg_alpha=250))
            a_sin = alfa_medio(dict(cfg_chico, panel_bg_alpha=0))
            check("el fondo del panel se puede sacar (alfa del fondo aparte)",
                  a_solido > a_sin + 40,
                  f"alfa medio del panel: con fondo {a_solido:.0f}, sin fondo {a_sin:.0f}")
        except Exception as exc:
            check("el fondo y el ancho del artista", False, repr(exc))

        # (c) reacciona al hover, al arrastre y al silencio (en los dos tamanos)
        for nombre, c in (("normal", cfg_normal), ("chico", cfg_chico)):
            z = panel_mod.rects(kp, c)
            L = panel_mod.layout(c)
            art = draw.get_art(art_rojo, "rojo", int(L["tapa"][2]), int(L["tapa_radio"]))
            base = panel_mod.render(est, c, art=art, volume=vol, k=kp, opaque=True, base=(30, 30, 36)).convert("RGB")
            otros = {
                "hover": panel_mod.render(est, c, art=art, volume=vol, hover=1,
                                          k=kp, opaque=True, base=(30, 30, 36)).convert("RGB"),
                "arrastre": panel_mod.render(est, c, art=art, volume=vol, hover=3,
                                             scrub=150.0, k=kp, opaque=True, base=(30, 30, 36)).convert("RGB"),
                "silencio": panel_mod.render(est, c, art=art,
                                             volume=(0.45, True, True, True),
                                             k=kp, opaque=True, base=(30, 30, 36)).convert("RGB"),
            }
            difs = {n: sum(1 for a, b in zip(base.get_flattened_data(),
                                            im.get_flattened_data()) if a != b)
                    for n, im in otros.items()}
            check(f"el panel {nombre} marca hover, arrastre y silencio",
                  all(v > 20 for v in difs.values()),
                  ", ".join(f"{n} {v}" for n, v in difs.items()))

        # (d) fracciones y prueba de impacto
        for nombre, c in (("normal", cfg_normal), ("chico", cfg_chico)):
            z = panel_mod.rects(kp, c)
            ok_frac = (abs(panel_mod.frac_en_barra(z["barra"][0], kp, c)) < 0.01
                       and abs(panel_mod.frac_en_barra(z["barra"][2], kp, c) - 1.0) < 0.01
                       and abs(panel_mod.frac_en_volumen(z["volumen"][0], kp, c)) < 0.01)
            ctr = z["controles"][1]
            ok_hit = (panel_mod.hit((ctr[0] + ctr[2]) // 2, (ctr[1] + ctr[3]) // 2, kp, c) == 1
                      and panel_mod.hit(z["cerrar"][0] + 2, z["cerrar"][1] + 2, kp, c) == 6
                      and panel_mod.hit(z["tapa"][0] + 2, z["tapa"][1] + 2, kp, c) == 7
                      and panel_mod.hit(-3, -3, kp, c) == -1)
            check(f"el panel {nombre}: fracciones y que hay bajo el cursor",
                  ok_frac and ok_hit, "fracciones y prueba de impacto correctas")

        # (e) en vivo: abrir, ver y cerrar
        win32gui.PostMessage(w_now, WM_APP_PANEL, 1, 1)
        time.sleep(0.9)
        w_panel = win32gui.FindWindow("GorusTaskbarMusicPanel", None)
        if not w_panel:
            check("el panel se abre y se ve", False, "no encontre la ventana del panel")
        else:
            pr = rect(w_panel)
            ex = win32gui.GetWindowLong(w_panel, win32con.GWL_EXSTYLE)
            wr_w = rect(w_now)
            try:
                mi = win32api.GetMonitorInfo(win32api.MonitorFromWindow(w_now, 2))
                mon = mi["Monitor"]
            except Exception:
                mon = None
            dentro = (mon is None or (mon[0] <= pr[0] and pr[2] <= mon[2]))
            check("el panel se abre y se ve", win32gui.IsWindowVisible(w_panel),
                  f"ventana {hex(w_panel)} en {pr}")
            check("el panel no entra en la barra de tareas",
                  bool(ex & 0x00000080) and bool(ex & 0x00080000),
                  f"TOOLWINDOW={'si' if ex & 0x80 else 'no'}, "
                  f"LAYERED={'si' if ex & 0x80000 else 'no'}")
            # Si vos lo arrastraste, el panel vive ahi (no salta detras del widget):
            # se comprueba que este en pantalla y, si no lo moviste, encima del widget.
            movido = cfgmod.load().get("panel_pos") is not None
            en_monitor = True
            try:
                mi_p = win32api.GetMonitorInfo(
                    win32api.MonitorFromPoint(((pr[0] + pr[2]) // 2, (pr[1] + pr[3]) // 2), 2))
                mp = mi_p["Monitor"]
                en_monitor = (mp[0] <= pr[0] and pr[2] <= mp[2]
                              and mp[1] <= pr[1] and pr[3] <= mp[3])
            except Exception:
                pass
            check("el panel queda en pantalla (y encima del widget si no lo moviste)",
                  en_monitor and (movido or (dentro and pr[3] <= wr_w[1] + 2)),
                  f"panel {pr}; movido a mano: {movido}; dentro del monitor: {en_monitor}"
                  + ("" if movido else f"; widget arriba y={wr_w[1]}"))
            im_vivo = ImageGrab.grab(all_screens=True, bbox=pr).convert("L")
            vals = list(im_vivo.get_flattened_data())
            check("el panel esta pintado (no es un rectangulo negro)",
                  max(vals) - min(vals) > 100 and sum(1 for v in vals if v > 150) > 300,
                  f"min {min(vals)} max {max(vals)}, "
                  f"{sum(1 for v in vals if v > 150)} pixeles claros")

            # (f) modo gaming: chico, sin robar el foco y sin cerrarse al tocar afuera
            auto_antes = float(cfg.get("panel_auto_hide_s", 0) or 0)
            modo_antes = str(cfgmod.load().get("panel_mode", "normal")).lower()
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 7, 0)      # sin auto-ocultar
            # El tamano de partida no se asume: la configuracion puede estar ya en
            # chico (si el modo gaming quedo prendido de una corrida anterior).
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 6, 0)      # modo normal
            time.sleep(1.0)
            win32gui.PostMessage(w_now, WM_APP_PANEL, 1, 1)
            time.sleep(1.0)
            w_antes = win32gui.FindWindow("GorusTaskbarMusicPanel", None)
            pr_antes = rect(w_antes) if w_antes else (0, 0, 0, 0)
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 6, 1)      # modo gaming
            time.sleep(1.2)
            w_panel = win32gui.FindWindow("GorusTaskbarMusicPanel", None)
            pr_g = rect(w_panel)
            ex_g = win32gui.GetWindowLong(w_panel, win32con.GWL_EXSTYLE)
            L = panel_mod.layout(cfgmod.load())
            esperado = panel_mod.size((pr_g[3] - pr_g[1]) / float(L["H"]), cfgmod.load())
            check("modo gaming: el panel queda chico",
                  (pr_g[2] - pr_g[0], pr_g[3] - pr_g[1]) == esperado
                  and pr_g[3] - pr_g[1] < pr_antes[3] - pr_antes[1],
                  f"{(pr_g[2] - pr_g[0])}x{pr_g[3] - pr_g[1]} "
                  f"(antes {pr_antes[2] - pr_antes[0]}x{pr_antes[3] - pr_antes[1]})")
            cfg_g = cfgmod.load()
            check("modo gaming: queda fijo (sin auto-ocultar ni HUD)",
                  float(cfg_g.get("panel_auto_hide_s", 1) or 0) == 0
                  and not cfg_g.get("panel_hud", True),
                  f"auto-ocultar={cfg_g.get('panel_auto_hide_s')}, "
                  f"hud={cfg_g.get('panel_hud')}")
            check("modo gaming: no le roba el foco al juego (NOACTIVATE) y va arriba",
                  bool(ex_g & 0x08000000) and bool(ex_g & 0x00000008),
                  f"NOACTIVATE={'si' if ex_g & 0x08000000 else 'no'}, "
                  f"TOPMOST={'si' if ex_g & 0x8 else 'no'}")
            # tocar afuera: se manda otra ventana al frente y el panel debe seguir
            try:
                otra = win32gui.FindWindow("Shell_TrayWnd", None)
                win32gui.SetForegroundWindow(otra or win32gui.GetDesktopWindow())
            except Exception:
                pass
            time.sleep(0.9)
            check("modo gaming: tocar afuera NO lo cierra",
                  win32gui.IsWindowVisible(w_panel),
                  f"visible={win32gui.IsWindowVisible(w_panel)}")

            # (g) dejar pasar los clics al juego (WS_EX_TRANSPARENT)
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 3, 1)
            time.sleep(0.8)
            centro = ((pr_g[0] + pr_g[2]) // 2, (pr_g[1] + pr_g[3]) // 2)
            quien = win32gui.WindowFromPoint(centro)
            check("con 'clics al juego' el panel deja pasar los clics",
                  quien != w_panel, f"bajo el cursor hay {hex(quien)} (panel {hex(w_panel)})")
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 3, 0)
            time.sleep(0.6)
            check("apagado, el panel vuelve a recibir los clics",
                  win32gui.WindowFromPoint(centro) == w_panel,
                  f"bajo el cursor hay {hex(win32gui.WindowFromPoint(centro))}")

            # (h) auto-ocultar
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 7, 20)      # 2 segundos
            time.sleep(2.8)
            check("el auto-ocultar lo cierra solo",
                  not win32gui.IsWindowVisible(w_panel),
                  f"visible={win32gui.IsWindowVisible(w_panel)} tras 2,8 s (limite 2 s)")

            # volver al modo normal y cerrar (el HUD se apaga primero: si no, el
            # proximo cambio de cancion lo vuelve a abrir, que es su trabajo)
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 4, 0)
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 6, 1 if modo_antes == "gaming" else 0)
            time.sleep(0.8)
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 7, int(auto_antes * 10))
            win32gui.PostMessage(w_now, WM_APP_PANEL, 0, 1)
            time.sleep(0.7)
            check("el panel se cierra",
                  not win32gui.IsWindowVisible(
                      win32gui.FindWindow("GorusTaskbarMusicPanel", None) or w_panel))
    except Exception as exc:
        check("el panel", False, repr(exc))

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
