"""Ventanas del reproductor: encontrar la que suena y traerla al frente.

Cierra el circulo del panel: si lo que suena es el navegador y queres ver el video, un
doble clic en la caratula del panel trae al frente la ventana de esa aplicacion.

Sin dependencias nuevas: el nombre del ejecutable de cada ventana se saca con
`QueryFullProcessImageNameW` (ctypes), y para ponerla al frente se engancha el hilo de
entrada con el de la ventana activa (`AttachThreadInput`), porque una ventana hija de la
barra de tareas no tiene el derecho de `SetForegroundWindow` por si sola.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os

import win32api
import win32con
import win32gui
import win32process

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# QueryFullProcessImageNameW vive en KERNEL32 (no en user32): pedirsela a user32
# levanta AttributeError, el except lo traga y la busqueda devuelve cero ventanas
# siempre... que es lo que pasaba (se veia como "no encontre su ventana").
kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                                ctypes.c_wchar_p,
                                                ctypes.POINTER(ctypes.c_ulong)]
kernel32.QueryFullProcessImageNameW.restype = ctypes.c_int


def exe_de_pid(pid: int) -> str:
    """Nombre del ejecutable de un PID, en minusculas ("" si no se puede)."""
    try:
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    except Exception:
        return ""
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        tam = wt.DWORD(1024)
        if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(tam)):
            return ""
        return os.path.basename(buf.value).lower()
    except Exception:
        return ""
    finally:
        try:
            kernel32.CloseHandle(h)
        except Exception:
            pass


def _normalizar_exe(app_id: str) -> str:
    """De `app_id` de SMTC ("brave.exe", una ruta, o "x!y") al nombre de ejecutable."""
    exe = os.path.basename(str(app_id or "").split("!")[0]).strip().lower()
    if exe and "." not in exe:
        exe += ".exe"
    return exe


def ventana_del_reproductor(app_id: str) -> int:
    """La ventana principal (visible, con titulo) del proceso que suena; 0 si no hay.

    `EnumWindows` recorre en orden Z (de arriba hacia abajo), asi que la primera que
    coincide es la que el usuario tiene mas a mano: si el navegador tiene varias
    ventanas, esa es la que esta mirando.
    """
    exe = _normalizar_exe(app_id)
    if not exe:
        return 0
    encontradas: list[int] = []

    def cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                return True                      # dialogos y ventanas dependientes
            if not win32gui.GetWindowText(hwnd).strip():
                return True                      # sin titulo: no es la principal
            if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid and exe_de_pid(pid) == exe:
                encontradas.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return encontradas[0] if encontradas else 0


def traer_al_frente(hwnd: int) -> bool:
    """Pone `hwnd` al frente y devuelve True si quedo como ventana activa."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        frente = win32gui.GetForegroundWindow()
        hilo_frente = win32process.GetWindowThreadProcessId(frente)[0]
        hilo_mio = win32api.GetCurrentThreadId()
        enganchado = False
        if hilo_frente and hilo_frente != hilo_mio:
            enganchado = bool(win32process.AttachThreadInput(hilo_mio, hilo_frente, True))
        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        finally:
            if enganchado:
                win32process.AttachThreadInput(hilo_mio, hilo_frente, False)
    except Exception:
        pass
    try:
        if win32gui.GetForegroundWindow() == hwnd:
            return True
        # Plan B: la funcion sin documentar que usa el propio shell para esto
        user32.SwitchToThisWindow(int(hwnd), True)
        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        return False
