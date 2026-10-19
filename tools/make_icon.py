"""Genera el icono del programa (assets/icono.ico y assets/icono.png).

    python tools/make_icon.py            usa el diseno elegido (por defecto el 1)
    python tools/make_icon.py --elegido 4   cambia el candidato

Los cuatro disenos viven en `tools/iconos_astra.py` (astral + musica): la nota estelar, la
estrella con la onda, la constelacion y el halo astral. Este script toma uno y escribe el
.ico con todos los tamanos que pide Windows, mas el PNG que usa el README.

Antes el icono eran cuatro barras de ecualizador sobre un cuadrado oscuro: se veia como
cualquier app de audio y no decia nada del nombre. Ahora es la corchea con su estrella.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from tools.iconos_astra import DISENOS, GRANDE  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICO = os.path.join(RAIZ, "assets", "icono.ico")
PNG = os.path.join(RAIZ, "assets", "icono.png")
TAMANOS = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
ELEGIDO = 1


def generar(elegido: int = ELEGIDO) -> tuple[str, str]:
    nombre, fn = DISENOS[max(0, min(len(DISENOS) - 1, elegido - 1))]
    grande = fn(GRANDE)
    png256 = grande.resize((256, 256), Image.LANCZOS)
    png256.save(PNG)
    grande.save(ICO, sizes=TAMANOS, format="ICO")
    return ICO, "%s (%s)" % (PNG, nombre)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--elegido", type=int, default=ELEGIDO,
                    help="1 nota estelar, 2 estrella con onda, 3 constelacion, 4 halo astral")
    args = ap.parse_args()
    ico, png = generar(args.elegido)
    print("icono:", ico)
    print("png:  ", png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
