"""Incrustacion en la barra de tareas de Windows 10.

Windows 10 no tiene API de "bandas" (se elimino despues de Vista), pero si acepta
ventanas hijas de la barra de tareas. El truco, igual que hace TrafficMonitor:

  1. crear la ventana como hija de la barra (WS_CHILD)
  2. apoyarse contra el borde izquierdo del bloque de la derecha (noticias, reloj)
  3. encoger el contenedor de la lista de tareas para liberar ese ancho
  4. restaurar el ancho natural al salir

Cada monitor tiene su propia barra, y **no tienen la misma estructura**:

  | monitor   | barra                  | contenedor de la lista | ancla           |
  |-----------|------------------------|------------------------|-----------------|
  | principal | Shell_TrayWnd          | ReBarWindow32          | DynamicContent2 |
  | secundario| Shell_SecondaryTrayWnd | WorkerW                | ClockButton     |

Ojo con las coordenadas: en ventanas hijas, SetWindowPos usa coordenadas
relativas al CLIENTE del padre, no a la pantalla. Mezclarlas desplaza la barra
fuera de su lugar.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os

import win32api
import win32con
import win32gui

# Anclas de la barra, en orden de preferencia (de derecha a izquierda): el bloque
# de noticias de la principal, el reloj de las secundarias, la bandeja.
ANCHOR_CLASSES = ("DynamicContent2", "ClockButton", "TrayNotifyWnd")
# Contenedor de la lista de tareas: ReBarWindow32 en la principal, WorkerW (el
# padre de MSTaskListWClass) en las secundarias.
CONTAINER_CLASSES = ("ReBarWindow32", "WorkerW")
TRAY_CLASS = "Shell_TrayWnd"
SECONDARY_CLASS = "Shell_SecondaryTrayWnd"
# La barra nueva (Windows 11) sigue teniendo Shell_TrayWnd, ReBarWindow32 y el reloj,
# pero su contenido lo dibuja XAML: el area entera de la barra queda tapada por el
# puente de composicion y la lista de tareas legacy (MSTaskListWClass) se apaga.
# Son pistas ESTRUCTURALES, no la version de Windows: en la 24H2/25H2 (build 26300
# probado) el ReBar y el ancla existen y estan "visibles", asi que preguntar solo por
# ellos daba "se puede incrustar" y el widget terminaba invisible, debajo del puente.
XAML_BRIDGE_CLASS = "Windows.UI.Composition.DesktopWindowContentBridge"

user32 = ctypes.windll.user32


def _child(parent: int, cls: str) -> int:
    try:
        return win32gui.FindWindowEx(parent, 0, cls, None)
    except Exception:
        return 0


def _hijo_con(padre: int, clase_nieta: str) -> int:
    """Primer hijo directo de `padre` que contiene una ventana de esa clase."""
    h = 0
    while True:
        h = win32gui.FindWindowEx(padre, h, None, None)
        if not h:
            return 0
        if _child(h, clase_nieta) or win32gui.GetClassName(h) == clase_nieta:
            return h


def list_bars() -> list[dict]:
    """Barras de tareas disponibles, ordenadas por monitor.

    Devuelve una por monitor: la principal (`Shell_TrayWnd`) y una por monitor
    secundario (`Shell_SecondaryTrayWnd`). Cada una trae `monitor` (el nombre del
    dispositivo, que es lo que se guarda en la configuracion) y `nombre` para el
    menu.
    """
    barras = []

    def cb(h, _):
        try:
            clase = win32gui.GetClassName(h)
            if clase in (TRAY_CLASS, SECONDARY_CLASS) and win32gui.IsWindowVisible(h):
                rect = win32gui.GetWindowRect(h)
                if rect[2] - rect[0] <= 0:
                    return
                info = win32api.GetMonitorInfo(win32api.MonitorFromRect(rect))
                barras.append({"tray": h, "clase": clase, "monitor": info["Device"],
                               "mon_rect": info["Monitor"], "rect": rect,
                               "primario": clase == TRAY_CLASS})
        except Exception:
            pass

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    barras.sort(key=lambda b: (b["mon_rect"][0], b["mon_rect"][1]))
    for i, b in enumerate(barras):
        b["nombre"] = "Principal" if b["primario"] else f"Monitor {i + 1}"
    return barras


def monitores() -> list[dict]:
    """Monitores conectados, ordenados como `list_bars()`: de izquierda a derecha.

    Cada uno trae `monitor` (el nombre del dispositivo, que es lo que se guarda en la
    configuracion), `rect` (el monitor entero), `trabajo` (el area util, sin la barra) y
    `franja` (la tira de abajo donde apoya el widget flotante).

    En el modo flotante esta es la lista que ofrece el menu: ahi no hay una barra por
    monitor que elegir (Windows 11 dibuja una sola), hay un monitor sobre el que apoyar
    la ventana. Con `list_bars()` no alcanza porque en Windows 11 la barra de los otros
    monitores puede no existir.
    """
    mons = []
    try:
        for hmon in win32api.EnumDisplayMonitors(None, None):
            h = hmon[0] if isinstance(hmon, (list, tuple)) else hmon
            info = win32api.GetMonitorInfo(h)
            mons.append({"monitor": info["Device"], "rect": tuple(info["Monitor"]),
                         "mon_rect": tuple(info["Monitor"]),
                         "trabajo": tuple(info["Work"]),
                         "primario": bool(info.get("Flags", 0) & 1)})
    except Exception:
        pass
    mons.sort(key=lambda m: (m["rect"][0], m["rect"][1]))
    for i, m in enumerate(mons):
        m["nombre"] = "Principal" if m["primario"] else f"Monitor {i + 1}"
        # Alto de la barra de ESE monitor: sale del area de trabajo. Con la barra
        # oculta o a un costado no hay diferencia abajo y se usa el alto tipico.
        alto = m["rect"][3] - m["trabajo"][3]
        m["alto"] = max(24, int(alto)) if alto > 0 else 48
        m["franja"] = (m["rect"][0], m["rect"][3] - m["alto"],
                       m["rect"][2], m["rect"][3])
    return mons


def barra_en_posicion_util(barra: dict | None) -> bool:
    """True si el widget se puede incrustar en esa barra.

    La geometria del widget (el tramo libre, encoger la lista de tareas, el ancho del chip)
    asume una barra horizontal pegada al borde de abajo, que es como viene Windows. Si la
    barra esta a un costado o arriba, el widget quedaria mal ubicado y encima tapando la
    barra: ahi conviene el modo flotante, que no la toca.

    La regla es geometrica a proposito (mide el rectangulo de la barra contra el del monitor)
    en vez de preguntar por la version o el idioma de Windows.
    """
    if not barra:
        return False
    r = barra.get("rect") or (0, 0, 0, 0)
    m = barra.get("mon_rect") or r
    ancho, alto = r[2] - r[0], r[3] - r[1]
    if ancho <= 0 or alto <= 0:
        return False
    if ancho < alto * 2:            # mas alta que ancha: esta a un costado
        return False
    return r[3] >= m[3] - 2         # pegada al borde de abajo del monitor


def barra_xaml(tray: int) -> bool:
    """True si esa barra la dibuja XAML (Windows 11) y no admite ventanas hijas.

    Se mira lo que hay, no la version: si el puente de composicion tapa el area de la
    barra, o si la lista de tareas legacy quedo apagada (la barra nueva dibuja los
    botones por su cuenta), no hay donde alojar el widget por mas que ReBarWindow32
    siga existiendo.
    """
    try:
        h = _child(tray, XAML_BRIDGE_CLASS)
        if h and win32gui.IsWindowVisible(h):
            return True
        rebar = _child(tray, "ReBarWindow32")
        if rebar:
            caja = _child(rebar, "MSTaskSwWClass") or rebar
            lista = _child(caja, "MSTaskListWClass")
            if lista and not win32gui.IsWindowVisible(lista):
                return True
    except Exception:
        pass
    return False


def motivo_no_incrustable() -> str | None:
    """Por que no se puede incrustar el widget (None = si se puede).

    Devuelve un texto corto y humano, que es el que termina en el log: cuando algo no anda
    en la maquina de otro, el log tiene que explicar la decision solo.
    """
    try:
        h = TaskbarHost()
        if not (h.refresh() and h.container and h.anchor):
            return "esta version de Windows no admite ventanas en la barra (Windows 11)"
        if barra_xaml(h.tray):
            return ("la barra de tareas es la nueva de Windows 11 (dibujada por XAML): "
                    "no se puede alojar una ventana")
        if not barra_en_posicion_util(h.barra):
            return "la barra de tareas no esta abajo"
        return None
    except Exception as exc:
        return "no pude revisar la barra (%s)" % (exc,)


def barras_usables() -> bool:
    """True si hay una barra donde incrustar el widget (Windows 10 con la barra abajo)."""
    return motivo_no_incrustable() is None


class TaskbarHost:
    """Gestiona el anclaje, el espacio reservado y la restauracion.

    `monitor` es el nombre del dispositivo del monitor cuya barra se usa
    (`None` = la principal); se guarda en la configuracion para respetarlo al
    arrancar.
    """

    def __init__(self, log=lambda *a, **k: None, monitor: str | None = None):
        self.log = log
        self.monitor = monitor or None
        self.tray = 0
        self.container = 0     # contenedor de la lista de tareas (ReBar o WorkerW)
        self.anchor = 0        # bloque de la derecha contra el que se apoya el widget
        self.barra = None      # datos de la barra elegida (list_bars)
        self._orig_rebar = None  # (x_rel, y_rel, ancho, alto)

    # ------------------------------------------------------------------ estado
    @property
    def available(self) -> bool:
        return bool(self.tray and win32gui.IsWindow(self.tray))

    def _resolver_contenedor(self, tray: int) -> int:
        """El que hay que encoger para liberar el ancho del widget.

        En la principal es ReBarWindow32 (la lista de tareas cuelga de ahi). En las
        secundarias no hay rebar: la lista vive dentro de un WorkerW, asi que hay que
        buscar el WorkerW que la contiene (no cualquier WorkerW de la barra).
        """
        for cls in CONTAINER_CLASSES:
            h = _child(tray, cls)
            if not h or not win32gui.IsWindowVisible(h):
                continue
            if cls == "WorkerW" and not (_child(h, "MSTaskListWClass")
                                         or win32gui.GetClassName(h) == "MSTaskListWClass"):
                continue
            return h
        return _hijo_con(tray, "MSTaskListWClass")

    def _resolver_ancla(self, tray: int) -> int:
        for cls in ANCHOR_CLASSES:
            h = _child(tray, cls)
            if h and win32gui.IsWindowVisible(h):
                return h
        return 0

    def select(self, monitor: str | None) -> None:
        """Elige en que barra vive el widget (None = la principal)."""
        self.monitor = monitor or None
        self.container = 0
        self.anchor = 0
        self.tray = 0
        self.refresh()

    def refresh(self) -> bool:
        barras = list_bars()
        elegida = None
        if self.monitor:
            for b in barras:
                if b["monitor"] == self.monitor:
                    elegida = b
                    break
            if elegida is None and barras:
                self.log("no encuentro la barra de %s; uso la principal", self.monitor)
                self.monitor = None
        if elegida is None:
            for b in barras:
                if b["primario"]:
                    elegida = b
                    break
        if elegida is None:
            self.tray = self.container = self.anchor = 0
            self.barra = None
            return False
        self.tray = elegida["tray"]
        self.barra = elegida
        self.container = self._resolver_contenedor(self.tray)
        self.anchor = self._resolver_ancla(self.tray)
        return True

    def barra_en(self, x: int) -> dict | None:
        """Barra cuyo tramo horizontal contiene esa x de pantalla."""
        for b in list_bars():
            if b["rect"][0] <= x < b["rect"][2]:
                return b
        return None

    def metrics(self) -> dict:
        """Medidas en px reales, listas para el renderizador."""
        tl, tt, tr, tb = win32gui.GetWindowRect(self.tray)
        h = max(24, tb - tt)
        return {"taskbar_h": h, "left": tl, "top": tt,
                "scale": h / 40.0, "width": tr - tl}

    def _rect(self, hwnd: int) -> tuple[int, int, int, int]:
        try:
            return win32gui.GetWindowRect(hwnd)
        except Exception:
            return (0, 0, 0, 0)

    def _anchor_rect(self) -> tuple[int, int, int, int]:
        """Rectangulo del ancla. Si la barra no tiene (reloj oculto, etc.), se usa
        el borde derecho de la barra, asi el widget nunca se sale de su monitor."""
        r = self._rect(self.anchor)
        if r[0] or r[2]:
            return r
        tl, tt, tr, tb = self._rect(self.tray)
        return (tr - 8, tt, tr, tb)

    def free_span(self) -> tuple[int, int]:
        """(borde izquierdo del hueco disponible, borde derecho) en coords de pantalla."""
        rb = self._rect(self.container)
        an = self._anchor_rect()
        return rb[0], an[0]

    # ------------------------------------------------------------- posicion libre
    def x_limits(self, width: int, min_free: int = 140) -> tuple[int, int]:
        """Rango de x (coords de pantalla) donde puede vivir el widget.

        El limite izquierdo deja siempre `min_free` px de lista de tareas; el
        derecho es el ancla menos el ancho del widget. Si el widget se ubica en el
        medio, el tramo entre el y el ancla queda como fondo de barra vacio: es el
        precio de poder moverlo a cualquier lado.
        """
        rb = self._rect(self.container)
        an = self._anchor_rect()
        lo = rb[0] + max(60, int(min_free))
        hi = max(lo, an[0] - width)
        return lo, hi

    def clamp_x(self, x: int, width: int, min_free: int = 140) -> int:
        lo, hi = self.x_limits(width, min_free)
        return int(max(lo, min(hi, x)))

    def frac_from_x(self, x: int, width: int, min_free: int = 140) -> float:
        lo, hi = self.x_limits(width, min_free)
        if hi <= lo:
            return 1.0
        return max(0.0, min(1.0, (x - lo) / float(hi - lo)))

    def x_from_frac(self, frac: float, width: int, min_free: int = 140) -> int:
        lo, hi = self.x_limits(width, min_free)
        f = max(0.0, min(1.0, float(frac)))
        return int(round(lo + f * (hi - lo)))

    def target_x(self, width: int, min_tasklist: int, frac: float | None = None,
                 min_free: int = 140) -> int:
        """x del widget en coords de pantalla. `frac=None` = extremo derecho."""
        rb = self._rect(self.container)
        an = self._anchor_rect()
        if not rb[0]:
            return 0
        if frac is None:
            # Comportamiento clasico: pegado al ancla, sin comerse nunca mas que el
            # minimo de lista de tareas configurado.
            return max(an[0] - width, rb[0] + int(min_tasklist))
        return self.x_from_frac(frac, width, min_free)

    # -------------------------------------------------------------- operaciones
    def reserve(self, width: int, min_tasklist: int, x: int | None = None,
                frac: float | None = None, min_free: int = 140) -> int:
        """Encoge la lista de tareas para hacer sitio. Devuelve la x del widget
        en coordenadas relativas al cliente de la barra.

        Con `x` se coloca en una posicion exacta (arrastre); con `frac` se usa la
        posicion fraccionaria guardada; sin ninguno de los dos, en el extremo.
        """
        if not self.available:
            return 0
        tl, tt, tr, tb = win32gui.GetWindowRect(self.tray)
        rb = self._rect(self.container)
        if not rb[0]:
            return 0
        if x is None:
            x = self.target_x(width, min_tasklist, frac, min_free)
        # no dejar la lista de tareas por debajo del minimo configurado
        new_w = max(80, (x - 2) - rb[0])
        if abs((rb[2] - rb[0]) - new_w) > 1:
            win32gui.SetWindowPos(self.container, 0, 0, 0, new_w, rb[3] - rb[1],
                                  win32con.SWP_NOMOVE | win32con.SWP_NOZORDER
                                  | win32con.SWP_NOACTIVATE)
        return x - tl

    def place(self, hwnd: int, x_rel: int, height: int) -> None:
        if not self.available or not win32gui.IsWindow(hwnd):
            return
        win32gui.SetWindowPos(hwnd, 0, x_rel, 0, 0, 0,
                              win32con.SWP_NOSIZE | win32con.SWP_NOZORDER
                              | win32con.SWP_NOACTIVATE)

    def detach_widget(self, hwnd: int) -> None:
        """Saca el widget y devuelve el espacio a la lista de tareas."""
        try:
            if hwnd and win32gui.IsWindow(hwnd):
                win32gui.DestroyWindow(hwnd)
        except Exception:
            pass
        self.restore()

    def restore(self) -> None:
        """Devuelve el contenedor de la lista de tareas a su ancho natural."""
        if not self.refresh() or not self.container:
            return
        tl, tt, tr, tb = win32gui.GetWindowRect(self.tray)
        rb = self._rect(self.container)
        an = self._anchor_rect()
        if not rb[0]:
            return
        want = max(80, an[0] - rb[0])
        if abs((rb[2] - rb[0]) - want) > 1:
            win32gui.SetWindowPos(self.container, 0, rb[0] - tl, 0, want, tb - tt,
                                  win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
            self.log("espacio devuelto a la lista de tareas (ancho %d)", want)

    def base_color(self, x_rel: int, width: int, height: int) -> tuple:
        """Muestrea el color de la barra justo donde va el widget, para que el
        chip translucido se mezcle con el fondo real."""
        try:
            tl, tt, tr, tb = win32gui.GetWindowRect(self.tray)
            hdc = win32gui.GetWindowDC(self.tray)
            try:
                samples = []
                for fx in (0.2, 0.5, 0.8):
                    for fy in (0.25, 0.6):
                        px = int(tl + x_rel + width * fx)
                        py = int(tt + height * fy)
                        v = win32gui.GetPixel(hdc, px - tl, py - tt)
                        r, g, b = v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF
                        samples.append((r, g, b))
                if samples:
                    n = len(samples)
                    return (sum(s[0] for s in samples) // n,
                            sum(s[1] for s in samples) // n,
                            sum(s[2] for s in samples) // n)
            finally:
                win32gui.ReleaseDC(self.tray, hdc)
        except Exception:
            pass
        return (26, 28, 36)


def taskbar_height() -> int:
    tray = win32gui.FindWindow(TRAY_CLASS, None)
    if not tray:
        return 40
    tl, tt, tr, tb = win32gui.GetWindowRect(tray)
    return max(24, tb - tt)


def set_dpi_aware() -> None:
    """Sin esto Windows escala la ventana por nosotros y todo sale borroso."""
    try:
        # -4 == DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
