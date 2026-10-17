"""Incrustacion en la barra de tareas de Windows 10.

Windows 10 no tiene API de "bandas" (se elimino despues de Vista), pero si acepta
ventanas hijas de Shell_TrayWnd. El truco, igual que hace TrafficMonitor:

  1. crear la ventana como hija de Shell_TrayWnd (WS_CHILD)
  2. apoyarse contra el borde izquierdo del bloque de noticias/bandeja
  3. encoger la lista de tareas (ReBarWindow32) para liberar ese ancho
  4. restaurar el ancho natural al salir

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

# Anclas de la barra, en orden de preferencia (de derecha a izquierda)
ANCHOR_CLASSES = ("DynamicContent2", "TrayNotifyWnd")
REBAR_CLASS = "ReBarWindow32"
TRAY_CLASS = "Shell_TrayWnd"

user32 = ctypes.windll.user32


def _child(parent: int, cls: str) -> int:
    try:
        return win32gui.FindWindowEx(parent, 0, cls, None)
    except Exception:
        return 0


class TaskbarHost:
    """Gestiona el anclaje, el espacio reservado y la restauracion."""

    def __init__(self, log=lambda *a, **k: None):
        self.log = log
        self.tray = 0
        self.rebar = 0
        self.anchor = 0
        self._orig_rebar = None  # (x_rel, y_rel, ancho, alto)

    # ------------------------------------------------------------------ estado
    @property
    def available(self) -> bool:
        return bool(self.tray and win32gui.IsWindow(self.tray))

    def refresh(self) -> bool:
        self.tray = win32gui.FindWindow(TRAY_CLASS, None)
        if not self.tray:
            return False
        self.rebar = _child(self.tray, REBAR_CLASS)
        self.anchor = 0
        for cls in ANCHOR_CLASSES:
            h = _child(self.tray, cls)
            if h and win32gui.IsWindowVisible(h):
                self.anchor = h
                break
        if not self.anchor:
            self.anchor = self.rebar
        return True

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

    def free_span(self) -> tuple[int, int]:
        """(borde izquierdo del hueco disponible, borde derecho) en coords de pantalla."""
        rb = self._rect(self.rebar)
        an = self._rect(self.anchor)
        return rb[0], an[0]

    # -------------------------------------------------------------- operaciones
    def reserve(self, width: int, min_tasklist: int) -> int:
        """Encoge la lista de tareas para hacer sitio. Devuelve la x del widget
        en coordenadas relativas al cliente de la barra."""
        if not self.available:
            return 0
        tl, tt, tr, tb = win32gui.GetWindowRect(self.tray)
        rb = self._rect(self.rebar)
        an = self._rect(self.anchor)
        if not rb[0]:
            return 0
        widget_x = an[0] - width
        # no dejar la lista de tareas por debajo del minimo configurado
        widget_x = max(widget_x, rb[0] + min_tasklist)
        new_w = max(80, (widget_x - 2) - rb[0])
        if abs((rb[2] - rb[0]) - new_w) > 1:
            win32gui.SetWindowPos(self.rebar, 0, 0, 0, new_w, rb[3] - rb[1],
                                  win32con.SWP_NOMOVE | win32con.SWP_NOZORDER
                                  | win32con.SWP_NOACTIVATE)
        return widget_x - tl

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
        """Devuelve a ReBarWindow32 su ancho natural (hasta el ancla)."""
        if not self.refresh() or not self.rebar:
            return
        tl, tt, tr, tb = win32gui.GetWindowRect(self.tray)
        rb = self._rect(self.rebar)
        an = self._rect(self.anchor)
        if not rb[0]:
            return
        want = max(80, an[0] - rb[0])
        if abs((rb[2] - rb[0]) - want) > 1:
            win32gui.SetWindowPos(self.rebar, 0, rb[0] - tl, 0, want, tb - tt,
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
