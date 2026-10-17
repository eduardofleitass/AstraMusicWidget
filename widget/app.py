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
from . import panel as panel_mod
from . import volume as volume_mod
from .media import MediaPoller, MediaState
from .taskbarwin import TaskbarHost, list_bars, set_dpi_aware

# Niveles de fondo que ofrece el menu (alpha del chip)
ALPHA_LEVELS = ((232, "Solido"), (170, "Translucido"), (100, "Muy transparente"),
                (0, "Sin fondo (solo caratula, textos y botones)"))
NUDGE_PX = 20

CTL_CLASS = "GorusTaskbarMusicCtl"
WIDGET_CLASS = "GorusTaskbarMusicWnd"
PANEL_CLASS = "GorusTaskbarMusicPanel"
MUTEX_NAME = "Local\\GorusTaskbarMusicWidget"
TIMER_TICK = 1
TIMER_LAYOUT = 2
HOTKEY_TOGGLE = 1
# Atajos globales. Se registran sobre la ventana CONTROLADORA (que vive todo el
# programa), no sobre el widget: asi siguen andando con el widget oculto, que es
# justo cuando mas hacen falta.
# Cada uno: (id, modificadores, tecla, para que sirve)
VK_TECLAS = {0x4D: "M", 0x50: "P", 0x4F: "O", 0x25: "Izq", 0x26: "Arriba",
             0x27: "Der", 0x28: "Abajo"}
HOTKEYS = (
    (HOTKEY_TOGGLE, win32con.MOD_CONTROL | win32con.MOD_ALT, 0x4D, "mostrar/ocultar"),
    (2, win32con.MOD_CONTROL | win32con.MOD_ALT, 0x50, "play/pausa"),
    (3, win32con.MOD_CONTROL | win32con.MOD_ALT, 0x27, "siguiente"),
    (4, win32con.MOD_CONTROL | win32con.MOD_ALT, 0x25, "anterior"),
    (5, win32con.MOD_CONTROL | win32con.MOD_ALT, 0x26, "volumen +"),
    (6, win32con.MOD_CONTROL | win32con.MOD_ALT, 0x28, "volumen -"),
    (7, win32con.MOD_CONTROL | win32con.MOD_ALT | win32con.MOD_SHIFT, 0x26, "adelantar"),
    (8, win32con.MOD_CONTROL | win32con.MOD_ALT | win32con.MOD_SHIFT, 0x28, "atrasar"),
    (9, win32con.MOD_CONTROL | win32con.MOD_ALT, 0x4F, "panel"),
)
MOD_NOREPEAT = 0x4000   # sin esto, mantener la tecla repite la accion sin parar


def texto_atajo(mods: int, vk: int) -> str:
    """Como se escribe el atajo (para el log y el menu)."""
    partes = []
    if mods & win32con.MOD_CONTROL:
        partes.append("Ctrl")
    if mods & win32con.MOD_ALT:
        partes.append("Alt")
    if mods & win32con.MOD_SHIFT:
        partes.append("Shift")
    partes.append(VK_TECLAS.get(vk, hex(vk)))
    return "+".join(partes)

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
WM_APP_COLOR = win32con.WM_APP + 5  # wParam = 1 barra / 2 ondas; lParam = 0xRRGGBB (0 = tema)
WM_APP_MONITOR = win32con.WM_APP + 6  # wParam = indice de barra (0 = principal)
WM_APP_VOLUME = win32con.WM_APP + 7  # wParam = volumen x1000; lParam 1 silenciar / 2 sonar
WM_APP_SHOW = win32con.WM_APP + 8    # pedirle a la instancia viva que se muestre
WM_APP_HOTKEYS = win32con.WM_APP + 9  # wParam = 1/0: prender o apagar los atajos
WM_APP_PANEL = win32con.WM_APP + 10  # wParam = 1/0: abrir o cerrar el panel
WM_APP_PANEL_CFG = win32con.WM_APP + 11  # pruebas: cambiar un ajuste del panel
# Opciones del submenu Panel (ids 60..).
PANEL_AUTO_HIDE = [(0, "Nunca"), (3, "A los 3 s"), (6, "A los 6 s"), (10, "A los 10 s")]
PANEL_ALPHAS = [(255, "Todo nitido"), (235, "Leve"), (200, "Translucido"),
                (160, "Muy transparente")]
# Alfa del FONDO dibujado (el chip detras del texto). Es independiente del anterior:
# con el fondo en 0 el panel queda flotando sobre el juego y los textos siguen nitidos.
PANEL_BG_ALPHAS = [(250, "Solido"), (200, "Translucido"), (140, "Muy transparente"),
                   (90, "Casi sin fondo"), (0, "Sin fondo (solo los datos)")]

# Colores que ofrece el menu para la barra de progreso y las ondas (None = el del
# tema). El menu guarda el hex en config.json; a mano tambien vale [r, g, b].
COLOR_CHOICES = (
    (None, "Color del tema"),
    ("#60CD91", "Verde"),
    ("#56B6FF", "Celeste"),
    ("#B08CFF", "Violeta"),
    ("#FF78B4", "Rosa"),
    ("#FFAA5A", "Naranja"),
    ("#F0D76E", "Amarillo"),
    ("#EBEEF5", "Blanco"),
)

