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

import ctypes  # noqa: E402

import win32con  # noqa: E402
import win32api  # noqa: E402
import win32gui  # noqa: E402
import win32process  # noqa: E402

from widget import config as cfgmod  # noqa: E402
from widget import sistema  # noqa: E402
from widget.taskbarwin import TaskbarHost, list_bars, monitores  # noqa: E402
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


FLOTANTE = False   # se resuelve en main(): en Windows 11 el widget es ventana propia


def widget_ventana() -> int:
    """El hwnd del widget donde este viviendo: incrustado en la barra o ventana propia.

    En Windows 10 vive adentro de la barra de tareas; en Windows 11 (barra dibujada por
    XAML) el widget pasa al modo flotante, que es una ventana de nivel superior. La
    suite tiene que encontrarlo igual, porque es la mitad de las comprobaciones. Las que
    dependen de estar incrustado quedan marcadas como SALTA con el motivo.
    """
    barra, w = barra_del_widget()
    return w or win32gui.FindWindow("AstraMusicWnd", None)


def barra_del_widget():
    """(datos de la barra, hwnd del widget) donde sea que este viviendo.

    No se asume la barra principal: el widget puede estar en la de otro monitor.
    """
    barras = list_bars()
    for b in barras:
        w = win32gui.FindWindowEx(b["tray"], 0, "AstraMusicWnd", None)
        if w:
            return b, w
    return (barras[0] if barras else None), 0


