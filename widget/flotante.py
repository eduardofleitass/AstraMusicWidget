"""Host flotante: el widget como ventana propia, para cuando no hay barra que lo aloje.

En Windows 11 la barra de tareas **ya no tiene** lo que hace posible la incrustacion en
Windows 10: no hay `ReBarWindow32` que encoja para hacer sitio ni ventanas hijas de
`Shell_TrayWnd`. Ahi el widget se dibuja como **ventana propia**, pegada a la franja de
abajo del monitor (encima de la barra, en el hueco libre entre los iconos y el reloj), con
el mismo dibujo, el mismo clic y la misma transparencia real.

Este host le da a la app **el mismo contrato que `TaskbarHost`** (metrics/reserve/place/
x_limits/base_color/...), asi que el resto del programa no cambia: lo unico distinto es que
`reserve()` devuelve coordenadas de PANTALLA (la ventana no tiene padre) y que no hay nada
que reservar.

El alto de la franja no se adivina: sale del area de trabajo del monitor (`GetMonitorInfo`
da el trabajo sin la barra), y si Windows la tiene oculta se usa el alto tipico. Medido en
Windows 10 con la barra de 40 px, da 40; en Windows 11 la barra mide 48.
"""
from __future__ import annotations

import win32api
import win32con
import win32gui


class FloatingHost:
    """Contrato de `TaskbarHost` apoyado en el rectangulo del monitor."""

    flotante = True
    tray = 0            # no hay barra
    container = 0
    anchor = 0
    barra = None

    def __init__(self, log=lambda *a, **k: None, monitor: str | None = None,
                 reserva_derecha: int = 300):
        self.log = log
        self.monitor_pedido = monitor
        self.reserva_derecha = int(reserva_derecha)
        self.rect = None            # (x0, y0, x1, y1) del monitor
        self.trabajo = None         # area de trabajo (sin la barra)
        self.alto = 44              # alto de la franja
        self.refresh()

    # ------------------------------------------------------------------ geometria
    def available(self) -> bool:
        return bool(self.rect)

    def refresh(self) -> bool:
        try:
            mon = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
            info = win32api.GetMonitorInfo(mon)
            self.rect = tuple(info["Monitor"])
            self.trabajo = tuple(info["Work"])
            alto = self.rect[3] - self.trabajo[3]
            if alto <= 0:
                # barra oculta o de otro lado: se usa el alto tipico de Windows 11
                alto = 48
            self.alto = max(24, int(alto))
            return True
        except Exception as exc:
            self.log("flotante: no pude medir el monitor: %r", exc)
            self.rect = None
            return False

    def metrics(self) -> dict:
        x0, y0, x1, y1 = self.rect
        return {"taskbar_h": self.alto, "left": x0, "top": y1 - self.alto,
                "scale": self.alto / 40.0, "width": x1 - x0}

    def strip_y(self) -> int:
        """y donde apoya el widget (coords de pantalla)."""
        return int(self.rect[3] - self.alto)

    def select(self, monitor: str | None) -> None:
        """En flotante siempre es el monitor principal (la barra de 11 es una sola)."""
        self.refresh()

    def restore(self) -> None:
        """No hay nada que devolver: la barra no se toco."""

    def detach_widget(self, hwnd: int) -> None:
        try:
            if hwnd and win32gui.IsWindow(hwnd):
                win32gui.DestroyWindow(hwnd)
        except Exception:
            pass

    def barra_en(self, x: int) -> dict | None:
        return None                 # no hay barras por las que mudarse

    # -------------------------------------------------------------------- posicion
    def free_span(self) -> tuple[int, int]:
        x0, _, x1, _ = self.rect
        return x0 + 8, x1 - self.reserva_derecha

    def x_limits(self, width: int, min_free: int = 140) -> tuple[int, int]:
        lo, hi = self.free_span()
        return lo, max(lo, hi - width)

    def clamp_x(self, x: int, width: int, min_free: int = 140) -> int:
        lo, hi = self.x_limits(width, min_free)
        return max(lo, min(hi, int(x)))

    def frac_from_x(self, x: int, width: int, min_free: int = 140) -> float:
        lo, hi = self.x_limits(width, min_free)
        if hi <= lo:
            return 0.0
        return max(0.0, min(1.0, (x - lo) / float(hi - lo)))

    def x_from_frac(self, frac: float, width: int, min_free: int = 140) -> int:
        lo, hi = self.x_limits(width, min_free)
        return int(round(lo + max(0.0, min(1.0, float(frac))) * (hi - lo)))

    def target_x(self, width: int, min_tasklist: int, frac: float | None = None,
                 min_free: int = 140) -> int:
        if frac is None:
            return self.x_limits(width, min_free)[1]
        return self.x_from_frac(frac, width, min_free)

    def reserve(self, width: int, min_tasklist: int, x: int | None = None,
                frac: float | None = None, min_free: int = 140) -> int:
        """x del widget en coords de PANTALLA (no hay barra que encoger)."""
        if not self.available():
            return 0
        if x is not None:
            return self.clamp_x(x - 0, width, min_free)
        return self.target_x(width, min_tasklist, frac=frac, min_free=min_free)

    def place(self, hwnd: int, x: int, height: int) -> None:
        """Coloca la ventana en (x, franja). En flotante es una ventana de nivel
        superior: x e y son de pantalla."""
        if not self.available() or not win32gui.IsWindow(hwnd):
            return
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, int(x), self.strip_y(),
                                  0, 0, win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        except Exception as exc:
            self.log("flotante: no pude colocar el widget: %r", exc)

    # -------------------------------------------------------------------- color
    def base_color(self, x_rel: int, width: int, height: int) -> tuple:
        """Color de lo que hay DETRAS del widget, en la franja donde se apoya.

        No se puede mirar dentro de su propio rectangulo (ahi esta el widget): se
        muestrean dos tiras finas a los costados, en la misma y, y se promedian. Es lo
        que decide el contraste del texto (claro u oscuro) cuando el fondo es real.
        """
        try:
            from PIL import ImageGrab
            _, y = int(x_rel), self.strip_y()
            tiras = [(max(self.rect[0], x_rel - 6), y, max(self.rect[0] + 1, x_rel - 1),
                      y + height),
                     (x_rel + width + 1, y, x_rel + width + 6, y + height)]
            medias = []
            for f in tiras:
                if f[2] <= f[0] or f[3] <= f[1]:
                    continue
                im = ImageGrab.grab(bbox=f, all_screens=True).convert("RGB")
                px = list(im.get_flattened_data())
                if px:
                    n = float(len(px))
                    medias.append(tuple(int(sum(p[i] for p in px) / n) for i in range(3)))
            if not medias:
                return (26, 28, 36)
            return tuple(int(sum(m[i] for m in medias) / len(medias)) for i in range(3))
        except Exception:
            return (26, 28, 36)
