"""Genera el GIF del README: el widget animando las ondas.

    python tools/make_demo_gif.py        # deja assets/demo.gif

Se dibuja con datos de ejemplo (Spotify / Bohemian Rhapsody), asi que se puede publicar:
no muestra lo que suena en la maquina de nadie.
"""
from __future__ import annotations

import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from widget import config as cfgmod, draw  # noqa: E402
from widget.media import MediaState  # noqa: E402

# Color y fondo FIJOS para las imagenes del README: no se toma lo que el usuario tenga
# puesto hoy (si cambia el color, las imagenes quedarian desactualizadas sin que nadie se
# entere). El violeta es el que se ve en las capturas publicadas.
DEMO = {"progress_color": "#B08CFF", "waves_color": "#B08CFF", "chip_alpha": 232,
        "panel_bg_alpha": 250}


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(HERE, "assets", "demo.gif")
BARRA = (28, 30, 38)
ANCHO, ALTO = 320, 40
CUADROS = 28
FPS = 12
BARRAS = 4


def estado() -> MediaState:
    return MediaState(
        has_session=True, app_id="Spotify.exe",
        title="Bohemian Rhapsody", artist="Queen", album="A Night at the Opera",
        playing=True, position=87.0, duration=355.0, position_at=time.monotonic(),
        art=None, art_key="demo", can_prev=True, can_next=True, can_toggle=True,
        can_seek=True, min_seek=0.0, max_seek=355.0)


def niveles(i: int) -> list:
    """Alturas de las barras: una animacion suave y repetible (no random) para que el
    GIF no salte y se vea igual cada vez que se regenera."""
    t = i / float(CUADROS)
    out = []
    for b in range(BARRAS):
        fase = b * 1.7
        base = 0.45 + 0.4 * math.sin(2 * math.pi * (t * 1.5) + fase)
        extra = 0.12 * math.sin(2 * math.pi * (t * 4.0) + fase * 2)
        out.append(max(0.12, min(1.0, base + extra)))
    return out


def main() -> int:
    cfg = dict(cfgmod.load(), **DEMO)
    st = estado()
    hoja = Image.new("RGB", (ANCHO + 160, ALTO + 24), (16, 17, 21))
    # una franja que hace de barra de tareas, con el widget a la derecha como se usa
    for y in range(ALTO + 24):
        hoja.paste(BARRA, [0, 20, hoja.width, 20 + ALTO])
    x = hoja.width - ANCHO - 30
    cuadros = []
    for i in range(CUADROS):
        img = draw.render(st, dict(cfg, width=ANCHO, show_waves=True), art=None, k=1.0,
                          base=BARRA, opaque=True, waves=niveles(i))
        cuadro = hoja.copy()
        cuadro.paste(img.convert("RGB"), (x, 20))
        cuadros.append(cuadro.convert("P", palette=Image.ADAPTIVE, colors=128))
    cuadros[0].save(DESTINO, save_all=True, append_images=cuadros[1:],
                    duration=int(1000 / FPS), loop=0, optimize=True, disposal=2)
    print("gif:", DESTINO, "| %.0f KB" % (os.path.getsize(DESTINO) / 1024.0),
          "|", ANCHO, "x", ALTO, "x", CUADROS, "cuadros")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
