"""Regresion SIN pantalla: no mira ni mueve el escritorio, asi que corre con la
sesion bloqueada. Cubre lo que se toco en los ultimos commits.

    python tools/regresion_headless.py
"""
from __future__ import annotations

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw

from widget import ajustes as A
from widget import config as cfgmod
from widget import draw
from widget import panel as panel_mod
from widget.media import MediaState

fallos = []
total = [0]


def check(nombre, ok, detalle=""):
    total[0] += 1
    if not ok:
        fallos.append(nombre)
        print("FALLA  %-58s %s" % (nombre, detalle))


def art_prueba(color=(200, 30, 30)):
    src = Image.new("RGB", (300, 300), color)
    d = ImageDraw.Draw(src)
    d.ellipse([75, 75, 225, 225], fill=(255, 255, 255))
    d.rectangle([240, 240, 299, 299], fill=(20, 200, 60))
    buf = io.BytesIO()
    src.save(buf, "PNG")
    return buf.getvalue()


def estado(art, key="k"):
    return MediaState(has_session=True, app_id="brave.exe", title="Titulo de prueba largo",
                      artist="Artista", album="", playing=True, position=30.0,
                      duration=100.0, position_at=0.0, art=art, art_key=key,
                      can_seek=True, min_seek=0, max_seek=100, can_toggle=True,
                      can_prev=True, can_next=True)


def rojo_en(img, caja):
    x0, y0, x1, y1 = caja
    n = 0
    for x in range(x0, x1):
        for y in range(y0, y1):
            r, g, b = img.convert("RGB").getpixel((x, y))[:3]
            if r > 150 and g < 90 and b < 90:
                n += 1
    return n / float((x1 - x0) * (y1 - y0))


cfg = cfgmod.load()
art = art_prueba()
st = estado(art)

# ---------------------------------------------------------------- 1. caratula
# La regresion del bug reportado: la caratula tiene que ocupar su caja entera, tanto en
# el widget como en la vista previa de Ajustes (que ahora usa la misma escala).
for k in (1.0, 1.2, 1.5):
    SS = max(1, int(cfg.get("supersample", 3)))
    S = k * SS
    a = draw.get_art(art, "k", int(round(draw.ART * S)), int(round(draw.ART_RADIUS * S)))
    img = draw.render(st, dict(cfg, width=370), art=a, hover=-1, marquee=0.0, k=k,
                      base=(26, 28, 36), height=int(round(40 * k)), opaque=False,
                      waves=[], volume=None)
    caja = (int(draw.PAD * k), int(draw.PAD * k),
            int((draw.PAD + draw.ART) * k), int((draw.PAD + draw.ART) * k))
    frac = rojo_en(img, caja)
    check("k=%.1f: la caratula llena su caja (>=50%% rojo)" % k, frac > 0.5,
          "%.0f%%" % (frac * 100))

# ---------------------------------------------------------------- 2. ajustes
mons = [{"nombre": "Principal", "rect": (0, 0, 1920, 1080), "tildado": True},
        {"nombre": "Monitor 2", "rect": (1920, 0, 3200, 1080), "tildado": False}]
atajos = ["Ctrl+Alt+M   ·   mostrar u ocultar el widget",
          "Ctrl+Alt+P   ·   play/pausa"]
for k in (1.0, 1.2, 1.5):
    ancho, alto = A.size(k)
    for seccion in A.SECCIONES:
        z = A.rects(k, cfg, seccion, mons, atajos)
        fuera = [f for f in z["filas"]
                 if f["rect"][0] < 0 or f["rect"][1] < 0
                 or f["rect"][2] > ancho or f["rect"][3] > alto]
        check("k=%.1f %s: los controles entran en la ventana" % (k, seccion), not fuera,
              fuera[:2])
        # el render no puede explotar ni salir en blanco
        img = A.render(cfg, seccion, None, k, None, mons, atajos)
        check("k=%.1f %s: el render sale del tamano pedido" % (k, seccion),
              img.size == (ancho, alto), img.size)
        colores = img.convert("RGB").getcolors(maxcolors=200000) or []
        check("k=%.1f %s: el render no es un plano de un solo color" % (k, seccion),
              len(colores) > 12, len(colores))

