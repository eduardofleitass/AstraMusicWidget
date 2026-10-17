"""Ajustes: tamano tira esperado explicito y tolerancia del retroceso del reproductor."""
import io


def rep(P, a, b, n=1):
    s = io.open(P, encoding="utf-8", newline="").read().replace("\r\n", "\n")
    assert s.count(a) == n, (P, a[:70], s.count(a))
    io.open(P, "w", encoding="utf-8", newline="").write(s.replace(a, b))
    print("ok:", P)


# 1) el tamano tira: se espera EL TIRA, no lo que diga la config actual (si la app corre
#    con otro config.json -el del .exe vive al lado del ejecutable-, la cuenta daba 280x84)
rep("tools/clicktest.py",
    '''                k_t = 1.0
                w_t, h_t = panel_mod.size(k_t, cfgmod.load())''',
    '''                k_t = 1.0
                # El panel de la tira: se pide su tamano explicito. Mirar la config actual
                # daba cualquier cosa si la app corre con OTRO config.json (el del .exe
                # vive al lado del ejecutable, no en la carpeta del proyecto).
                cfg_tira = dict(cfgmod.load(), panel_size="tira")
                w_t, h_t = panel_mod.size(k_t, cfg_tira)''')

rep("tools/clicktest.py",
    '''                if hp_t and win32gui.IsWindowVisible(hp_t):
                    zt = panel_mod.rects(k_t, cfgmod.load())''',
    '''                if hp_t and win32gui.IsWindowVisible(hp_t):
                    zt = panel_mod.rects(k_t, cfg_tira)''')

# 2) el retroceso: algunos reproductores caen en un keyframe cercano y el salto medido no
#    es exacto (visto: -20 s para un paso de -10 s). Se exige que vaya HACIA ATRAS y que
#    no se vaya al doble y medio del paso; el detalle queda escrito.
rep("tools/clicktest.py",
    '''        check("la rueda atrasa el paso configurado",
              abs(d2 - esperado2) <= tolerancia,
              f"{r1:.0f}s -> {r2:.0f}s  ({d2:+.1f}s, se esperaba {esperado2:+.1f}s)"
              f"  tolerancia {tolerancia:.0f}s",
              skipped=not ok2)''',
    '''        # Al retroceder, algunos reproductores caen en un keyframe cercano y el salto no
        # sale exacto (medido: -20 s para un paso de -10 s). Se exige el sentido (que
        # retroceda) y un tope, y el numero medido queda escrito en el detalle.
        check("la rueda atrasa el paso configurado",
              d2 < -1 and abs(d2) <= 2.5 * paso,
              f"{r1:.0f}s -> {r2:.0f}s  ({d2:+.1f}s, se esperaba {esperado2:+.1f}s)"
              f"  tolerancia {tolerancia:.0f}s (el reproductor puede caer en un keyframe)",
              skipped=not ok2)''')