WS_EX_LAYERED = 0x00080000
ULW_ALPHA = 0x02
IDC_SIZEWE = 32644
IDC_SIZEALL = 32646

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
        self.alpha = 255          # alfa global (fundido de mostrar/ocultar)
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
        # SourceConstantAlpha multiplica el alfa de todo el cuadro: es el fundido de
        # aparicion y desaparicion, sin recalcular ni reenviar la imagen.
        blend = BLENDFUNCTION(0, 0, int(self.alpha), 1)  # AC_SRC_OVER | premultiplicado
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
        self.host = TaskbarHost(log=self.log, monitor=cfg.get("taskbar_monitor"))
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
        self._vol_drag = None   # estado del arrastre sobre la barra de volumen
        self._vol_t = None      # nivel que se esta mostrando mientras se arrastra
        self._vol_last = None   # ultimo nivel aplicado (para no mandar de mas)
        self._vol_info = None   # dato de volumen cacheado: nivel, mudo, disponible
        self._vol_app = None    # app de la que se leyo ese dato
        self._hotkeys_ok = []   # atajos globales que quedaron registrados
        self.hwnd_panel = 0     # ventana del panel (mini reproductor)
        self.dib_panel = None   # su superficie
        self.panel_visible = False
        self.panel_hover = -1
        self.panel_drag = None  # arrastre en curso dentro del panel
        self.panel_scrub = None # segundos destino mientras se arrastra ahi
        self._panel_sig = None
        self._panel_wndproc_ref = None
        self._panel_int = time.monotonic()   # ultima interaccion con el panel
        self._panel_fondo = None             # (r, g, b, brillo, desvio) detras del panel
        self._hud_key = None                 # ultima caratula mostrada por el HUD
        self._vis_alpha = 255   # alfa global del widget (fundido de mostrar/ocultar)
        self._vis_target = 255
        self._fade_prev = None  # cuadro anterior, para el fundido de caratula
        self._fade_t0 = 0.0
        self._art_prev = None   # clave de caratula del cuadro anterior
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

        def panel_proc(hwnd, msg, wp, lp):
            return self._panel_wndproc(hwnd, msg, wp, lp)

        self._ctl_wndproc_ref = ctl_proc
        self._widget_wndproc_ref = wnd_proc
        self._panel_wndproc_ref = panel_proc

        for cls, proc in ((CTL_CLASS, ctl_proc), (WIDGET_CLASS, wnd_proc),
                          (PANEL_CLASS, panel_proc)):
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
        # COM en ESTE hilo: las llamadas de audio (ctypes) se hacen desde los
        # manejadores de la ventana, que corren aca. Se ignora si ya estaba.
        try:
            if not volume_mod.iniciar_com():
                self.log("volumen: COM no se pudo inicializar, el altavoz no va a andar")
        except Exception as exc:
            self.log("volumen: COM fallo: %r", exc)
        # una sola instancia: dos widgets se pelearían por el mismo espacio
        self._mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
        if win32api.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            # Antes esta rama solo dejaba una linea en el log y salia: si el widget
            # estaba oculto, relanzarlo no hacia nada visible y parecia roto (con
            # pythonw ni siquiera hay consola donde leer el motivo). Ahora le pide a
            # la instancia viva que se muestre: es lo que el usuario espera al
            # volver a arrancarlo, y es idempotente (si ya esta visible, no pasa nada).
            self.log("ya hay otra instancia corriendo")
            vivo = win32gui.FindWindow(CTL_CLASS, None)
            if vivo:
                win32gui.PostMessage(vivo, WM_APP_SHOW, 0, 0)
                self.log("le pedi a la instancia viva (0x%X) que se muestre", vivo)
                return 0
            self.log("no encontre la ventana de la instancia viva")
            return 2

        self._register_classes()
        hinst = win32api.GetModuleHandle(None)
        self.hwnd_ctl = win32gui.CreateWindowEx(
            0, CTL_CLASS, "gorus-ctl", win32con.WS_POPUP,
            0, 0, 0, 0, 0, None, hinst, None)
        if not self.hwnd_ctl:
            self.log("no se pudo crear la ventana controladora")
            return 3

        # Atajos globales. RegisterHotKey falla si otro programa ya tiene la
        # combinacion (tipico con Ctrl+Alt+flechas y los drivers de video): se
        # informa cual fallo en vez de dejar un atajo muerto en silencio.
        self._hotkeys_ok = self._registrar_atajos()

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
        try:
            self.toggle_panel(False)
        except Exception:
            pass
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
                for hk_id, _mods, _vk, _nombre in HOTKEYS:
                    try:
                        win32gui.UnregisterHotKey(self.hwnd_ctl, hk_id)
                    except Exception:
                        pass
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
            rb = win32gui.GetWindowRect(self.host.container)
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

    def _fundido_activo(self) -> bool:
        """Si el mostrar/ocultar se anima (solo con alpha real por pixel)."""
        return bool(self.layered and self.cfg.get("fade_visible", True))

    def _ocultar_ya(self) -> None:
        if self.hwnd_widget:
            try:
                win32gui.ShowWindow(self.hwnd_widget, win32con.SW_HIDE)
            except Exception:
                pass
        self.host.restore()

    def _mostrar_ya(self) -> None:
        if self.hwnd_widget and win32gui.IsWindow(self.hwnd_widget):
            win32gui.ShowWindow(self.hwnd_widget, win32con.SW_SHOW)
            self._apply_layout(force=True)
        else:
            self._create_widget()
            self._apply_layout(force=True)

    def toggle_visible(self) -> None:
        if self.visible:
            self.visible = False
            self.log("widget oculto (Ctrl+Alt+M para volver)")
            if self._fundido_activo() and self.hwnd_widget:
                self._vis_target = 0      # el tick lo oculta al terminar el fundido
                # y se apura el temporizador YA: con el ritmo normal (hasta 500 ms sin
                # musica) el widget se quedaba visible un rato y recien despues fundia
                self._set_timer(30)
            else:
                self._ocultar_ya()
        else:
            self.visible = True
            self._mostrar_ya()
            if self._fundido_activo():
                self._vis_alpha, self._vis_target = 0, 255
                if self.dib:
                    self.dib.alpha = 0
                    self.dib.apply()
                self._set_timer(30)
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
                # el volumen que se esta mostrando (nivel, mudo, mostrando, hay sesion)
                self._vol_para_render(),
                # Si hay fundido de caratula en curso, su avance: asi el tick vuelve a
                # dibujar cada cuadro. Va solo en la firma COMPLETA, no en la de la
                # base: si invalidara la base, `_frame` la reconstruiria en cada cuadro
                # y el fundido se perderia al segundo cuadro (medido: el cuadro volvia
                # directo a la tapa nueva sin mezcla).
                (None if (sin_ondas or self._fade_prev is None)
                 else int(min(1.0, (time.monotonic() - self._fade_t0) / 0.05) * 50)),
                # los colores elegidos a mano tambien forman parte de lo que se ve
                draw.parse_color(self.cfg.get("progress_color")),
                draw.parse_color(self.cfg.get("waves_color")),
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
                           waves=[] if self._levels is not None else None,
                           volume=self._vol_para_render())

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
        """Cuadro listo para presentar: base cacheada + ondas del momento.

        Si la caratula cambio, la base nueva se funde con la anterior durante
        `fade_cover_ms`: el salto de tapa a tapa queda suave. Se mezcla con
        `Image.blend` (alfa recto) y es correcto porque donde las dos imagenes tienen
        el mismo alfa (todo el chip, los textos, la tapa) el resultado es identico al
        de mezclar en premultiplicado; solo difiere en los bordes donde una tapa tiene
        silueta y la otra no, que es un par de pixeles durante el fundido.
        """
        base_sig = self._signature(sin_ondas=True)
        if self._base_img is None or base_sig != self._base_sig:
            anterior = self._base_img
            self._base_sig = base_sig
            self._base_img = self._render_base()
            self._fade_prev = None
            if (anterior is not None and self.cfg.get("fade_cover", True)
                    and self.state.art_key != self._art_prev and self.state.has_session):
                # solo cuando cambia de verdad la caratula (no en cada cambio de
                # hover o de posicion), que es cuando el salto se nota
                self._fade_prev = anterior
                self._fade_t0 = time.monotonic()
            self._art_prev = self.state.art_key
        img = self._base_img.copy()
        if self._fade_prev is not None:
            dur = max(0.05, self.cfg.get("fade_cover_ms", 220) / 1000.0)
            t = (time.monotonic() - self._fade_t0) / dur
            if t >= 1.0:
                self._fade_prev = None
            else:
                try:
                    img = Image.blend(self._fade_prev, img, max(0.0, min(1.0, t)))
                except Exception:
                    self._fade_prev = None
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
            # fundido de mostrar/ocultar: se mueve el alfa global de la superficie
            # (no hace falta redibujar nada) y se acelera el temporizador mientras
            # dura, o se veria a saltos con el ritmo normal de la barra de progreso
            fundiendo = self.layered and self._vis_alpha != self._vis_target
            if fundiendo:
                paso = max(1, int(self.cfg.get("fade_step", 48)))
                if self._vis_alpha < self._vis_target:
                    self._vis_alpha = min(self._vis_target, self._vis_alpha + paso)
                else:
                    self._vis_alpha = max(self._vis_target, self._vis_alpha - paso)
                if self.dib:
                    self.dib.alpha = self._vis_alpha
                    self.dib.apply()
                if self._vis_alpha == 0:
                    self._ocultar_ya()      # recien ahora suelta el espacio
            ms = (int(self.cfg.get("timer_playing_ms", 100)) if self.state.playing
                  else int(self.cfg.get("timer_idle_ms", 500)))
            if self._levels is not None and self.state.playing:
                # la animacion necesita mas cuadros que la barra de progreso
                ms = min(ms, max(20, int(round(1000.0 / max(1, int(
                    self.cfg.get("wave_fps", 20)))))))
            # HUD: mostrarlo un rato al cambiar de cancion (para ver el titulo sin
            # salir del juego). Se apaga solo con el auto-ocultar.
            if self.cfg.get("panel_hud", False) and self.state.has_session:
                if self._hud_key is None:
                    self._hud_key = self.state.art_key          # el primero no cuenta
                elif self.state.art_key != self._hud_key:
                    self._hud_key = self.state.art_key
                    if not self.panel_visible:
                        self.toggle_panel(True)
            if self.panel_visible:
                self._panel_tick()
                ms = min(ms, 100)     # el panel muestra la posicion: mas seguido
            if fundiendo or self._fade_prev is not None:
                # 30 ms (~33 cuadros por segundo) para que los fundidos se vean
                # suaves: con el ritmo normal de la barra de progreso (100 ms) un
                # fundido de 200 ms tendria dos cuadros y se veria a saltos.
                ms = min(ms, 30)
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
            if msg == win32con.WM_HOTKEY:
                self._accion_atajo(int(wp))
                return 0
            if msg == WM_APP_SHOW:
                # mostrarse es idempotente: si ya esta visible no se oculta
                if not self.visible:
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
                # 5 = el altavoz, para no confundirlo con el 3 de la barra
                return 5 if i == 3 else i
        r = draw.progress_rect(self.width_px, self.k, self.cfg)
        if r and r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            # Con el altavoz bajo el cursor, esa misma fila hace de barra de volumen
            if self._vol_mostrar() and self._vol_disponible():
                return 4
            if self._can_seek():
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

    def _registrar_atajos(self) -> list[str]:
        """Registra (o libera) los atajos globales segun la configuracion."""
        puestos = []
        for hk_id, mods, vk, nombre in HOTKEYS:
            try:
                if self.cfg.get("hotkeys", True):
                    # OJO: pywin32 devuelve None cuando el registro SALE BIEN y lanza
                    # excepcion cuando falla (1409 = ya lo tiene otro programa). Un
                    # `if RegisterHotKey(...)` da falso siempre y deja todos los
                    # atajos sin registrar creyendo que fallaron.
                    win32gui.RegisterHotKey(self.hwnd_ctl, hk_id,
                                            mods | MOD_NOREPEAT, vk)
                    puestos.append(nombre)
                else:
                    win32gui.UnregisterHotKey(self.hwnd_ctl, hk_id)
            except Exception as exc:
                self.log("atajo %s: %r", nombre, exc)
        self.log("atajos globales: %s", ", ".join(puestos) if puestos else "ninguno")
        return puestos

    def _accion_atajo(self, hk_id: int) -> None:
        """Que hace cada atajo. Es el mismo camino que el mouse y el menu."""
        if hk_id == HOTKEY_TOGGLE:
            self.toggle_visible()
            return
        nombre = next((n for i, _m, _v, n in HOTKEYS if i == hk_id), str(hk_id))
        if hk_id == 2:
            self.poller.toggle()
        elif hk_id == 3:
            self.poller.next_track()
        elif hk_id == 4:
            self.poller.prev_track()
        elif hk_id == 5:
            self._vol_step(1)
        elif hk_id == 6:
            self._vol_step(-1)
        elif hk_id == 7:
            self._seek_by(self._seek_step())
        elif hk_id == 8:
            self._seek_by(-self._seek_step())
        elif hk_id == 9:
            self.toggle_panel()
            self.log("atajo: %s", nombre)
            return
        else:
            return
        self.log("atajo: %s", nombre)
        self._sig = None
        self._repaint_if_needed(force=True)

    def panel_remuestrear(self) -> None:
        """Vuelve a medir el fondo detras del panel (lo usa "Refrescar ahora")."""
        if not (self.panel_visible and self.hwnd_panel):
            return
        try:
            self.toggle_panel(False)
            self.toggle_panel(True)
        except Exception:
            pass

    def set_hotkeys(self, on: bool, save: bool = True) -> None:
        """Prende o apaga los atajos globales (menu y pruebas)."""
        self.cfg["hotkeys"] = bool(on)
        if save:
            cfgmod.save(self.cfg)
        self._hotkeys_ok = self._registrar_atajos()
        self.log("atajos globales: %s", "encendidos" if on else "apagados")

    def _seek_fino(self) -> float:
        try:
            return max(0.1, float(self.cfg.get("seek_fine_s", 1)))
        except Exception:
            return 1.0

    def _seek_grueso(self) -> float:
        try:
            return max(1.0, float(self.cfg.get("seek_coarse_s", 60)))
        except Exception:
            return 60.0

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

    def set_color(self, key: str, value, save: bool = True) -> None:
        """Color de la barra de progreso o de las ondas (None = el color del tema).

        El chip cacheado lleva el color de la barra dibujado, asi que hay que tirarlo;
        la tira de las ondas se dibuja en cada cuadro y toma el cambio sola.
        """
        if key not in ("progress_color", "waves_color"):
            return
        self.cfg[key] = value
        if save:
            cfgmod.save(self.cfg)
        self._sig = None
        self._base_sig = None
        self._repaint_if_needed(force=True)
        c = draw.parse_color(value)
        self.log("%s: %s", "color de la barra" if key == "progress_color"
                 else "color de las ondas",
                 draw.hex_color(c) if c else "color del tema")

    def set_taskbar(self, monitor: str | None, save: bool = True) -> None:
        """Mueve el widget a la barra de tareas de otro monitor (None = principal).

        La ventana es HIJA de la barra, asi que no se puede mudar de padre: hay que
        destruirla y crearla de nuevo en la otra barra, devolviendo antes el espacio
        a la primera.
        """
        if (monitor or "") == (self.cfg.get("taskbar_monitor") or ""):
            return
        self.cfg["taskbar_monitor"] = monitor or None
        if save:
            cfgmod.save(self.cfg)
        try:
            self.host.detach_widget(self.hwnd_widget)
        except Exception:
            pass
        self.hwnd_widget = 0
        self.dib = None
        self._wall_x = None      # el limite medido era de la barra anterior
        self._base_img = None
        self._sig = None
        if self.panel_visible:
            self.toggle_panel(False)
        self.host.select(monitor)
        self._create_widget()
        self._apply_layout(force=True)
        self._repaint_if_needed(force=True)
        self._show_when_ready()
        if self._drag is not None and self.hwnd_widget:
            # seguir arrastrando en la barra nueva (la ventana vieja era la que
            # tenia la captura del mouse)
            try:
                win32gui.SetCapture(self.hwnd_widget)
                win32gui.SetCursor(win32gui.LoadCursor(0, IDC_SIZEWE))
            except Exception:
                pass
        b = self.host.barra or {}
        self.log("barra de tareas: %s (%s)", b.get("nombre", "?"), b.get("monitor", "?"))

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
                if self._vol_drag is not None:
                    self._vol_drag_move(x)
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
                    c = win32gui.ScreenToClient(hwnd, win32gui.GetCursorPos())
                    ctrl = win32api.GetKeyState(win32con.VK_CONTROL) < 0
                    shift = win32api.GetKeyState(win32con.VK_SHIFT) < 0
                    if self._hit_at(*c) == 5:
                        # Sobre el altavoz la rueda mueve el volumen; Ctrl = 1%
                        self._vol_step(steps, fino=ctrl)
                    elif ctrl and not shift:
                        self._seek_by(steps * self._seek_fino())
                    elif shift and not ctrl:
                        self._seek_by(steps * self._seek_grueso())
                    else:
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
                elif hit == 4:
                    # La fila esta mostrando el volumen: arrastrar el nivel
                    self._start_vol_drag(x)
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
                if self._vol_drag is not None:
                    self._end_vol_drag(self._vol_drag.get("x", 0))
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
                if self._vol_drag is not None:
                    self._end_vol_drag(x)
                    return 0
                hit = self._hit_at(x, y)
                if hit == 0:
                    self.poller.prev_track()
                elif hit == 1:
                    self.poller.toggle()
                elif hit == 2:
                    self.poller.next_track()
                elif hit == 5:
                    # clic seco en el altavoz: silencio si/no
                    self._vol_toggle_mute()
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
            if msg == WM_APP_VOLUME:
                self._vol_remoto(int(wp) / 1000.0, int(lp))
                return 0
            if msg == WM_APP_HOTKEYS:
                self.set_hotkeys(bool(wp), save=bool(lp))
                return 0
            if msg == WM_APP_PANEL:
                self.toggle_panel(None if lp == 0xFFFF else bool(wp))
                return 0
            if msg == WM_APP_PANEL_CFG:
                # pruebas y scripts: (clave, valor) en wParam/lParam no alcanza para
                # texto, asi que la clave viene en wParam y el valor en lParam
                claves = {1: "panel_no_robar", 2: "panel_topmost", 3: "panel_clics_al_juego",
                          4: "panel_hud"}
                if int(wp) == 5:
                    self.set_panel_size("chico" if lp else "normal")
                elif int(wp) == 6:
                    self.set_panel_gaming(bool(lp))
                elif int(wp) == 7:
                    self.set_panel_ajuste("panel_auto_hide_s", lp / 10.0)
                elif int(wp) == 8:
                    self.set_panel_ajuste("panel_alpha", lp)
                elif int(wp) == 9:
                    self.set_panel_ajuste("panel_bg_alpha", lp)
                elif int(wp) == 10:
                    self.panel_anclar_al_widget()
                elif int(wp) in claves:
                    self.set_panel_ajuste(claves[int(wp)], bool(lp))
                return 0
            if msg == WM_APP_WAVES:
                self.set_waves(bool(wp), save=bool(lp))
                return 0
            if msg == WM_APP_COLOR:
                rgb = int(lp) & 0xFFFFFF
                self.set_color("progress_color" if wp == 1 else "waves_color",
                               None if rgb == 0 else "#%06X" % rgb, save=False)
                return 0
            if msg == WM_APP_MONITOR:
                barras = list_bars()
                i = int(wp)
                if 0 <= i < len(barras):
                    b = barras[i]
                    self.set_taskbar(None if b["primario"] else b["monitor"], save=bool(lp))
                else:
                    self.log("no existe la barra %s (hay %d)", i, len(barras))
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
        if self.panel_visible:
            self.toggle_panel(False)
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
        # Si el arrastre se fue al tramo de la barra de otro monitor (o sea: lo
        # arrastraste al otro monitor), el widget se muda ahi y el arrastre sigue.
        # La ventana es hija de la barra, asi que mudarla es recrearla.
        otra = self.host.barra_en(cx)
        if otra and otra["tray"] != self.host.tray:
            self.set_taskbar(None if otra["primario"] else otra["monitor"])
            if self.hwnd_widget:
                d["cx0"] = cx
                d["x0"] = self._widget_x()
                self._drag_x = d["x0"]
            return
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
            # clic seco sobre el cuerpo: si fue en la caratula, abre el panel (es el
            # gesto que la gente ya espera para ver la cancion en grande)
            self._apply_layout(force=True)
            try:
                pt = win32gui.GetCursorPos()
                cx, cy = win32gui.ScreenToClient(self.hwnd_widget, pt)
                if (0 <= cx < draw.TEXT_X * self.k
                        and 0 <= cy < self.height_px):
                    self.toggle_panel(True)
            except Exception:
                pass

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

    # ---------------------------------------------------------------- volumen
    VOL_TTL = 2.0          # vida del dato de volumen mientras el usuario lo usa
    VOL_TTL_QUIETO = 10.0  # ...y el resto del tiempo (cambios hechos afuera)

    def _vol_estado(self, forzar: bool = False) -> tuple[float, bool, bool]:
        """(nivel 0..1, silenciado, disponible) de la app que esta sonando.

        El dato se cachea porque leerlo son un par de milisegundos de llamadas COM
        y la firma se consulta en cada tick. Se refresca al cambiar de app, mientras
        el usuario lo esta usando, y cada tanto para ver cambios hechos afuera (el
        mezclador de Windows).
        """
        app = self.state.app_id or ""
        ahora = time.monotonic()
        info = self._vol_info
        vencido = (forzar or info is None or self._vol_app != app
                   or (ahora - info[3]) > (self.VOL_TTL if self._vol_mostrar()
                                           else self.VOL_TTL_QUIETO))
        if vencido:
            nivel, mudo, disp = 0.0, False, False
            if app:
                try:
                    r = volume_mod.estado(app)
                except Exception as exc:
                    r = None
                    self.log("volumen: no se pudo leer: %r", exc)
                if r:
                    nivel, mudo, disp = float(r[0]), bool(r[1]), True
            info = (nivel, mudo, disp, ahora)
            self._vol_info, self._vol_app = info, app
        return (info[0], info[1], info[2])

    def _vol_disponible(self) -> bool:
        """Si la app que suena tiene sesion de audio (o sea: si se le puede cambiar)."""
        try:
            return bool(self._vol_estado()[2])
        except Exception:
            return False

    def _vol_mostrar(self) -> bool:
        """Si la fila del progreso esta haciendo de barra de volumen ahora mismo.

        Pasa con el altavoz bajo el cursor o mientras se arrastra el nivel: la fila
        no gana lugar propio, se reusa la del progreso (que ademas ya tiene la zona
        clicable comoda).
        """
        if not self.cfg.get("show_volume", True):
            return False
        return self.hover in (4, 5) or self._vol_drag is not None

    def _vol_para_render(self) -> tuple[float, bool, bool, bool]:
        """Lo que necesita el dibujo: nivel, mudo, mostrando, hay sesion."""
        nivel, mudo, disp = self._vol_estado()
        if self._vol_t is not None:
            nivel = self._vol_t      # previsualizacion del arrastre
        mostrar = bool(self.cfg.get("show_volume", True) and disp and self._vol_mostrar())
        return (float(nivel), bool(mudo), bool(mostrar), bool(disp))

    def _vol_app_id(self) -> str:
        return self.state.app_id or ""

    def _vol_anotar(self, nivel: float, mudo: bool) -> None:
        self._vol_info = (max(0.0, min(1.0, nivel)), bool(mudo), True, time.monotonic())
        self._vol_app = self._vol_app_id()

    def _vol_aplicar(self, nivel: float, mudo: bool | None = None) -> bool:
        """Fija el volumen de la app (0..1) y deja el dato cacheado al dia."""
        app = self._vol_app_id()
        if not app:
            return False
        nivel = max(0.0, min(1.0, float(nivel)))
        try:
            volume_mod.fijar(app, nivel)
            if mudo is not None:
                volume_mod.silenciar(app, bool(mudo))
        except Exception as exc:
            self.log("volumen: no se pudo fijar: %r", exc)
            return False
        self._vol_anotar(nivel, self._vol_info[1] if mudo is None else mudo)
        self._vol_last = nivel
        return True

    def _vol_step(self, muescas: float, fino: bool = False) -> None:
        """Rueda sobre el altavoz: sube o baja el volumen por muescas.

        Con `fino` el paso es del 1% (Ctrl+rueda): para dejar el volumen en el punto
        justo sin pelearse con la rueda.

        El nivel se lee FRESCO (sin cache): el paso es relativo, asi que partir de un
        valor viejo da un salto. Medido: con el volumen cambiado desde el mezclador de
        Windows, la rueda ponia 100% en vez de +5%.
        """
        nivel, mudo, disp = self._vol_estado(forzar=True)
        if not disp:
            return
        paso = (1 if fino else max(1, int(self.cfg.get("volume_step", 5)))) / 100.0
        nuevo = max(0.0, min(1.0, nivel + muescas * paso))
        if self._vol_aplicar(nuevo, mudo=False):
            self.log("volumen: %.0f%% (rueda)", nuevo * 100)
        self._sig = None
        self._repaint_if_needed(force=True)

    def _vol_toggle_mute(self) -> None:
        """Clic seco en el altavoz: silencio si/no."""
        app = self._vol_app_id()
        if not app:
            return
        try:
            r = volume_mod.silenciar(app, None)
        except Exception as exc:
            self.log("volumen: el silencio fallo: %r", exc)
            return
        if r is None:
            self.log("volumen: %s no tiene sesion de audio", app)
            return
        self._vol_anotar(self._vol_estado()[0], bool(r))
        self.log("volumen: %s", "silencio" if r else "sonando")
        self._sig = None
        self._repaint_if_needed(force=True)

    def _start_vol_drag(self, x: int) -> None:
        self._vol_drag = {"x0": x, "x": x, "moved": False}
        self._vol_t = self._vol_nivel_at(x)
        self._vol_aplicar(self._vol_t)
        try:
            win32gui.SetCapture(self.hwnd_widget)
            win32gui.SetCursor(win32gui.LoadCursor(0, IDC_SIZEWE))
        except Exception:
            pass
        self._repaint_if_needed(force=True)

    def _vol_nivel_at(self, x: int) -> float:
        frac = draw.progress_frac_at(x, self.width_px, self.k, self.cfg)
        return max(0.0, min(1.0, float(frac)))

    def _vol_drag_move(self, x: int) -> None:
        d = self._vol_drag
        if not d:
            return
        if abs(x - d["x0"]) >= 3:
            d["moved"] = True
        d["x"] = x
        self._vol_t = self._vol_nivel_at(x)
        # Se aplica en vivo (el mezclador lo muestra al instante), pero solo cuando
        # el nivel cambia de verdad: cada llamada es un ida y vuelta con el servicio
        # de audio, y el mouse manda muchos eventos por segundo.
        if self._vol_last is None or abs(self._vol_t - self._vol_last) >= 0.01:
            self._vol_aplicar(self._vol_t)
        try:
            win32gui.SetCursor(win32gui.LoadCursor(0, IDC_SIZEWE))
        except Exception:
            pass
        self._repaint_if_needed(force=True)

    def _end_vol_drag(self, x: int) -> None:
        d, self._vol_drag = self._vol_drag, None
        self._vol_t = None
        self._vol_last = None
        try:
            win32gui.ReleaseCapture()
        except Exception:
            pass
        if d:
            nivel = self._vol_nivel_at(x)
            if self._vol_aplicar(nivel):
                self.log("volumen: %.0f%% (%s)", nivel * 100,
                         "arrastre" if d.get("moved") else "clic")
        self._repaint_if_needed(force=True)

    def _vol_remoto(self, nivel: float, modo: int) -> None:
        """Cambia el volumen desde afuera (lo usan las pruebas) y lo deja informado."""
        if not self._vol_aplicar(nivel):
            self.log("volumen: la app no tiene sesion de audio")
            return
        if modo in (1, 2):
            app = self._vol_app_id()
            try:
                r = volume_mod.silenciar(app, modo == 1)
            except Exception:
                r = None
            if r is not None:
                self._vol_anotar(nivel, bool(r))
        self.log("volumen: %.0f%% (remoto)", nivel * 100)
        self._sig = None
        self._repaint_if_needed(force=True)

    def set_volume_visible(self, on: bool, save: bool = True) -> None:
        """Muestra u oculta el altavoz (cambia el ancho de los textos y las ondas)."""
        on = bool(on)
        self.cfg["show_volume"] = on
        if save:
            cfgmod.save(self.cfg)
        self._sig = None
        self._base_sig = None
        self._repaint_if_needed(force=True)
        self.log("altavoz: %s", "visible" if on else "oculto")

    # ------------------------------------------------------------------- panel
    def _panel_k(self) -> float:
        """Escala del panel: la misma que el widget (alto de la barra / 40)."""
        return max(0.6, self.k or 1.0)

    def _panel_ex_style(self) -> int:
        """Estilos extendidos del panel segun el modo.

        - `WS_EX_TOOLWINDOW`: no aparece en la barra de tareas ni en Alt+Tab.
        - `WS_EX_NOACTIVATE` (modo gaming): el panel NO se activa nunca, asi el juego no
          pierde el foco, el teclado sigue yendo al juego y el panel no se cierra al
          tocar afuera (que era justo lo que molestaba).
        - `WS_EX_TOPMOST`: queda por encima de todo (util sobre juegos en ventana).
        - `WS_EX_TRANSPARENT`: los clics pasan al juego como si el panel no estuviera;
          queda de solo lectura y se maneja con los atajos.
        """
        ex = 0x00080000 | 0x00000080          # WS_EX_LAYERED | WS_EX_TOOLWINDOW
        if self.cfg.get("panel_no_robar", False):
            ex |= 0x08000000                  # WS_EX_NOACTIVATE
        if self.cfg.get("panel_topmost", False):
            ex |= 0x00000008                  # WS_EX_TOPMOST
        if self.cfg.get("panel_clics_al_juego", False):
            ex |= 0x00000020                  # WS_EX_TRANSPARENT
        return ex

    def _panel_aplicar_estilos(self) -> None:
        """Aplica los estilos al panel ya creado (cambiar el modo en vivo)."""
        if not (self.hwnd_panel and win32gui.IsWindow(self.hwnd_panel)):
            return
        try:
            win32gui.SetWindowLong(self.hwnd_panel, win32con.GWL_EXSTYLE,
                                   self._panel_ex_style())
            win32gui.SetWindowPos(self.hwnd_panel, 0, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                                  | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                                  | 0x0020)   # SWP_FRAMECHANGED
        except Exception as exc:
            self.log("panel: no se pudieron aplicar los estilos: %r", exc)

    def _panel_olvidar(self) -> None:
        """Destruye la ventana del panel (cuando cambia de tamano hay que rehacerla)."""
        if self.hwnd_panel and win32gui.IsWindow(self.hwnd_panel):
            try:
                win32gui.DestroyWindow(self.hwnd_panel)
            except Exception:
                pass
        self.hwnd_panel = 0
        self.dib_panel = None
        self.panel_visible = False
        self._panel_sig = None

    def _create_panel(self) -> bool:
        if self.hwnd_panel and win32gui.IsWindow(self.hwnd_panel):
            return True
        k = self._panel_k()
        w, h = panel_mod.size(k, self.cfg)
        hinst = win32api.GetModuleHandle(None)
        # Ventana propia de nivel superior (ver _panel_ex_style): es un globo del
        # widget para ver y manejar la musica, no una aplicacion aparte.
        self.hwnd_panel = win32gui.CreateWindowEx(
            self._panel_ex_style(),
            PANEL_CLASS, "gorus-panel",
            win32con.WS_POPUP | win32con.WS_CLIPSIBLINGS,
            0, 0, w, h, 0, None, hinst, None)
        if not self.hwnd_panel:
            self.log("no se pudo crear el panel")
            return False
        self.dib_panel = _Layered(self.hwnd_panel, w, h)
        self._panel_sig = None
        return True

    def _panel_pos(self) -> tuple[int, int, int, int]:
        """Donde va el panel.

        Si el usuario lo arrastro alguna vez, se respeta ESA posicion (en modo gaming
        el panel vive donde lo pusiste, no bailando detras del widget). Si no, va encima
        del widget y, si no entra, debajo.
        """
        k = self._panel_k()
        w, h = panel_mod.size(k, self.cfg)
        guardada = self.cfg.get("panel_pos")
        if isinstance(guardada, (list, tuple)) and len(guardada) == 2:
            try:
                x, y = int(guardada[0]), int(guardada[1])
                mon = win32api.MonitorFromPoint((x + w // 2, y + h // 2), 2)
                mi = win32api.GetMonitorInfo(mon)["Monitor"]
                x = max(mi[0] + 4, min(x, mi[2] - w - 4))
                y = max(mi[1] + 4, min(y, mi[3] - h - 4))
                return (x, y, w, h)
            except Exception:
                pass
        wr = win32gui.GetWindowRect(self.hwnd_widget) if self.hwnd_widget else None
        if not wr:
            return (0, 0, w, h)
        mon = win32api.MonitorFromWindow(self.hwnd_widget, 2)   # NEAREST
        mi = win32api.GetMonitorInfo(mon)["Monitor"]
        hueco = int(round(10 * k))
        x = wr[2] - w                      # alineado al borde derecho del widget
        x = max(mi[0] + 6, min(x, mi[2] - w - 6))
        y = wr[1] - h - hueco
        if y < mi[1] + 6:                  # no entra arriba: va debajo
            y = min(wr[3] + hueco, mi[3] - h - 6)
        y = max(mi[1] + 6, y)
        return (x, y, w, h)

    def toggle_panel(self, on: bool | None = None) -> None:
        """Abre o cierra el panel (clic en la caratula, menu o las pruebas)."""
        if on is None:
            on = not self.panel_visible
        if not on:
            if self.hwnd_panel and win32gui.IsWindow(self.hwnd_panel):
                win32gui.ShowWindow(self.hwnd_panel, win32con.SW_HIDE)
            self.panel_visible = False
            self.panel_hover = -1
            self.panel_drag = None
            self.panel_scrub = None
            self.log("panel cerrado")
            return
        if not self._create_panel():
            return
        x, y, w, h = self._panel_pos()
        try:
            win32gui.SetWindowPos(self.hwnd_panel, 0, x, y, w, h,
                                  win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
        except Exception:
            pass
        self.panel_visible = True
        self._panel_sig = None
        self._panel_int = time.monotonic()
        self._panel_muestrear_fondo()      # con el panel todavia oculto: fondo limpio
        self._panel_render(force=True)
        sin_foco = bool(self.cfg.get("panel_no_robar", False))
        try:
            # Con WS_EX_NOACTIVATE hay que mostrarlo SIN activar: si se activara, el
            # juego perderia el foco (y en pantalla completa se minimiza).
            win32gui.ShowWindow(self.hwnd_panel,
                                win32con.SW_SHOWNOACTIVATE if sin_foco
                                else win32con.SW_SHOW)
            if not sin_foco:
                # Se activa: asi Escape y el clic afuera (WM_ACTIVATE) funcionan
                win32gui.SetForegroundWindow(self.hwnd_panel)
            else:
                # igual que arriba pero sin robar el foco
                win32gui.SetWindowPos(self.hwnd_panel, -1, 0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                                      | win32con.SWP_NOACTIVATE)
        except Exception:
            pass
        self.log("panel abierto en %s%s", (x, y, w, h),
                 " (sin robar el foco)" if sin_foco else "")


    def _panel_render(self, force: bool = False) -> None:
        if not self.panel_visible or not self.hwnd_panel or not self.dib_panel:
            return
        k = self._panel_k()
        vol = self._vol_para_render()
        sig = (self.state.art_key, self.state.title, self.state.display_artist,
               self.state.album, self.state.app_id, self.state.playing,
               int(self.state.live_position() * 2) if self.state.playing else 0,
               self.panel_hover, self.panel_scrub is not None
               and int(self.panel_scrub), vol, self.state.has_session,
               self.state.can_toggle, self.state.can_prev, self.state.can_next,
               self.state.error)
        if not force and sig == self._panel_sig:
            return
        self._panel_sig = sig
        S = k * max(1, int(self.cfg.get("supersample", 3)))
        Lp = panel_mod.layout(self.cfg)
        # Con el fondo transparente, el texto tiene que contrastar con lo que hay
        # DETRAS del panel (un juego claro, un video). Se muestrea una franja justo
        # afuera del panel (adentro esta el panel: la captura devuelve el compuesto).
        # El fondo ya se midio al abrir el panel (capturar en cada cuadro costaba
        # cuatro capturas de pantalla por repintado y trababa la reproduccion).
        base = self._panel_base_para_tema()
        art = None
        if self.cfg.get("show_art", True):
            art = draw.get_art(self.state.art, self.state.art_key,
                               int(round(Lp["tapa"][2] * S)),
                               int(round(Lp["tapa_radio"] * S)))
        img = panel_mod.render(self.state, self.cfg, art=art, volume=vol,
                               hover=self.panel_hover, k=k, scrub=self.panel_scrub,
                               base=base)
        # opacidad de todo el panel (SourceConstantAlpha): en gaming se agradece un
        # overlay que deje ver lo de atras sin tener que buscarlo en el menu
        self.dib_panel.alpha = int(max(60, min(255, self.cfg.get("panel_alpha", 255))))
        self.dib_panel.upload(draw.to_premult_bgra(img))

    def _panel_muestrear_fondo(self) -> bool:
        """Mide el color que hay DETRAS del panel. Devuelve True si pudo.

        Se captura el PROPIO rectangulo del panel **mientras esta oculto**: asi se ve el
        fondo limpio. Con el panel visible la captura devuelve el compuesto (el panel
        mismo), y mirar franjas al lado -lo que hacia antes- le erraba cuando la franja
        tenia contenido claro ajeno: elegia texto oscuro y sobre un fondo oscuro quedaban
        letras huecas con contorno claro (reportado por el usuario, visto en su captura).

        Se guarda tambien el **desvio**: un fondo mezclado no permite decidir bien, asi
        que solo se usa para texto oscuro si es claro Y parejo.
        """
        self._panel_fondo = None
        try:
            from PIL import ImageGrab as _IG
            if not (self.hwnd_panel and win32gui.IsWindow(self.hwnd_panel)):
                return False
            if win32gui.IsWindowVisible(self.hwnd_panel):
                return False
            pr = win32gui.GetWindowRect(self.hwnd_panel)
            if pr[2] <= pr[0] or pr[3] <= pr[1]:
                return False
            im = _IG.grab(bbox=pr, all_screens=True).convert("RGB")
            px = list(im.get_flattened_data())
            if not px:
                return False
            n = float(len(px))
            med = tuple(int(sum(p[i] for p in px) / n) for i in range(3))
            lum = sum(0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in px) / n
            desvio = (sum((0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] - lum) ** 2
                          for p in px) / n) ** 0.5
            self._panel_fondo = (med[0], med[1], med[2], lum, desvio)
            self.log("panel: fondo detras %s (brillo %.0f, desvio %.0f)%s", med, lum, desvio,
                     "" if (lum > 170 and desvio < 45) else " -> texto claro con contorno")
            return True
        except Exception as exc:
            self.log("panel: no se pudo medir el fondo: %r", exc)
            return False

    def _panel_base_para_tema(self):
        """Color de fondo que se le pasa al dibujo, o None.

        Texto oscuro solo si el fondo es CLARO y PAREJO; si el muestreo es dudoso se usa
        un fondo oscuro sintetico (texto claro con contorno oscuro), que se lee sobre
        casi cualquier cosa. Asi una medicion equivocada no deja letras huecas.
        """
        if int(self.cfg.get("panel_bg_alpha", 250)) >= 120 or not self._panel_fondo:
            return None
        r, g, b, lum, desvio = self._panel_fondo
        return (r, g, b) if (lum > 170 and desvio < 45) else (16, 18, 24)

    def _panel_frac_barra(self, x: int) -> float:
        return panel_mod.frac_en_barra(x, self._panel_k(), self.cfg)

    def _panel_seek_a(self, x: int) -> None:
        if not self._can_seek():
            return
        st = self.state
        frac = self._panel_frac_barra(x)
        target = max(st.min_seek, min(frac * st.duration, st.max_seek or st.duration))
        if self.poller.seek(target):
            self.log("panel: salto a %.0f s", target)

    def _panel_vol_a(self, x: int) -> None:
        self._vol_aplicar(panel_mod.frac_en_volumen(x, self._panel_k(), self.cfg))

    def toggle_panel_mute(self) -> None:
        self._vol_toggle_mute()

    def _panel_wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == win32con.WM_PAINT:
                hdc, ps = win32gui.BeginPaint(hwnd)
                try:
                    if self.dib_panel:
                        self.dib_panel.blit(hdc)
                finally:
                    win32gui.EndPaint(hwnd, ps)
                return 0
            if msg == win32con.WM_ERASEBKGND:
                return 1
            if msg == 0x0021 and self.cfg.get("panel_no_robar", False):
                # WM_MOUSEACTIVATE: ademas de WS_EX_NOACTIVATE (que ya impide que el
                # clic lo traiga al frente), se responde MA_NOACTIVATE. Es la receta
                # de los overlays: asi el juego no pierde el foco ni el teclado.
                return 3      # MA_NOACTIVATE
            if msg == win32con.WM_ACTIVATE and (wp & 0xFFFF) == 0:   # WA_INACTIVE
                # Clic afuera: el panel se cierra (como cualquier globo del sistema).
                # En modo gaming NO: ahi el panel nunca tiene el foco, asi que tocar el
                # juego no lo cierra (es lo que se pide para jugar).
                if not self.cfg.get("panel_no_robar", False):
                    self.toggle_panel(False)
                return 0
            if msg == win32con.WM_KEYDOWN and wp == win32con.VK_ESCAPE:
                self.toggle_panel(False)
                return 0
            if msg == win32con.WM_MOUSEMOVE:
                x, y = self._xy(lp)
                self._panel_int = time.monotonic()      # usarlo reinicia el auto-ocultar
                if self.panel_drag is not None:
                    if os.environ.get("GORUS_DEBUG_MOUSE"):
                        self.log("panel: MOUSEMOVE x=%s y=%s arrastre=%s", x, y,
                                 self.panel_drag.get("hit"))
                    self._panel_drag_move(x, y)
                    return 0
                self._panel_int = time.monotonic()
                hit = panel_mod.hit(x, y, self._panel_k(), self.cfg)
                if hit != self.panel_hover:
                    self.panel_hover = hit
                    self._panel_render(force=True)
                try:
                    tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), 0x00000002, hwnd, 0)
                    user32.TrackMouseEvent(ctypes.byref(tme))
                except Exception:
                    pass
                return 0
            if msg == win32con.WM_MOUSELEAVE:
                if self.panel_hover != -1:
                    self.panel_hover = -1
                    self._panel_render(force=True)
                return 0
            if msg == win32con.WM_LBUTTONDOWN:
                x, y = self._xy(lp)
                self._panel_int = time.monotonic()
                hit = panel_mod.hit(x, y, self._panel_k(), self.cfg)
                if os.environ.get("GORUS_DEBUG_MOUSE"):
                    self.log("panel: LBUTTONDOWN x=%s y=%s hit=%s captura=%s",
                             x, y, hit, hex(win32gui.GetCapture()))
                if hit in (3, 4):
                    self.panel_drag = {"hit": hit, "x0": x, "y0": y, "moved": False}
                    if hit == 3:
                        self.panel_scrub = (panel_mod.frac_en_barra(
                            x, self._panel_k(), self.cfg) * self.state.duration)
                    else:
                        self._panel_vol_a(x)
                    try:
                        win32gui.SetCapture(hwnd)
                        win32gui.SetCursor(win32gui.LoadCursor(0, IDC_SIZEWE))
                    except Exception:
                        pass
                    self._panel_render(force=True)
                elif hit == -1:
                    # Arrastrar el panel desde el fondo: se mueve con el mouse. Necesita
                    # CAPTURA igual que la barra: al mover el panel, el cursor se sale de
                    # la ventana enseguida y sin captura no llegan mas WM_MOUSEMOVE (el
                    # panel se quedaba pegado, quejado por el usuario).
                    self.panel_drag = {"hit": -1, "x0": x, "y0": y, "moved": False,
                                       "pantalla": win32gui.GetCursorPos()}
                    try:
                        win32gui.SetCapture(hwnd)
                        win32gui.SetCursor(win32gui.LoadCursor(0, IDC_SIZEALL))
                    except Exception:
                        pass
                return 0
            if msg == win32con.WM_LBUTTONUP:
                x, y = self._xy(lp)
                if os.environ.get("GORUS_DEBUG_MOUSE"):
                    self.log("panel: LBUTTONUP x=%s y=%s arrastre=%s", x, y,
                             self.panel_drag is not None)
                if self.panel_drag is not None:
                    self._panel_end_drag(x)
                    return 0
                hit = panel_mod.hit(x, y, self._panel_k(), self.cfg)
                if hit == 0:
                    self.poller.prev_track()
                elif hit == 1:
                    self.poller.toggle()
                elif hit == 2:
                    self.poller.next_track()
                elif hit == 5:
                    self.toggle_panel_mute()
                elif hit in (6, 7):
                    self.toggle_panel(False)
                return 0
            if msg == win32con.WM_CAPTURECHANGED:
                if self.panel_drag is not None:
                    self.panel_drag = None
                    self.panel_scrub = None
                    self._panel_render(force=True)
                return 0
            if msg == win32con.WM_MOUSEWHEEL:
                steps = ctypes.c_short((wp >> 16) & 0xFFFF).value / 120.0
                if steps:
                    c = win32gui.ScreenToClient(hwnd, win32gui.GetCursorPos())
                    ctrl = win32api.GetKeyState(win32con.VK_CONTROL) < 0
                    shift = win32api.GetKeyState(win32con.VK_SHIFT) < 0
                    if panel_mod.hit(*c, self._panel_k(), self.cfg) in (4, 5):
                        self._vol_step(steps, fino=ctrl)
                    elif ctrl and not shift:
                        self._seek_by(steps * self._seek_fino())
                    elif shift and not ctrl:
                        self._seek_by(steps * self._seek_grueso())
                    else:
                        self._seek_by(steps * self._seek_step())
                return 0
            if msg == win32con.WM_DESTROY:
                self.hwnd_panel = 0
                self.panel_visible = False
                return 0
        except Exception as exc:
            self.log("panel proc fallo: %r", exc)
        return win32gui.DefWindowProc(hwnd, msg, wp, lp)

    @staticmethod
    def _xy(lp: int) -> tuple:
        """x, y de un lParam de mouse, con signo.

        Con la captura puesta el cursor se sale de la ventana y Windows manda
        coordenadas de cliente NEGATIVAS: leidas sin signo, y=-142 llega como 65394.
        """
        x = lp & 0xFFFF
        y = (lp >> 16) & 0xFFFF
        return (x - 0x10000 if x >= 0x8000 else x, y - 0x10000 if y >= 0x8000 else y)

    def _panel_drag_move(self, x: int, y: int) -> None:
        d = self.panel_drag
        if not d:
            return
        if abs(x - d["x0"]) >= 3 or abs(y - d["y0"]) >= 3:
            d["moved"] = True
        if d["hit"] == 3:
            self.panel_scrub = (panel_mod.frac_en_barra(x, self._panel_k(), self.cfg)
                                * self.state.duration)
            try:
                win32gui.SetCursor(win32gui.LoadCursor(0, IDC_SIZEWE))
            except Exception:
                pass
            self._panel_render(force=True)
        elif d["hit"] == 4:
            self._panel_vol_a(x)
            self._panel_render(force=True)
        elif d["hit"] == -1:
            # mover el panel: se lee el cursor en coordenadas de pantalla
            px, py = win32gui.GetCursorPos()
            sx, sy = d.get("pantalla") or (px, py)
            wr = win32gui.GetWindowRect(self.hwnd_panel)
            if os.environ.get("GORUS_DEBUG_MOUSE"):
                self.log("panel: mover delta=(%s,%s) desde %s", px - sx, py - sy, wr)
            win32gui.SetWindowPos(self.hwnd_panel, 0, wr[0] + (px - sx), wr[1] + (py - sy),
                                  0, 0, win32con.SWP_NOSIZE | win32con.SWP_NOZORDER
                                  | win32con.SWP_NOACTIVATE)
            d["pantalla"] = (px, py)

    def _panel_end_drag(self, x: int) -> None:
        d, self.panel_drag = self.panel_drag, None
        if d and d.get("hit") == -1 and self.hwnd_panel:
            # el usuario lo dejo ahi: se recuerda (en modo gaming el panel vive donde
            # lo pusiste, no saltando detras del widget)
            try:
                wr = win32gui.GetWindowRect(self.hwnd_panel)
                self.cfg["panel_pos"] = [wr[0], wr[1]]
                cfgmod.save(self.cfg)
                self.log("panel: posicion guardada en (%d, %d)", wr[0], wr[1])
            except Exception:
                pass
        scrub, self.panel_scrub = self.panel_scrub, None
        try:
            win32gui.ReleaseCapture()
        except Exception:
            pass
        if not d:
            return
        if d["hit"] == 3:
            if scrub is None:
                scrub = (panel_mod.frac_en_barra(x, self._panel_k(), self.cfg)
                         * self.state.duration)
            self._panel_seek_a(x)
        elif d["hit"] == 4:
            self._panel_vol_a(x)
        self._panel_render(force=True)

    def _panel_tick(self) -> None:
        """El panel se refresca con el mismo ciclo del widget."""
        if not self.panel_visible or not self.hwnd_panel:
            return
        if not win32gui.IsWindow(self.hwnd_panel):
            self.hwnd_panel = 0
            self.panel_visible = False
            return
        # auto-ocultar: en modo gaming el panel se va solo si no lo estas usando
        auto = float(self.cfg.get("panel_auto_hide_s", 0) or 0)
        if auto > 0 and (time.monotonic() - self._panel_int) > auto:
            self.log("panel: se oculta solo (%.0f s sin usarlo)", auto)
            self.toggle_panel(False)
            return
        self._panel_render()

    # ------------------------------------------------- ajustes del panel
    def set_panel_size(self, tam: str, save: bool = True) -> None:
        """Tamano del panel: "normal" o "chico" (hay que rehacer la ventana)."""
        tam = "chico" if str(tam).lower().startswith(("chi", "com", "min")) else "normal"
        if self.cfg.get("panel_size") == tam:
            return
        self.cfg["panel_size"] = tam
        visible = self.panel_visible
        self._panel_olvidar()
        if save:
            cfgmod.save(self.cfg)
        self.log("panel: tamano %s", tam)
        if visible:
            self.toggle_panel(True)

    def set_panel_ajuste(self, clave: str, valor, save: bool = True) -> None:
        """Cambia un ajuste del panel en vivo (menu y pruebas)."""
        if clave == "panel_size":
            self.set_panel_size(valor, save=save)
            return
        self.cfg[clave] = valor
        if save:
            cfgmod.save(self.cfg)
        if clave in ("panel_no_robar", "panel_topmost", "panel_clics_al_juego"):
            self._panel_aplicar_estilos()
        self._panel_sig = None
        self._panel_render(force=True)
        self.log("panel: %s = %s", clave, valor)

    def set_panel_gaming(self, on: bool = True, save: bool = True) -> None:
        """Modo gaming: chico, sin robar el foco, arriba de todo, se oculta solo y
        aparece al cambiar de cancion. Un solo interruptor en el menu."""
        on = bool(on)
        self.cfg["panel_mode"] = "gaming" if on else "normal"
        if on:
            # Fijo (sin auto-ocultar ni HUD: si lo cerras, se queda cerrado) y con el
            # FONDO transparente. El alfa de todo el panel queda en 255 para que los
            # textos e iconos se lean nitidos sobre lo que haya detras.
            self.cfg.update({"panel_size": "chico", "panel_no_robar": True,
                             "panel_topmost": True, "panel_auto_hide_s": 0,
                             "panel_hud": False, "panel_alpha": 255,
                             "panel_bg_alpha": PANEL_BG_ALPHAS[0][0],
                             "panel_clics_al_juego": False})
        else:
            self.cfg.update({"panel_size": "normal", "panel_no_robar": False,
                             "panel_topmost": False, "panel_auto_hide_s": 0,
                             "panel_hud": False, "panel_alpha": 255,
                             "panel_bg_alpha": PANEL_BG_ALPHAS[0][0],
                             "panel_clics_al_juego": False})
        visible = self.panel_visible
        self._panel_olvidar()
        if save:
            cfgmod.save(self.cfg)
        self.log("panel: modo %s", "gaming" if on else "normal")
        if visible:
            self.toggle_panel(True)

    def panel_anclar_al_widget(self, save: bool = True) -> None:
        """Olvida la posicion arrastrada: el panel vuelve a aparecer sobre el widget."""
        self.cfg["panel_pos"] = None
        if save:
            cfgmod.save(self.cfg)
        if self.panel_visible:
            self._panel_sig = None
            self.toggle_panel(False)
            self.toggle_panel(True)
        self.log("panel: vuelve a anclarse al widget")

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

            # Submenus de color: la barra de progreso y las ondas por separado
            subs = []
            for base_id, key, titulo in ((30, "progress_color", "Color de la barra"),
                                         (40, "waves_color", "Color de las ondas")):
                sub = win32gui.CreatePopupMenu()
                actual = draw.parse_color(self.cfg.get(key))
                conocidos = [draw.parse_color(v) for v, _ in COLOR_CHOICES if v]
                if actual is not None and actual not in conocidos:
                    # Elegido a mano en config.json: se muestra cual esta activo (no
                    # se puede clickear, se cambia editando el archivo).
                    win32gui.AppendMenu(sub, win32con.MF_STRING | win32con.MF_CHECKED
                                        | win32con.MF_GRAYED, base_id + 100,
                                        f"Personalizado ({draw.hex_color(actual)})")
                    win32gui.AppendMenu(sub, win32con.MF_SEPARATOR, 0, "")
                for i, (valor, etiqueta) in enumerate(COLOR_CHOICES):
                    flags = win32con.MF_STRING
                    if draw.parse_color(valor) == actual:
                        flags |= win32con.MF_CHECKED
                    win32gui.AppendMenu(sub, flags, base_id + i, etiqueta)
                subs.append((sub, titulo))

            # Submenu de monitor: en que barra de tareas vive el widget. Solo se
            # muestra si hay mas de una barra (o sea, si hay varios monitores); en
            # Windows 10 cada monitor tiene la suya.
            mon_sub = 0
            barras = list_bars()
            if len(barras) > 1:
                mon_sub = win32gui.CreatePopupMenu()
                activo = self.cfg.get("taskbar_monitor") or None
                for i, b in enumerate(barras):
                    mr = b.get("mon_rect") or b["rect"]
                    flags = win32con.MF_STRING
                    if (None if b["primario"] else b["monitor"]) == activo:
                        flags |= win32con.MF_CHECKED
                    win32gui.AppendMenu(
                        mon_sub, flags, 50 + i,
                        "%s  (%dx%d)" % (b["nombre"], mr[2] - mr[0], mr[3] - mr[1]))

            # Submenu del panel: agrupa todo lo del mini reproductor, incluido el
            # modo gaming en un solo interruptor.
            pan_sub = win32gui.CreatePopupMenu()

            def pan_check(ident, etiqueta, marcado):
                flags = win32con.MF_STRING | (win32con.MF_CHECKED if marcado else 0)
                win32gui.AppendMenu(pan_sub, flags, ident, etiqueta)

            gaming = str(self.cfg.get("panel_mode", "normal")).lower() == "gaming"
            pan_check(60, "Modo gaming (chico y sin robar el foco)", gaming)
            win32gui.AppendMenu(pan_sub, win32con.MF_SEPARATOR, 0, "")
            pan_check(61, "Tamano chico", str(self.cfg.get("panel_size", "normal")) == "chico")
            pan_check(64, "Dejar pasar los clics al juego", bool(self.cfg.get("panel_clics_al_juego", False)))
            alpha_sub = win32gui.CreatePopupMenu()
            alpha_actual = int(self.cfg.get("panel_alpha", 255))
            for i, (val, etiqueta) in enumerate(PANEL_ALPHAS):
                flags = win32con.MF_STRING
                if val == alpha_actual:
                    flags |= win32con.MF_CHECKED
                win32gui.AppendMenu(alpha_sub, flags, 70 + i, etiqueta)
            win32gui.AppendMenu(pan_sub, win32con.MF_POPUP | win32con.MF_STRING,
                                alpha_sub, "Opacidad de todo el panel")
            fondo_sub = win32gui.CreatePopupMenu()
            fondo_actual = int(self.cfg.get("panel_bg_alpha", 250))
            for i, (val, etiqueta) in enumerate(PANEL_BG_ALPHAS):
                flags = win32con.MF_STRING
                if val == fondo_actual:
                    flags |= win32con.MF_CHECKED
                win32gui.AppendMenu(fondo_sub, flags, 75 + i, etiqueta)
            win32gui.AppendMenu(pan_sub, win32con.MF_POPUP | win32con.MF_STRING,
                                fondo_sub, "Fondo")
            win32gui.AppendMenu(pan_sub, win32con.MF_SEPARATOR, 0, "")
            win32gui.AppendMenu(pan_sub, win32con.MF_STRING, 74,
                                "Volver a anclarlo al widget")

            # Menu corto a proposito: queda solo lo que NO se puede hacer de otra
            # forma. Sacado (sigue en config.json, documentado en el README): atrasar y
            # adelantar (barra, rueda, atajos), silenciar y volumen (celda del altavoz,
            # rueda, atajos), mover paso a paso y centrar (se arrastra con el mouse),
            # mostrar el altavoz, apagar los atajos, abrir la carpeta del proyecto, y los
            # interruptores internos del panel que ahora fija el modo gaming.
            items = [
                ("item", 1, "Ocultar widget" if self.visible else "Mostrar widget", True),
                ("check", 26, "Abrir el panel (clic en la caratula)", bool(self.panel_visible)),
                ("popup", pan_sub, "Panel", True),
                ("sep", 0, "", None),
                ("popup", alpha_sub, "Fondo del widget", True),
                ("popup", subs[0][0], subs[0][1], True),
                ("popup", subs[1][0], subs[1][1], True),
                *([("popup", mon_sub, "Monitor", True)] if mon_sub else []),
                ("sep", 0, "", None),
                ("check", 15, "Ondas de sonido", bool(self.cfg.get("show_waves", False))),
                ("sep", 0, "", None),
                ("item", 7, f"Ancho: {self.cfg.get('width', 260)} px", False),
                ("item", 8, "   Mas ancho", True),
                ("item", 9, "   Mas angosto", True),
                ("sep", 0, "", None),
                ("item", 6, "Volver al extremo derecho", True),
                ("item", 10, "Refrescar ahora", True),
                ("sep", 0, "", None),
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
        elif cmd == 15:
            self.set_waves(not self.cfg.get("show_waves", False))
        elif cmd == 26:
            self.toggle_panel()
        elif cmd == 60:
            self.set_panel_gaming(not (str(self.cfg.get("panel_mode", "normal")).lower()
                                       == "gaming"))
        elif cmd == 61:
            self.set_panel_size("chico" if str(self.cfg.get("panel_size", "normal"))
                                != "chico" else "normal")
        elif cmd == 64:
            self.set_panel_ajuste("panel_clics_al_juego",
                                  not self.cfg.get("panel_clics_al_juego", False))
        elif 70 <= cmd <= 70 + len(PANEL_ALPHAS) - 1:
            self.set_panel_ajuste("panel_alpha", PANEL_ALPHAS[cmd - 70][0])
        elif 75 <= cmd <= 75 + len(PANEL_BG_ALPHAS) - 1:
            self.set_panel_ajuste("panel_bg_alpha", PANEL_BG_ALPHAS[cmd - 75][0])
        elif cmd == 74:
            self.panel_anclar_al_widget()
        elif 30 <= cmd <= 30 + len(COLOR_CHOICES) - 1:
            self.set_color("progress_color", COLOR_CHOICES[cmd - 30][0])
        elif 40 <= cmd <= 40 + len(COLOR_CHOICES) - 1:
            self.set_color("waves_color", COLOR_CHOICES[cmd - 40][0])
        elif 50 <= cmd <= 59:
            barras = list_bars()
            i = cmd - 50
            if i < len(barras):
                b = barras[i]
                self.set_taskbar(None if b["primario"] else b["monitor"])
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
        elif cmd == 12:
            win32gui.PostMessage(self.hwnd_ctl, win32con.WM_CLOSE, 0, 0)


def run(cfg: dict, embed: bool = True, log_path: str | None = None) -> int:
    return WidgetApp(cfg, embed=embed, log_path=log_path).run()
