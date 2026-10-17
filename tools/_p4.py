"""Iman del panel: funcion pura en panel.py + el resto sin depender del cursor."""
import io


def rep(P, a, b, n=1):
    s = io.open(P, encoding="utf-8", newline="").read().replace("\r\n", "\n")
    assert s.count(a) == n, (P, a[:60], s.count(a))
    io.open(P, "w", encoding="utf-8", newline="").write(s.replace(a, b))
    print("ok:", P)


# 1) panel.py: la matematica del iman, aparte y verificable sin ventana
rep("widget/panel.py",
    '''def _frac(x: int, z: tuple) -> float:''',
    '''def imantar(x: int, y: int, w: int, h: int, monitor: tuple, piso: int,
            margen: int = 22) -> tuple:
    """Pega (x, y) al borde o esquina del monitor si esta a menos de `margen` px.

    `monitor` es (x0, y0, x1, y1) y `piso` la y donde termina el monitor para el panel
    (el borde de arriba de la barra de tareas de ese monitor). Devuelve la posicion
    final, siempre dentro del monitor. Un panel a 3 px del borde se ve como un error de
    dibujo, y esta es la parte que conviene poder medir sin mover el mouse.
    """
    mx0, my0, mx1, my1 = monitor
    piso = min(max(piso, my0), my1)
    nx, ny = x, y
    if abs(nx - mx0) <= margen:
        nx = mx0
    elif abs(nx - (mx1 - w)) <= margen:
        nx = mx1 - w
    if abs(ny - my0) <= margen:
        ny = my0
    elif abs(ny - (piso - h)) <= margen:
        ny = piso - h
    nx = max(mx0, min(nx, mx1 - w))
    ny = max(my0, min(ny, max(my0, piso - h)))
    return (int(nx), int(ny))


def _frac(x: int, z: tuple) -> float:''')

# 2) app.py: el iman usa la funcion pura, y la rueda del panel toma la posicion del
#    propio mensaje (es la fuente documentada, y ademas asi se puede probar mandando el
#    mensaje en vez de mover el cursor de verdad)
rep("widget/app.py",
    '''            nx, ny = wr[0], wr[1]
            if abs(nx - mx0) <= margen:
                nx = mx0
            elif abs(nx - (mx1 - w)) <= margen:
                nx = mx1 - w
            if abs(ny - my0) <= margen:
                ny = my0
            elif abs(ny - (piso - h)) <= margen:
                ny = piso - h
            nx = max(mx0, min(nx, mx1 - w))
            ny = max(my0, min(ny, max(my0, piso - h)))
            if (nx, ny) != (wr[0], wr[1]):''',
    '''            nx, ny = panel_mod.imantar(wr[0], wr[1], w, h, (mx0, my0, mx1, my1),
                                       piso, margen)
            if (nx, ny) != (wr[0], wr[1]):''')

rep("widget/app.py",
    '''            if msg == win32con.WM_MOUSEWHEEL:
                steps = ctypes.c_short((wp >> 16) & 0xFFFF).value / 120.0
                if steps:
                    c = win32gui.ScreenToClient(hwnd, win32gui.GetCursorPos())''',
    '''            if msg == win32con.WM_MOUSEWHEEL:
                steps = ctypes.c_short((wp >> 16) & 0xFFFF).value / 120.0
                if steps:
                    # La posicion viene en el propio mensaje (coordenadas de PANTALLA):
                    # es la fuente documentada y no depende de donde este el cursor, asi
                    # que la prueba puede mandar el mensaje sin mover el mouse.
                    sx = ctypes.c_short(lp & 0xFFFF).value
                    sy = ctypes.c_short((lp >> 16) & 0xFFFF).value
                    c = win32gui.ScreenToClient(hwnd, (sx, sy))''')
