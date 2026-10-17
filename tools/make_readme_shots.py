"""Genera la imagen del README: el widget en una franja tipo barra y el panel debajo.

Se dibuja con datos de ejemplo (nada de lo que suena en la maquina del que lo corre), asi
que la imagen se puede publicar. Se regenera con:

    python tools/make_readme_shots.py        # deja assets/captura.png
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402

from widget import config as cfgmod, draw, panel as panel_mod  # noqa: E402
from widget.media import MediaState  # noqa: E402

# Color y fondo FIJOS para las imagenes del README: no se toma lo que el usuario tenga
# puesto hoy (si cambia el color, las imagenes quedarian desactualizadas sin que nadie se
# entere). El violeta es el que se ve en las capturas publicadas.
DEMO = {"progress_color": "#B08CFF", "waves_color": "#B08CFF", "chip_alpha": 232,
        "panel_bg_alpha": 250}


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(HERE, "assets", "captura.png")
BARRA = (28, 30, 38)          # el color de una barra de tareas oscura


def estado() -> MediaState:
    return MediaState(
        has_session=True, app_id="Spotify.exe",
        title="Bohemian Rhapsody", artist="Queen",
        album="A Night at the Opera", playing=True, position=87.0, duration=355.0,
        position_at=time.monotonic(), art=None, art_key="demo",
        can_prev=True, can_next=True, can_toggle=True, can_seek=True,
        min_seek=0.0, max_seek=355.0)


def caratula(lado: int, radio: int) -> Image.Image:
    """Una caratula de mentira (un degradado con ondas), para no usar arte de nadie."""
    img = Image.new("RGB", (lado * 4, lado * 4))
    d = ImageDraw.Draw(img)
    for y in range(img.height):
        t = y / float(img.height)
        d.line([(0, y), (img.width, y)],
               fill=(int(60 + 90 * t), int(40 + 60 * t), int(110 + 80 * t)))
    x = 6
    for h in (0.35, 0.7, 0.5, 0.9, 0.45, 0.8):
        alto = (lado * 4 - 24) * h
        d.rounded_rectangle([x, (lado * 4 - alto) / 2, x + 10, (lado * 4 + alto) / 2],
                            radius=5, fill=(240, 240, 255))
        x += 18
    return img.resize((lado, lado), Image.LANCZOS).convert("RGBA")


def main() -> int:
    cfg = dict(cfgmod.load(), **DEMO)
    st = estado()
    W = 640                      # ancho de la franja que simula la barra
    alto = 40
    hoja = Image.new("RGB", (W + 40, alto + 12 + 178 + 40), (16, 17, 21))
    d = ImageDraw.Draw(hoja)

    # 1) la franja de la barra con el widget adentro (a la derecha, como se usa)
    x0, y0 = 20, 20
    d.rounded_rectangle([0, y0, hoja.width, y0 + alto], radius=0, fill=BARRA)
    ancho = 320
    widget = draw.render(st, dict(cfg, width=ancho, show_waves=True), art=None,
                         k=1.0, base=BARRA, opaque=True, waves=[0.45, 0.9, 0.6, 0.75])
    hoja.paste(widget.convert("RGB"),
               (x0 + W - ancho - 90, y0 + (alto - widget.height) // 2))
    d.text((x0, y0 - 12), "en la barra de tareas", fill=(150, 155, 175))

    # 2) el panel normal, debajo, como flota sobre el escritorio
    py = y0 + alto + 28
    d.text((x0, py - 18), "el panel (clic en la carátula)", fill=(150, 155, 175))
    art = caratula(92, 10)
    pan = panel_mod.render(st, dict(cfg, panel_size="normal", panel_bg_alpha=250),
                           art=art, volume=(0.62, False, True, True), k=1.0,
                           opaque=True, base=(22, 24, 30))
    hoja.paste(pan.convert("RGB"), (x0 + 20, py), pan)
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    hoja.save(DESTINO)
    print("captura:", DESTINO, hoja.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