# hit de cada tipo de control, en el centro de lo que se dibuja
z = A.rects(1.2, cfg, "Apariencia")
seg = next(f for f in z["filas"] if f["tipo"] == "seg")
for b in seg["botones"]:
    r = b["rect"]
    got = A.hit((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, 1.2, cfg, "Apariencia")
    check("segmentado '%s' responde" % b["texto"], got == ("chip_alpha", b["valor"]), got)
sw = next(f for f in z["filas"] if f["tipo"] == "swatches")
for b in sw["botones"]:
    r = b["rect"]
    got = A.hit((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, 1.2, cfg, "Apariencia")
    check("swatch '%s' responde" % b["texto"], got == ("chip_color", b["valor"]), got)
for i, r in enumerate(z["nav"]):
    got = A.hit((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, 1.2, cfg, "Apariencia")
    check("navegacion a %s responde" % A.SECCIONES[i], got == ("seccion", A.SECCIONES[i]), got)
r = z["cerrar"]
check("la cruz responde",
      A.hit((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, 1.2, cfg, "Apariencia")
      == ("cerrar", None))
for nombre, lo, hi in (("width", 150, 520), ("widget_alpha", 40, 255)):
    check("%s: el deslizador arranca en el minimo" % nombre,
          A.valor_slider(nombre, 0.0) == lo, A.valor_slider(nombre, 0.0))
    check("%s: el deslizador termina en el maximo" % nombre,
          A.valor_slider(nombre, 1.0) == hi, A.valor_slider(nombre, 1.0))
check("el deslizador del medio cae en el medio",
      abs(A.valor_slider("width", 0.5) - 335) <= 1, A.valor_slider("width", 0.5))

# ---------------------------------------------------------------- 3. paleta
P = A._paleta(cfg)
check("la paleta tiene todas las claves que usa el dibujo",
      all(k in P for k in ("fondo", "caja", "linea", "txt", "dim", "acc", "sel",
                           "riel", "off", "hueco", "noche")), sorted(P))
check("el acento es morado (azul > rojo > verde)",
      P["acc"][2] > P["acc"][0] > P["acc"][1], P["acc"])
check("el fondo sigue siendo oscuro", max(P["fondo"]) < 60, P["fondo"])
check("el contorno es morado (azul > rojo > verde)",
      P["linea"][2] > P["linea"][0] > P["linea"][1], P["linea"])
# nada de tuplas de color sueltas en el dibujo (se escapaban de la paleta)
import re
fuente = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "widget",
                           "ajustes.py"), encoding="utf-8").read()
cuerpo = fuente[fuente.index("def render("):]
sueltas = re.findall(r"fill=\(\d+, \d+, \d+\)|outline=\(\d+, \d+, \d+\)", cuerpo)
check("el dibujo no tiene colores sueltos fuera de la paleta", not sueltas, sueltas[:4])

# ---------------------------------------------------------------- 4. panel
for tam in ("normal", "chico", "tira"):
    L = panel_mod.layout(dict(cfg, panel_size=tam))
    W, H = L["W"], L["H"]
    check("panel %s: el tamano es coherente" % tam, 120 < W < 800 and 26 < H < 400, (W, H))
    for nombre, r in L.items():
        if isinstance(r, tuple) and len(r) == 4 and all(isinstance(v, (int, float)) for v in r):
            check("panel %s: %s no se sale del panel" % (tam, nombre),
                  r[0] >= -2 and r[1] >= -2 and r[2] <= W + 2 and r[3] <= H + 2,
                  (nombre, r, (W, H)))

# ---------------------------------------------------------------- 5. config
base = cfgmod.defaults() if hasattr(cfgmod, "defaults") else None
if base:
    faltan = [k for k in base if k not in cfg]
    check("config.json tiene todas las claves conocidas", not faltan, faltan[:5])

print("\n%d comprobaciones, %d fallas" % (total[0], len(fallos)))
if fallos:
    print("FALLARON:", fallos)
raise SystemExit(1 if fallos else 0)
