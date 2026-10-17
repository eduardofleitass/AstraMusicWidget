"""selftest: el iman del panel (matematica pura) + pruebas nuevas sin cursor."""
import io


def rep(P, a, b, n=1):
    s = io.open(P, encoding="utf-8", newline="").read().replace("\r\n", "\n")
    assert s.count(a) == n, (P, a[:60], s.count(a))
    io.open(P, "w", encoding="utf-8", newline="").write(s.replace(a, b))
    print("ok:", P)


# --- selftest: el iman ---------------------------------------------------------
rep("tools/selftest.py",
    "        # (d) fracciones y prueba de impacto",
    '''        # (c3) el iman del panel: la matematica sola, sin ventana ni mouse. Un panel
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

        # (d) fracciones y prueba de impacto''')

# --- clicktest: rueda, teclado y doble clic por MENSAJE ------------------------
rep("tools/clicktest.py",
    '''                elif place_cursor(*pto_v) and win32gui.WindowFromPoint(pto_v) == hp:
                    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_UP, 0)
                    time.sleep(0.5)''',
    '''                elif True:
                    # La rueda se manda como MENSAJE con la posicion en su lParam (que
                    # es la fuente documentada): asi la prueba mide la logica del panel
                    # sin depender de donde quede el cursor.
                    win32gui.SendMessage(hp, win32con.WM_MOUSEWHEEL,
                                         WHEEL_UP << 16, lp(*pto_v))
                    time.sleep(0.5)''')

rep("tools/clicktest.py",
    '''                antes_pos = sample(poller).live_position()
                if place_cursor(*pto_t) and win32gui.WindowFromPoint(pto_t) == hp:
                    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_UP, 0)
                    time.sleep(0.6)''',
    '''                antes_pos = sample(poller).live_position()
                if True:
                    win32gui.SendMessage(hp, win32con.WM_MOUSEWHEEL, WHEEL_UP << 16,
                                         lp(*pto_t))
                    time.sleep(0.6)''')

rep("tools/clicktest.py",
    '''                zt = zp["texto"]
                pto_t = (pr[0] + (zt[0] + zt[2]) // 2, pr[1] + 20)
                sono_antes = bool(poller.state().playing)
                if click_en(hp, *pto_t) and win32gui.GetForegroundWindow() == hp:
                    user32.keybd_event(0x20, 0, 0, 0)          # VK_SPACE
                    time.sleep(0.1)
                    user32.keybd_event(0x20, 0, 2, 0)          # keyup
                    time.sleep(0.9)''',
    '''                sono_antes = bool(poller.state().playing)
                if True:
                    # Tecla por mensaje: lo que se prueba es el manejador del panel (que
                    # el foco y el teclado lleguen es de Windows, y en modo gaming el
                    # panel no toma el foco a proposito).
                    win32gui.SendMessage(hp, win32con.WM_KEYDOWN, 0x20, 0)
                    time.sleep(0.15)
                    win32gui.SendMessage(hp, win32con.WM_KEYUP, 0x20, 0)
                    time.sleep(0.9)''')

rep("tools/clicktest.py",
    '''                    sono_ahora = bool(poller.state().playing)
                    check("espacio con el panel enfocado cambia play/pausa",
                          sono_ahora != sono_antes,
                          f"sonando {sono_antes} -> {sono_ahora}")
                    user32.keybd_event(0x20, 0, 0, 0)
                    time.sleep(0.1)
                    user32.keybd_event(0x20, 0, 2, 0)
                    time.sleep(0.6)
                else:
                    check("espacio con el panel enfocado cambia play/pausa", False,
                          "el panel no tomo el foco (interferencia)", skipped=True)''',
    '''                    sono_ahora = bool(poller.state().playing)
                    check("espacio con el panel cambia play/pausa",
                          sono_ahora != sono_antes,
                          f"sonando {sono_antes} -> {sono_ahora}")
                    win32gui.SendMessage(hp, win32con.WM_KEYDOWN, 0x20, 0)
                    time.sleep(0.15)
                    win32gui.SendMessage(hp, win32con.WM_KEYUP, 0x20, 0)
                    time.sleep(0.6)
                    # las flechas buscan (paso normal, Ctrl fino, Shift grueso)
                    pos0 = sample(poller).live_position()
                    win32gui.SendMessage(hp, win32con.WM_KEYDOWN, win32con.VK_RIGHT, 0)
                    time.sleep(0.7)
                    pos1 = sample(poller).live_position()
                    check("la flecha derecha con el panel adelanta la cancion",
                          abs((pos1 - pos0) - 10) < 7,
                          f"{pos0:.0f}s -> {pos1:.0f}s (se esperaba +10)")
                else:
                    check("espacio con el panel cambia play/pausa", False, "no aplica",
                          skipped=True)''')

rep("tools/clicktest.py",
    '''                frente_antes = win32gui.GetForegroundWindow()
                if not h_rep:
                    check("el doble clic en la caratula trae el reproductor al frente",
                          False, "no encontre su ventana", skipped=True)
                elif not (place_cursor(*pto_c) and win32gui.WindowFromPoint(pto_c) == hp):
                    check("el doble clic en la caratula trae el reproductor al frente",
                          False, "el cursor no quedo sobre el panel (interferencia)",
                          skipped=True)
                else:
                    for _ in range(2):
                        user32.mouse_event(0x0002, 0, 0, 0, 0)
                        user32.mouse_event(0x0004, 0, 0, 0, 0)
                        time.sleep(0.12)
                    time.sleep(0.9)''',
    '''                frente_antes = win32gui.GetForegroundWindow()
                if not h_rep:
                    check("el doble clic en la caratula trae el reproductor al frente",
                          False, "no encontre su ventana", skipped=True)
                else:
                    # Doble clic por mensaje (WM_LBUTTONDBLCLK con la posicion): la clase
                    # del panel tiene CS_DBLCLKS, asi que este es el mismo mensaje que
                    # manda el sistema.
                    win32gui.SendMessage(hp, 0x0203, 0, lp(*pto_c))
                    time.sleep(0.9)''')

rep("tools/clicktest.py",
    '''                    if click_en(hp_t, *pto_x):
                        time.sleep(0.8)
                        check("la cruz de la tira fina lo cierra",
                              not win32gui.IsWindowVisible(hp_t),
                              f"visible={win32gui.IsWindowVisible(hp_t)}")''',
    '''                    if click_en(hp_t, *pto_x):
                        time.sleep(0.8)
                        check("la cruz de la tira fina lo cierra",
                              not win32gui.IsWindowVisible(hp_t),
                              f"visible={win32gui.IsWindowVisible(hp_t)}")
                    else:
                        check("la cruz de la tira fina lo cierra", False,
                              "el cursor no quedo sobre el panel (interferencia)",
                              skipped=True)''')

# helper lp(x, y) para los lParam de pantalla
rep("tools/clicktest.py",
    '''def click_en(hwnd, x, y) -> bool:''',
    '''def lp(x, y) -> int:
    """lParam con la posicion en PANTALLA (como lo manda Windows en la rueda)."""
    return (int(x) & 0xFFFF) | ((int(y) & 0xFFFF) << 16)


def click_en(hwnd, x, y) -> bool:''')
