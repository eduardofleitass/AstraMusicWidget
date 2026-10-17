"""Volumen de la aplicacion que esta sonando (Core Audio / mezclador de Windows).

SMTC dice **que** suena y donde, pero no su volumen. Para eso hay que hablar con la
API de audio del sistema (la misma del mezclador de volumen), que expone una "sesion"
por aplicacion con su propio volumen y su propio silencio.

Se controla el volumen de la sesion de la **app del reproductor**, no el del sistema:
si estas escuchando musica mientras una reunion habla, bajar la musica no te deja
sordo en la reunion.

No agrega dependencias: pywin32 y winsdk no exponen estas interfaces, asi que los
objetos COM se llaman a mano con ctypes (puntero a vtable). Se usan desde el hilo de
la ventana, con COM inicializado una vez por hilo.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import POINTER, byref, c_float, c_int, c_uint16, c_uint32, c_void_p

import win32process

ole32 = ctypes.windll.ole32
kernel32 = ctypes.windll.kernel32
HRESULT = ctypes.c_long

CLSCTX_ALL = 0x17
COINIT_APARTMENTTHREADED = 0x2
S_OK = 0
RPC_E_CHANGED_MODE = -2147417850  # 0x80010106: ya inicializado con otro modelo


class GUID(ctypes.Structure):
    _fields_ = [("Data1", c_uint32), ("Data2", c_uint16), ("Data3", c_uint16),
                ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, texto: str):
        super().__init__()
        ole32.CLSIDFromString(ctypes.c_wchar_p(texto), byref(self))


# CLSID de los objetos y IID de las interfaces que se necesitan. Tienen que quedar
# vivos en el modulo: si se pasan como temporales (`byref(GUID("..."))`), el recolector
# puede liberar la estructura antes de la llamada y COM contesta E_NOINTERFACE.
CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
IID_IAudioSessionManager2 = "{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}"
IID_IAudioSessionControl2 = "{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}"
IID_ISimpleAudioVolume = "{87CE5498-68D6-44E5-9215-6DA47EF883D8}"

CLSID_ENUM = GUID(CLSID_MMDeviceEnumerator)
IID_ENUM = GUID(IID_IMMDeviceEnumerator)
IID_MGR = GUID(IID_IAudioSessionManager2)
IID_CTRL2 = GUID(IID_IAudioSessionControl2)
IID_VOL = GUID(IID_ISimpleAudioVolume)

eRender, eMultimedia = 0, 1


class ErrorCoreAudio(Exception):
    pass


def _vt(ptr, indice: int, restype, argtypes: list):
    """Llama a un metodo de una interfaz COM por indice de vtable."""
    vtable = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vtable[indice])
    return fn


def _llamar(ptr, indice: int, restype, argtypes: list, *args, error: str = ""):
    hr = _vt(ptr, indice, restype, argtypes)(ptr, *args)
    if error and hr != S_OK:
        raise ErrorCoreAudio(f"{error} (hr=0x{hr & 0xFFFFFFFF:08X})")
    return hr


def _soltar(ptr) -> None:
    """Release() del objeto COM (indice 2 de IUnknown)."""
    if not ptr:
        return
    try:
        _vt(ptr, 2, c_uint32, [])(ptr)
    except Exception:
        pass


def iniciar_com() -> bool:
    """Inicializa COM en el hilo actual. Se puede llamar muchas veces."""
    try:
        hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        return hr in (S_OK, 1) or hr == RPC_E_CHANGED_MODE
    except Exception:
        return False


def _exe_de_pid(pid: int) -> str:
    if not pid:
        return ""
    try:
        h = kernel32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = c_uint32(1024)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, byref(size)):
                return os.path.basename(buf.value)
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        pass
    return ""


class _Sesion:
    """Una sesion de audio (una aplicacion con sonido en el mezclador)."""

    __slots__ = ("volumen_ptr", "pid", "exe")

    def __init__(self, volumen_ptr, pid: int, exe: str):
        self.volumen_ptr = volumen_ptr
        self.pid = pid
        self.exe = exe

    # ISimpleAudioVolume: 3 SetMasterVolume, 4 GetMasterVolume, 5 SetMute, 6 GetMute
    def volumen(self) -> float:
        v = c_float()
        _llamar(self.volumen_ptr, 4, HRESULT, [POINTER(c_float)], byref(v),
                error="GetMasterVolume")
        return max(0.0, min(1.0, float(v.value)))

    def silenciado(self) -> bool:
        b = c_int()
        _llamar(self.volumen_ptr, 6, HRESULT, [POINTER(c_int)], byref(b),
                error="GetMute")
        return bool(b.value)

    def fijar(self, nivel: float) -> None:
        nivel = max(0.0, min(1.0, float(nivel)))
        GUID_NULL = ctypes.c_void_p(None)
        _llamar(self.volumen_ptr, 3, HRESULT, [c_float, c_void_p], c_float(nivel),
                GUID_NULL, error="SetMasterVolume")

    def silenciar(self, on: bool) -> None:
        GUID_NULL = ctypes.c_void_p(None)
        _llamar(self.volumen_ptr, 5, HRESULT, [c_int, c_void_p], c_int(1 if on else 0),
                GUID_NULL, error="SetMute")

    def soltar(self) -> None:
        _soltar(self.volumen_ptr)


def _sesiones_del_dispositivo() -> list[_Sesion]:
    """Todas las sesiones de audio del dispositivo de salida por defecto."""
    enumd = c_void_p()
    dev = c_void_p()
    mgr = c_void_p()
    enum_s = c_void_p()
    sesiones: list[_Sesion] = []
    try:
        hr = ole32.CoCreateInstance(
            byref(CLSID_ENUM), None, CLSCTX_ALL, byref(IID_ENUM), byref(enumd))
        if hr != S_OK or not enumd:
            raise ErrorCoreAudio(f"CoCreateInstance del enumerador fallo (0x{hr & 0xFFFFFFFF:08X})")
        # IMMDeviceEnumerator: 4 GetDefaultAudioEndpoint
        _llamar(enumd, 4, HRESULT, [c_int, c_int, POINTER(c_void_p)],
                c_int(eRender), c_int(eMultimedia), byref(dev), error="GetDefaultAudioEndpoint")
        # IMMDevice: 3 Activate
        _llamar(dev, 3, HRESULT, [ctypes.c_void_p, c_uint32, c_void_p, POINTER(c_void_p)],
                ctypes.cast(byref(IID_MGR), c_void_p),
                c_uint32(CLSCTX_ALL), None, byref(mgr), error="Activate(IAudioSessionManager2)")
        # IAudioSessionManager2: 5 GetSessionEnumerator
        _llamar(mgr, 5, HRESULT, [POINTER(c_void_p)], byref(enum_s),
                error="GetSessionEnumerator")
        n = c_int()
        _llamar(enum_s, 3, HRESULT, [POINTER(c_int)], byref(n), error="GetCount")
        for i in range(n.value):
            ctrl = c_void_p()
            ctrl2 = c_void_p()
            vol = c_void_p()
            try:
                _llamar(enum_s, 4, HRESULT, [c_int, POINTER(c_void_p)], c_int(i),
                        byref(ctrl), error="GetSession")
                ctrl2_hr = _llamar(ctrl, 0, HRESULT,
                                   [ctypes.c_void_p, POINTER(c_void_p)],
                                   ctypes.cast(byref(IID_CTRL2), c_void_p),
                                   byref(ctrl2))
                if ctrl2_hr == S_OK and ctrl2:
                    pid = c_uint32()
                    _llamar(ctrl2, 14, HRESULT, [POINTER(c_uint32)], byref(pid),
                            error="GetProcessId")
                else:
                    pid = c_uint32(0)
                vol_hr = _llamar(ctrl, 0, HRESULT,
                                 [ctypes.c_void_p, POINTER(c_void_p)],
                                 ctypes.cast(byref(IID_VOL), c_void_p),
                                 byref(vol))
                if vol_hr == S_OK and vol:
                    sesiones.append(_Sesion(vol, int(pid.value), _exe_de_pid(int(pid.value))))
            except Exception:
                _soltar(vol)
            finally:
                _soltar(ctrl2)
                _soltar(ctrl)
    finally:
        _soltar(enum_s)
        _soltar(mgr)
        _soltar(dev)
        _soltar(enumd)
    return sesiones


def sesiones() -> list[dict]:
    """Para depurar: que apps tienen sesion de audio y con que volumen."""
    out = []
    for s in _sesiones_del_dispositivo():
        try:
            out.append({"pid": s.pid, "exe": s.exe, "volumen": s.volumen(),
                        "silenciado": s.silenciado()})
        except Exception as exc:
            out.append({"pid": s.pid, "exe": s.exe, "error": repr(exc)})
        finally:
            s.soltar()
    return out


def _normalizar(app: str) -> str:
    """De un app_id de SMTC (a veces ruta completa) al nombre del ejecutable."""
    app = (app or "").strip()
    app = app.split("!")[0]
    return os.path.basename(app.replace("\\", "/")).lower()


def _sesiones_de(app: str) -> list[_Sesion]:
    objetivo = _normalizar(app)
    if not objetivo:
        return []
    return [s for s in _sesiones_del_dispositivo() if s.exe.lower() == objetivo]


def estado(app: str) -> tuple[float, bool] | None:
    """(volumen 0..1, silenciado) de la app, o None si no tiene sesion de audio."""
    ses = _sesiones_de(app)
    if not ses:
        return None
    try:
        # con varias sesiones (Chrome/Brave abren una por proceso de audio) se toma
        # la primera: todas deberian compartir el volumen del mezclador
        return (ses[0].volumen(), ses[0].silenciado())
    finally:
        for s in ses:
            s.soltar()


def fijar(app: str, nivel: float) -> bool:
    """Cambia el volumen de la app (0..1). False si no tiene sesion de audio."""
    ses = _sesiones_de(app)
    if not ses:
        return False
    ok = True
    try:
        for s in ses:
            try:
                s.fijar(nivel)
                if nivel > 0 and s.silenciado():
                    s.silenciar(False)   # subir el volumen des-silencia, como Windows
            except Exception:
                ok = False
    finally:
        for s in ses:
            s.soltar()
    return ok


def silenciar(app: str, on: bool | None = None) -> bool | None:
    """Pone o saca el silencio. Con `on=None` lo alterna y devuelve el estado nuevo."""
    ses = _sesiones_de(app)
    if not ses:
        return None
    try:
        if on is None:
            on = not ses[0].silenciado()
        for s in ses:
            s.silenciar(bool(on))
        return bool(on)
    finally:
        for s in ses:
            s.soltar()
