"""Cuatro candidatos de icono para Astra-Music-widget (astral + musica).

    python tools/iconos_astra.py

Deja en assets/candidatos/ cada diseno en 256, 48, 32 y 16 px, y una hoja comparativa
en el Escritorio para elegir mirando. No toca assets/icono.ico: eso lo hace
`tools/make_icon.py --elegido N` cuando el usuario decide.

La idea: "Astra" = astral (estrella, halo, constelacion) y "music" = la nota / la onda.
Todo se dibuja a 1024 y se baja con LANCZOS, que es como se ve nitido en la barra.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "assets", "candidatos")
GRANDE = 1024
RADIO = 0.22

VIOLETA = (167, 139, 250)
VIOLETA_OSCURO = (92, 62, 190)
FONDO_A = (36, 26, 70)       # arriba a la izquierda
FONDO_B = (18, 15, 36)       # abajo a la derecha
BLANCO = (247, 245, 255)


def degradado(px: int, a=(120, 80, 230), esquina=(52, 34, 108),
              b=(16, 13, 30)) -> Image.Image:
    """Degradado diagonal suave: se arma un cuadrado de 2x2 y se estira con BICUBIC.

    Antes se rotaba una imagen ya dibujada y `rotate` rellenaba de negro las esquinas:
    el icono terminaba pareciendo un hexagono con las puntas cortadas.
    """
    chico = Image.new("RGB", (2, 2))
    chico.putpixel((0, 0), a)
    chico.putpixel((1, 0), esquina)
    chico.putpixel((0, 1), esquina)
    chico.putpixel((1, 1), b)
    return chico.resize((px, px), Image.BICUBIC)


def estrella(centro, radio, puntiaguda=0.24) -> list[tuple[float, float]]:
    cx, cy = centro
    r = radio * puntiaguda
    return [(cx, cy - radio), (cx + r, cy - r), (cx + radio, cy), (cx + r, cy + r),
            (cx, cy + radio), (cx - r, cy + r), (cx - radio, cy), (cx - r, cy - r)]


def nota(d: ImageDraw.ImageDraw, x, y, alto, color, ancho=None):
    """Corchea: cabeza ovalada, plica y bandera. `y` es la punta de arriba de la plica."""
    ancho = ancho or alto * 0.30
    cabeza_r = alto * 0.17
    # cabeza
    d.ellipse([x - cabeza_r, y + alto - cabeza_r, x + cabeza_r, y + alto + cabeza_r],
              fill=color)
    # plica
    d.rounded_rectangle([x + cabeza_r * 0.55, y, x + cabeza_r * 1.25, y + alto],
                        radius=ancho * 0.28, fill=color)
    # bandera
    d.polygon([(x + cabeza_r * 1.2, y), (x + cabeza_r * 2.9, y + alto * 0.20),
               (x + cabeza_r * 2.9, y + alto * 0.46), (x + cabeza_r * 1.2, y + alto * 0.26)],
              fill=color)


def base(px: int) -> Image.Image:
    """Cuadrado redondeado con el degradado violeta, sobre transparente."""
    fondo = degradado(px)
    mascara = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, px - 1, px - 1],
                                              radius=px * RADIO, fill=255)
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    img.paste(fondo, (0, 0), mascara)
    # brillo suave arriba a la izquierda, para que no sea un plano
    halo = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse([-px * 0.35, -px * 0.55, px * 0.95, px * 0.55],
                                 fill=(190, 160, 255, 70))
    halo = halo.filter(ImageFilter.GaussianBlur(px * 0.06))
    halo.putalpha(Image.composite(halo.split()[3], Image.new("L", (px, px), 0), mascara))
    img.alpha_composite(halo)
    return img


def diseno_1(px: int) -> Image.Image:
    """Nota estelar: la corchea blanca con su estrella de cuatro puntas (astral + musica)."""
    img = base(px)
    d = ImageDraw.Draw(img)
    alto = px * 0.50
    nota(d, px * 0.345, px * 0.285, alto, BLANCO)
    # estrella en la punta de la plica: la nota "es" un astro
    cx, cy = px * 0.675, px * 0.245
    d.polygon(estrella((cx, cy), px * 0.150), fill=VIOLETA)
    d.polygon(estrella((cx, cy), px * 0.078), fill=BLANCO)
    # destellos chicos, sin competir con la nota
    d.polygon(estrella((px * 0.235, px * 0.665), px * 0.045), fill=(232, 222, 255, 200))
    return img


def diseno_2(px: int) -> Image.Image:
    """Estrella astral con la onda de sonido abajo (astro + musica, sin nota)."""
    img = base(px)
    d = ImageDraw.Draw(img)
    cx, cy = px * 0.50, px * 0.40
    d.polygon(estrella((cx, cy), px * 0.30), fill=BLANCO)
    d.polygon(estrella((cx, cy), px * 0.16), fill=(150, 110, 245))
    alturas = (0.55, 1.0, 0.72, 0.45)
    ancho = px * 0.085
    hueco = px * 0.045
    total = len(alturas) * ancho + (len(alturas) - 1) * hueco
    x = (px - total) / 2
    base_y = px * 0.90
    for h in alturas:
        alto = px * 0.20 * h
        d.rounded_rectangle([x, base_y - alto, x + ancho, base_y], radius=ancho * 0.5,
                            fill=BLANCO)
        x += ancho + hueco
    return img


def diseno_3(px: int) -> Image.Image:
    """Constelacion: la nota dibujada con puntos y lineas finas, como un cielo."""
    img = base(px)
    d = ImageDraw.Draw(img)
    lw = max(2, int(px * 0.022))
    puntos = [(px * 0.36, px * 0.70), (px * 0.64, px * 0.26),
              (px * 0.64, px * 0.44), (px * 0.80, px * 0.34)]
    d.line([puntos[0], puntos[1]], fill=(226, 218, 255, 235), width=lw)
    d.line([puntos[1], puntos[2]], fill=(226, 218, 255, 235), width=lw)
    d.line([puntos[2], puntos[3]], fill=(226, 218, 255, 235), width=lw)
    for i, (x, y) in enumerate(puntos):
        r = px * (0.075 if i == 0 else 0.035)
        d.ellipse([x - r, y - r, x + r, y + r],
                  fill=BLANCO if i == 0 else (200, 185, 255))
    for (x, y, r) in ((px * 0.22, px * 0.30, 0.028), (px * 0.78, px * 0.72, 0.022),
                      (px * 0.30, px * 0.52, 0.016)):
        d.polygon(estrella((x, y), px * r), fill=(225, 215, 255, 220))
    return img


def diseno_4(px: int) -> Image.Image:
    """Halo astral: la nota dentro de un anillo de luz (orbita)."""
    img = base(px)
    d = ImageDraw.Draw(img)
    r = px * 0.325
    d.ellipse([px / 2 - r, px / 2 - r, px / 2 + r, px / 2 + r],
              outline=(214, 200, 255, 240), width=max(3, int(px * 0.028)))
    nota(d, px * 0.395, px * 0.315, px * 0.40, BLANCO)
    d.polygon(estrella((px / 2 + r * 0.70, px / 2 - r * 0.78), px * 0.08),
              fill=(245, 238, 255))
    return img


DISENOS = (("1 - Nota estelar", diseno_1), ("2 - Estrella con onda", diseno_2),
           ("3 - Constelacion", diseno_3), ("4 - Halo astral", diseno_4))


def main() -> int:
    os.makedirs(SALIDA, exist_ok=True)
    tam = (256, 48, 32, 16)
    for nombre, fn in DISENOS:
        n = nombre.split(" ")[0]
        grande = fn(GRANDE)
        for t in tam:
            grande.resize((t, t), Image.LANCZOS).save(
                os.path.join(SALIDA, "c%s_%d.png" % (n, t)))
        grande.resize((256, 256), Image.LANCZOS).save(os.path.join(SALIDA, "c%s_256.png" % n))

    # hoja comparativa: el grande + los chicos ampliados x4 + una tira tipo barra de tareas
    filas = len(DISENOS)
    cols = [(48, 192), (32, 128), (16, 64)]
    ancho = 20 + 256 + 32 + sum(w for _t, w in cols) + 20 * len(cols) + 20
    alto = 20 + filas * (256 + 26) + 86
    hoja = Image.new("RGB", (ancho, alto), (16, 16, 22))
    hd = ImageDraw.Draw(hoja)
    try:
        from widget import draw as wdraw
        f = wdraw._font("title", 15)
        fs = wdraw._font("body", 11)
    except Exception:
        f = fs = None
    for i, (nombre, _fn) in enumerate(DISENOS):
        y = 20 + i * (256 + 26)
        n = nombre.split(" ")[0]
        big = Image.open(os.path.join(SALIDA, "c%s_256.png" % n)).convert("RGBA")
        hoja.paste(big, (20, y + 18), big)
        if f:
            hd.text((20, y), nombre, font=f, fill=(232, 228, 246))
        x = 20 + 256 + 32
        for t, w in cols:
            im = Image.open(os.path.join(SALIDA, "c%s_%d.png" % (n, t))).convert("RGBA")
            im = im.resize((t * 4, t * 4), Image.NEAREST)
            hoja.paste(im, (x, y + 30), im)
            if fs:
                hd.text((x, y + 30 + t * 4 + 6), "%d px" % t, font=fs, fill=(150, 146, 170))
            x += w + 20
    # tira tipo barra de tareas de Windows 11 (48 px de alto, iconos de 24)
    tira_y = alto - 74
    hd.rectangle([0, tira_y, ancho, alto], fill=(32, 32, 36))
    if fs:
        hd.text((20, tira_y + 6), "como se veria en la barra de tareas (24 px)", font=fs,
                fill=(180, 176, 196))
    x = 20
    for nombre, _fn in DISENOS:
        n = nombre.split(" ")[0]
        im = Image.open(os.path.join(SALIDA, "c%s_48.png" % n)).convert("RGBA")
        im = im.resize((24, 24), Image.LANCZOS)
        hoja.paste(im, (x, tira_y + 26), im)
        x += 44
    destino = os.path.join(os.path.expanduser("~"), "Desktop", "astra_iconos.png")
    hoja.save(destino)
    print("hoja:", destino, hoja.size)
    print("piezas en:", SALIDA)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
