"""app.py: tamano del panel (3), submenu, teclado local, iman a los bordes, doble clic."""
import io

P = "widget/app.py"
s = io.open(P, encoding="utf-8", newline="").read().replace("\r\n", "\n")


def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (a[:70], s.count(a))
    s = s.replace(a, b)


# 1) import del modulo de ventanas
rep("""from . import panel as panel_mod
""", """from . import panel as panel_mod
from . import ventanas
""")

# 2) clases con CS_DBLCLKS: sin eso el doble clic no llega (el mensaje no existe)
rep('''            wc.lpfnWndProc = proc
            wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)''',
    '''            wc.lpfnWndProc = proc
            # CS_DBLCLKS: sin este estilo el sistema no manda nunca WM_LBUTTONDBLCLK
            # (el doble clic en la caratula del panel no llegaria)
            wc.style = win32con.CS_DBLCLKS
            wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)''')

# 3) tamano del panel: 3 opciones, con el nombre canonico en un solo lugar
rep('''    def set_panel_size(self, tam: str, save: bool = True) -> None:
        """Tamano del panel: "normal" o "chico" (hay que rehacer la ventana)."""
        tam = "chico" if str(tam).lower().startswith(("chi", "com", "min")) else "normal"''',
    '''    def set_panel_size(self, tam: str, save: bool = True) -> None:
        """Tamano del panel: normal / chico / tira (hay que rehacer la ventana)."""
        tam = panel_mod.normalizar(tam)''')

# 4) submenu "Tamano" en vez del interruptor "Tamano chico"
rep('''            pan_check(61, "Tamano chico", str(self.cfg.get("panel_size", "normal")) == "chico")''',
    '''            tam_sub = win32gui.CreatePopupMenu()
            tam_actual = panel_mod.normalizar(self.cfg.get("panel_size", "normal"))
            for i, (val, etq) in enumerate(PANEL_TAMANOS):
                flags = win32con.MF_STRING
                if val == tam_actual:
                    flags |= win32con.MF_CHECKED
                win32gui.AppendMenu(tam_sub, flags, 81 + i, etq)
            win32gui.AppendMenu(pan_sub, win32con.MF_POPUP | win32con.MF_STRING,
                                tam_sub, "Tamano")''')

rep('''        elif cmd == 61:
            self.set_panel_size("chico" if str(self.cfg.get("panel_size", "normal"))
                                != "chico" else "normal")''',
    '''        elif 81 <= cmd <= 81 + len(PANEL_TAMANOS) - 1:
            self.set_panel_size(PANEL_TAMANOS[cmd - 81][0])''')

# 5) teclado con el panel enfocado + doble clic en la caratula que trae el reproductor
rep('''            if msg == win32con.WM_KEYDOWN and wp == win32con.VK_ESCAPE:
                self.toggle_panel(False)
                return 0''',
    '''            if msg == win32con.WM_KEYDOWN:
                # Con el panel enfocado (modo escritorio) se maneja todo por teclado. En
                # modo gaming el panel no toma el foco a proposito: ahi manda el atajo
                # global, que anda igual con el juego adelante.
                if wp == win32con.VK_ESCAPE:
                    self.toggle_panel(False)
                    return 0
                if wp in (win32con.VK_SPACE, win32con.VK_RETURN):
                    self.poller.toggle()
                    self._panel_render(force=True)
                    return 0
                if wp in (win32con.VK_LEFT, win32con.VK_RIGHT,
                          win32con.VK_UP, win32con.VK_DOWN):
                    ctrl = win32api.GetKeyState(win32con.VK_CONTROL) < 0
                    shift = win32api.GetKeyState(win32con.VK_SHIFT) < 0
                    signo = 1 if wp in (win32con.VK_RIGHT, win32con.VK_UP) else -1
                    if wp in (win32con.VK_UP, win32con.VK_DOWN):
                        self._vol_step(signo, fino=ctrl)
                    elif ctrl and not shift:
                        self._seek_by(signo * self._seek_fino())
                    elif shift and not ctrl:
                        self._seek_by(signo * self._seek_grueso())
                    else:
                        self._seek_by(signo * self._seek_step())
                    self._panel_render(force=True)
                    return 0
            if msg == 0x0203:      # WM_LBUTTONDBLCLK
                # Doble clic en la caratula: traer al frente la ventana de lo que suena
                x, y = self._xy(lp)
                if panel_mod.hit(x, y, self._panel_k(), self.cfg) == 7:
                    self.traer_reproductor()
                return 0''')

# 6) iman a los bordes al soltar, antes de guardar la posicion
rep('''    def _panel_end_drag(self, x: int) -> None:
        d, self.panel_drag = self.panel_drag, None
        if d and d.get("hit") == -1 and self.hwnd_panel:''',
    '''    def _panel_imantar(self, margen: int = 22) -> None:
        """Pega el panel al borde o esquina del monitor si quedo a menos de `margen` px.

        Un panel a 3 px del borde se ve como un error de dibujo. Se imanta al borde del
        MONITOR donde esta (no al de la pantalla virtual) y al borde de arriba de la
        barra de tareas de ese monitor, que es su piso natural. Ademas lo deja siempre
        dentro del monitor.
        """
        try:
            wr = win32gui.GetWindowRect(self.hwnd_panel)
            w, h = wr[2] - wr[0], wr[3] - wr[1]
            mon = win32api.MonitorFromRect(wr)
            mx0, my0, mx1, my1 = win32api.GetMonitorInfo(mon)["Monitor"]
            piso = my1
            for b in list_bars():
                br = b["rect"]
                if br[0] <= (wr[0] + wr[2]) // 2 <= br[2] and my0 <= br[1] <= my1:
                    piso = min(piso, br[1])       # arriba de la barra de tareas
            nx, ny = wr[0], wr[1]
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
            if (nx, ny) != (wr[0], wr[1]):
                win32gui.SetWindowPos(self.hwnd_panel, 0, int(nx), int(ny), 0, 0,
                                      win32con.SWP_NOSIZE | win32con.SWP_NOZORDER
                                      | win32con.SWP_NOACTIVATE)
                self.log("panel: imantado a (%d, %d)", nx, ny)
        except Exception as exc:
            self.log("panel: no se pudo imantar: %r", exc)

    def traer_reproductor(self) -> None:
        """Trae al frente la ventana de lo que suena (doble clic en la caratula)."""
        try:
            hwnd = ventanas.ventana_del_reproductor(self.state.app_id or self.state.app_name)
            if not hwnd:
                self.log("reproductor: no encontre su ventana (%s)", self.state.app_id)
                return
            if ventanas.traer_al_frente(hwnd):
                self.log("reproductor: %s quedo al frente (%s)", self.state.app_id,
                         hex(hwnd))
            else:
                self.log("reproductor: no pude ponerlo al frente (%s)", hex(hwnd))
        except Exception as exc:
            self.log("reproductor: fallo %r", exc)

    def _panel_end_drag(self, x: int) -> None:
        d, self.panel_drag = self.panel_drag, None
        if d and d.get("hit") == -1 and self.hwnd_panel:
            self._panel_imantar()''')

# 7) tabla de tamanos del panel
rep('''PANEL_CLASS = "GorusTaskbarMusicPanel"''',
    '''PANEL_CLASS = "GorusTaskbarMusicPanel"

# Tamanos del panel en el submenu (la etiqueta solo la usa el menu).
PANEL_TAMANOS = (
    ("normal", "Normal (caratula grande)"),
    ("chico", "Chico (para jugar)"),
    ("tira", "Tira fina (una sola fila)"),
)''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("app.py: tamano/submenu/teclado/iman/doble clic")
