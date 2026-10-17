"""Arma la tarjeta social del repo (la imagen que se ve al compartir el link).

    python tools/make_social_card.py        # deja assets/social.png (1280x640)

GitHub la pide de 1280x640 en Settings -> Social preview. No se puede subir por API (no
existe endpoint), asi que el archivo se genera aca y se sube a mano.

El estilo sigue al de la app: fondo oscuro, el violeta de acento, la tipografia del widget
(`draw._font`) y un **render real** del widget sobre una franja que simula la barra de
tareas (misma funcion que usa el programa, no una maqueta dibujada aparte).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

from widget import config as cfgmod, draw  # noqa: E402
from widget.media import MediaState  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(HERE, "assets", "social.png")
ICONO = os.path.join(HERE, "assets", "icono.png")

W, H = 1280, 640
FONDO_ARRIBA = (13, 14, 18)
FONDO_ABAJO = (22, 24, 32)
BARRA = (30, 32, 41)          # la franja que simula la barra de tareas
ACENTO = (176, 140, 255)      # el violeta de la app (#B08CFF)
TEXTO = (240, 242, 250)
TENUE = (150, 156, 178)
DEMO = {"progress_color": "#B08CFF", "waves_color": "#B08CFF", "chip_alpha": 232}


def estado() -> MediaState:
    return MediaState(
        has_session=True, app_id="Spotify.exe", title="Bohemian Rhapsody",
        artist="Queen", album="A Night at the Opera", playing=True, position=87.0,
        duration=355.0, position_at=time.monotonic(), art=None, art_key="demo",
        can_prev=True, can_next=True, can_toggle=True, can_seek=True,
        min_seek=0.0, max_seek=355.0)


def fondo() -> Image.Image:
    """Degradado vertical + un resplandor violeta suave, dibujado con desenfoque."""
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / float(H - 1)
        d.line([(0, y), (W, y)],
               fill=tuple(int(FONDO_ARRIBA[i] + (FONDO_ABAJO[i] - FONDO_ARRIBA[i]) * t)
                          for i in range(3)))
    # resplandor: una elipse violeta muy difusa detras de donde va el widget
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(capa).ellipse([W * 0.30, H * 0.42, W * 1.02, H * 1.12],
                                 fill=ACENTO + (58,))
    img = Image.alpha_composite(img.convert("RGBA"),
                                capa.filter(ImageFilter.GaussianBlur(70)))
    return img.convert("RGB")


def franja_barra(d: ImageDraw.ImageDraw) -> int:
    """La franja de abajo, con lo que se ve en una barra real: iconos y el reloj.

    Son sugerencias (rectangulos apagados), no dibujos de otras apps: la idea es que se
    entienda que el widget esta *dentro* de la barra.
    """
    y0 = H - 96
    d.rectangle([0, y0, W, H], fill=BARRA)
    d.line([(0, y0), (W, y0)], fill=(48, 51, 63), width=2)
    # iconos de la izquierda (como los anclados)
    x = 40
    for _ in range(6):
        d.rounded_rectangle([x, y0 + 28, x + 40, y0 + 68], radius=10, fill=(44, 47, 58))
        x += 58
    # el reloj de la derecha
    d.text((W - 96, y0 + 34), "20:26", font=draw._font("body", 20), fill=TENUE)
    d.text((W - 96, y0 + 58), "17/10/2026", font=draw._font("body", 15), fill=(112, 118, 138))
    return y0


def main() -> int:
    cfg = dict(cfgmod.load(), **DEMO)
    hoja = fondo()
    d = ImageDraw.Draw(hoja)

    # --- marca: icono + nombre + frase -------------------------------------------------
    icono = Image.open(ICONO).convert("RGBA").resize((104, 104), Image.LANCZOS)
    hoja.paste(icono, (72, 72), icono)
    f_nombre = draw._font("title", 76)
    d.text((204, 84), "Astra-Music-widget", font=f_nombre, fill=TEXTO)
    d.text((208, 178), "Musica en la barra de tareas de Windows",
           font=draw._font("body", 30), fill=ACENTO)

    # --- lo que hace, en renglones cortos -----------------------------------------------
    f_chico = draw._font("body", 26)
    lineas = (
        "Caratula, titulo, controles y el volumen de la app que suena.",
        "Anda con Spotify, VLC y lo que suene en el navegador.",
        "Panel con tres tamanos y modo gaming: no le roba el foco al juego.",
        "Gratis y con licencia MIT. Instalador o un portatil de un solo archivo.",
    )
    for i, t in enumerate(lineas):
        d.text((76, 262 + i * 40), t, font=f_chico, fill=(206, 210, 224))

    # la direccion, en el hueco del medio: abajo a la izquierda chocaba con el widget
    d.text((76, 452), "github.com/eduardofleitass/AstraMusicWidget",
           font=draw._font("body", 22), fill=(128, 134, 156))

    # --- el widget de verdad, sobre la franja de la barra ------------------------------
    y0 = franja_barra(d)
    # el ancho real es cfg["width"] * k: 310 x 2 = 620 px de ancho, 80 de alto
    widget = draw.render(estado(), dict(cfg, width=310, show_waves=True), art=None,
                         k=2.0, base=BARRA, opaque=True,
                         waves=[0.5, 0.95, 0.62, 0.8])
    # se ubica a la derecha de la franja, como se usa en la realidad
    x = W - widget.width - 150
    hoja.paste(widget.convert("RGB"), (x, y0 + (96 - widget.height) // 2))

    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    hoja.save(DESTINO)
    print("tarjeta social:", DESTINO, hoja.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
