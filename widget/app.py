"""Aplicacion: ventana en la barra, entrada, timers y ciclo de vida.

Dos ventanas propias:
  * controlador  -> ventana oculta de nivel superior. Nunca muere con explorer,
                    asi que es la que sostiene los timers y puede reconstruir el
                    widget si la barra de tareas se reinicia.
  * widget       -> hija de Shell_TrayWnd. Solo se pinta y recibe el mouse.

Doble buffer: se dibuja el widget con Pillow, se copia a un DIB de 32bpp y se
hace BitBlt en WM_PAINT. Nada de parpadeo, y el repintado solo ocurre cuando la
firma de lo visible cambia (evita repintar 10 veces por segundo al pedo).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import math
import os
import time

import win32api
import win32con
import win32event
import win32gui
from PIL import Image, ImageChops

from . import config as cfgmod
from . import draw
from .media import MediaPoller, MediaState
from .taskbarwin import TaskbarHost, set_dpi_aware

# Niveles de fondo que ofrece el menu (alpha del chip)
ALPHA_LEVELS = ((232, "Solido"), (170, "Translucido"), (100, "Muy transparente"),
                (0, "Sin fondo (solo caratula, textos y botones)"))
NUDGE_PX = 20

CTL_CLASS = "GorusTaskbarMusicCtl"
WIDGET_CLASS = "GorusTaskbarMusicWnd"
MUTEX_NAME = "Local\\GorusTaskbarMusicWidget"
TIMER_TICK = 1
TIMER_LAYOUT = 2
HOTKEY_TOGGLE = 1

WM_TASKBARCREATED = ctypes.windll.user32.RegisterWindowMessageW("TaskbarCreated")
# win32con no define WM_DPICHANGED; el literal es 0x02E0
WM_DPICHANGED = 0x02E0
WM_DISPLAYCHANGE = getattr(win32con, "WM_DISPLAYCHANGE", 0x007E)
WM_SETTINGCHANGE = getattr(win32con, "WM_SETTINGCHANGE", 0x001A)

# Mensajes propios: dejan mover y transparentar el widget desde afuera (los usa
# tools/selftest.py para verificar las dos cosas contra el widget en marcha).
WM_APP_MOVE = win32con.WM_APP + 1   # wParam = fraccion de posicion x1000; 0xFFFF = extremo
WM_APP_ALPHA = win32con.WM_APP + 2  # wParam = alpha del chip (0 = sin fondo)
WM_APP_CANCEL_SCRUB = win32con.WM_APP + 3   # aborta un arrastre de la barra de progreso
WM_APP_WAVES = win32con.WM_APP + 4  # wParam = 1/0: prende y apaga las ondas de sonido

WS_EX_LAYERED = 0x00080000
ULW_ALPHA = 0x02
IDC_SIZEWE = 32644

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetTimer.restype = ctypes.c_void_p
user32.SetTimer.argtypes = [wt.HWND, ctypes.c_void_p, wt.UINT, ctypes.c_void_p]
user32.KillTimer.argtypes = [wt.HWND, ctypes.c_void_p]
user32.UpdateLayeredWindow.restype = wt.BOOL
user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.c_void_p,
                                       ctypes.c_void_p, wt.HDC, ctypes.c_void_p,
                                       wt.DWORD, ctypes.c_void_p, wt.DWORD]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("dwFlags", wt.DWORD), ("hwndTrack", wt.HWND),
                ("dwHoverTime", wt.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte), ("AlphaFormat", ctypes.c_byte)]


class _Dib:
    """Canvas de 32bpp que se blitea a la ventana."""

    def __init__(self, hwnd: int, w: int, h: int):
        self.w, self.h = w, h
        self.bits = ctypes.c_void_p()
        hdc = win32gui.GetDC(hwnd)
        try:
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = w
            bmi.bmiHeader.biHeight = -h  # negativo = filas de arriba hacia abajo
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0  # BI_RGB
            self.bmp = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0,
                                              ctypes.byref(self.bits), None, 0)
            self.dc = gdi32.CreateCompatibleDC(hdc)
            gdi32.SelectObject(self.dc, self.bmp)
        finally:
            win32gui.ReleaseDC(hwnd, hdc)

    def upload(self, raw: bytes) -> None:
        ctypes.memmove(self.bits, raw, min(len(raw), self.w * self.h * 4))

    def blit(self, hdc: int) -> None:
        gdi32.BitBlt(hdc, 0, 0, self.w, self.h, self.dc, 0, 0, 0x00CC0020)

    def free(self) -> None:
        try:
            gdi32.DeleteDC(self.dc)
            gdi32.DeleteObject(self.bmp)
        except Exception:
            pass


class _Layered:
    """Superficie con alpha por pixel, presentada con UpdateLayeredWindow.

    Requiere que la ventana se haya creado con WS_EX_LAYERED. En Windows 8+ ese
    estilo tambien vale para ventanas hijas (hasta Windows 7 solo servia en
    ventanas de nivel superior), y eso es justo lo que permite que el widget se
    mezcle de verdad con la barra de tareas en vez de simularlo: el alpha del chip
    se compone contra los pixeles reales de atras, incluso si la barra tiene un
    degradado o un tema claro.
    """

    def __init__(self, hwnd: int, w: int, h: int):
        self.hwnd, self.w, self.h = hwnd, w, h
        self.bits = ctypes.c_void_p()
        hdc = win32gui.GetDC(0)
        try:
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = w
            bmi.bmiHeader.biHeight = -h  # filas de arriba hacia abajo
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0
            self.bmp = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0,
                                              ctypes.byref(self.bits), None, 0)
            self.dc = gdi32.CreateCompatibleDC(hdc)
            gdi32.SelectObject(self.dc, self.bmp)
        finally:
            win32gui.ReleaseDC(0, hdc)

    def upload(self, raw: bytes) -> None:
        ctypes.memmove(self.bits, raw, min(len(raw), self.w * self.h * 4))
        self.apply()

    def apply(self) -> None:
        # pptDst en NULL: la posicion la manda SetWindowPos y no queremos dos
        # fuentes de verdad sobre la geometria (la ventana es hija de la barra,
        # asi que ahi las coordenadas son relativas al cliente del padre y
        # mezclarlas es exactamente el bug que ya nos costo una barra fuera de lugar).
        size = wt.SIZE(self.w, self.h)
        src = wt.POINT(0, 0)
        blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER | premultiplicado
        user32.UpdateLayeredWindow(self.hwnd, 0, None, ctypes.byref(size),
                                   self.dc, ctypes.byref(src), 0,
                                   ctypes.byref(blend), ULW_ALPHA)

    def blit(self, hdc: int) -> None:  # compatibilidad: nada que hacer por WM_PAINT
        return

    def free(self) -> None:
        try:
            gdi32.DeleteDC(self.dc)
            gdi32.DeleteObject(self.bmp)
        except Exception:
            pass


class WidgetApp:
    def __init__(self, cfg: dict, embed: bool = True, log_path: str | None = None):
        self.cfg = cfg
        self.embed = embed
        self.host = TaskbarHost(log=self.log)
        self._log_fh = None
        if log_path:
            try:
                self._log_fh = open(log_path, "a", encoding="utf-8", buffering=1)
            except Exception:
                self._log_fh = None
        self.poller = MediaPoller(interval=max(0.1, cfg.get("poll_interval_ms", 500) / 1000.0),
                                  log=self.log)
        self.state = MediaState()
        self.hwnd_widget = 0
        self.hwnd_ctl = 0
        self.dib: _Dib | None = None
        self.hover = -1
        self.marquee = 0.0
        self._marquee_t = time.monotonic()
        self._last_title = ""
        self.k = 1.0
        self.width_px = 0
        self.height_px = 0
        self.base = (26, 28, 36)
        self.layered = str(cfg.get("bg_mode", "layered")).lower() == "layered"
        self.pos_frac = cfg.get("position_frac", None)
        self._drag = None      # estado del arrastre en curso
        self._drag_x = None    # x (pantalla) mientras se arrastra
        self._scrub = None     # estado del arrastre sobre la barra de progreso
        self._scrub_t = None   # segundos destino mientras se arrastra la barra
        self._wave_phase = 0.0    # fase de la animacion de ondas (solo avanza suena)
        self._wave_t = time.monotonic()
        self._levels: list[float] | None = None   # alturas de las ondas ahora mismo
        self._base_img = None     # chip cacheado sin ondas (se le pegan encima)
        self._base_sig = None
        self._wall_x = None    # limite real: a partir de aca la lista de tareas tapa
        self._last_cover_check = 0.0
        self.visible = True
        self._needs_show = False
        self._sig = None
        self._timer_ms = 0
        self._last_layout = 0.0
        self._ctl_wndproc_ref = None
        self._widget_wndproc_ref = None
        self._menu_ids = {}

    # ------------------------------------------------------------------ log
    def log(self, msg: str, *args) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg % args if args else msg}"
        if self._log_fh:
            try:
                self._log_fh.write(line + "\n")
            except Exception:
                pass

    # -------------------------------------------------------- registro de clase
    def _register_classes(self) -> None:
        hinst = win32api.GetModuleHandle(None)

        def ctl_proc(hwnd, msg, wp, lp):
            return self._ctl_wndproc(hwnd, msg, wp, lp)

        def wnd_proc(hwnd, msg, wp, lp):
            return self._widget_wndproc(hwnd, msg, wp, lp)

        self._ctl_wndproc_ref = ctl_proc
        self._widget_wndproc_ref = wnd_proc

        for cls, proc in ((CTL_CLASS, ctl_proc), (WIDGET_CLASS, wnd_proc)):
            wc = win32gui.WNDCLASS()
            wc.hInstance = hinst
            wc.lpszClassName = cls
            wc.lpfnWndProc = proc
            wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
            try:
                win32gui.RegisterClass(wc)
            except Exception:
                pass  # ya registrada

    # ------------------------------------------------------------------ ciclo
    def run(self) -> int:
        set_dpi_aware()
        # una sola instancia: dos widgets se pelearían por el mismo espacio
        self._mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
        if win32api.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            self.log("ya hay otra instancia corriendo")
            return 2

        self._register_classes()
        hinst = win32api.GetModuleHandle(None)
        self.hwnd_ctl = win32gui.CreateWindowEx(
            0, CTL_CLASS, "gorus-ctl", win32con.WS_POPUP,
            0, 0, 0, 0, 0, None, hinst, None)
        if not self.hwnd_ctl:
            self.log("no se pudo crear la ventana controladora")
            return 3

        win32gui.RegisterHotKey(self.hwnd_ctl, HOTKEY_TOGGLE,
                                win32con.MOD_CONTROL | win32con.MOD_ALT, ord("M"))

        self.host.refresh()
        self.host.restore()  # sanea cualquier reserva que haya quedado de un cierre sucio

        self.poller.start()
        self.poller.wait_ready(6.0)

        self._create_widget()
        self._apply_layout(force=True)
        self._repaint_if_needed(force=True)
        self._show_when_ready()
        self._set_timer(self.cfg.get("timer_idle_ms", 500))
        user32.SetTimer(self.hwnd_ctl, TIMER_LAYOUT, int(self.cfg.get("layout_check_ms", 1000)), None)
        self.log("widget iniciado (embed=%s)", self.embed)

        try:
            win32gui.PumpMessages()
        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()
        return 0

    def _shutdown(self) -> None:
        self.log("cerrando")
        self.poller.stop()
        try:
            self.host.detach_widget(self.hwnd_widget)
        except Exception:
            pass
        self.hwnd_widget = 0
        if self.dib:
            self.dib.free()
            self.dib = None
        if self.hwnd_ctl and win32gui.IsWindow(self.hwnd_ctl):
            user32.KillTimer(self.hwnd_ctl, TIMER_TICK)
            user32.KillTimer(self.hwnd_ctl, TIMER_LAYOUT)
            try:
                win32gui.UnregisterHotKey(self.hwnd_ctl, HOTKEY_TOGGLE)
            except Exception:
                pass
        try:
            win32gui.DestroyWindow(self.hwnd_ctl)
        except Exception:
            pass
        if self._log_fh:
            self._log_fh.close()

    # ------------------------------------------------------------------ widget
    def _create_widget(self) -> bool:
        if not self.embed:
            self._create_plain_window()
            return bool(self.hwnd_widget)
        if not self.host.refresh():
            return False
        m = self.host.metrics()
        self.k = m["scale"]
        self.height_px = m["taskbar_h"]
        self.width_px = int(round(self.cfg.get("width", 260) * self.k))
        # Reservar el espacio ANTES de crear la ventana y crearla ya en su sitio:
        # si naciera en (0,0) apareceria un parpadeo encima del boton Inicio.
        x_rel = self._reserve_x()
        hinst = win32api.GetModuleHandle(None)
        self.hwnd_widget = win32gui.CreateWindowEx(
            WS_EX_LAYERED if self.layered else 0,
            WIDGET_CLASS, "gorus-widget",
            win32con.WS_CHILD | win32con.WS_CLIPSIBLINGS,
            x_rel, 0, self.width_px, self.height_px,
            self.host.tray, None, hinst, None)
        if not self.hwnd_widget:
            self.log("no se pudo crear la ventana del widget")
            return False
        self._needs_show = True
        self.dib = None
        self._ensure_surface()
        self._sig = None
        return True

    def _create_plain_window(self) -> None:
        """Modo --no-embed: ventana normal, util para desarrollar."""
        hinst = win32api.GetModuleHandle(None)
        self.k = 1.0
        self.height_px = 40
        self.width_px = int(self.cfg.get("width", 260))
        self.hwnd_widget = win32gui.CreateWindowEx(
            win32con.WS_EX_TOPMOST | (WS_EX_LAYERED if self.layered else 0),
            WIDGET_CLASS, "Gorus - widget de musica", win32con.WS_POPUP,
            1200, 960, self.width_px, self.height_px, 0, None, hinst, None)
        self._needs_show = True
        self.dib = None
        self._ensure_surface()
        self._sig = None

    def _reserve_x(self) -> int:
        """x del widget (relativa al cliente de la barra) segun el modo de posicion.

        Tres fuentes de verdad, en orden: el arrastre en curso, la posicion
        fraccionaria guardada, o el extremo derecho (por defecto).
        """
        min_free = int(self.cfg.get("min_tasklist_free", 140))
        min_tasklist = int(self.cfg.get("min_tasklist_width", 420))
        if self._drag_x is not None:
            return self.host.reserve(self.width_px, min_tasklist,
                                    x=self._drag_x, min_free=min_free)
        return self.host.reserve(self.width_px, min_tasklist,
                                 frac=self.pos_frac, min_free=min_free)

    # ---------------------------------------------------- limite real de la barra
    def _covered(self) -> bool:
        """True si la lista de tareas quedo por encima del widget (la tapa)."""
        try:
            rb = win32gui.GetWindowRect(self.host.rebar)
            wl = win32gui.GetWindowRect(self.hwnd_widget)[0]
        except Exception:
            return False
        return rb[2] > wl + 1

    def _place_at(self, x: int) -> None:
        """Reserva y coloca el widget en una x concreta (pantalla), sin tocar la
        posicion guardada. Devuelve nada: para saber si quedo tapado, _covered()."""
        r = self.host.reserve(self.width_px, int(self.cfg.get("min_tasklist_width", 420)),
                              x=x, min_free=self._min_free())
        self.host.place(self.hwnd_widget, r, self.height_px)

    def _free_x(self, x_want: int, hi: int) -> int:
        """x mas cercana a x_want que no quede tapada por la lista de tareas.

        Windows estira ReBarWindow32 cuando la dejariamos demasiado angosta, y esa
        lista estirada tapa el widget (la lista de tareas esta por encima en el
        orden Z y no se puede ganar esa pelea: explorer la vuelve a subir en cuanto
        se toca la barra). El ancho minimo que Windows tolera depende de cuantas
        ventanas haya abiertas, asi que no se adivina: se busca el limite real por
        biseccion — la cobertura es monotona, cuanto mas a la izquierda peor.
        """
        x = self.host.clamp_x(x_want, self.width_px, self._min_free())
        self._place_at(x)
        if not self._covered():
            return x
        self._place_at(hi)
        if self._covered():
            # No hay posicion libre ni en el extremo: se lo deja arriba a la fuerza
            # (tapa botones, pero al menos se ve; Ctrl+Alt+M lo oculta).
            try:
                win32gui.SetWindowPos(self.hwnd_widget, win32con.HWND_TOP, 0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                                      | win32con.SWP_NOACTIVATE)
            except Exception:
                pass
            return hi
        a, b = x, hi  # a = tapado, b = libre
        while b - a > 4:
            m = (a + b) // 2
            self._place_at(m)
            if self._covered():
                a = m
            else:
                b = m
        self._place_at(b)
        self.log("limite de la barra: la lista de tareas necesita su espacio, "
                 "posicion ajustada de x=%d a x=%d", x_want, b)
        return b

    def _ensure_surface(self) -> None:
        if self.hwnd_widget and self.width_px and self.height_px:
            need = (self.dib is None or self.dib.w != self.width_px
                    or self.dib.h != self.height_px
                    or isinstance(self.dib, _Layered) != self.layered)
            if need:
                if self.dib:
                    self.dib.free()
                cls = _Layered if self.layered else _Dib
                self.dib = cls(self.hwnd_widget, self.width_px, self.height_px)

    def _ensure_attached(self) -> None:
        """Reconstruye o re-ancla el widget si algo se movio por debajo."""
        if not self.embed or not self.visible:
            return
        if self.hwnd_widget and win32gui.IsWindow(self.hwnd_widget):
            try:
                parent = win32gui.GetParent(self.hwnd_widget)
            except Exception:
                parent = 0
            if parent and parent == self.host.tray:
                return
            # el padre cambio (explorer nuevo): rehacer
            try:
                win32gui.DestroyWindow(self.hwnd_widget)
            except Exception:
                pass
            self.hwnd_widget = 0
        self.log("reconstruyendo widget")
        self.host.refresh()
        self._wall_x = None
        self._create_widget()
        self._apply_layout(force=True)
        self._repaint_if_needed(force=True)
        self._show_when_ready()

    def _apply_layout(self, force: bool = False) -> None:
        if not self.embed or not self.visible:
            return
        now = time.monotonic()
        if not force and now - self._last_layout < 0.4:
            return
        self._last_layout = now
        try:
            m = self.host.metrics()
        except Exception:
            return
        self.k = m["scale"]
        want_h = m["taskbar_h"]
        want_w = int(round(self.cfg.get("width", 260) * self.k))
        if want_h != self.height_px or want_w != self.width_px:
            self.height_px, self.width_px = want_h, want_w
            self.dib = None
            self._ensure_surface()
            if self.hwnd_widget and win32gui.IsWindow(self.hwnd_widget):
                win32gui.SetWindowPos(self.hwnd_widget, 0, 0, 0, want_w, want_h,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOZORDER
                                      | win32con.SWP_NOACTIVATE)
            self._sig = None
        x_rel = self._apply_x(m)
        self.base = self.host.base_color(x_rel, self.width_px, self.height_px)

    def _apply_x(self, m: dict) -> int:
        """Coloca el widget segun la posicion pedida y devuelve su x relativa.

        Si la posicion pedida dejaria a la lista de tareas tan angosta que Windows
        la estira por encima del widget, se usa la posicion libre mas cercana.
        """
        hi = self.host.x_limits(self.width_px, self._min_free())[1]
        if self._drag_x is not None:
            x_want = self.host.clamp_x(self._drag_x, self.width_px, self._min_free())
            if self._wall_x:
                x_want = max(x_want, self._wall_x)
        elif self.pos_frac is not None:
            x_want = self.host.x_from_frac(self.pos_frac, self.width_px, self._min_free())
            if self._wall_x:
                x_want = max(x_want, self._wall_x)
        else:
            x_rel = self._reserve_x()   # extremo derecho (posicion automatica)
            self.host.place(self.hwnd_widget, x_rel, self.height_px)
            return x_rel
        x = self._free_x(x_want, hi)
        if x != x_want:
            # la posicion pedida no era viable: se recuerda la lograda para no
            # pelear con la lista de tareas en cada ciclo
            self._wall_x = x
            if self._drag_x is None:
                self._set_frac_noauto(self.host.frac_from_x(x, self.width_px,
                                                            self._min_free()))
        return x - m["left"]

    def toggle_visible(self) -> None:
        if self.visible:
            self.visible = False
            if self.hwnd_widget:
                try:
                    win32gui.ShowWindow(self.hwnd_widget, win32con.SW_HIDE)
                except Exception:
                    pass
            self.host.restore()
            self.log("widget oculto (Ctrl+Alt+M para volver)")
        else:
            self.visible = True
            if self.hwnd_widget and win32gui.IsWindow(self.hwnd_widget):
                win32gui.ShowWindow(self.hwnd_widget, win32con.SW_SHOW)
                self._apply_layout(force=True)
            else:
                self._create_widget()
                self._apply_layout(force=True)
            self.log("widget visible")

    # ------------------------------------------------------------------ pintar
    def _signature(self, sin_ondas: bool = False):
        st = self.state
        bar_px = max(1, self.width_px - int(draw.TEXT_X * self.k) - int(draw.RIGHT_PAD * self.k))
        frac = (st.live_position() / st.duration) if (st.duration and st.playing) else 0.0
        return (st.has_session, st.art_key, st.title, st.artist, st.playing,
                int(frac * bar_px), int(self.marquee) if self._overflow() else 0,
                self.hover, self.width_px, self.height_px, self.base, st.stopped,
                int(self.cfg.get("chip_alpha", 232)), self.layered,
                -1 if self._scrub_t is None else int(self._scrub_t),
                # Con sin_ondas=True, la firma ignora las alturas: es la que decide si
                # hay que redibujar el chip completo (caratula, textos, barra). La
                # animacion de las ondas se pega encima y no obliga a repintarlo todo.
                None if (sin_ondas or self._levels is None)
                else tuple(int(v * 24) for v in self._levels))

    def _overflow(self) -> bool:
        try:
            return draw.title_overflows(self.state, self.cfg, self.k, self.width_px)
        except Exception:
            return False

    def _render_base(self) -> Image.Image:
        """Dibuja el widget completo SIN las ondas (que se pegan encima aparte).

        Se le pasa una lista vacia de alturas: asi reserva la franja de las ondas
        (el texto se recorta antes de llegar) pero no dibuja ninguna barra.
        """
        SS = max(1, int(self.cfg.get("supersample", 3)))
        S = self.k * SS
        art = None
        if self.cfg.get("show_art", True):
            art = draw.get_art(self.state.art, self.state.art_key,
                               int(round(draw.ART * S)), int(round(draw.ART_RADIUS * S)))
        return draw.render(self.state, self.cfg, art=art, hover=self.hover,
                           marquee=self.marquee, k=self.k, base=self.base,
                           height=self.height_px, opaque=not self.layered,
                           scrub=self._scrub_t,
                           waves=[] if self._levels is not None else None)

    def _pegar_ondas(self, img: Image.Image) -> None:
        """Pega la tira de las ondas sobre un cuadro ya dibujado.

        La tira se dibuja aparte, a 4x, y se compone encima: asi la animacion puede
        ir a 20 cuadros por segundo sin repintar el chip entero (medido: 4,4 ms el
        render completo contra 0,08 ms copiar la base y pegar la tira).
        """
        wb = draw.wave_rect(self.width_px, self.k, self.cfg)
        if not wb or not self._levels:
            return
        capa = draw.render_waves(self.state, self.cfg, self._levels, self.k,
                                 self.base, opaque=not self.layered)
        if capa is None:
            return
        if self.layered:
            # Espacio premultiplicado: out = origen + fondo*(1 - alpha). Con
            # Image.paste quedaria alpha*alpha en los bordes suavizados.
            roi = img.crop(wb)
            inv = Image.eval(capa.getchannel("A"), lambda v: 255 - v)
            canales = [ImageChops.add(capa.getchannel(c), ImageChops.multiply(roi.getchannel(c), inv))
                       for c in "RGBA"]
            img.paste(Image.merge("RGBA", canales), wb)
        else:
            img.paste(capa.convert("RGB"), wb, capa)

    def _frame(self) -> Image.Image:
        """Cuadro listo para presentar: base cacheada + ondas del momento."""
        base_sig = self._signature(sin_ondas=True)
        if self._base_img is None or base_sig != self._base_sig:
            self._base_sig = base_sig
            self._base_img = self._render_base()
        img = self._base_img.copy()
        self._pegar_ondas(img)
        return img

    def _render(self) -> None:
        if not self.hwnd_widget or not win32gui.IsWindow(self.hwnd_widget):
            return
        self._ensure_surface()
        if not self.dib:
            return
        img = self._frame()
        if img is None:
            return
        if self.layered:
            # Alpha real: la transparencia del chip se compone contra los pixeles
            # que estan detras, asi que no se mezcla contra ningun color muestreado.
            self.dib.upload(draw.to_premult_bgra(img))
        else:
            self.dib.upload(draw.to_bgra(img))

    def _repaint_if_needed(self, force: bool = False) -> None:
        sig = self._signature()
        if force or sig != self._sig:
            self._sig = sig
            self._render()
        if self.layered:
            # Con alpha por pixel no hace falta invalidar: la ventana en capas la
            # compone DWM, la barra de tareas no pinta encima suyo.
            return
        # Invalidar SIEMPRE, aunque no haga falta redibujar: el blit del DIB ya
        # renderizado cuesta casi nada, y la barra de tareas puede pintar encima
        # de sus ventanas hijas. Sin esto el widget queda borrado (se ve el fondo
        # de la barra) hasta que cambie algo del contenido.
        try:
            win32gui.InvalidateRect(self.hwnd_widget, None, False)
        except Exception:
            pass

    def _show_when_ready(self) -> None:
        """Mostrar la ventana recien despues del primer render.

        Si se crea visible, pinta el DIB vacio y se ve un rectangulo negro por un
        instante hasta que llega el primer dibujo.
        """
        if not self._needs_show or not self.hwnd_widget:
            return
        try:
            win32gui.ShowWindow(self.hwnd_widget, win32con.SW_SHOWNOACTIVATE)
            self._needs_show = False
        except Exception:
            pass

    # ------------------------------------------------------------------ timers
    def _set_timer(self, ms: int) -> None:
        if ms == self._timer_ms or not self.hwnd_ctl:
            return
        self._timer_ms = ms
        user32.KillTimer(self.hwnd_ctl, TIMER_TICK)
        user32.SetTimer(self.hwnd_ctl, TIMER_TICK, int(ms), None)

    def tick(self) -> None:
        try:
            self.state = self.poller.state()
            self._ensure_attached()
            # Red de seguridad: si la lista de tareas crecio (mas ventanas abiertas)
            # y quedo por encima del widget, se corrige la posicion enseguida.
            if self.embed and self.hwnd_widget:
                now_c = time.monotonic()
                if now_c - self._last_cover_check >= 0.5:
                    self._last_cover_check = now_c
                    if self._covered():
                        self._apply_layout(force=True)
            # marquesina: solo avanza si el titulo no cabe
            now = time.monotonic()
            if self.state.title != self._last_title:
                self._last_title = self.state.title
                self.marquee = 0.0
            if self._overflow():
                dt = now - self._marquee_t
                self.marquee = (self.marquee + dt * self.cfg.get("marquee_speed", 32))
            self._marquee_t = now
            # ondas: la fase solo avanza mientras hay musica (en pausa quedan
            # quietas), y las alturas se recalculan una vez por ciclo
            dt_w = now - self._wave_t
            self._wave_t = now
            if self.state.playing:
                self._wave_phase += max(0.0, min(0.25, dt_w))
            self._levels = self._wave_levels()
            ms = (int(self.cfg.get("timer_playing_ms", 100)) if self.state.playing
                  else int(self.cfg.get("timer_idle_ms", 500)))
            if self._levels is not None and self.state.playing:
                # la animacion necesita mas cuadros que la barra de progreso
                ms = min(ms, max(20, int(round(1000.0 / max(1, int(
                    self.cfg.get("wave_fps", 20)))))))
            self._set_timer(ms)
            self._repaint_if_needed()
        except Exception as exc:
            self.log("tick fallo: %r", exc)

    def layout_tick(self) -> None:
        try:
            self._apply_layout()
        except Exception as exc:
            self.log("layout fallo: %r", exc)

    # -------------------------------------------------------------- procs
    def _ctl_wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == win32con.WM_TIMER:
                if wp == TIMER_TICK:
                    self.tick()
                elif wp == TIMER_LAYOUT:
                    self.layout_tick()
                return 0
            if msg == win32con.WM_HOTKEY and wp == HOTKEY_TOGGLE:
                self.toggle_visible()
                return 0
            if msg == WM_APP_MOVE:
                self.set_position(None if wp >= 0xFFFF else wp / 1000.0,
                                  save=bool(lp))
                return 0
            if msg == WM_APP_ALPHA:
                self.set_chip_alpha(int(wp), save=bool(lp))
                return 0
            if msg == win32con.WM_CLOSE:
                # cerrar por pedido explicito (menu o script): terminar el bucle ya
                win32gui.PostQuitMessage(0)
                return 0
            if msg == WM_TASKBARCREATED:
                self.log("la barra de tareas se reinicio; reanclando")
                self.hwnd_widget = 0
                self.host.refresh()
                if self.visible:
                    self._create_widget()
                    self._apply_layout(force=True)
                    self._repaint_if_needed(force=True)
                return 0
            if msg in (WM_SETTINGCHANGE, WM_DISPLAYCHANGE, WM_DPICHANGED):
                self._apply_layout(force=True)
                self._repaint_if_needed(force=True)
                return 0
            if msg == win32con.WM_DESTROY:
                win32gui.PostQuitMessage(0)
                return 0
        except Exception as exc:
            self.log("ctl proc fallo: %r", exc)
        return win32gui.DefWindowProc(hwnd, msg, wp, lp)

    def _hit_at(self, x: int, y: int) -> int:
        """Que hay bajo el cursor: 0/1/2 = anterior/play-pausa/siguiente,
        3 = barra de progreso (solo si ese reproductor admite saltos), -1 = nada.

        Los botones se prueban primero: ocupan toda la altura, asi que si se
        probara la barra antes, el borde de abajo de "siguiente" saltaria de tema.
        """
        for i, (x0, y0, x1, y1) in enumerate(draw.control_rects(self.width_px, self.k, self.cfg)):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return i
        r = draw.progress_rect(self.width_px, self.k, self.cfg)
        if r and self._can_seek() and r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            return 3
        return -1

    # ------------------------------------------------------------ salto de tiempo
    def _can_seek(self) -> bool:
        st = self.state
        return bool(st.has_session and st.can_seek and st.duration > 0)

    def _seek_step(self) -> float:
        try:
            return max(1.0, float(self.cfg.get("seek_step_s", 10)))
        except Exception:
            return 10.0

    def _seek_target(self, x: int) -> float:
        """Segundos que corresponden a una x del cliente sobre la barra."""
        st = self.state
        frac = draw.progress_frac_at(x, self.width_px, self.k, self.cfg)
        return max(st.min_seek, min(frac * st.duration, st.max_seek or st.duration))

    def _seek_by(self, delta: float) -> None:
        st = self.state
        if not self._can_seek():
            return
        target = st.live_position() + delta
        self.poller.seek(max(st.min_seek, min(target, st.max_seek or st.duration)))
        self.log("salto: %+.1f s", delta)
        self._repaint_if_needed(force=True)

    # --------------------------------------------------------------- ondas
    def _wave_levels(self) -> list[float] | None:
        """Alturas (0..1) de las ondas, una por barra; None si estan apagadas.

        Es una ANIMACION, no un analisis del audio: SMTC no expone niveles de
        sonido, asi que las oscilaciones se generan con el reloj. Cada barra tiene
        su frecuencia y hay una envolvente lenta encima, para que no se vean como un
        metronomo perfecto. La fase solo avanza mientras hay musica: en pausa las
        barras quedan planas y apagadas.
        """
        if not self.cfg.get("show_waves", False) or not self.state.has_session:
            return None
        n = max(1, min(12, int(self.cfg.get("wave_bars", 4))))
        if not self.state.playing:
            return [0.12] * n
        fase = self._wave_phase
        env = 0.72 + 0.28 * math.sin(fase * 0.62 + 1.0)
        niveles = []
        for i in range(n):
            v = 0.5 + 0.5 * math.sin(fase * 2.4 * (1.0 + 0.32 * i) + i * 1.7)
            niveles.append(max(0.05, min(1.0, (0.18 + 0.82 * v ** 1.7) * env)))
        return niveles

    def set_waves(self, on: bool, save: bool = True) -> None:
        """Prende y apaga las ondas de sonido (menu contextual y pruebas)."""
        on = bool(on)
        self.cfg["show_waves"] = on
        if save:
            cfgmod.save(self.cfg)
        self._levels = self._wave_levels()
        self._sig = None
        self._repaint_if_needed(force=True)
        self.log("ondas de sonido: %s", "encendidas" if on else "apagadas")

    def _widget_wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == win32con.WM_PAINT:
                hdc, ps = win32gui.BeginPaint(hwnd)
                try:
                    if self.dib:
                        self.dib.blit(hdc)
                finally:
                    win32gui.EndPaint(hwnd, ps)
                return 0
            if msg == win32con.WM_ERASEBKGND:
                return 1
            if msg == win32con.WM_MOUSEMOVE:
                if self._drag is not None:
                    self._drag_move()
                    return 0
                x = lp & 0xFFFF
                y = (lp >> 16) & 0xFFFF
                if self._scrub is not None:
                    self._scrub_move(x)
                    return 0
                if os.environ.get("GORUS_DEBUG_MOUSE"):
                    self.log("WM_MOUSEMOVE x=%s y=%s hit=%s hover_prev=%s",
                             x, y, self._hit_at(x, y), self.hover)
                hit = self._hit_at(x, y)
                if hit != self.hover:
                    self.hover = hit
                    self._repaint_if_needed(force=True)
                try:
                    tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), 0x00000002, hwnd, 0)
                    user32.TrackMouseEvent(ctypes.byref(tme))
                except Exception:
                    pass
                return 0
            if msg == win32con.WM_MOUSELEAVE:
                if self.hover != -1:
                    self.hover = -1
                    self._repaint_if_needed(force=True)
                return 0
            if msg == win32con.WM_MOUSEWHEEL:
                # Rueda sobre el widget: adelanta o atrasa. Windows manda la rueda
                # a la ventana que esta bajo el cursor, no a la que tiene el foco.
                steps = ctypes.c_short((wp >> 16) & 0xFFFF).value / 120.0
                if steps:
                    self._seek_by(steps * self._seek_step())
                return 0
            if msg == win32con.WM_LBUTTONDOWN:
                x = lp & 0xFFFF
                y = (lp >> 16) & 0xFFFF
                hit = self._hit_at(x, y)
                if os.environ.get("GORUS_DEBUG_MOUSE"):
                    r = draw.progress_rect(self.width_px, self.k, self.cfg)
                    dentro = bool(r and r[0] <= x <= r[2] and r[1] <= y <= r[3])
                    self.log("WM_LBUTTONDOWN x=%s y=%s hit=%s barra=%s dentro=%s "
                             "can_seek=%s dur=%.2f captura=%s arrastre=%s",
                             x, y, hit, r, dentro, self._can_seek(), self.state.duration,
                             hex(win32gui.GetCapture()), self._drag is not None)
                if hit == 3:
                    # Sobre la barra de progreso: arrastrar (o un clic seco) salta
                    # a esa posicion.
                    self._start_scrub(x)
                elif hit == -1 and self.cfg.get("drag_to_move", True):
                    # Arrastrar desde cualquier parte que no sea un boton ni la
                    # barra mueve el widget a lo largo de la barra de tareas.
                    self._start_drag()
                return 0
            if msg == win32con.WM_CAPTURECHANGED:
                # Perder la captura NO se trata como "el arrastre no existio": si
                # se cancelara, el clic del usuario se perderia en silencio (visto
                # de verdad: con la captura en un estado inconsistente, el sistema
                # la resetea en el mismo mousedown y el salto nunca se mandaba). Si
                # el usuario esta arrastrando la barra, el salto se aplica igual.
                if os.environ.get("GORUS_DEBUG_MOUSE"):
                    self.log("WM_CAPTURECHANGED arrastre=%s arrastre_barra=%s",
                             self._drag is not None, self._scrub is not None)
                if self._scrub is not None:
                    self._end_scrub(self._scrub.get("x", 0))
                    return 0
                if self._drag is not None:
                    self._drag = None
                    self._drag_x = None
                    self._apply_layout(force=True)
                return 0
            if msg == win32con.WM_LBUTTONUP:
                if os.environ.get("GORUS_DEBUG_MOUSE"):
                    self.log("WM_LBUTTONUP x=%s y=%s arrastre=%s arrastre_barra=%s",
                             lp & 0xFFFF, (lp >> 16) & 0xFFFF,
                             self._drag is not None, self._scrub is not None)
                if self._drag is not None:
                    self._end_drag()
                    return 0
                x = lp & 0xFFFF
                y = (lp >> 16) & 0xFFFF
                if self._scrub is not None:
                    self._end_scrub(x)
                    return 0
                hit = self._hit_at(x, y)
                if hit == 0:
                    self.poller.prev_track()
                elif hit == 1:
                    self.poller.toggle()
                elif hit == 2:
                    self.poller.next_track()
                self._repaint_if_needed(force=True)
                return 0
            if msg == WM_APP_MOVE:
                self.set_position(None if wp >= 0xFFFF else wp / 1000.0,
                                  save=bool(lp))
                return 0
            if msg == WM_APP_ALPHA:
                self.set_chip_alpha(int(wp), save=bool(lp))
                return 0
            if msg == WM_APP_CANCEL_SCRUB:
                self.cancel_scrub()
                return 0
            if msg == WM_APP_WAVES:
                self.set_waves(bool(wp), save=bool(lp))
                return 0
            if msg == win32con.WM_RBUTTONUP:
                if self.cfg.get("right_click_menu", True):
                    self._show_menu()
                return 0
            if msg == win32con.WM_DESTROY:
                self.hwnd_widget = 0
                # Si la ventana controladora ya no existe, nadie va a cerrar el
                # bucle: sin esto el proceso queda zombi y la barra pierde espacio.
                if not self.hwnd_ctl or not win32gui.IsWindow(self.hwnd_ctl):
                    win32gui.PostQuitMessage(0)
                return 0
        except Exception as exc:
            self.log("widget proc fallo: %r", exc)
        return win32gui.DefWindowProc(hwnd, msg, wp, lp)

    # ------------------------------------------------------- posicion y fondo
    def _min_free(self) -> int:
        return int(self.cfg.get("min_tasklist_free", 140))

    def _widget_x(self) -> int:
        """x actual del widget en pantalla (lo que se ve, no lo que dice el config)."""
        try:
            return win32gui.GetWindowRect(self.hwnd_widget)[0]
        except Exception:
            return self.host.target_x(self.width_px,
                                      int(self.cfg.get("min_tasklist_width", 420)),
                                      self.pos_frac, self._min_free())

    def _set_frac_noauto(self, frac: float | None) -> None:
        self.pos_frac = frac
        self.cfg["position_frac"] = round(frac, 4) if frac is not None else None

    def set_position(self, frac: float | None, save: bool = True) -> None:
        """Mueve el widget a una fraccion del tramo util (None = extremo derecho)."""
        if frac is not None:
            frac = max(0.0, min(1.0, float(frac)))
            # pegado al extremo derecho = comportamiento automatico, asi la barra
            # queda ordenada (sin tramo vacio) cuando lo devuelven a su lugar
            hi = self.host.x_limits(self.width_px, self._min_free())[1]
            x = self.host.x_from_frac(frac, self.width_px, self._min_free())
            if hi - x <= 6:
                frac = None
        self._drag_x = None
        self._set_frac_noauto(frac)
        self._apply_layout(force=True)
        self._repaint_if_needed(force=True)
        if save:
            cfgmod.save(self.cfg)
        self.log("posicion: %s", "extremo derecho" if self.pos_frac is None
                 else f"fraccion {self.pos_frac:.3f}")

    def set_chip_alpha(self, alpha: int, save: bool = True) -> None:
        """Transparencia del fondo. 0 = sin fondo (queda flotando sobre la barra)."""
        alpha = max(0, min(255, int(alpha)))
        self.cfg["chip_alpha"] = alpha
        if save:
            cfgmod.save(self.cfg)
        self._sig = None
        self._repaint_if_needed(force=True)
        self.log("fondo: alpha %d", alpha)

    def _nudge(self, delta: int) -> None:
        x = self.host.clamp_x(self._widget_x() + delta, self.width_px, self._min_free())
        self.set_position(self.host.frac_from_x(x, self.width_px, self._min_free()))

    # ------------------------------------------------------------------ arrastre
    def _start_drag(self) -> None:
        try:
            cx, _ = win32gui.GetCursorPos()
            x0 = win32gui.GetWindowRect(self.hwnd_widget)[0]
        except Exception:
            return
        self._drag = {"cx0": cx, "x0": x0, "moved": False}
        self._drag_x = x0
        self._wall_x = None   # el limite se vuelve a descubrir en cada arrastre
        try:
            win32gui.SetCapture(self.hwnd_widget)
            win32gui.SetCursor(win32gui.LoadCursor(0, IDC_SIZEWE))
        except Exception:
            pass

    def _drag_move(self) -> None:
        d = self._drag
        try:
            cx, _ = win32gui.GetCursorPos()
        except Exception:
            return
        # El cursor se lee en coordenadas de PANTALLA. Los mensajes de mouse llegan
        # relativos a la ventana, y como la ventana se mueve bajo el cursor, usarlos
        # haria que el widget se escape o vibre.
        dx = cx - d["cx0"]
        if abs(dx) >= 3:
            d["moved"] = True
        self._drag_x = self.host.clamp_x(d["x0"] + dx, self.width_px, self._min_free())
        self._apply_layout(force=True)
        try:
            win32gui.SetCursor(win32gui.LoadCursor(0, IDC_SIZEWE))
        except Exception:
            pass

    def _end_drag(self) -> None:
        d, self._drag = self._drag, None
        try:
            win32gui.ReleaseCapture()
        except Exception:
            pass
        x, self._drag_x = self._drag_x, None
        if x is not None and d and d.get("moved"):
            self.set_position(self.host.frac_from_x(x, self.width_px, self._min_free()))
        else:
            # clic seco sobre el cuerpo: no mover nada
            self._apply_layout(force=True)

    # ---------------------------------------------------- arrastre de la barra
    def _start_scrub(self, x: int) -> None:
        self._scrub = {"x0": x, "x": x, "moved": False}
        self._scrub_t = self._seek_target(x)
        try:
            win32gui.SetCapture(self.hwnd_widget)
            win32gui.SetCursor(win32gui.LoadCursor(0, IDC_SIZEWE))
        except Exception:
            pass
        self._repaint_if_needed(force=True)

    def _scrub_move(self, x: int) -> None:
        d = self._scrub
        if not d:
            return
        if abs(x - d["x0"]) >= 3:
            d["moved"] = True
        d["x"] = x
        # Mientras se arrastra no se toca la reproduccion: la barra y el renglon
        # del artista muestran a donde va a saltar, y el salto se manda al soltar.
        self._scrub_t = self._seek_target(x)
        try:
            win32gui.SetCursor(win32gui.LoadCursor(0, IDC_SIZEWE))
        except Exception:
            pass
        self._repaint_if_needed(force=True)

    def cancel_scrub(self) -> None:
        """Aborta un arrastre de la barra sin mandar el salto (lo usan las pruebas).

        Suelta la captura DE VERDAD. Si se dejara puesta, el proximo clic real
        llegaria con la captura en un estado inconsistente: el sistema la resetea
        en el mismo mousedown y el clic se perderia.
        """
        if self._scrub is None and self._scrub_t is None:
            return
        self._scrub = None
        self._scrub_t = None
        try:
            win32gui.ReleaseCapture()
        except Exception:
            pass
        self._repaint_if_needed(force=True)

    def _end_scrub(self, x: int) -> None:
        d, self._scrub = self._scrub, None
        target, self._scrub_t = self._scrub_t, None
        try:
            win32gui.ReleaseCapture()
        except Exception:
            pass
        if target is None:
            target = self._seek_target(x)
        # Un clic seco tambien salta: el objetivo es la posicion clickeada.
        if self.poller.seek(target):
            self.log("salto a %.0f s (%s)", target,
                     "arrastre" if (d or {}).get("moved") else "clic")
        self._repaint_if_needed(force=True)

    # ------------------------------------------------------------------- menu
    def _show_menu(self) -> None:
        try:
            menu = win32gui.CreatePopupMenu()
            alpha_sub = win32gui.CreatePopupMenu()
            cur = int(self.cfg.get("chip_alpha", 232))
            for i, (alpha, label) in enumerate(ALPHA_LEVELS):
                flags = win32con.MF_STRING
                if alpha == cur:
                    flags |= win32con.MF_CHECKED
                win32gui.AppendMenu(alpha_sub, flags, 20 + i, label)

            step = self._seek_step()
            seek_ok = self._can_seek()
            items = [
                ("item", 1, "Ocultar widget" if self.visible else "Mostrar widget", True),
                ("sep", 0, "", None),
                ("popup", alpha_sub, "Fondo", True),
                ("sep", 0, "", None),
                ("item", 13, f"◀◀   Atrasar {step:.0f} s", seek_ok),
                ("item", 14, f"Adelantar {step:.0f} s   ▶▶", seek_ok),
                ("sep", 0, "", None),
                ("check", 15, "Ondas de sonido", bool(self.cfg.get("show_waves", False))),
                ("sep", 0, "", None),
                ("item", 3, "◀  Mover a la izquierda", True),
                ("item", 4, "Mover a la derecha  ▶", True),
                ("item", 5, "Centrar en la barra", True),
                ("item", 6, "Volver al extremo derecho", True),
                ("sep", 0, "", None),
                ("item", 7, f"Ancho: {self.cfg.get('width', 260)} px", False),
                ("item", 8, "   Más ancho", True),
                ("item", 9, "   Más angosto", True),
                ("sep", 0, "", None),
                ("item", 10, "Refrescar ahora", True),
                ("item", 11, "Abrir carpeta del proyecto", True),
                ("item", 12, "Salir", True),
            ]
            for kind, ident, label, enabled in items:
                if kind == "sep":
                    win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
                    continue
                if kind == "popup":
                    win32gui.AppendMenu(menu, win32con.MF_POPUP | win32con.MF_STRING,
                                        ident, label)
                    continue
                if kind == "check":
                    flags = win32con.MF_STRING
                    if enabled:
                        flags |= win32con.MF_CHECKED
                    win32gui.AppendMenu(menu, flags, ident, label)
                    continue
                flags = win32con.MF_STRING
                flags |= win32con.MF_ENABLED if enabled else win32con.MF_GRAYED
                win32gui.AppendMenu(menu, flags, ident, label)
            x, y = win32gui.GetCursorPos()
            try:
                win32gui.SetForegroundWindow(self.hwnd_ctl)
            except Exception:
                pass
            cmd = win32gui.TrackPopupMenu(
                menu, win32con.TPM_RETURNCMD | win32con.TPM_RIGHTBUTTON
                | win32con.TPM_NONOTIFY, x, y, 0, self.hwnd_ctl, None)
            win32gui.PostMessage(self.hwnd_ctl, win32con.WM_NULL, 0, 0)
            win32gui.DestroyMenu(menu)
            self._handle_menu(cmd)
        except Exception as exc:
            self.log("menu fallo: %r", exc)

    def _handle_menu(self, cmd: int) -> None:
        if cmd == 1:
            self.toggle_visible()
        elif 20 <= cmd <= 20 + len(ALPHA_LEVELS) - 1:
            self.set_chip_alpha(ALPHA_LEVELS[cmd - 20][0])
        elif cmd == 13:
            self._seek_by(-self._seek_step())
        elif cmd == 14:
            self._seek_by(self._seek_step())
        elif cmd == 15:
            self.set_waves(not self.cfg.get("show_waves", False))
        elif cmd == 3:
            self._nudge(-int(round(NUDGE_PX * self.k)))
        elif cmd == 4:
            self._nudge(int(round(NUDGE_PX * self.k)))
        elif cmd == 5:
            self.set_position(0.5)
        elif cmd == 6:
            self.set_position(None)
        elif cmd == 8:
            self.cfg["width"] = min(520, int(self.cfg.get("width", 260)) + 20)
            cfgmod.save(self.cfg)
            self._apply_layout(force=True)
            self._repaint_if_needed(force=True)
        elif cmd == 9:
            self.cfg["width"] = max(150, int(self.cfg.get("width", 260)) - 20)
            cfgmod.save(self.cfg)
            self._apply_layout(force=True)
            self._repaint_if_needed(force=True)
        elif cmd == 10:
            self.state = self.poller.state()
            self._sig = None
            self._repaint_if_needed(force=True)
        elif cmd == 11:
            try:
                os.startfile(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            except Exception:
                pass
        elif cmd == 12:
            win32gui.PostMessage(self.hwnd_ctl, win32con.WM_CLOSE, 0, 0)


def run(cfg: dict, embed: bool = True, log_path: str | None = None) -> int:
    return WidgetApp(cfg, embed=embed, log_path=log_path).run()
