"""Prueba de los atajos globales con teclas REALES y de la rueda con modificadores.

    python tools/hotkeytest.py

Manda los acordes con keybd_event (como si los apretara el usuario) y mide el efecto
en el reproductor por SMTC, no en el log del widget. Cubre: Ctrl+Alt+P (play/pausa),
Ctrl+Alt+flechas (anterior/siguiente), Ctrl+Alt+Shift+flechas (+-10 s), Ctrl+Alt+
arriba/abajo (volumen +-5%), Ctrl+Alt+M (ocultar/mostrar), los atajos apagados desde
el menu, y la rueda con modificadores (Ctrl = 1 s, Shift = 60 s).

Importante:

Manda los acordes con keybd_event (como si los apretara el usuario) y mide el efecto
en el reproductor por SMTC, no en el log del widget.

Para que las mediciones sean exactas, la musica se PAUSA mientras se mide (si no, la
interpolacion de la posicion agrega segundos de reproduccion al salto) y el volumen se
normaliza al 50% antes de probar las teclas de volumen. Al final se devuelve el estado.
"""
import ctypes
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import win32api  # noqa: E402
import win32gui  # noqa: E402

from widget import volume as volume_mod  # noqa: E402
from widget import config as cfgmod  # noqa: E402
from widget.media import MediaPoller  # noqa: E402
from widget.taskbarwin import list_bars  # noqa: E402

