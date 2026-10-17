"""Configuracion del widget de musica para la barra de tareas."""
from __future__ import annotations

import copy
import json
import os

DEFAULTS = {
    "width": 260,
    "min_tasklist_width": 420,
    "poll_interval_ms": 500,
    "timer_playing_ms": 100,
    "timer_idle_ms": 500,
    "layout_check_ms": 1000,
    "marquee_speed": 32,
    "marquee_gap": 40,
    "supersample": 3,
    "show_progress": True,
    "show_controls": True,
    "show_art": True,
    "corner_radius": 7,
    "chip_alpha": 232,
    # "layered" = transparencia real (alpha por pixel sobre lo que haya detras);
    # "opaque"  = el metodo clasico, mezclando contra el color muestreado de la barra.
    "bg_mode": "layered",
    # None = pegado al extremo derecho (junto al bloque de la bandeja).
    # 0..1 = posicion libre dentro de la zona util de la barra (0 = bien a la
    # izquierda, 1 = extremo derecho). Lo fija el menu o el arrastre.
    "position_frac": None,
    "min_tasklist_free": 140,
    "drag_to_move": True,
    # Cuantos segundos adelanta/atrasa la rueda del mouse y los items del menu.
    # La barra de progreso siempre se puede clickear para saltar a donde sea.
    "seek_step_s": 10,
    # Paso fino y grueso de la rueda con modificador: Ctrl = fino, Shift = grueso.
    # El paso normal (seek_step_s) es sin modificador.
    "seek_fine_s": 1,
    "seek_coarse_s": 60,
    # Atajos globales (Ctrl+Alt+M/arriba/abajo/izquierda/derecha y con Shift para
    # adelantar y atrasar). Se pueden apagar desde el menu.
    "hotkeys": True,
    # Alpha minimo de cada pixel en modo transparente. Windows usa el alpha por
    # pixel para decidir que ventana recibe el mouse: con 0, las zonas vacias del
    # widget se vuelven "agujeros" y los clics van a la barra de tareas. 2 es
    # invisible (0,8% de mezcla) y mantiene todo el widget sensible al mouse.
    "hit_alpha_floor": 2,
    # Ondas de sonido animadas entre el texto y los botones. Es una animacion
    # visual (SMTC no expone niveles de audio), no un analisis del sonido.
    "show_waves": False,
    "wave_bars": 4,
    # Cuadros por segundo de la animacion. Baja la cifra si te importa la CPU:
    # es el unico motivo por el que el widget repinta mas seguido que el texto.
    "wave_fps": 20,
    # Color de la barra de progreso y de las ondas. null = el color de acento del
    # tema. Se puede escribir como "#RRGGBB" o [r, g, b]; el menu guarda hex.
    # Son independientes del auto-contraste: si los elegis, se usan tal cual.
    "progress_color": None,
    "waves_color": None,
    # Volumen de la app que esta sonando (API de audio de Windows, no el del
    # sistema): la celda del altavoz va despues de los botones del transporte.
    # Con el cursor encima, la fila del progreso pasa a ser la barra de volumen;
    # un clic seco en el altavoz silencia y la rueda mueve `volume_step` por muesca.
    # Fundido al cambiar de caratula (el salto de tapa a tapa se nota) y al
    # mostrar/ocultar el widget con Ctrl+Alt+M (solo con el fondo transparente, que
    # es donde hay alpha global para animar).
    "fade_cover": True,
    "fade_cover_ms": 220,
    "fade_visible": True,
    "fade_step": 48,
    "show_volume": True,
    "volume_step": 5,
    # Barra de tareas donde vive el widget: null = la del monitor principal. El
    # menu "Monitor" guarda aca el nombre del dispositivo (p. ej. "\\.\DISPLAY2").
    "taskbar_monitor": None,
    "auto_contrast": True,
    "theme": {
        "chip": [21, 23, 30],
        "border": [60, 64, 80],
        "title": [238, 240, 248],
        "artist": [144, 151, 173],
        "accent": [96, 205, 145],
        "track": [74, 80, 98],
        "icon": [222, 226, 238],
        "icon_dim": [104, 110, 128],
    },
    "right_click_menu": True,
    "log_file": "widget.log",
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str | None = None) -> dict:
    path = path or CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return _merge(DEFAULTS, json.load(fh))
    except FileNotFoundError:
        return copy.deepcopy(DEFAULTS)
    except Exception:
        return copy.deepcopy(DEFAULTS)


def save(cfg: dict, path: str | None = None) -> None:
    path = path or CONFIG_PATH
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
    except Exception:
        pass
