"""Ajustes de verificacion: config del .exe, rueda sin cursor encima, juego que tapa."""
import io


def rep(P, a, b, n=1):
    s = io.open(P, encoding="utf-8", newline="").read().replace("\r\n", "\n")
    assert s.count(a) == n, (P, a[:70], s.count(a))
    io.open(P, "w", encoding="utf-8", newline="").write(s.replace(a, b))
    print("ok:", P)


# 1) la rueda: se manda el mensaje con el cursor APARCADO lejos. Asi una muesca real del
#    usuario (que va a la ventana bajo el cursor) no se suma a la de la prueba.
rep("tools/clicktest.py",
    '''        place_cursor(*centro)          # se deja el cursor encima igual, por realismo
        # Pausar: con la musica andando la posicion informada no es confiable (al''',
    '''        # El cursor se aparca LEJOS antes de mandar la rueda: el mensaje lleva su propia
        # posicion, asi que no hace falta tenerlo encima, y si el usuario mueve la rueda
        # de verdad mientras corre la prueba, sus muescas van a otra ventana.
        park_away(wrect)
        time.sleep(0.3)
        # Pausar: con la musica andando la posicion informada no es confiable (al''')

# 2) el selftest: si una ventana AJENA tapa toda la barra (un juego en primer plano), la
#    comprobacion de cobertura salta en vez de ponerse roja
rep("tools/selftest.py",
    '''                    tr = win32gui.GetWindowRect(win32gui.WindowFromPoint(
                        wt.POINT(int(centro[0]), int(centro[1]))))
                    mr = win32gui.GetMonitorInfo(win32api.MonitorFromRect(tr))["Monitor"]
                    juego = (tr[0] <= mr[0] and tr[1] <= mr[1]
                             and tr[2] >= mr[2] and tr[3] >= mr[3])''',
    '''                    tapadora_h = win32gui.WindowFromPoint(
                        wt.POINT(int(centro[0]), int(centro[1])))
                    tr = win32gui.GetWindowRect(tapadora_h)
                    clase = win32gui.GetClassName(tapadora_h)
                    # Barra de arriba en pantalla completa, o cualquier ventana AJENA
                    # (un juego en primer plano) que tape toda la barra: en los dos
                    # casos el widget no puede verse y no hay nada que comprobar.
                    ajena = clase not in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                                          "WorkerW", "Progman", "GorusTaskbarMusicWnd")
                    br = destino["rect"]
                    juego = ajena and tr[0] <= br[0] and tr[1] <= br[1] \\
                        and tr[2] >= br[2] and tr[3] >= br[3]''')