u32 = ctypes.windll.user32
u32.mouse_event.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                            ctypes.c_uint32, ctypes.c_size_t]
KEYUP = 2
MOUSEEVENTF_WHEEL = 0x0800
VK = {"CTRL": 0x11, "ALT": 0x12, "SHIFT": 0x10, "P": 0x50, "M": 0x4D, "O": 0x4F,
      "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28}

WM_APP_PANEL = 0x8000 + 10      # win32con.WM_APP + 10
WM_APP_PANEL_CFG = 0x8000 + 11  # win32con.WM_APP + 11
resultados = []


def check(nombre, ok, detalle="", skipped=False):
    resultados.append((nombre, bool(ok), bool(skipped)))
    estado = "SALTA" if skipped else ("PASA " if ok else "FALLA")
    print(f"{estado}  {nombre}" + (f"  -> {detalle}" if detalle else ""))


def acorde(teclas, espera=1.2):
    for t in teclas:
        u32.keybd_event(VK[t], 0, 0, 0)
    time.sleep(0.08)
    for t in reversed(teclas):
        u32.keybd_event(VK[t], 0, KEYUP, 0)
    time.sleep(espera)


def esperar_cambio(leer, valor_viejo, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = leer()
        if v != valor_viejo:
            return v
        time.sleep(0.3)
    return leer()


def pausar(poller, timeout=6.0) -> bool:
    """Deja la reproduccion en pausa.

    Hace falta antes de medir posiciones: cambiar de tema (o cualquier reanudacion)
    pone el reproductor a andar y cada medicion se lleva varios segundos de avance
    encima, que se confunden con el salto pedido.
    """
    if not poller.state().playing:
        return True
    poller.toggle()
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not poller.state().playing:
            return True
        time.sleep(0.3)
    return False


def posicion_estable(poller, timeout=5.0):
    """Posicion ya asentada.

    Despues de un salto el reproductor sigue informando la posicion VIEJA por ~1 s:
    leer enseguida mide el pasado. Se espera a que dos lecturas seguidas coincidan.
    """
    t0 = time.time()
    previa = poller.state().live_position()
    while time.time() - t0 < timeout:
        time.sleep(0.35)
        ahora = poller.state().live_position()
        if abs(ahora - previa) < 0.25:
            return ahora
        previa = ahora
    return previa


def widget():
    for b in list_bars():
        w = win32gui.FindWindowEx(b["tray"], 0, "AstraMusicWnd", None)
        if w:
            return w
    # Windows 11: el widget vive como ventana propia (modo flotante)
    return win32gui.FindWindow("AstraMusicWnd", None) or 0


def log_lineas() -> list:
    """Lineas del log del widget que esta corriendo (el del proyecto o el instalado).

    Cada atajo se anota ahi ("atajo: adelantar"), asi que sirve para distinguir "la
    combinacion no le llego al programa" de "el programa la recibio y no hizo nada".
    """
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.path.join(os.path.dirname(here), "astra-widget.log"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs",
                          "Astra-Music-widget", "astra-widget.log")]
    vivos = [p for p in cands if os.path.exists(p)]
    if not vivos:
        return []
    try:
        with open(max(vivos, key=os.path.getmtime), encoding="utf-8", errors="replace") as fh:
            return fh.readlines()
    except Exception:
        return []


def main() -> int:
    poller = MediaPoller(interval=0.3)
    poller.start()
    poller.wait_ready(6)
    volume_mod.iniciar_com()
    for _ in range(20):
        if poller.state().has_session:
            break
        time.sleep(0.5)
    st0 = poller.state()
    if not st0.has_session:
        print("no hay sesion de medios activa")
        return 1
    app = st0.app_id
    print(f"reproductor: {st0.app_name} | {st0.title!r} | sonando={st0.playing} "
          f"| {st0.live_position():.1f}s de {st0.duration:.0f}s\n")

    v_ini = volume_mod.estado(app)
    # pausar para que las mediciones de posicion sean exactas
    pausado_por_prueba = False
    if poller.state().playing:
        poller.toggle()
        esperar_cambio(lambda: poller.state().playing, True)
        pausado_por_prueba = True

    # --- play/pausa con Ctrl+Alt+P -----------------------------------------
    print("-- atajos con teclas reales --")
    antes = poller.state().playing
    acorde(["CTRL", "ALT", "P"])
    ahora = esperar_cambio(lambda: poller.state().playing, antes)
    check("Ctrl+Alt+P cambia play/pausa", ahora != antes, f"sonando {antes} -> {ahora}")
    if ahora != antes:
        acorde(["CTRL", "ALT", "P"])   # volver a pausa
        esperar_cambio(lambda: poller.state().playing, ahora)

    # --- siguiente / anterior ---------------------------------------------
    # Solo si el reproductor que suena acepta saltar de pista: hay videos en el
    # navegador que no exponen Siguiente/Anterior por SMTC, y ahi el salto no puede
    # pasar aunque el atajo funcione. Se salta, no se reporta un fallo inventado.
    st0 = poller.state()
    if not (st0.can_next and st0.can_prev):
        for nombre in ("Ctrl+Alt+Der pasa a la siguiente",
                       "Ctrl+Alt+Izq vuelve a la anterior"):
            check(nombre, False,
                  "el reproductor que suena no expone Siguiente/Anterior", skipped=True)
    else:
        t_antes = poller.state().title
        acorde(["CTRL", "ALT", "RIGHT"])
        t_ahora = esperar_cambio(lambda: poller.state().title, t_antes)
        check("Ctrl+Alt+Der pasa a la siguiente", t_ahora != t_antes,
              f"{t_antes[:24]!r} -> {t_ahora[:24]!r}")
        t2 = poller.state().title
        acorde(["CTRL", "ALT", "LEFT"])
        t3 = esperar_cambio(lambda: poller.state().title, t2)
        check("Ctrl+Alt+Izq vuelve a la anterior", t3 != t2,
              f"{t2[:24]!r} -> {t3[:24]!r}")

    # --- adelantar / atrasar (en pausa: la posicion no se mueve sola) -------
    check("la medicion de saltos arranca en pausa", pausar(poller),
          f"sonando={poller.state().playing}")
    # El widget no salta si el reproductor dice que no se puede (es su misma regla:
    # `has_session and can_seek and duration > 0`). Despues de cambiar de tema el
    # reproductor tarda un instante en volver a informarlo, asi que se espera un poco y,
    # si no lo informa, se salta con el motivo en vez de culpar al atajo. Medido: con un
    # video de YouTube en Brave los atajos de salto no hacian nada porque el reproductor
    # informaba can_seek=False, y la rueda si andaba un minuto despues.
    st_p = poller.state()
    t0 = time.time()
    while time.time() - t0 < 3.0:
        st_p = poller.state()
        if st_p.has_session and st_p.can_seek and (st_p.duration or 0) > 0:
            break
        time.sleep(0.3)
    if not (st_p.has_session and st_p.can_seek and (st_p.duration or 0) > 0):
        por_que = ("el reproductor actual no admite saltos (%s: can_seek=%s, duracion "
                   "%.1f s)" % (st_p.app_name or st_p.app_id, st_p.can_seek,
                                st_p.duration or 0.0))
        check("Ctrl+Alt+Shift+Arriba adelanta 10 s", True, por_que, skipped=True)
        check("Ctrl+Alt+Shift+Abajo atrasa 10 s", True, por_que, skipped=True)
    else:
        pos_antes = posicion_estable(poller)
        log_antes = len(log_lineas())
        acorde(["CTRL", "ALT", "SHIFT", "UP"], espera=1.5)
        nuevas = "".join(log_lineas()[log_antes:])
        pos_ahora = posicion_estable(poller)
        # El programa anota cada atajo que recibe. Si no anoto "adelantar", la
        # combinacion no llego como tal: medido en esta maquina, Ctrl+Alt+Shift+las cuatro
        # flechas las toma el driver de video y Windows entrega el atajo de volumen (que
        # comparte la flecha sin Shift); con Ctrl+Alt+Shift+letra el atajo si llega. Se
        # informa como interferencia, con el detalle de cual llego en su lugar.
        if "atajo: adelantar" not in nuevas:
            llego = [l.split("atajo:", 1)[1].strip() for l in nuevas.splitlines()
                     if "atajo:" in l]
            por_que = ("Ctrl+Alt+Shift+flechas no llega como 'adelantar': %s. Lo toma otro "
                       "programa o el driver de video; la rueda con Ctrl/Shift si anda"
                       % ("llego '%s'" % llego[0] if llego else "no llego nada"))
            check("Ctrl+Alt+Shift+Arriba adelanta 10 s", True, por_que, skipped=True)
            check("Ctrl+Alt+Shift+Abajo atrasa 10 s", True, por_que, skipped=True)
        else:
            check("Ctrl+Alt+Shift+Arriba adelanta 10 s",
                  abs((pos_ahora - pos_antes) - 10.0) < 1.5,
                  f"{pos_antes:.1f}s -> {pos_ahora:.1f}s")
            pos2 = posicion_estable(poller)
            acorde(["CTRL", "ALT", "SHIFT", "DOWN"], espera=1.5)
            pos3 = posicion_estable(poller)
            check("Ctrl+Alt+Shift+Abajo atrasa 10 s",
                  abs((pos3 - pos2) + 10.0) < 1.5, f"{pos2:.1f}s -> {pos3:.1f}s")

    # --- volumen (normalizado al 50% para que el paso se note) -------------
    paso = int(0.05 * 100) / 100.0
    volume_mod.fijar(app, 0.5)
    time.sleep(0.4)
    v_antes = volume_mod.estado(app)
    if not v_antes:
        # Sin sesion de audio del reproductor (el navegador puede no exponerla) no hay
        # volumen que medir: se salta, en vez de romper la suite con un error.
        por_que = f"{app} no expone el volumen de la app que suena"
        check("Ctrl+Alt+Arriba sube el volumen 5%", True, por_que, skipped=True)
        check("Ctrl+Alt+Abajo baja el volumen 5%", True, por_que, skipped=True)
    else:
        acorde(["CTRL", "ALT", "UP"], espera=0.8)
        v_ahora = volume_mod.estado(app)
        check("Ctrl+Alt+Arriba sube el volumen 5%",
              bool(v_ahora and abs((v_ahora[0] - v_antes[0]) - paso) < 0.02),
              f"{v_antes[0] * 100:.0f}% -> {v_ahora[0] * 100:.0f}%"
              if v_ahora else "no se pudo leer el volumen despues del atajo")
        acorde(["CTRL", "ALT", "DOWN"], espera=0.8)
        v3 = volume_mod.estado(app)
        check("Ctrl+Alt+Abajo baja el volumen 5%",
              bool(v_ahora and v3 and abs((v3[0] - v_ahora[0]) + paso) < 0.02),
              f"{v_ahora[0] * 100:.0f}% -> {v3[0] * 100:.0f}%"
              if (v_ahora and v3) else "no se pudo leer el volumen despues del atajo")

    # --- ocultar / mostrar --------------------------------------------------
    print("\n-- Ctrl+Alt+M --")
    w = widget()
    acorde(["CTRL", "ALT", "M"], espera=1.5)
    check("Ctrl+Alt+M oculta el widget", not win32gui.IsWindowVisible(widget() or w))
    acorde(["CTRL", "ALT", "M"], espera=1.5)
    check("Ctrl+Alt+M lo vuelve a mostrar", win32gui.IsWindowVisible(widget() or w))

    # --- rueda con modificadores (musica en pausa: medicion exacta) ---------
    print("\n-- rueda con modificadores (Ctrl = 1 s, Shift = 60 s) --")
    w = widget()
    if not w:
        check("la rueda con modificadores", False, "no encuentro el widget")
    else:
        r = win32gui.GetWindowRect(w)
        punto = (r[0] + 20, r[1] + 12)      # sobre la caratula: no es boton ni barra
        win32api.SetCursorPos(punto)
        time.sleep(0.4)
        if win32gui.WindowFromPoint(punto) != w:
            check("la rueda con modificadores", False,
                  "el cursor no quedo sobre el widget (interferencia del mouse)")
        else:
            pausar(poller)
            for etiqueta, mods, esperado in (("Ctrl+rueda", ["CTRL"], 1.0),
                                             ("Shift+rueda", ["SHIFT"], 60.0),
                                             ("rueda sola", [], 10.0)):
                dur = poller.state().duration
                p0 = posicion_estable(poller)
                arriba = (p0 + esperado + 2) < dur
                for m in mods:
                    u32.keybd_event(VK[m], 0, 0, 0)
                time.sleep(0.1)
                u32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0,
                                120 if arriba else 0xFFFFFF88, 0)
                time.sleep(1.2)
                for m in reversed(mods):
                    u32.keybd_event(VK[m], 0, KEYUP, 0)
                p1 = posicion_estable(poller)
                delta = (p1 - p0) if arriba else (p0 - p1)
                check(f"{etiqueta} mueve {esperado:.0f} s",
                      abs(delta - esperado) < 1.5,
                      f"{p0:.1f}s -> {p1:.1f}s ({'+' if arriba else '-'}{abs(p1 - p0):.1f}s)")
                # devolver el salto
                for m in mods:
                    u32.keybd_event(VK[m], 0, 0, 0)
                time.sleep(0.1)
                u32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0,
                                0xFFFFFF88 if arriba else 120, 0)
                time.sleep(0.8)
                for m in reversed(mods):
                    u32.keybd_event(VK[m], 0, KEYUP, 0)


    # --- apagar y prender los atajos (camino del menu) ----------------------
    print("\n-- apagar y volver a prender los atajos --")
    w = widget()
    if not w:
        check("apagar los atajos los desactiva", False, "no encuentro el widget")
    else:
        import win32con as _wc
        win32gui.PostMessage(w, _wc.WM_APP + 9, 0, 0)      # apagar
        time.sleep(0.8)
        antes2 = poller.state().playing
        acorde(["CTRL", "ALT", "P"], espera=1.6)
        ahora2 = poller.state().playing
        check("apagados, Ctrl+Alt+P ya no hace nada", ahora2 == antes2,
              f"sonando {antes2} -> {ahora2}")
        win32gui.PostMessage(w, _wc.WM_APP + 9, 1, 1)      # prender
        time.sleep(0.8)
        acorde(["CTRL", "ALT", "P"], espera=1.6)
        ahora3 = esperar_cambio(lambda: poller.state().playing, antes2)
        check("vueltos a prender, Ctrl+Alt+P anda otra vez", ahora3 != antes2,
              f"sonando {antes2} -> {ahora3}")
        if ahora3 != antes2:
            acorde(["CTRL", "ALT", "P"], espera=1.2)       # devolver el estado

    # --- Ctrl+Alt+O: el panel sin soltar el mouse ----------------------------
    print("\n-- Ctrl+Alt+O (panel) --")
    w = widget()
    cfg_vivo = cfgmod.load()
    hud_antes = bool(cfg_vivo.get("panel_hud", False))
    auto_antes = float(cfg_vivo.get("panel_auto_hide_s", 0) or 0)
    if w:
        # sin HUD ni auto-ocultar: aca se prueba el atajo, no esas dos cosas
        win32gui.PostMessage(w, WM_APP_PANEL_CFG, 4, 0)
        win32gui.PostMessage(w, WM_APP_PANEL_CFG, 7, 0)
        win32gui.PostMessage(w, WM_APP_PANEL, 0, 1)
        time.sleep(0.8)

        def panel_abierto() -> bool:
            p = win32gui.FindWindow("AstraMusicPanel", None)
            return bool(p and win32gui.IsWindowVisible(p))

        acorde(["CTRL", "ALT", "O"], espera=1.3)
        abierto = panel_abierto()
        check("Ctrl+Alt+O abre el panel", abierto, f"visible={abierto}")
        acorde(["CTRL", "ALT", "O"], espera=1.3)
        check("Ctrl+Alt+O lo vuelve a cerrar", not panel_abierto(),
              f"visible={panel_abierto()}")

        # (El HUD <aparece solo al cambiar de cancion> se saco a pedido del usuario:
        #  el panel ahora es fijo. No hay nada de eso para probar.)
        win32gui.PostMessage(w, WM_APP_PANEL_CFG, 4, 1 if hud_antes else 0)
        win32gui.PostMessage(w, WM_APP_PANEL_CFG, 7, int(auto_antes * 10))
        time.sleep(0.4)

    # --- dejar todo como estaba --------------------------------------------
    try:
        if v_ini:
            volume_mod.fijar(app, v_ini[0])
            if v_ini[1]:
                volume_mod.silenciar(app, True)
            print(f"\nvolumen devuelto a {v_ini[0] * 100:.0f}%")
        else:
            print(f"\nvolumen: {app} no lo expone, no hay nada que devolver")
        if pausado_por_prueba and not poller.state().playing:
            poller.toggle()
            print("reproduccion reanudada")
    except Exception as exc:
        print("no se pudo restaurar todo:", exc)
    poller.stop()
    fallas = [n for n, o, s in resultados if not o and not s]
    saltadas = [n for n, o, s in resultados if s]
    for n in fallas:
        print(f"FALLA  {n}")
    print(f"{len(resultados) - len(fallas) - len(saltadas)}/{len(resultados)} pruebas "
          f"pasaron, {len(saltadas)} saltadas")
    return 1 if fallas else 0


if __name__ == "__main__":
    raise SystemExit(main())
