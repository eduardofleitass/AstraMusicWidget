"""Colores que da Windows: el acento con el que tiñe la barra de tareas y los bordes.

Lo usa el modo "Del tema de Windows" del fondo del widget (menu: Color del widget). La
consulta queda cacheada unos segundos: el color cambia rara vez y el dibujo lo pide en cada
cuadro.

Windows guarda esto en dos lugares y no siempre coinciden:
  - `DwmGetColorizationColor` (dwmapi) devuelve lo que el sistema esta usando de verdad
    —medido en la maquina de prueba: 0x2B2F1B11, que es el marron de la barra de tareas—, en
    formato ARGB;
  - `HKCU\\Software\\Microsoft\\Windows\\DWM\\ColorizationColor` es el valor que eligio el
    usuario o el que salio del fondo de pantalla, tambien ARGB.
Se prueban en ese orden y, si ninguno contesta, queda el acento del tema del widget (el verde
por defecto), asi que nunca se rompe el dibujo.
"""
from __future__ import annotations

import ctypes
import time

try:
    import winreg
except ImportError:                      # pragma: no cover - solo Windows
    winreg = None

ACENTO_POR_DEFECTO = (96, 205, 145)      # el mismo del tema (config: theme.accent)
_TTL_S = 5.0
_cache: tuple[tuple[int, int, int], float] | None = None


def color_acento() -> tuple[int, int, int]:
    """(r, g, b) con el que Windows tiñe la barra de tareas y los bordes."""
    global _cache
    ahora = time.monotonic()
    if _cache and ahora - _cache[1] < _TTL_S:
        return _cache[0]
    color = _de_dwm() or _del_registro() or ACENTO_POR_DEFECTO
    _cache = (color, ahora)
    return color


def _de_dwm() -> tuple[int, int, int] | None:
    """El colorization actual, que es el que se ve en la barra: ARGB."""
    try:
        valor = ctypes.c_uint32()
        opaco = ctypes.c_int()
        if ctypes.windll.dwmapi.DwmGetColorizationColor(ctypes.byref(valor),
                                                        ctypes.byref(opaco)) == 0:
            return _argb(valor.value)
    except Exception:
        pass
    return None


def _del_registro() -> tuple[int, int, int] | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\DWM") as clave:
            valor, _tipo = winreg.QueryValueEx(clave, "ColorizationColor")
        return _argb(int(valor))
    except Exception:
        return None


def _argb(valor: int) -> tuple[int, int, int]:
    return ((valor >> 16) & 0xFF, (valor >> 8) & 0xFF, valor & 0xFF)
