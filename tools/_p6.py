"""Arreglos de las pruebas nuevas del panel (bugs mios, no del producto)."""
import io

P = "tools/clicktest.py"
s = io.open(P, encoding="utf-8", newline="").read().replace("\r\n", "\n")


def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (a[:70], s.count(a))
    s = s.replace(a, b)


# 1) el volumen: si esta al 100% no hay lugar para subir -> arrancar en 50%
rep('''                if not (volume_mod and vol_ini):
                    check("la rueda sobre el altavoz del panel mueve el volumen", False,
                          "no hay sesion de audio", skipped=True)
                elif True:''',
    '''                if not (volume_mod and vol_ini):
                    check("la rueda sobre el altavoz del panel mueve el volumen", False,
                          "no hay sesion de audio", skipped=True)
                else:
                    # Al 100% no hay lugar para subir: se arranca en 50% y se restaura
                    volume_mod.fijar(poller.state().app_id or "", 0.5)
                    time.sleep(0.4)
                    base_v = volume_mod.estado(poller.state().app_id or "")[0]''')

rep('''                    win32gui.SendMessage(hp, win32con.WM_MOUSEWHEEL,
                                         WHEEL_UP << 16, lp(*pto_v))
                    time.sleep(0.5)
                    ahora_v = volume_mod.estado(poller.state().app_id or "")
                    check("la rueda sobre el altavoz del panel mueve el volumen",
                          abs(ahora_v[0] - vol_ini[0]) > 0.01
                          and abs((ahora_v[0] - vol_ini[0]) * 100 - 5) < 2.5,
                          f"{vol_ini[0] * 100:.0f}% -> {ahora_v[0] * 100:.0f}%")
                    volume_mod.fijar(poller.state().app_id or "", vol_ini[0])
                else:
                    check("la rueda sobre el altavoz del panel mueve el volumen", False,
                          "el cursor no quedo sobre el panel (interferencia)", skipped=True)''',
    '''                    win32gui.SendMessage(hp, win32con.WM_MOUSEWHEEL,
                                         WHEEL_UP << 16, lp(*pto_v))
                    time.sleep(0.5)
                    ahora_v = volume_mod.estado(poller.state().app_id or "")
                    check("la rueda sobre el altavoz del panel mueve el volumen",
                          abs((ahora_v[0] - base_v) * 100 - 5) < 2.5,
                          f"{base_v * 100:.0f}% -> {ahora_v[0] * 100:.0f}% (paso 5%)")
                    volume_mod.fijar(poller.state().app_id or "", vol_ini[0])
                    if vol_ini[1]:
                        volume_mod.silenciar(poller.state().app_id or "", True)''')

# 2) el arrastre del panel: elegir un destino lejos de los bordes (el iman pega a 22 px
#    y el cursor no puede salirse de la pantalla: medido, el panel quedaba a 26 px en
#    vez de los 150 pedidos)
rep('''                pr0 = win32gui.GetWindowRect(hp)
                agarre = (pr0[0] + (pr0[2] - pr0[0]) // 2, pr0[1] + 8)
                dx, dy = 150, -90''',
    '''                pr0 = win32gui.GetWindowRect(hp)
                agarre = (pr0[0] + (pr0[2] - pr0[0]) // 2, pr0[1] + 8)
                mon = win32api.MonitorFromRect(pr0)
                mx0, my0, mx1, my1 = win32api.GetMonitorInfo(mon)["Monitor"]
                ancho, alto = pr0[2] - pr0[0], pr0[3] - pr0[1]
                dx = 150 if pr0[0] + 150 + ancho + 60 <= mx1 else -150
                dy = -90 if pr0[1] - 90 >= my0 + 60 else 90''')

# 3) la vuelta al lugar original: el delta es (destino - posicion actual), sin sumar el
#    punto de agarre (medido: quedaba 140 px corrido)
rep('''                        for i in (1, 2, 3, 4):
                            place_cursor(ag2[0] + (pr_a[0] - ag2[0]) * i // 4,
                                         ag2[1] + (pr_a[1] - ag2[1]) * i // 4)
                            time.sleep(0.12)''',
    '''                        for i in (1, 2, 3, 4):
                            place_cursor(pr_c[0] + (pr_a[0] - pr_c[0]) * i // 4,
                                         pr_c[1] + (pr_a[1] - pr_c[1]) * i // 4)
                            time.sleep(0.12)''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("clicktest: 3 arreglos de las pruebas del panel")