def monitor_de_ventana(hwnd) -> dict | None:
    """Monitor donde esta esa ventana, por el centro de su rectangulo."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return None
    try:
        r = win32gui.GetWindowRect(hwnd)
    except Exception:
        return None
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    for m in monitores():
        if m["rect"][0] <= cx < m["rect"][2] and m["rect"][1] <= cy < m["rect"][3]:
            return m
    return None


def probar_otro_monitor_flotante(check) -> None:
    """Modo flotante: elegir monitor tiene que mover la ventana a ESE monitor.

    En Windows 11 no hay una barra por monitor donde alojarse: el menu elige el monitor
    sobre cuya franja de abajo apoya la ventana. Es lo que no pasaba en la 1.0.9 (el host
    flotante resolvia siempre el principal, asi que la opcion no movia nada y la ventana
    seguia en su lugar). La comprobacion es geometrica: donde quedo la ventana, no lo que
    dice la configuracion.
    """
    mons = monitores()
    w = widget_ventana()
    actual = monitor_de_ventana(w)
    if len(mons) < 2 or not w or actual is None:
        check("el equipo tiene mas de un monitor", False,
              f"{len(mons)} monitor(es): no hay otro donde probar", skipped=True)
        return
    idx_actual = next(i for i, m in enumerate(mons) if m["rect"] == actual["rect"])
    idx_destino = next(i for i, m in enumerate(mons) if m["rect"] != actual["rect"])
    destino = mons[idx_destino]
    win32gui.SendMessage(w, WM_APP_MONITOR, idx_destino, 0)     # lParam 0 = no guardar
    time.sleep(1.7)
    w2 = widget_ventana()
    r2 = win32gui.GetWindowRect(w2) if w2 else (0, 0, 0, 0)
    en2 = monitor_de_ventana(w2)
    check("el widget se muda al monitor elegido",
          bool(en2) and en2["rect"] == destino["rect"],
          f"ventana {r2} en {en2['nombre'] if en2 else '?'} "
          f"(se pidio {destino['nombre']})")
    check("apoya en la franja de abajo de ese monitor",
          bool(en2) and r2[3] == en2["rect"][3],
          f"ventana {r2} monitor {en2['rect'] if en2 else '-'}")
    check("queda adentro de ese monitor",
          bool(en2) and r2[0] >= en2["rect"][0] and r2[2] <= en2["rect"][2],
          f"widget {r2} dentro de {en2['rect'] if en2 else '-'}")
    check("el widget esta visible en el otro monitor",
          bool(w2) and bool(win32gui.IsWindowVisible(w2)))
    check("no se mete en el bloque de la derecha del monitor",
          bool(en2) and r2[2] <= en2["rect"][2] - 8, r2)
    if not w2:
        return
    win32gui.SendMessage(w2, WM_APP_MONITOR, idx_actual, 0)
    time.sleep(1.7)
    w3 = widget_ventana()
    en3 = monitor_de_ventana(w3)
    check("la vuelta deja el widget en su monitor",
          bool(en3) and en3["rect"] == actual["rect"],
          f"quedo en {en3['nombre'] if en3 else '?'}")


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
            "widget": widget_ventana(), "barra": host.barra}


def rect(h) -> tuple:
    return win32gui.GetWindowRect(h)


def franja(x0: int, x1: int, y: int) -> list:
    from PIL import ImageGrab
    return list(ImageGrab.grab(all_screens=True, bbox=(x0, y, x1, y + 1)).convert("RGB").getdata())


def difusa(a: list, b: list) -> tuple:
    d = [max(abs(a[i][c] - b[i][c]) for c in range(3)) for i in range(min(len(a), len(b)))]
    return sum(d) / max(1, len(d)), max(d)


def barra_dibujada(cfg: dict, k: float) -> tuple | None:
    """Donde se DIBUJA la barra de progreso, en px del cuadro (x0, x1).

    Se mide el dibujo en vez de repetir la formula: el error que tenia Windows 11
    (k=1.2) no estaba en `progress_rect` sino en quien lo llamaba con el ancho real,
    asi que comparar la formula contra si misma no probaba nada. Con el progreso al
    100% y un verde puro, los pixeles de la barra se encuentran solos.
    """
    from widget.media import MediaState as _MS
    cfg2 = dict(cfg, progress_color="#00FF00", show_waves=False, chip_alpha=230)
    est = _MS(has_session=True, app_id="test.exe", title="Titulo", artist="Artista",
              playing=True, position=60.0, duration=60.0, position_at=time.monotonic(),
              art=None, art_key="k", can_seek=True, can_toggle=True)
    img = draw.render(est, cfg2, art=None, k=k, base=(29, 35, 32),
                      height=int(round(40 * k)), opaque=False, waves=None)
    xs = [x for x in range(img.size[0])
          if any(img.getpixel((x, y))[:3] == (0, 255, 0) for y in range(img.size[1]))]
    return (min(xs), max(xs)) if xs else None


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
        with open(os.path.join(os.path.dirname(HERE), "astra-widget.log"), encoding="utf-8") as fh:
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


def cfg_del_widget_en_ejecucion(cfg: dict) -> dict:
    """Los ajustes que esta usando el widget que corre, aunque no sean los del proyecto.

    Si lo que esta andando es el .exe portatil o el instalado, su `config.json` vive **al
    lado de ese .exe**: leer el del proyecto da otros ajustes (medido: ancho 260 contra 320)
    y media suite se pone en rojo por una diferencia que no es del programa. Se busca la
    carpeta del proceso dueno de la ventana y, si tiene `config.json`, se usa ese.
    """
    try:
        h = widget_ventana()
        if not h:
            return cfg
        _hilo, pid = win32process.GetWindowThreadProcessId(h)
        k32 = ctypes.windll.kernel32
        ph = k32.OpenProcess(0x1000, False, pid)      # PROCESS_QUERY_LIMITED_INFORMATION
        if not ph:
            return cfg
        try:
            buf = ctypes.create_unicode_buffer(1024)
            tam = ctypes.c_uint(1024)
            # OJO: QueryFullProcessImageNameW vive en KERNEL32, no en user32.
            if not k32.QueryFullProcessImageNameW(ph, 0, buf, ctypes.byref(tam)):
                return cfg
        finally:
            k32.CloseHandle(ph)
        carpeta = os.path.dirname(buf.value)
        ruta = os.path.join(carpeta, "config.json")
        if not os.path.exists(ruta):
            return cfg
        if os.path.abspath(carpeta) == os.path.dirname(HERE):
            return cfg
        print(f"      (ajustes: los del widget que corre, en {carpeta})")
        # OJO: no alcanza con devolver este dict. El bloque del panel vuelve a llamar a
        # cfgmod.load(), y con el CONFIG_PATH del proyecto leia otros ajustes y despues los
        # "restauraba" en el archivo del usuario (le dejaba el panel en modo gaming).
        cfgmod.CONFIG_PATH = ruta
        return cfgmod.load(ruta)
    except Exception:
        return cfg


def main() -> int:
    global FLOTANTE
    cfg = cfgmod.load()
    cfg = cfg_del_widget_en_ejecucion(cfg)
    p = tray_parts()
    if not check("la barra de tareas existe", bool(p["tray"])):
        return 1
    # El widget vive incrustado en la barra (Windows 10) o como ventana propia (el modo
    # flotante, que es el unico que se ve en Windows 11). Si la barra lo admite y igual
    # quedo suelto, es un fallo del detector y se informa como tal; si la barra no lo
    # admite, la suite sigue en modo flotante y saltea solo las pruebas de anclaje.
    if not p["widget"]:
        check("el widget esta corriendo", False, "arrancalo antes de correr esto")
        return 1
    incrustado = win32gui.GetParent(p["widget"]) == p["tray"]
    from widget.taskbarwin import motivo_no_incrustable
    admite = motivo_no_incrustable() is None
    if incrustado:
        check("el widget esta incrustado en la barra", True)
    elif admite:
        check("el widget esta incrustado en la barra", False,
              "la barra lo admite y el widget quedo como ventana propia: revisar "
              "motivo_no_incrustable()")
    else:
        FLOTANTE = True
        check("el widget esta donde debe: ventana propia (modo flotante)", True,
              "la barra no admite ventanas ajenas; las pruebas de anclaje se marcan SALTA")
    check("el widget esta visible", bool(win32gui.IsWindowVisible(p["widget"])),
          "se crea oculto y se muestra recien tras el primer render")

    def check_barra(nombre: str, ok: bool, detalle: str = "") -> bool:
        """Comprobacion de las que solo valen con el widget INCRUSTADO en la barra.

        En modo flotante (Windows 11) el widget es una ventana propia: no le pide lugar
        a la lista de tareas, no se apoya en el bloque de la bandeja y puede estar en
        cualquier parte del tramo. Marcarlas SALTA con el motivo es mas honesto que
        informar un fallo que no existe (y que taparia un fallo de verdad).
        """
        if FLOTANTE:
            return check(nombre, True, "no aplica en modo flotante: el widget es ventana "
                                       "propia y no reserva lugar en la barra", skipped=True)
        return check(nombre, ok, detalle)

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
    check_barra("no pisa el bloque de la bandeja (pegado al ancla o frenado por la lista)",
                w_rect[2] <= a_rect[0] + 3,
                f"widget.right={w_rect[2]} vs ancla.left={a_rect[0]}"
                + ("" if pegado else " (frenado por el espacio de la lista de tareas)"))
    check_barra("pegado al ancla cuando la lista no lo impide",
                pegado or frenado,
                "pegado" if pegado else "frenado por la lista, que es lo esperado con "
                "muchas ventanas abiertas")
    check_barra("la lista de tareas cedio el espacio", r_rect[2] <= w_rect[0] + 2,
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
    gone = win32gui.FindWindowEx(p["tray"], 0, "AstraMusicWnd", None)
    reborn = 0
    for _ in range(30):
        time.sleep(0.2)
        reborn = widget_ventana()
        if reborn:
            break
    check("el widget se reconstruye solo", bool(reborn),
          f"hwnd {hex(reborn) if reborn else 'ninguno'} (antes {hex(gone)})")
    if reborn:
        time.sleep(0.6)
        rb = win32gui.GetWindowRect(reborn)
        r2 = win32gui.GetWindowRect(p["rebar"])
        a2 = win32gui.GetWindowRect(p["anchor"])
        check_barra("renace sin pisar el bloque de la bandeja", rb[2] <= a2[0] + 3,
                    f"right={rb[2]} ancla={a2[0]}"
                    + ("" if abs(rb[2] - a2[0]) <= 3 else " (frenado por la lista)"))
        check("renace visible", bool(win32gui.IsWindowVisible(reborn)))
        check_barra("vuelve a reservar su espacio", r2[2] <= rb[0] + 2,
                    f"rebar.right={r2[2]} widget.left={rb[0]}")

    # --- recuperacion: la barra se reacomoda a lo ancho --------------------
    print("\n-- prueba de recuperacion: la barra recupera su ancho natural --")
    reb = p["rebar"]
    rr = win32gui.GetWindowRect(reb)
    an = win32gui.GetWindowRect(p["anchor"])
    if not FLOTANTE:
        win32gui.SetWindowPos(reb, 0, 0, 0, an[0] - rr[0], rr[3] - rr[1],
                              win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
        print(f"  la lista de tareas vuelve a ocupar todo: right={an[0]}")
    ok = False
    for _ in range(25):
        time.sleep(0.2)
        rr2 = win32gui.GetWindowRect(p["rebar"])
        wg = widget_ventana()
        if wg and rr2[2] <= win32gui.GetWindowRect(wg)[0] + 2:
            ok = True
            break
    check_barra("el widget recupera su espacio solo", ok, f"rebar.right={rr2[2]}")

    # --- transparencia real -------------------------------------------------
    print("\n-- fondos: transparencia real medida contra la barra --")
    try:
        w_now = widget_ventana()
        tt = rect(p["tray"])[1]
        wr = posicion(w_now, 0xFFFF, 232)          # extremo derecho, chip solido
        an = rect(p["anchor"])
        # La franja de prueba es la parte pelada de la barra, a la izquierda del bloque
        # de la bandeja y a la derecha del widget. En modo flotante el widget no se apoya
        # en la barra y puede quedar encima o a la derecha de esa franja: cuando no queda
        # franja libre no hay nada que medir (la transparencia del chip se mide, en modo
        # flotante, en tools/flotante_test.py).
        x0 = max(wr[0] + 40, 1250)
        x1 = min(wr[2] - 10, an[0] - 10)
        y = tt + 6                                  # dentro del chip
        if x1 - x0 < 40:
            check("transparencia del fondo medida contra la barra", True,
                  f"no quedo franja pelada donde medir ({x0}..{x1}): el widget en modo "
                  f"flotante no se apoya en la barra", skipped=True)
        else:
            zona = (x0, x1)
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

        w_now = widget_ventana()
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
        check_barra("nunca queda tapado por la lista de tareas",
                    all(f[2][2] <= f[1][0] + 1 for f in filas),
                    f"peor: {max(f[2][2] - f[1][0] for f in filas)} px de invasión")
        check("nadie mas lo tapa en su zona",
              all(f[4] == "AstraMusicWnd" for f in filas),
              str({f[4] for f in filas}))
        check_barra("nunca invade el bloque de la bandeja",
                    all(f[1][2] <= f[3][0] for f in filas),
                    f"peor: {max(f[1][2] - f[3][0] for f in filas)} px")
        check_barra("al extremo derecho queda pegado al ancla",
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
        w_now = widget_ventana()
        wr = rect(w_now)
        ww2, wh2 = wr[2] - wr[0], wr[3] - wr[1]
        # Dos anchos, que no son lo mismo: `ww2` es el real del cuadro (lo que piden
        # control_rects y las capturas) y `wlog` el logico de la config, que es lo que
        # piden progress_rect / progress_frac_at / wave_rect (escalan por k adentro).
        # Medir la barra de progreso con ww2 daba por bueno el error que en Windows 11
        # (k=1.2) corria la zona clicable 68 px a la derecha.
        wlog = int(cfg.get("width", 260))
        pr = draw.progress_rect(wlog, k, cfg)
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
            # Ademas de la formula, se comprueba contra lo que se ve: la zona clicable
            # tiene que empezar y terminar donde empieza y termina la barra dibujada.
            pintada = barra_dibujada(cfg, k)
            check("la zona clicable cae donde se dibuja la barra",
                  bool(pintada) and abs(pr[0] - pintada[0]) <= 2 and abs(pr[2] - pintada[1]) <= 2,
                  f"clicable x={pr[0]}..{pr[2]} / dibujada x={pintada[0]}..{pintada[1]}"
                  if pintada else "no encontre la barra dibujada")
            medio = draw.progress_frac_at((pr[0] + pr[2]) / 2.0, wlog, k, cfg)
            check("la mitad de la barra corresponde a la mitad del tema",
                  abs(medio - 0.5) <= 0.06, f"fraccion {medio:.3f}")
            check("los extremos de la barra dan 0 y 1",
                  draw.progress_frac_at(pr[0], wlog, k, cfg) <= 0.01
                  and draw.progress_frac_at(pr[2], wlog, k, cfg) >= 0.99,
                  f"{draw.progress_frac_at(pr[0], wlog, k, cfg):.2f} / "
                  f"{draw.progress_frac_at(pr[2], wlog, k, cfg):.2f}")

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
        w_now = widget_ventana()
        # Sin fondo es el caso que fallaba: el alpha 0 por pixel hace que Windows
        # le entregue el mouse a la barra de tareas en las zonas vacias.
        posicion(w_now, 0xFFFF, 0)
        wr = rect(w_now)
        ancho = wr[2] - wr[0]
        # Los puntos NO pueden estar escritos en px de un ancho fijo: con un widget de 260
        # (config del usuario) el "hueco del play" a x=263 caia FUERA de la ventana y la
        # prueba culpaba al widget de un hueco que era suyo. Se saca la celda del play de la
        # tabla de layout, que ya escala con el ancho.
        k_w = (wr[3] - wr[1]) / 40.0
        celdas = draw.control_rects(ancho, k_w, cfg) or []
        if len(celdas) > 2:
            c_play = celdas[1]
            hueco = (wr[0] + c_play[0] + 3, wr[1] + (c_play[1] + c_play[3]) // 2)
        else:
            hueco = ((wr[0] + wr[2]) // 2, (wr[1] + wr[3]) // 2)
        puntos = {
            "centro": ((wr[0] + wr[2]) // 2, (wr[1] + wr[3]) // 2),
            "hueco del boton play/pausa": hueco,
            "zona vacia arriba al medio": (wr[0] + ancho // 2 - 10, wr[1] + 8),
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
        w_now = widget_ventana()
        wr = rect(w_now)
        ww2 = wr[2] - wr[0]
        # La franja de las ondas se calcula con el ancho LOGICO (el mismo que usa el
        # widget para pegarla); los botones, con el real (ver _w_log en app.py).
        wlog2 = int(cfg.get("width", 260))
        wb = draw.wave_band(wlog2, cfg)
        ctl = draw.control_rects(ww2, k, cfg)
        check("la franja de las ondas entra entre el texto y los botones",
              bool(wb) and (not ctl or wb[1] < ctl[0][0])
              and wb[0] >= draw.TEXT_X + draw.WAVE_MIN_TEXT,
              f"franja {wb} / los botones empiezan en x={ctl[0][0] if ctl else '-'}")
        wrec = draw.wave_rect(wlog2, k, cfg)

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
        # El fondo "liso" de la franja se toma del color mas repetido DENTRO de la franja,
        # no de un color fijo: con el fondo del widget en el acento de Windows (o en
        # cualquier otro color), el chip no es el (40,34,33) muestreado y contar contra
        # ese valor daba 396 pixeles "fuera del fondo" con las ondas perfectamente
        # apagadas. Lo que se quiere medir es "no hay pixeles de onda", sea cual sea el
        # color del chip.
        datos_franja = [apagado.getpixel((x, y))
                        for x in range(wr_off[0] + 1, wr_off[2] - 1)
                        for y in range(wr_off[1] + 1, wr_off[3] - 1)]
        fondo_franja = max(set(datos_franja), key=datos_franja.count) if datos_franja else (0, 0, 0)
        fuera = sum(1 for p in datos_franja
                    if max(abs(p[i] - fondo_franja[i]) for i in range(3)) > 6)
        check("con las ondas apagadas la franja queda lisa", fuera == 0,
              f"{fuera} pixeles fuera del fondo liso en la franja {wr_off} "
              f"(fondo {fondo_franja[:3]}, medido en el dibujo)")

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

    # --- ondas y barra con la barra de tareas de mas de 40 px -----------------
    # El bug de Windows 11 (barra de 48 px -> k=1.2): el widget pegaba la tira de las
    # ondas con una franja calculada con el ancho REAL del cuadro y la tira con el
    # ancho logico. Con algunos anchos eso daba 1 px de diferencia y ImageChops tiraba
    # "images do not match" en cada cuadro (el widget quedaba congelado y parecia que
    # el menu no hacia nada); con otros, la tira caia 60 px a la derecha, encima de los
    # botones. Con k=1.0 las dos cuentas coinciden, asi que se prueba a mano con k=1.2
    # y 1.5 llamando a la MISMA funcion que usa el widget.
    print("\n-- ondas y barra con la barra de tareas grande (k != 1) --")
    import types as _types
    from widget.app import WidgetApp
    from widget.media import MediaState as _MS3
    for kk in (1.2, 1.5):
        try:
            cfg_k = dict(cfg, width=280, show_waves=True, wave_bars=4, show_controls=True)
            alto_k = int(round(40 * kk))
            est_k = _MS3(has_session=True, app_id="test.exe", title="Titulo", artist="Artista",
                         playing=True, position=30.0, duration=180.0,
                         position_at=time.monotonic(), art=None, art_key="k",
                         can_seek=True, can_toggle=True)
            wl = int(cfg_k["width"])
            # (a) la zona clicable de la barra cae donde se dibuja (no donde dice otra formula)
            pr_k = draw.progress_rect(wl, kk, cfg_k)
            pintada_k = barra_dibujada(cfg_k, kk)
            check("k=%.1f: la barra clicable cae donde se dibuja la barra" % kk,
                  bool(pr_k) and bool(pintada_k)
                  and abs(pr_k[0] - pintada_k[0]) <= 2 and abs(pr_k[2] - pintada_k[1]) <= 2,
                  f"clicable x={pr_k[0]}..{pr_k[2]} / dibujada {pintada_k}")
            # (b) el pegado real de las ondas: pixels cambiados dentro y fuera de la franja
            img_k = draw.render(est_k, cfg_k, art=None, k=kk, base=(30, 30, 30),
                                height=alto_k, opaque=False, waves=[])
            falso = _types.SimpleNamespace(
                cfg=cfg_k, k=kk, layered=True, base=(30, 30, 30), state=est_k,
                _levels=[0.95, 0.2, 0.85, 0.4], log=lambda *a: None,
                # el widget real tiene estos dos; sin ellos la prueba no seria la misma
                width_px=int(round(wl * kk)), height_px=alto_k)
            antes = img_k.copy()
            WidgetApp._pegar_ondas(falso, img_k)
            fr = draw.wave_rect(wl, kk, cfg_k)
            ctl_k = draw.control_rects(int(round(wl * kk)), kk, cfg_k)
            dentro = sum(1 for x in range(fr[0], fr[2]) for y in range(fr[1], fr[3])
                         if img_k.getpixel((x, y)) != antes.getpixel((x, y)))
            sobre_botones = sum(1 for x in range(ctl_k[0][0] - 2, ctl_k[-1][2] + 2)
                                for y in range(alto_k)
                                if img_k.getpixel((x, y)) != antes.getpixel((x, y)))
            check("k=%.1f: las ondas se pegan dentro de su franja" % kk, dentro > 10,
                  f"{dentro} pixeles cambiados dentro de la franja {fr}")
            check("k=%.1f: las ondas no se pegan encima de los botones" % kk,
                  sobre_botones == 0, f"{sobre_botones} pixeles cambiados sobre los botones")
        except Exception as exc:
            check("k=%.1f: pegado de las ondas" % kk, False, repr(exc))

    # --- color del widget y opacidad de todo el widget ------------------------
    # Se prueba sobre el tema que arma draw (no hace falta pantalla) para que corra en
    # cualquier maquina: es lo que decide el fondo del chip.
    print("\n-- color del widget (auto / del tema de Windows / claro / oscuro) --")
    try:
        oscuro = (26, 28, 36)
        claro = (243, 244, 248)
        chip_cfg = tuple(cfg.get("theme", {}).get("chip") or ())
        t_claro = draw.theme_for_base(dict(cfg, chip_color="light"), oscuro)
        t_osc = draw.theme_for_base(dict(cfg, chip_color="dark"), claro)
        t_auto = draw.theme_for_base(dict(cfg, chip_color="auto"), oscuro)
        t_acc = draw.theme_for_base(dict(cfg, chip_color="accent"), oscuro)
        acento = sistema.color_acento()
        check("chip_color 'light' pone el tema claro aunque detrás haya oscuro",
              draw._lum(t_claro["chip"]) > 180, f"chip {t_claro['chip']}")
        check("chip_color 'dark' pone el tema oscuro aunque detrás haya claro",
              draw._lum(t_osc["chip"]) < 90, f"chip {t_osc['chip']}")
        check("chip_color 'auto' sigue mirando el fondo",
              tuple(t_auto["chip"]) == chip_cfg, f"chip {t_auto['chip']} (tema {chip_cfg})")
        check("chip_color 'accent' toma el color de Windows",
              tuple(t_acc["chip"]) == tuple(acento),
              f"chip {t_acc['chip']} contra acento {acento}")
        check("chip_color 'accent' pone un borde distinto del chip",
              tuple(t_acc["border"]) != tuple(t_acc["chip"]), f"borde {t_acc['border']}")
        d = cfgmod.DEFAULTS
        check("la config por defecto trae las dos opciones nuevas",
              d.get("widget_alpha") == 255 and d.get("chip_color") == "auto",
              f"widget_alpha={d.get('widget_alpha')} chip_color={d.get('chip_color')!r}")
    except Exception as exc:
        check("color del widget", False, repr(exc))

    # --- colores personalizados --------------------------------------------
    print("\n-- colores de la barra de progreso y de las ondas --")
    try:
        from PIL import ImageGrab
        w_now = widget_ventana()
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

        pr = draw.progress_rect(int(cfg.get("width", 260)), k, cfg)
        wrec = draw.wave_rect(int(cfg.get("width", 260)), k, cfg)
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
        if FLOTANTE:
            probar_otro_monitor_flotante(check)
        elif len(barras) < 2 or not w_now or actual is None:
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
            # Un juego en PANTALLA COMPLETA tapa la barra entera: ahi no hay nada que
            # comprobar (Windows le entrega la pantalla al juego). Se detecta por la
            # ventana que aparece encima y se salta, en vez de contarlo como falla.
            juego = False
            if w2 and tapado != "AstraMusicWnd":
                try:
                    tapadora_h = win32gui.WindowFromPoint(
                        wt.POINT(int(centro[0]), int(centro[1])))
                    tr = win32gui.GetWindowRect(tapadora_h)
                    clase = win32gui.GetClassName(tapadora_h)
                    # Barra de arriba en pantalla completa, o cualquier ventana AJENA
                    # (un juego en primer plano) que tape toda la barra: en los dos
                    # casos el widget no puede verse y no hay nada que comprobar.
                    ajena = clase not in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                                          "WorkerW", "Progman", "AstraMusicWnd")
                    br = destino["rect"]
                    juego = ajena and tr[0] <= br[0] and tr[1] <= br[1] \
                        and tr[2] >= br[2] and tr[3] >= br[3]
                except Exception:
                    juego = False
            check("nadie lo tapa en la barra nueva", bool(w2) and tapado == "AstraMusicWnd",
                  f"en el centro devuelve {tapado}"
                  + (" (hay una ventana en pantalla completa tapando la barra)" if juego
                     else ""),
                  skipped=juego)
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
        w_now = widget_ventana()
        posicion(w_now, 0xFFFF, 232)
        malos = 0
        total = 0
        for _ in range(30):
            time.sleep(0.3)
            wr3 = rect(w_now)
            # La y sale del WIDGET, no de la barra principal: el widget puede estar en la
            # franja de otro monitor y ahi muestrear la barra principal compara barra con
            # barra (daba 0/30 aun viendose perfecto).
            tt = wr3[1] + 3
            fondo = franja(wr3[0] - 2, wr3[0] - 1, tt)[0]
            borde = franja(wr3[2] - 12, wr3[2] - 11, tt)[0]
            total += 1
            if max(abs(fondo[i] - borde[i]) for i in range(3)) <= 3:
                malos += 1
        check(f"el widget no queda borrado por la barra", malos <= 1,
              f"{total - malos}/{total} cuadros correctos")
    except Exception as exc:
        check("vigilancia del pintado", False, repr(exc))

    try:
        w_now = widget_ventana()
        posicion(w_now, 0xFFFF, int(cfg.get("chip_alpha", 232)))  # dejar como estaba
    except Exception:
        pass

    # --- volumen: celda del altavoz, fila de volumen y sesion de audio ---------
    print("\n-- volumen de la app --")
    # (a) geometria: el altavoz va despues de los botones y no pisa nada
    w_now = widget_ventana()
    ww3 = (rect(w_now)[2] - rect(w_now)[0]) if w_now else int(cfg.get("width", 300) * k)
    wlog3 = int(cfg.get("width", 260))     # ancho logico: lo que piden progress_span
    ctrls = draw.control_rects(ww3, k, cfg)
    wrec = draw.wave_rect(wlog3, k, cfg)
    prg = draw.progress_span(wlog3, cfg)
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

        def filas_rojas(im, x, exacto=True, y_ini=None, y_fin=None):
            """Filas con relleno rojo en esa columna.

            Con exacto=True se cuentan solo los pixeles de rojo puro (el nucleo del
            relleno); con exacto=False se toleran los bordes suavizados, que es lo
            que hace falta para comparar grosores. Las filas salen de la geometria de
            la barra (y no de un 26..40 fijo): con la barra de tareas de 48 px la
            barra vive mas abajo y un rango fijo no la veia.
            """
            n = 0
            for y in range(y_ini, min(y_fin, im.height)):
                r, g, b = im.getpixel((x, y))
                if (255, 0, 0) == (r, g, b) if exacto else (r > 140 and g < 120 and b < 120):
                    n += 1
            return n

        # Columnas de prueba, sacadas de donde se dibuja la barra: una adentro del
        # relleno del progreso (15%) y otra donde solo llega el volumen (45%).
        prg = draw.progress_rect(int(cfg.get("width", 260)), k, cfg)
        if prg:
            x_dentro = prg[0] + 6
            x_solo_vol = prg[0] + int((prg[2] - prg[0]) * 0.30)
            y_ini, y_fin = max(0, prg[1] - 3), prg[3] + 5
        else:
            x_dentro, x_solo_vol, y_ini, y_fin = 50, 100, 26, 40

        normal = cuadro(None)
        volumen = cuadro((0.45, False, True, True))
        mudo = cuadro((0.45, True, True, True))
        sin_sesion = cuadro((0.45, False, True, False))
        # La cancion esta en 30 s de 200 (15%): en x_dentro tienen relleno el progreso y
        # el volumen (ahi se comparan los grosores) y en x_solo_vol (30% de la barra) solo
        # llega el volumen al 45%, que ademas se dibuja 1,8 veces mas grueso.
        rojo_n = filas_rojas(cuadro_rojo(None), x_solo_vol, True, y_ini, y_fin)
        rojo_v = filas_rojas(cuadro_rojo((0.45, False, True, True)), x_solo_vol, True,
                             y_ini, y_fin)
        rojo_m = filas_rojas(cuadro_rojo((0.45, True, True, True)), x_solo_vol, True,
                             y_ini, y_fin)
        grue_n = filas_rojas(cuadro_rojo(None), x_dentro, False, y_ini, y_fin)
        grue_v = filas_rojas(cuadro_rojo((0.45, False, True, True)), x_dentro, False,
                             y_ini, y_fin)
        check("con el volumen a la vista la fila muestra el nivel donde el progreso no llega",
              rojo_v >= 2 and rojo_n == 0,
              f"filas de rojo puro en x={x_solo_vol}: progreso {rojo_n}, volumen {rojo_v}")
        check("la barra de volumen se dibuja mas gruesa que el progreso",
              grue_v >= grue_n + 2,
              f"grosor en x={x_dentro}: {grue_n} -> {grue_v} filas")
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
        ses = volume_mod.sesiones()
        # Si la app que suena TIENE sesion de audio pero `estado()` no la encuentra, es un
        # fallo del emparejamiento de nombres, no interferencia: paso con Brave, que manda
        # "Brave" en SMTC mientras la sesion es "brave.exe". Antes se marcaba SALTA y
        # tapaba el bug (el altavoz del widget quedaba como un boton muerto).
        objetivo = volume_mod._normalizar(app_sonando) if app_sonando else ""
        parecidas = [s["exe"] for s in ses
                     if objetivo and volume_mod._normalizar(s["exe"]) == objetivo]
        check("se lee el volumen de la app que esta sonando",
              (bool(est) and 0.0 <= est[0] <= 1.0) or not parecidas,
              f"{app_sonando or 'sin app'}: "
              + (f"{est[0] * 100:.0f}%" + (" (silenciado)" if est[1] else "")
                 if est else
                 (f"la sesion existe ({', '.join(parecidas)}) pero estado() no la encuentra"
                  if parecidas else "no tiene sesion de audio")),
              skipped=not est and not parecidas)
        # La API puede contestar bien y no haber NINGUNA sesion de audio (nada usando el
        # sonido en este momento, como una maquina con la musica en pausa): eso es el estado
        # de la maquina, no una falla del programa. Solo es falla si la llamada revienta.
        check("la API de audio del sistema responde",
              isinstance(ses, list),
              f"{len(ses)} sesiones: "
              + (", ".join(sorted({x.get('exe', '?') for x in ses}))[:80]
                 or "nada esta usando el audio ahora"),
              skipped=isinstance(ses, list) and not ses)
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
        w_now = widget_ventana()
        ctl = win32gui.FindWindow("AstraMusicCtl", None)
        wr = rect(w_now)

        def captura():
            return ImageGrab.grab(all_screens=True, bbox=wr).convert("RGB")

        def distintos(a, b):
            """Pixeles del widget: los que difieren del cuadro SIN el widget.

            Antes se contaban los pixeles claros del recorte, y eso depende del papel
            tapiz: con la barra clara (o el chip del color del sistema) el cuadro sin el
            widget tiene mas pixeles claros que el widget mismo, y la cuenta daba al
            reves (medido: visible 4330 -> oculto 14898). Comparar contra el cuadro
            oculto mide el aporte del widget, no el brillo del fondo.
            """
            return sum(1 for pa, pb in zip(a.get_flattened_data(), b.get_flattened_data())
                       if max(abs(pa[i] - pb[i]) for i in range(3)) > 25)

        cap_visible = captura()
        win32gui.PostMessage(ctl, win32con.WM_HOTKEY, 1, 0)   # ocultar: arranca el fundido
        time.sleep(max(0.08, cfg.get("fade_step", 48) and 0.10))
        cap_medio = captura()
        time.sleep(0.7)
        cap_oculto = captura()
        visible_antes = distintos(cap_visible, cap_oculto)
        medio = distintos(cap_medio, cap_oculto)
        check("al ocultar, el widget pasa por un estado intermedio (fundido)",
              visible_antes > medio > 5,
              f"pixeles del widget contra el fondo: visible {visible_antes} -> "
              f"mitad {medio} -> oculto 0")

        win32gui.PostMessage(ctl, win32con.WM_HOTKEY, 1, 0)   # mostrar: fundido al reves
        # Al mostrar, el primer cuadro puede tardar hasta un ciclo del temporizador (500 ms
        # sin musica, 100 ms con musica): medir a los 0,10 s fijos daba 0 en silencio y
        # parecia que no habia fundido. Se espera el primer cambio, que es el cuadro del
        # medio (alfa 0 -> 48 de 255).
        cap_medio2 = cap_oculto
        for _ in range(6):
            time.sleep(0.10)
            tentativa = captura()
            if distintos(tentativa, cap_oculto) > 5:
                cap_medio2 = tentativa
                break
        time.sleep(0.7)
        cap_visible2 = captura()
        medio2 = distintos(cap_medio2, cap_oculto)
        visible_despues = distintos(cap_visible2, cap_oculto)
        check("al mostrarlo tambien aparece con fundido",
              visible_despues > medio2 > 5,
              f"pixeles del widget contra el fondo: oculto 0 -> mitad {medio2} -> "
              f"visible {visible_despues}")
        check("el widget termina visible y completo",
              abs(visible_despues - visible_antes) <= max(80, 0.25 * max(1, visible_antes)),
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

            # ...y el texto tiene que contrastar con lo que hay DETRAS (se da vuelta).
            # Se prueba el caso "sin fondo" de verdad: sin fondo en el widget y en el
            # panel (con el chip del color del sistema a la vista, el texto contrasta
            # con ESE color y no con el fondo, que es lo correcto).
            contrastes = []
            cfg_sf = dict(cfg_chico, chip_alpha=0, panel_bg_alpha=0)
            for base in ((235, 235, 235), (30, 30, 36)):
                th = draw.theme_for_base(cfg_sf, base)
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

        # (c3) el iman del panel: la matematica sola, sin ventana ni mouse. Un panel
        # a 3 px del borde se ve como un error de dibujo.
        mon = (0, 0, 1920, 1080)
        piso = 1040        # borde de arriba de la barra de tareas
        casos = [
            ("esquina con 10 px", (10, 10, 320, 34), (0, 0)),
            ("borde izquierdo con 15 px", (15, 300, 320, 34), (0, 300)),
            ("borde derecho con 12 px", (1920 - 320 - 12, 400, 320, 34), (1600, 400)),
            ("piso de la barra con 8 px", (600, 1040 - 34 - 8, 320, 34), (600, 1006)),
            ("lejos de todo no se toca", (600, 300, 320, 34), (600, 300)),
            ("fuera del monitor se mete adentro", (2500, 2000, 320, 34), (1600, 1006)),
        ]
        malos = [(n, panel_mod.imantar(x, y, w, h, mon, piso), e)
                 for n, (x, y, w, h), e in casos
                 if panel_mod.imantar(x, y, w, h, mon, piso) != e]
        check("el panel se imanta a los bordes y esquinas del monitor", not malos,
              f"casos que no dan: {malos}" if malos else
              f"{len(casos)} casos: esquina, los dos bordes, el piso de la barra, "
              f"lejos y fuera del monitor")

        # (d) fracciones y prueba de impacto
        cfg_tira = dict(cfg, panel_size="tira")
        for nombre, c in (("normal", cfg_normal), ("chico", cfg_chico), ("tira", cfg_tira)):
            z = panel_mod.rects(kp, c)
            ok_frac = (abs(panel_mod.frac_en_barra(z["barra"][0], kp, c)) < 0.01
                       and abs(panel_mod.frac_en_barra(z["barra"][2], kp, c) - 1.0) < 0.01
                       and abs(panel_mod.frac_en_volumen(z["volumen"][0], kp, c)) < 0.01)
            ctr = z["controles"][1]
            alt = z["altavoz"]
            vol = z["volumen"]
            ok_hit = (panel_mod.hit((ctr[0] + ctr[2]) // 2, (ctr[1] + ctr[3]) // 2, kp, c) == 1
                      and panel_mod.hit(z["cerrar"][0] + 2, z["cerrar"][1] + 2, kp, c) == 6
                      and panel_mod.hit(z["tapa"][0] + 2, z["tapa"][1] + 2, kp, c) == 7
                      and panel_mod.hit(-3, -3, kp, c) == -1
                      # el altavoz manda sobre la zona del volumen: si no, el clic de
                      # silencio se toma como "poner el nivel" (pasaba en el tamano tira)
                      and panel_mod.hit((alt[0] + alt[2]) // 2, (alt[1] + alt[3]) // 2,
                                        kp, c) == 5
                      and panel_mod.hit((vol[0] + vol[2]) // 2, (vol[1] + vol[3]) // 2,
                                        kp, c) == 4)
            check(f"el panel {nombre}: fracciones y que hay bajo el cursor",
                  ok_frac and ok_hit,
                  "fracciones y prueba de impacto correctas"
                  if ok_hit else
                  f"altavoz={panel_mod.hit((alt[0] + alt[2]) // 2, (alt[1] + alt[3]) // 2, kp, c)}"
                  f" volumen={panel_mod.hit((vol[0] + vol[2]) // 2, (vol[1] + vol[3]) // 2, kp, c)}"
                  f" (se esperaba 5 y 4)")

        # (e) en vivo: abrir, ver y cerrar
        win32gui.PostMessage(w_now, WM_APP_PANEL, 1, 1)
        time.sleep(0.9)
        w_panel = win32gui.FindWindow("AstraMusicPanel", None)
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
            # Si otra ventana tapa el panel (una consola abierta encima, por ejemplo), la
            # captura muestra esa ventana y la medida no dice nada del panel: se informa
            # como interferencia, igual que hace la prueba de los atajos, en vez de
            # inventar un fallo. Pasa cuando el panel vive en una esquina donde hay otra
            # ventana, que es lo que ocurre si lo arrastraste ahi.
            try:
                encima = win32gui.WindowFromPoint(((pr[0] + pr[2]) // 2,
                                                   (pr[1] + pr[3]) // 2))
            except Exception:
                encima = 0
            tapado = bool(encima) and encima != w_panel
            # El panel va SIEMPRE por encima de la ventana que estes usando. Si queda
            # debajo, al tocar otra ventana *parece* que se cerro: sigue abierto, tapado.
            # Ese es el reporte tipico de uso, asi que aca es FALLA... salvo que lo tape
            # OTRA ventana siempre-arriba (el panel de Noticias de la barra, un cartel de
            # UAC, un overlay de juego): eso es del sistema, no del panel.
            try:
                clase_encima = win32gui.GetClassName(encima) if encima else "?"
                ex_encima = win32gui.GetWindowLong(encima, win32con.GWL_EXSTYLE) if encima else 0
            except Exception:
                clase_encima, ex_encima = "?", 0
            check("el panel queda arriba de la ventana de adelante", not tapado,
                  f"lo tapa {clase_encima} (0x{encima:X})" if tapado else "nada lo tapa",
                  skipped=tapado and bool(ex_encima & 0x00000008))
            check("el panel esta pintado (no es un rectangulo negro)",
                  (not tapado) and max(vals) - min(vals) > 100
                  and sum(1 for v in vals if v > 150) > 300,
                  f"otra ventana (0x{encima:X}) tapa el panel: no se puede medir el panel"
                  if tapado else
                  f"min {min(vals)} max {max(vals)}, "
                  f"{sum(1 for v in vals if v > 150)} pixeles claros",
                  skipped=tapado)

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
            w_antes = win32gui.FindWindow("AstraMusicPanel", None)
            pr_antes = rect(w_antes) if w_antes else (0, 0, 0, 0)
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 6, 1)      # modo gaming (se devuelve al final)
            time.sleep(1.2)
            w_panel = win32gui.FindWindow("AstraMusicPanel", None)
            pr_g = rect(w_panel)
            ex_g = win32gui.GetWindowLong(w_panel, win32con.GWL_EXSTYLE)
            # El modo gaming usa SIEMPRE la disposicion chica: el tamano esperado sale de
            # esa, no de la que el usuario tenga guardada (si guardo la "tira", la cuenta
            # con su alto no cierra y la prueba fallaba sin que hubiera nada roto), y se
            # calcula con la escala de la barra (la misma que usa el panel), no con la que
            # se deduce de su alto ya redondeado (101/84 daba 1,2024 en vez de 1,2).
            cfg_chico = dict(cfgmod.load(), panel_size="chico")
            esperado = panel_mod.size(k, cfg_chico)
            check("modo gaming: el panel queda chico",
                  (pr_g[2] - pr_g[0], pr_g[3] - pr_g[1]) == esperado
                  and pr_g[3] - pr_g[1] < pr_antes[3] - pr_antes[1],
                  f"{(pr_g[2] - pr_g[0])}x{pr_g[3] - pr_g[1]} "
                  f"(antes {pr_antes[2] - pr_antes[0]}x{pr_antes[3] - pr_antes[1]})")
            # Se mira el comportamiento y no el archivo: la suite no guarda ajustes (los
            # del usuario son suyos), asi que leer config.json diria cualquier cosa.
            time.sleep(2.5)
            check("modo gaming: queda fijo (no se oculta solo)",
                  win32gui.IsWindowVisible(w_panel),
                  f"visible a los 2,5 s = {win32gui.IsWindowVisible(w_panel)}")
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

            # Perder la activacion (lo que manda Windows al tocar otra ventana) tampoco lo
            # cierra: el panel es para cambiar de tema sin salir de la app de adelante. Se
            # manda el mensaje exacto en vez de esperar a que el sistema lo mande.
            win32gui.SendMessage(w_panel, win32con.WM_ACTIVATE, 0, 0)   # WA_INACTIVE
            time.sleep(0.7)
            check("perder el foco NO cierra el panel",
                  win32gui.IsWindowVisible(w_panel),
                  f"visible={win32gui.IsWindowVisible(w_panel)}")
            # la opcion que devuelve el comportamiento de globo del sistema (sin guardar)
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 11, 1)
            time.sleep(0.6)
            win32gui.SendMessage(w_panel, win32con.WM_ACTIVATE, 0, 0)
            time.sleep(0.7)
            check("con 'cerrar al tocar afuera' si se cierra",
                  not win32gui.IsWindowVisible(w_panel),
                  f"visible={win32gui.IsWindowVisible(w_panel)}")
            win32gui.PostMessage(w_now, WM_APP_PANEL_CFG, 11, 0)
            win32gui.PostMessage(w_now, WM_APP_PANEL, 1, 0)
            time.sleep(0.8)
            w_panel = win32gui.FindWindow("AstraMusicPanel", None)

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
                      win32gui.FindWindow("AstraMusicPanel", None) or w_panel))
    except Exception as exc:
        check("el panel", False, repr(exc))

    # --- la barra tiene que estar abajo para incrustar; si no, modo flotante ---------
    try:
        from widget.taskbarwin import barra_en_posicion_util, motivo_no_incrustable
        casos = [
            ("abajo", {"rect": (0, 1040, 1920, 1080), "mon_rect": (0, 0, 1920, 1080)}, True),
            ("secundaria abajo", {"rect": (1920, 849, 3286, 889),
                                  "mon_rect": (1920, 121, 3286, 889)}, True),
            ("a un costado", {"rect": (0, 0, 62, 1080), "mon_rect": (0, 0, 1920, 1080)}, False),
            ("arriba", {"rect": (0, 0, 1920, 40), "mon_rect": (0, 0, 1920, 1080)}, False),
            ("sin datos", None, False),
        ]
        malos = [n for n, b, e in casos if barra_en_posicion_util(b) != e]
        check("la barra tiene que estar abajo y horizontal", not malos,
              ("mal: " + ", ".join(malos)) if malos else "")
        m = motivo_no_incrustable()
        check("el motivo se explica solo (texto o None)", m is None or isinstance(m, str),
              repr(m) if m else "")
    except Exception as exc:
        check("la barra tiene que estar abajo y horizontal", False, repr(exc))

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
