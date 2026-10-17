"""Genera el icono del programa (assets/icono.ico) con el mismo dibujo del widget.

El motivo es el de las ondas: cuatro barras del color de acento sobre un cuadrado oscuro
redondeado. Es lo que se ve en la barra de tareas cuando suena algo.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(HERE, "assets", "icono.ico")
FONDO = (26, 28, 36, 255)
ACENTO = (176, 140, 255, 255)      # el violeta que eligio el usuario
BORDE = (60, 64, 80, 255)
ALTURAS = (0.42, 0.78, 0.58, 0.92)  # como las ondas: ninguna igual a la otra


def dibujar(px: int) -> Image.Image:
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = px * 0.22
    d.rounded_rectangle([0, 0, px - 1, px - 1], radius=r, fill=FONDO, outline=BORDE,
                        width=max(1, int(px / 32)))
    # cuatro barras centradas, redondeadas, como el visualizador
    ancho = px * 0.11
    hueco = px * 0.075
    total = len(ALTURAS) * ancho + (len(ALTURAS) - 1) * hueco
    x = (px - total) / 2.0
    for h in ALTURAS:
        alto = px * 0.62 * h
        y0 = (px - alto) / 2.0
        d.rounded_rectangle([x, y0, x + ancho, y0 + alto], radius=ancho / 2.0, fill=ACENTO)
        x += ancho + hueco
    return img


def main() -> int:
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    grande = dibujar(256)
    grande.save(DESTINO.replace(".ico", ".png"))
    grande.save(DESTINO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                (128, 128), (256, 256)])
    print("icono:", DESTINO)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
