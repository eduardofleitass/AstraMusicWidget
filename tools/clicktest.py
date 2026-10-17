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

import win32con  # noqa: E402
import win32gui  # noqa: E402

from widget import config as cfgmod, draw  # noqa: E402
from widget import panel as panel_mod  # noqa: E402
from widget.media import MediaPoller  # noqa: E402
from widget.taskbarwin import list_bars  # noqa: E402

user32 = ctypes.windll.user32
PASS, FAIL, SKIP = "PASA", "FALLA", "SALTA"
results = []
interfered = []

# La rueda: dwData lleva 120 por muesca y hace falta el tipo declarado para poder
# pasar el valor negativo (-120) sin que ctypes se queje.
WHEEL_UP = 120
WHEEL_DOWN = 0xFFFFFF88          # -120 como DWORD de 32 bits
MOUSEEVENTF_WHEEL = 0x0800
user32.mouse_event.argtypes = [wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
user32.mouse_event.restype = None


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
    """El widget y la barra donde vive, sea la principal o la de otro monitor.

    En Windows 10 cada monitor tiene su propia barra (Shell_SecondaryTrayWnd), asi
    que no se puede asumir la principal.
    """
    for b in list_bars():
        w = win32gui.FindWindowEx(b["tray"], 0, "GorusTaskbarMusicWnd", None)
        if w:
            # WIN lo usan las comprobaciones "el cursor quedo sobre el widget": al
            # mudarse de barra el hwnd cambia, asi que hay que refrescarlo aca.
            WIN["widget"] = w
            return b["tray"], w
    return 0, 0


def rect_actual():
    """Handle y rectangulo del widget AHORA.

    La barra de tareas cambia de ancho (se abren y cierran ventanas, y el widget se
    corre con la lista de tareas), y el widget se puede arrastrar: una coordenada
    tomada al arrancar la prueba puede terminar apuntando a otro lado, y entonces el
    clic cae fuera y la prueba se salta sola por "interferencia" que no existe.
    """
    tray, w = find_widget()
    if not w:
        return 0, (0, 0, 0, 0)
    WIN["widget"] = w
    return w, win32gui.GetWindowRect(w)


def button_centers(wrect, k, cfg):
    x0, y0, x1, y1 = wrect
    mid_y = (y0 + y1) // 2
    return [(x0 + (rx0 + rx1) // 2, mid_y)
            for rx0, ry0, rx1, ry1 in draw.control_rects(x1 - x0, k, cfg)]


def window_at(x, y):
    try:
        return win32gui.WindowFromPoint((x, y))
    except Exception:
        return 0


def sobre_widget(x, y) -> bool:
    """Confirma que el widget es la ventana bajo el cursor.

    Windows entrega la rueda del mouse a la ventana que esta debajo del cursor, no
    a la que tiene el foco: si el cursor se movio (o lo movio el usuario), la prueba
    mediria un salto que nunca se pidio.
    """
    return window_at(x, y) == WIN.get("widget")


WIN = {}


def click_en(hwnd, x, y) -> bool:
    """Clic real sobre OTRA ventana (el panel), confirmando que esa es la de abajo."""
    if not place_cursor(x, y):
        return False
    if win32gui.WindowFromPoint((x, y)) != hwnd:
        return False
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    time.sleep(0.06)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
    time.sleep(0.4)
    return True


def click(x, y) -> bool:
    if not place_cursor(x, y):
        return False
    if not sobre_widget(x, y):
        return False
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    time.sleep(0.06)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
    time.sleep(0.35)
    return True


def grab(wrect):
    """Captura del widget. Con all_screens=True: si el widget vive en la barra del
    monitor secundario, sin esto sale todo negro (ImageGrab solo toma el principal)."""
    from PIL import ImageGrab
    return ImageGrab.grab(bbox=wrect, all_screens=True).convert("L")


def filas_barra(img, wrect):
    """Cuantas filas de la franja de la barra estan pintadas, medido contra el fondo.

    Sirve para distinguir la barra de progreso (2,5 px) de la de volumen, que se
    dibuja 1,8 veces mas gruesa cuando esta activa. Se toma la MEDIANA entre columnas
    y no la union de filas: la perilla del progreso tiene ~6 px de alto y en una sola
    columna infla el conteo (medido: 6 filas de "grosor" en una barra de 2,5 px).
    El fondo se estima con las filas entre el renglon del artista y la barra, para que
    no dependa del tema ni del color que haya elegido el usuario.
    """
    k = (wrect[3] - wrect[1]) / float(draw.REF_H)
    cols = list(range(90, 160, 10))
    fondo = min(img.getpixel((x, y)) for x in cols for y in (29, 30, 31, 32))
    y0 = max(0, int(draw.PROG_Y * k) - 4)
    y1 = min(img.height, int(draw.PROG_Y * k) + 5)
    por_columna = []
    for x in cols:
        n = 0
        for y in range(y0, y1):
            if img.getpixel((x, y)) > fondo + 25:
                n += 1
        por_columna.append(n)
    # Se SUMAN las columnas (no mediana): lo que cambia con el volumen es el grosor,
    # o sea cuantos pixeles se pintan en la franja. Medido: la barra de 2,5 px da 4
    # filas por columna y la de volumen 5 (los bordes suavizados comprimen la
    # diferencia), asi que exigir "+2 filas" es fragil; la suma pasa de ~18 a ~32.
    return sum(por_columna)


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


def pos_reportada(poller, desde=None, timeout=6.0):
    """(segundos, instante, hubo_cambio) del primer reporte NUEVO del reproductor.

    No alcanza con leer la posicion interpolada: los reproductores informan cada
    varios segundos y el valor puede venir atrasado mas de 10 s, asi que medir un
    salto de 10 s contra un valor viejo da cualquier cosa (medido: +33 s para un
    salto de 10 s). Se espera a que el reproductor informe algo distinto del valor
    de referencia; si no lo hace, se informa que no hubo reporte nuevo (y la
    comprobacion se salta en vez de convertirse en un fallo inventado).
    """
    t0 = time.time()
    ref = poller.state().position if desde is None else desde
    while time.time() - t0 < timeout:
        st = poller.state()
        if st.position != ref:
            return st.position, time.time(), True
        time.sleep(0.12)
    return poller.state().position, time.time(), False


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
    WIN["widget"] = w
    wrect = win32gui.GetWindowRect(w)
    k = (wrect[3] - wrect[1]) / 40.0
    centers = button_centers(wrect, k, cfg)
    print(f"widget en pantalla: {wrect}")
    print(f"centros de botones: {centers}\n")

    # El arrastre de prueba muda el widget de barra y de lugar: se anota donde
    # estaba y se devuelve al final, para no dejarlo cambiado.
    pos_ini = cfg.get("position_frac")

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
    w, wrect = rect_actual()
    k = (wrect[3] - wrect[1]) / 40.0
    centers = button_centers(wrect, k, cfg)
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
            if not place_cursor(cx, cy) or not sobre_widget(cx, cy):
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
    w, wrect = rect_actual()
    k = (wrect[3] - wrect[1]) / 40.0
    centers = button_centers(wrect, k, cfg)
    toggle = centers[1]
    if not click(*toggle):
        check("el clic cambia el estado de reproduccion", False,
              "el cursor no quedo sobre el widget (interferencia del mouse)", skipped=True)
        check("el segundo clic restaura el estado original", False,
              "no aplica", skipped=True)
    else:
        time.sleep(1.6)
        mid = sample(poller)
        if mid.title != before.title:
            # La lista de reproduccion puede cambiar de tema justo mientras se mide:
            # en ese caso el comando se pierde y la prueba fallaria por algo que no
            # tiene que ver con el widget. Se informa como interferencia.
            check("el clic cambia el estado de reproduccion", False,
                  f"cambio de tema durante la medicion ({before.title!r} -> {mid.title!r})",
                  skipped=True)
        else:
            check("el clic cambia el estado de reproduccion", mid.playing != before.playing,
                  f"{before.playing} -> {mid.playing}")
        if not click(*toggle):
            check("el segundo clic restaura el estado original", False,
                  "el cursor no quedo sobre el widget (interferencia del mouse)", skipped=True)
        else:
            time.sleep(1.8)
            after = sample(poller)
            check("el segundo clic restaura el estado original",
                  after.playing == before.playing, f"{mid.playing} -> {after.playing}")

    # --- 3. clic sobre una zona neutra: no debe hacer nada -------------------
    print("\n-- clic en una zona neutra (el titulo: no debe disparar nada) --")
    ref = sample(poller)
    w, wrect = rect_actual()
    k = (wrect[3] - wrect[1]) / 40.0
    # Sobre el TITULO y no sobre la caratula: un clic seco en la caratula abre el
    # panel (a proposito), que es otra prueba. Aca se busca una zona que no haga nada.
    art_x = wrect[0] + int(120 * k)
    if click(art_x, (wrect[1] + wrect[3]) // 2):
        time.sleep(1.2)
        st = sample(poller)
        check("un clic fuera de los botones no cambia nada",
              st.playing == ref.playing and st.title == ref.title,
              f"sonando={st.playing}")
    else:
        check("un clic fuera de los botones no cambia nada", False,
              "el cursor no quedo sobre el widget (interferencia del mouse)", skipped=True)

    # --- 4. clic real sobre la barra de progreso ----------------------------
    print("\n-- clic real sobre la barra de progreso (se devuelve a su lugar) --")
    base = sample(poller)
    w, wrect = rect_actual()
    k = (wrect[3] - wrect[1]) / 40.0
    pr = draw.progress_rect(wrect[2] - wrect[0], k, cfg)
    y_barra = wrect[1] + int(35.5 * k)
    if not (pr and base.can_seek and base.duration > 20):
        check("un clic en la barra salta a la posicion clickeada", False,
              "este reproductor no admite saltos (¿vivo?)", skipped=True)
        check("el widget no se mueve al hacer clic en la barra", False, "no aplica",
              skipped=True)
        check("el salto se puede devolver a la posicion original", False, "no aplica",
              skipped=True)
    else:
        frac = 0.8
        x_obj = wrect[0] + int(pr[0] + (pr[2] - pr[0]) * frac)
        quiere = frac * base.duration
        r0, t0, ok0 = pos_reportada(poller)
        pos_widget = win32gui.GetWindowRect(w)
        tolerancia = max(6.0, 0.04 * base.duration)
        if not click(x_obj, y_barra):
            check("un clic en la barra salta a la posicion clickeada", False,
                  "el cursor no quedo sobre el widget (interferencia del mouse)", skipped=True)
            check("el widget no se mueve al hacer clic en la barra", False, "no aplica",
                  skipped=True)
            check("el salto se puede devolver a la posicion original", False, "no aplica",
                  skipped=True)
        else:
            # El reproductor informa la posicion cada varios segundos: se espera al
            # primer reporte nuevo y se le suma lo que el audio avanzo mientras tanto.
            r1, t1, ok1 = pos_reportada(poller, desde=r0)
            esperado = min(quiere + (t1 - t0), base.duration)
            check("un clic en la barra salta a la posicion clickeada",
                  abs(r1 - esperado) <= tolerancia,
                  f"clic al {frac:.0%} = {quiere:.0f}s (venia de {r0:.0f}s) -> informado "
                  f"{r1:.0f}s, se esperaba {esperado:.0f}s"
                  f"  desvio {r1 - esperado:+.1f}s (tolerancia {tolerancia:.0f}s)",
                  skipped=not ok1)
            check("el widget no se mueve al hacer clic en la barra",
                  win32gui.GetWindowRect(w) == pos_widget,
                  f"{pos_widget} -> {win32gui.GetWindowRect(w)}")
            # devolverlo a donde estaba: el audio siguio sonando mientras se medía
            volver = min(r0 + (time.time() - t0) + 1.0, base.duration - 1)
            poller.seek(volver)
            time.sleep(1.6)
            atras = poller.state().live_position()
            check("el salto se puede devolver a la posicion original",
                  abs(atras - (volver + 1.6)) <= tolerancia,
                  f"pedido {volver:.0f}s -> {atras:.0f}s")

    # --- 5. rueda del mouse sobre el widget ---------------------------------
    print("\n-- rueda del mouse sobre el widget --")
    base = sample(poller)
    w, wrect = rect_actual()
    k = (wrect[3] - wrect[1]) / 40.0
    paso = float(cfg.get("seek_step_s", 10))
    centro = ((wrect[0] + wrect[2]) // 2, (wrect[1] + wrect[3]) // 2)
    if not (base.can_seek and base.duration > 20):
        check("la rueda adelanta el paso configurado", False,
              "este reproductor no admite saltos", skipped=True)
        check("la rueda atrasa el paso configurado", False, "no aplica", skipped=True)
    elif not place_cursor(*centro) or not sobre_widget(*centro):
        check("la rueda adelanta el paso configurado", False,
              "el cursor no quedo sobre el widget (interferencia del mouse)",
              skipped=True)
        check("la rueda atrasa el paso configurado", False, "no aplica", skipped=True)
    else:
        antes = sample(poller).live_position()
        if not sobre_widget(*centro):
            check("la rueda adelanta el paso configurado", False,
                  "el cursor se movio justo antes de mandar la rueda", skipped=True)
            check("la rueda atrasa el paso configurado", False, "no aplica", skipped=True)
            user32.SetCursorPos(wrect[0] - 300, 560)
            poller.stop()
            return _summary()
        r0, t0, ok0 = pos_reportada(poller)
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_UP, 0)
        r1, t1, ok1 = pos_reportada(poller, desde=r0)
        d = r1 - r0
        esperado = paso + (t1 - t0)
        # El reproductor informa la posicion con un atraso propio (medido: el valor
        # nuevo puede describir una posicion ~5 s vieja), asi que la tolerancia es
        # amplia: igual distingue un salto de verdad de la simple reproduccion.
        tolerancia = max(7.0, 0.5 * paso)
        check("la rueda adelanta el paso configurado",
              abs(d - esperado) <= tolerancia,
              f"{r0:.0f}s -> {r1:.0f}s  ({d:+.1f}s, se esperaba +{esperado:.1f}s)"
              f"  tolerancia {tolerancia:.0f}s",
              skipped=not ok1)
        # Si el tema esta al principio no hay lugar para atras: se adelanta con la
        # MISMA rueda (el propio camino del widget). Hacerlo con el poller de la
        # prueba deja dos escritores sobre la misma sesion y el salto medido sale
        # cualquier cosa (medido: -40 s en vez de -10 s).
        if r1 < paso * 2:
            for _ in range(3):
                if not sobre_widget(*centro):
                    break
                user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_UP, 0)
                time.sleep(0.6)
            r1, t1, ok1 = pos_reportada(poller, desde=r0)
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_DOWN, 0)
        r2, t2, ok2 = pos_reportada(poller, desde=r1)
        d2 = r2 - r1
        esperado2 = (t2 - t1) - paso
        check("la rueda atrasa el paso configurado",
              abs(d2 - esperado2) <= tolerancia,
              f"{r1:.0f}s -> {r2:.0f}s  ({d2:+.1f}s, se esperaba {esperado2:+.1f}s)"
              f"  tolerancia {tolerancia:.0f}s",
              skipped=not ok2)

    # --- 6. arrastrar el widget a la barra del otro monitor -----------------
    print("\n-- arrastrar el widget a la barra de otro monitor (se devuelve) --")
    barras = list_bars()
    actual, w_now = find_widget()
    if len(barras) < 2:
        check("el equipo tiene mas de una barra de tareas", False,
              "un solo monitor: no aplica", skipped=True)
    elif not w_now:
        check("el widget esta corriendo", False, "no lo encuentro")
    else:
        barra_actual = next(b for b in barras if b["tray"] == actual)
        otra = next(b for b in barras if b["tray"] != actual)
        rw = win32gui.GetWindowRect(w_now)
        agarre = (rw[0] + 80, rw[1] + 12)          # por el titulo: no es boton ni barra
        destino = ((otra["rect"][0] + otra["rect"][2]) // 2, otra["rect"][1] + 12)
        if not place_cursor(*agarre) or not sobre_widget(*agarre):
            check("arrastrar el widget a la otra barra lo muda de monitor", False,
                  "el cursor no quedo sobre el widget (interferencia del mouse)",
                  skipped=True)
            check("la vuelta devuelve el widget a su barra", False, "no aplica",
                  skipped=True)
        else:
            user32.mouse_event(0x0002, 0, 0, 0, 0)     # LEFTDOWN
            time.sleep(0.15)
            # en pasos, entrando al tramo del otro monitor
            for paso in (0.25, 0.5, 0.75, 1.0):
                x = int(agarre[0] + (destino[0] - agarre[0]) * paso)
                y = int(agarre[1] + (destino[1] - agarre[1]) * paso)
                user32.SetCursorPos(x, y)
                time.sleep(0.25)
            user32.mouse_event(0x0004, 0, 0, 0, 0)     # LEFTUP
            time.sleep(1.2)
            b2, w2 = find_widget()
            check("arrastrar el widget a la otra barra lo muda de monitor",
                  bool(w2) and b2 == otra["tray"],
                  f"quedo en la barra {hex(b2) if b2 else '-'} (se esperaba "
                  f"{hex(otra['tray'])}, {otra['nombre']})")
            if w2:
                wr2 = win32gui.GetWindowRect(w2)
                check("queda dentro de la barra nueva",
                      otra["rect"][0] <= wr2[0] and wr2[2] <= otra["rect"][2],
                      f"widget {wr2} dentro de {otra['rect']}")

            # volver arrastrandolo para el otro lado
            b3, w3 = find_widget()
            if w3:
                rw3 = win32gui.GetWindowRect(w3)
                ag3 = (rw3[0] + 80, rw3[1] + 12)
                volver = ((barra_actual["rect"][0] + barra_actual["rect"][2]) // 2,
                          barra_actual["rect"][1] + 12)
                if not place_cursor(*ag3) or not sobre_widget(*ag3):
                    check("la vuelta devuelve el widget a su barra", False,
                          "el cursor no quedo sobre el widget (interferencia)",
                          skipped=True)
                else:
                    user32.mouse_event(0x0002, 0, 0, 0, 0)
                    time.sleep(0.15)
                    for paso in (0.25, 0.5, 0.75, 1.0):
                        x = int(ag3[0] + (volver[0] - ag3[0]) * paso)
                        y = int(ag3[1] + (volver[1] - ag3[1]) * paso)
                        user32.SetCursorPos(x, y)
                        time.sleep(0.25)
                    user32.mouse_event(0x0004, 0, 0, 0, 0)
                    time.sleep(1.2)
                    b4, w4 = find_widget()
                    check("la vuelta devuelve el widget a su barra",
                          bool(w4) and b4 == actual,
                          f"quedo en la barra {hex(b4) if b4 else '-'} "
                          f"(se esperaba {hex(actual)}, {barra_actual['nombre']})")

    # --- 7. volumen de la app (celda del altavoz) -----------------------------
    print("\n-- volumen de la app (altavoz, rueda y arrastre) --")
    try:
        from widget import volume as volume_mod
        volume_mod.iniciar_com()
    except Exception as exc:
        volume_mod = None
        check("el control de volumen carga", False, f"{exc!r}")
    app = getattr(poller.state(), "app_id", "") or ""
    inicial = None
    if volume_mod and app:
        try:
            inicial = volume_mod.estado(app)
        except Exception as exc:
            check("se puede leer el volumen de la app", False, f"{exc!r}")
    if not (volume_mod and inicial):
        check("se puede leer el volumen de la app", False,
              f"{app!r} no tiene sesion de audio (¿no esta sonando?)", skipped=True)
        check("la rueda sobre el altavoz mueve el volumen", False, "no aplica",
              skipped=True)
        check("un clic real en el altavoz silencia", False, "no aplica", skipped=True)
        check("arrastrar sobre la barra de volumen cambia el nivel", False, "no aplica",
              skipped=True)
    else:
        check("se puede leer el volumen de la app", True,
              f"{app} al {inicial[0] * 100:.0f}%"
              + (" (silenciado)" if inicial[1] else ""))
        # el rect anterior puede estar viejo: el arrastre entre monitores deja el
        # widget en otro lugar de la barra
        w, wrect = rect_actual()
        k = (wrect[3] - wrect[1]) / 40.0
        centros = button_centers(wrect, k, cfg)
        altavoz = centros[3] if len(centros) > 3 else centros[-1]
        w_win = WIN["widget"]
        # nivel conocido: asi lo que se mida despues es comparable
        win32gui.PostMessage(w_win, win32con.WM_APP + 7, 300, 0)
        time.sleep(0.4)

        # (a) el cursor sobre el altavoz convierte la fila del progreso en volumen
        park_away(wrect)
        img_antes = grab(wrect)
        if not place_cursor(*altavoz) or not sobre_widget(*altavoz):
            check("con el cursor en el altavoz la fila hace de barra de volumen", False,
                  "el cursor no quedo sobre el widget (interferencia)", skipped=True)
        else:
            time.sleep(0.6)
            img_despues = grab(wrect)
            # Comparar los dos cuadros en la franja de la barra: al volverse barra de
            # volumen se dibuja 1,8 veces mas gruesa y cambian las filas de arriba y de
            # abajo del relleno. Contar por luminancia no sirve: 2,5 px y 4,5 px dan 4 y
            # 5 filas "pintadas" (medido), y la diferencia parece chica.
            kk = (wrect[3] - wrect[1]) / float(draw.REF_H)
            y0 = max(0, int((draw.PROG_Y - 5) * kk))
            y1 = min(img_antes.height, int((draw.PROG_Y + 6) * kk))
            banda_a = img_antes.crop((0, y0, img_antes.width, y1))
            banda_d = img_despues.crop((0, y0, img_despues.width, y1))
            cambiados = sum(1 for p, q in zip(banda_a.get_flattened_data(),
                                              banda_d.get_flattened_data())
                            if abs(p - q) > 12)
            check("con el cursor en el altavoz la fila hace de barra de volumen",
                  cambiados > 150,
                  f"{cambiados} pixeles de la franja cambiaron "
                  f"(la barra de volumen es 1,8 veces mas gruesa)")

            # (b) la rueda sobre el altavoz mueve el volumen, no el tiempo
            v0 = volume_mod.estado(app)
            user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_UP, 0)
            time.sleep(0.6)
            v1 = volume_mod.estado(app)
            paso = int(cfg.get("volume_step", 5)) / 100.0
            if v0 and v1:
                check("la rueda sobre el altavoz mueve el volumen",
                      abs((v1[0] - v0[0]) - paso) < 0.02,
                      f"{v0[0] * 100:.0f}% -> {v1[0] * 100:.0f}% (paso {paso * 100:.0f}%)")
            else:
                check("la rueda sobre el altavoz mueve el volumen", False,
                      "no se pudo leer el volumen despues de la rueda")

            # (c) arrastrar sobre la fila del volumen (se baja el cursor a la fila)
            span = draw.progress_span(wrect[2] - wrect[0], cfg)
            fila_y = wrect[1] + int(draw.PROG_Y * k) + 1
            if span:
                x_25 = int(wrect[0] + span[0] + (span[1] - span[0]) * 0.25)
                x_75 = int(wrect[0] + span[0] + (span[1] - span[0]) * 0.75)
                # La celda del altavoz ocupa toda la altura, asi que el arrastre tiene
                # que empezar sobre la fila a la izquierda de esa celda.
                if place_cursor(x_25, fila_y) and sobre_widget(x_25, fila_y):
                    time.sleep(0.4)
                    user32.mouse_event(0x0002, 0, 0, 0, 0)      # LEFTDOWN en la fila
                    time.sleep(0.2)
                    for paso_x in (0.4, 0.7, 1.0):
                        x = int(x_25 + (x_75 - x_25) * paso_x)
                        user32.SetCursorPos(x, fila_y)
                        time.sleep(0.2)
                    user32.mouse_event(0x0004, 0, 0, 0, 0)      # LEFTUP
                    time.sleep(0.6)
                    v2 = volume_mod.estado(app)
                    objetivo = (x_75 - wrect[0] - span[0]) / float(span[1] - span[0])
                    if v2:
                        check("arrastrar sobre la barra de volumen cambia el nivel",
                              abs(v2[0] - objetivo) < 0.12,
                              f"quedo en {v2[0] * 100:.0f}% (se apunto a "
                              f"{objetivo * 100:.0f}%)")
                    else:
                        check("arrastrar sobre la barra de volumen cambia el nivel",
                              False, "no se pudo leer el volumen")
                else:
                    check("arrastrar sobre la barra de volumen cambia el nivel", False,
                          "el cursor no quedo sobre el widget (interferencia)",
                          skipped=True)
            else:
                check("arrastrar sobre la barra de volumen cambia el nivel", False,
                      "no hay barra de progreso en este ancho", skipped=True)

            # (d) clic seco en el altavoz: silencio si/no (se restaura)
            antes_mudo = (volume_mod.estado(app) or (0, False))[1]
            if click(*altavoz):
                mudo1 = (volume_mod.estado(app) or (0, False))[1]
                time.sleep(0.3)
                click(*altavoz)
                mudo2 = (volume_mod.estado(app) or (0, False))[1]
                check("un clic real en el altavoz silencia y el otro lo saca",
                      mudo1 != antes_mudo and mudo2 == antes_mudo,
                      f"silencio {antes_mudo} -> {mudo1} -> {mudo2}")
            else:
                check("un clic real en el altavoz silencia y el otro lo saca", False,
                      "el cursor no quedo sobre el widget (interferencia)",
                      skipped=True)

        # dejar el volumen como estaba
        try:
            volume_mod.fijar(app, inicial[0])
            volume_mod.silenciar(app, inicial[1])
        except Exception:
            pass
        print(f"   volumen restaurado a {inicial[0] * 100:.0f}%"
              + (" silenciado" if inicial[1] else ""))

    # --- 8. panel (mini reproductor) ------------------------------------------
    print("\n-- panel (clic real) --")
    w, wrect = rect_actual()
    k = (wrect[3] - wrect[1]) / 40.0
    sonando_antes = sample(poller).playing
    # El panel se prueba con el modo gaming fijo (sin auto-ocultar y sin robar el
    # foco): si se ocultara solo en el medio, las comprobaciones fallarian por algo
    # que no es el objeto de esta prueba. Los ajustes se devuelven al final.
    cfg_panel = cfgmod.load()
    auto_panel = float(cfg_panel.get("panel_auto_hide_s", 0) or 0)
    hud_panel = bool(cfg_panel.get("panel_hud", False))
    foco_panel = bool(cfg_panel.get("panel_no_robar", False))
    win32gui.PostMessage(w, win32con.WM_APP + 11, 4, 0)     # sin HUD
    win32gui.PostMessage(w, win32con.WM_APP + 11, 7, 0)     # sin auto-ocultar
    win32gui.PostMessage(w, win32con.WM_APP + 11, 1, 1)     # no robar el foco
    win32gui.PostMessage(w, win32con.WM_APP + 10, 0, 1)     # cerrado para empezar
    time.sleep(0.9)
    tapa = (int(wrect[0] + 20 * k), int(wrect[1] + 20 * k))   # sobre la caratula
    if not (place_cursor(*tapa) and sobre_widget(*tapa)):
        check("un clic seco en la caratula abre el panel", False,
              "el cursor no quedo sobre el widget (interferencia)", skipped=True)
    else:
        click(*tapa)
        time.sleep(1.1)
        hp = win32gui.FindWindow("GorusTaskbarMusicPanel", None)
        abierto = bool(hp and win32gui.IsWindowVisible(hp))
        check("un clic seco en la caratula abre el panel", abierto,
              f"panel {hex(hp or 0)}, rect {win32gui.GetWindowRect(hp) if hp else '-'}")
        if abierto:
            pr = win32gui.GetWindowRect(hp)
            zp = panel_mod.rects(k, cfgmod.load())

            # (a) play/pausa del panel
            c_play = zp["controles"][1]
            pto_play = (pr[0] + (c_play[0] + c_play[2]) // 2,
                        pr[1] + (c_play[1] + c_play[3]) // 2)
            antes_p = sample(poller).playing
            if click_en(hp, *pto_play):
                ahora_p = antes_p
                for _ in range(12):
                    time.sleep(0.35)
                    ahora_p = sample(poller).playing
                    if ahora_p != antes_p:
                        break
                check("el play/pausa del panel cambia la reproduccion",
                      ahora_p != antes_p, f"sonando {antes_p} -> {ahora_p}")
                click_en(hp, *pto_play)      # devolver el estado
                time.sleep(0.6)
            else:
                check("el play/pausa del panel cambia la reproduccion", False,
                      "el cursor no quedo sobre el panel (interferencia)", skipped=True)

            # (b) salto con la barra del panel
            zb = zp["barra"]
            xb = int(pr[0] + zb[0] + (zb[2] - zb[0]) * 0.7)
            yb = int(pr[1] + (zb[1] + zb[3]) // 2)
            st_antes = sample(poller)
            if st_antes.can_seek and st_antes.duration > 20 and click_en(hp, xb, yb):
                time.sleep(1.3)
                st_desp = sample(poller)
                objetivo = 0.7 * st_desp.duration
                tol = max(8.0, 0.06 * st_desp.duration)
                check("un clic en la barra del panel salta a esa posicion",
                      abs(st_desp.live_position() - objetivo) <= tol,
                      f"clic al 70% = {objetivo:.0f}s -> informado "
                      f"{st_desp.live_position():.0f}s (tolerancia {tol:.0f}s)")
            else:
                check("un clic en la barra del panel salta a esa posicion", False,
                      "este reproductor no admite saltos", skipped=True)

            # (c) el volumen del panel
            zv = zp["volumen"]
            xv = int(pr[0] + zv[0] + (zv[2] - zv[0]) * 0.3)
            yv = int(pr[1] + (zv[1] + zv[3]) // 2)
            try:
                app_p = sample(poller).app_id
                v_antes = volume_mod.estado(app_p) if app_p else None
            except Exception:
                v_antes = None
            if v_antes and click_en(hp, xv, yv):
                time.sleep(0.6)
                v_ahora = volume_mod.estado(app_p)
                check("un clic en la barra de volumen del panel lo pone ahi",
                      bool(v_ahora and abs(v_ahora[0] - 0.3) < 0.08),
                      f"{v_antes[0] * 100:.0f}% -> {v_ahora[0] * 100:.0f}% "
                      f"(se apunto a 30%)")
                volume_mod.fijar(app_p, v_antes[0])
            else:
                check("un clic en la barra de volumen del panel lo pone ahi", False,
                      "no hay sesion de audio", skipped=True)

            # (c2) en modo gaming el panel no le roba el foco a la ventana de adelante
            try:
                frente = win32gui.GetForegroundWindow()
                check("el panel no le roba el foco (modo gaming)",
                      frente != hp,
                      f"al frente hay {hex(frente)} (panel {hex(hp)})")
            except Exception as exc:
                check("el panel no le roba el foco (modo gaming)", False, repr(exc))

            # (d) cerrar con la cruz
            zc = zp["cerrar"]
            pto_x = (pr[0] + (zc[0] + zc[2]) // 2, pr[1] + (zc[1] + zc[3]) // 2)
            if click_en(hp, *pto_x):
                time.sleep(0.9)
                check("la cruz del panel lo cierra",
                      not win32gui.IsWindowVisible(hp),
                      f"visible={win32gui.IsWindowVisible(hp)}")
            else:
                check("la cruz del panel lo cierra", False,
                      "el cursor no quedo sobre el panel (interferencia)", skipped=True)

            # por si quedo abierto (una prueba fallo antes de cerrarlo)
            try:
                if win32gui.IsWindowVisible(hp):
                    win32gui.PostMessage(w, win32con.WM_APP + 10, 0, 1)
                    time.sleep(0.6)
            except Exception:
                pass
    # devolver los ajustes del panel como estaban
    try:
        win32gui.PostMessage(w, win32con.WM_APP + 11, 4, 1 if hud_panel else 0)
        win32gui.PostMessage(w, win32con.WM_APP + 11, 7, int(auto_panel * 10))
        win32gui.PostMessage(w, win32con.WM_APP + 11, 1, 1 if foco_panel else 0)
        time.sleep(0.5)
    except Exception:
        pass
    # devolver la reproduccion como estaba
    try:
        if sample(poller).playing != sonando_antes:
            poller.toggle()
            time.sleep(0.5)
    except Exception:
        pass

    # devolver el widget a su barra y a su lugar de siempre
    w_fin = WIN.get("widget")
    if w_fin and win32gui.IsWindow(w_fin):
        barras = list_bars()
        quiero = cfg.get("taskbar_monitor") or None
        i = next((n for n, b in enumerate(barras)
                  if (None if b["primario"] else b["monitor"]) == quiero), None)
        if i is not None:
            win32gui.PostMessage(w_fin, win32con.WM_APP + 6, i, 1)
            time.sleep(0.6)
            w_fin = find_widget()[1] or w_fin
        if w_fin and win32gui.IsWindow(w_fin):
            win32gui.PostMessage(w_fin, win32con.WM_APP + 1,
                                 0xFFFF if pos_ini is None else int(pos_ini * 1000), 1)
            time.sleep(0.6)

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
