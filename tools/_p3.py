"""clicktest: rueda y teclado en el panel, iman a los bordes, doble clic, tira fina."""
import io

P = "tools/clicktest.py"
s = io.open(P, encoding="utf-8", newline="").read().replace("\r\n", "\n")

a = "            # (d) cerrar con la cruz"
b = '''            # (c4) la rueda sobre el panel: en el altavoz mueve el volumen, en el
            # resto adelanta/atrasa. Misma logica que en el widget (Ctrl = fino).
            try:
                zvol = zp["volumen"]
                pto_v = (pr[0] + (zvol[0] + zvol[2]) // 2, pr[1] + (zvol[1] + zvol[3]) // 2)
                vol_ini = None
                try:
                    from widget import volume as volume_mod
                    volume_mod.iniciar_com()
                    vol_ini = volume_mod.estado(poller.state().app_id or "")
                except Exception:
                    volume_mod = None
                if not (volume_mod and vol_ini):
                    check("la rueda sobre el altavoz del panel mueve el volumen", False,
                          "no hay sesion de audio", skipped=True)
                elif place_cursor(*pto_v) and win32gui.WindowFromPoint(pto_v) == hp:
                    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_UP, 0)
                    time.sleep(0.5)
                    ahora_v = volume_mod.estado(poller.state().app_id or "")
                    check("la rueda sobre el altavoz del panel mueve el volumen",
                          abs(ahora_v[0] - vol_ini[0]) > 0.01
                          and abs((ahora_v[0] - vol_ini[0]) * 100 - 5) < 2.5,
                          f"{vol_ini[0] * 100:.0f}% -> {ahora_v[0] * 100:.0f}%")
                    volume_mod.fijar(poller.state().app_id or "", vol_ini[0])
                else:
                    check("la rueda sobre el altavoz del panel mueve el volumen", False,
                          "el cursor no quedo sobre el panel (interferencia)", skipped=True)

                # la rueda sobre el texto busca (sobre la zona de la barra tambien)
                zt = zp["texto"]
                pto_t = (pr[0] + (zt[0] + zt[2]) // 2, pr[1] + (zt[1] + zt[3]) // 2)
                antes_pos = sample(poller).live_position()
                if place_cursor(*pto_t) and win32gui.WindowFromPoint(pto_t) == hp:
                    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_UP, 0)
                    time.sleep(0.6)
                    ahora_pos = sample(poller).live_position()
                    check("la rueda sobre el panel busca la cancion",
                          abs((ahora_pos - antes_pos) - 10) < 7,
                          f"{antes_pos:.0f}s -> {ahora_pos:.0f}s (se esperaba +10)")
                else:
                    check("la rueda sobre el panel busca la cancion", False,
                          "el cursor no quedo sobre el panel (interferencia)", skipped=True)
            except Exception as exc:
                check("la rueda sobre el panel busca la cancion", False, repr(exc))

            # (c5) teclado con el panel enfocado (modo escritorio): espacio play/pausa.
            #      En modo gaming el panel no toma el foco a proposito, asi que primero
            #      se apaga "no robar el foco" y despues se restaura.
            try:
                win32gui.PostMessage(w, win32con.WM_APP + 11, 1, 0)
                time.sleep(0.8)
                zt = zp["texto"]
                pto_t = (pr[0] + (zt[0] + zt[2]) // 2, pr[1] + 20)
                sono_antes = bool(poller.state().playing)
                if click_en(hp, *pto_t) and win32gui.GetForegroundWindow() == hp:
                    user32.keybd_event(0x20, 0, 0, 0)          # VK_SPACE
                    time.sleep(0.1)
                    user32.keybd_event(0x20, 0, 2, 0)          # keyup
                    time.sleep(0.9)
                    sono_ahora = bool(poller.state().playing)
                    check("espacio con el panel enfocado cambia play/pausa",
                          sono_ahora != sono_antes,
                          f"sonando {sono_antes} -> {sono_ahora}")
                    user32.keybd_event(0x20, 0, 0, 0)
                    time.sleep(0.1)
                    user32.keybd_event(0x20, 0, 2, 0)
                    time.sleep(0.6)
                else:
                    check("espacio con el panel enfocado cambia play/pausa", False,
                          "el panel no tomo el foco (interferencia)", skipped=True)
            except Exception as exc:
                check("espacio con el panel enfocado cambia play/pausa", False, repr(exc))
            finally:
                try:
                    win32gui.PostMessage(w, win32con.WM_APP + 11, 1, 1 if foco_panel else 0)
                    time.sleep(0.4)
                except Exception:
                    pass

            # (c6) doble clic en la caratula: trae al frente la ventana de lo que suena
            try:
                from widget import ventanas as ventanas_mod
                h_rep = ventanas_mod.ventana_del_reproductor(poller.state().app_id)
                zc2 = zp["tapa"]
                pto_c = (pr[0] + (zc2[0] + zc2[2]) // 2, pr[1] + (zc2[1] + zc2[3]) // 2)
                frente_antes = win32gui.GetForegroundWindow()
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
                    time.sleep(0.9)
                    frente = win32gui.GetForegroundWindow()
                    check("el doble clic en la caratula trae el reproductor al frente",
                          frente == h_rep,
                          f"al frente quedo {hex(frente)} ({win32gui.GetWindowText(frente)[:24]!r}), "
                          f"se esperaba {hex(h_rep)} de {poller.state().app_id}")
                    try:
                        if frente_antes and win32gui.IsWindow(frente_antes):
                            win32gui.SetForegroundWindow(frente_antes)
                    except Exception:
                        pass
            except Exception as exc:
                check("el doble clic en la caratula trae el reproductor al frente", False,
                      repr(exc))

            # (c7) el iman: soltandolo a 10 px de la esquina, queda en la esquina exacta
            try:
                mon = win32api.MonitorFromRect(pr)
                mx0, my0, _, _ = win32api.GetMonitorInfo(mon)["Monitor"]
                pr_a = win32gui.GetWindowRect(hp)
                ag = (pr_a[0] + 140, pr_a[1] + 8)
                dx, dy = (mx0 + 10) - ag[0], (my0 + 10) - ag[1]
                if not place_cursor(*ag):
                    check("soltandolo cerca del borde queda pegado al borde", False,
                          "el cursor no quedo donde se lo puso (interferencia)",
                          skipped=True)
                else:
                    user32.mouse_event(0x0002, 0, 0, 0, 0)
                    time.sleep(0.2)
                    for i in (1, 2, 3, 4):
                        place_cursor(ag[0] + dx * i // 4, ag[1] + dy * i // 4)
                        time.sleep(0.12)
                    user32.mouse_event(0x0004, 0, 0, 0, 0)
                    time.sleep(0.6)
                    pr_b = win32gui.GetWindowRect(hp)
                    check("soltandolo cerca del borde queda pegado al borde",
                          abs(pr_b[0] - mx0) <= 1 and abs(pr_b[1] - my0) <= 1,
                          f"quedo en {(pr_b[0], pr_b[1])}, se esperaba la esquina "
                          f"({mx0}, {my0})")
                    # devolverlo a su lugar (dos arrastres reales: el iman no molesta
                    # lejos de los bordes)
                    pr_c = win32gui.GetWindowRect(hp)
                    ag2 = (pr_c[0] + 140, pr_c[1] + 8)
                    if place_cursor(*ag2):
                        user32.mouse_event(0x0002, 0, 0, 0, 0)
                        time.sleep(0.2)
                        for i in (1, 2, 3, 4):
                            place_cursor(ag2[0] + (pr_a[0] - ag2[0]) * i // 4,
                                         ag2[1] + (pr_a[1] - ag2[1]) * i // 4)
                            time.sleep(0.12)
                        user32.mouse_event(0x0004, 0, 0, 0, 0)
                        time.sleep(0.6)
                    pr_d = win32gui.GetWindowRect(hp)
                    check("el panel vuelve a su lugar despues del iman",
                          abs(pr_d[0] - pr_a[0]) <= 2 and abs(pr_d[1] - pr_a[1]) <= 2,
                          f"quedo en {(pr_d[0], pr_d[1])}, estaba en {(pr_a[0], pr_a[1])}")
            except Exception as exc:
                check("soltandolo cerca del borde queda pegado al borde", False, repr(exc))

            # (c8) tercer tamano: tira fina (320x34 a k=1) y sigue siendo usable
            try:
                win32gui.PostMessage(w, win32con.WM_APP + 11, 5, 2)     # tira
                time.sleep(1.0)
                k_t = 1.0
                w_t, h_t = panel_mod.size(k_t, cfgmod.load())
                hp_t = win32gui.FindWindow(PANEL_CLASS if "PANEL_CLASS" in dir() else
                                           "GorusTaskbarMusicPanel", None)
                rr = win32gui.GetWindowRect(hp_t) if hp_t else (0, 0, 0, 0)
                check("el tamano tira fina achica el panel a una fila",
                      hp_t and win32gui.IsWindowVisible(hp_t)
                      and abs((rr[2] - rr[0]) - w_t) <= 2,
                      f"ventana {rr[2] - rr[0]}x{rr[3] - rr[1]}, esperado {w_t}x{h_t}")
                if hp_t and win32gui.IsWindowVisible(hp_t):
                    zt = panel_mod.rects(k_t, cfgmod.load())
                    pto_x = (rr[0] + (zt["cerrar"][0] + zt["cerrar"][2]) // 2,
                             rr[1] + (zt["cerrar"][1] + zt["cerrar"][3]) // 2)
                    if click_en(hp_t, *pto_x):
                        time.sleep(0.8)
                        check("la cruz de la tira fina lo cierra",
                              not win32gui.IsWindowVisible(hp_t),
                              f"visible={win32gui.IsWindowVisible(hp_t)}")
                win32gui.PostMessage(w, win32con.WM_APP + 11, 5, tam_panel)
                time.sleep(0.8)
                hp = win32gui.FindWindow("GorusTaskbarMusicPanel", None)
                win32gui.PostMessage(w, win32con.WM_APP + 10, 1, 1)     # reabrir
                time.sleep(1.0)
                hp = win32gui.FindWindow("GorusTaskbarMusicPanel", None)
                pr = win32gui.GetWindowRect(hp)
            except Exception as exc:
                check("el tamano tira fina achica el panel a una fila", False, repr(exc))

            # (d) cerrar con la cruz'''

assert s.count(a) == 1
s = s.replace(a, b)

# el tamano original se guarda antes de la seccion del panel (para restaurarlo)
c = '''    cfg_panel = cfgmod.load()'''
d = '''    cfg_panel = cfgmod.load()
    # tamano del panel al arrancar la prueba (0 normal / 1 chico / 2 tira)
    tam_panel = {"normal": 0, "chico": 1, "tira": 2}[
        panel_mod.normalizar(cfg_panel.get("panel_size", "normal"))]'''
assert s.count(c) == 1
s = s.replace(c, d)

# import de win32api (lo usa el iman)
e = "import win32con  # noqa: E402"
f = "import win32api  # noqa: E402\nimport win32con  # noqa: E402"
assert s.count(e) == 1
s = s.replace(e, f)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("clicktest: rueda/teclado/iman/doble clic/tira agregados")
