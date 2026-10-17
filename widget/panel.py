"""Panel del widget: una ventana flotante con la cancion en grande.

Aparece al hacer clic en la caratula del widget y se cierra al perder el foco, con
Escape o haciendo clic afuera. Es la version "mini reproductor": caratula grande,
titulo y artista legibles, barra de progreso clickeable, controles de transporte y
volumen.

El dibujo vive aca (igual que el del widget, en `draw.py`) para poder verificarlo sin
ventana: `render()` devuelve una imagen y `rects()` las zonas clicables, y las pruebas
comprueban las dos cosas por separado.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from . import draw

# Geometria en unidades logicas (se escala por k = alto de la barra / 40).
W = 320
H = 178
MARGEN = 14
TAPA = 92
TAPA_X = 16
TAPA_Y = 16
TEXTO_X = TAPA_X + TAPA + 16
TITULO_Y = 24
ARTISTA_Y = 50
TERCERA_Y = 72
BARRA_Y = 108
BARRA_H = 5
TIEMPOS_Y = 120
CTRL_Y = 140
CTRL_CELL = 46
VOL_X = 250
VOL_Y = 158
VOL_W = 58
CERRAR = 13          # lado de la cruz de cerrar


def size(k: float) -> tuple[int, int]:
    return (int(round(W * k)), int(round(H * k)))


def rects(k: float) -> dict:
    """Zonas del panel en px reales (coordenadas del cliente)."""
    def r(x, y, w, h):
        return (int(round(x * k)), int(round(y * k)),
                int(round((x + w) * k)), int(round((y + h) * k)))

    ctrls = []
    # 10 px a la izquierda del centro: asi la zona de "siguiente" no pisa la del
    # altavoz (medido: se tocaban por 3 px, y dos zonas que se pisan se roban clics)
    x0 = (W - 3 * CTRL_CELL) / 2.0 - 10
    for i in range(3):
        ctrls.append(r(x0 + i * CTRL_CELL, CTRL_Y, CTRL_CELL, H - CTRL_Y))
    return {
        "tapa": r(TAPA_X, TAPA_Y, TAPA, TAPA),
        "barra": r(MARGEN, BARRA_Y, W - 2 * MARGEN, BARRA_H),
        "barra_zona": r(MARGEN, BARRA_Y - 6, W - 2 * MARGEN, BARRA_H + 12),
        "controles": ctrls,
        "volumen": r(VOL_X, VOL_Y, VOL_W, 8),
        "volumen_zona": r(VOL_X - 4, VOL_Y - 8, VOL_W + 8, 24),
        "altavoz": r(VOL_X - 24, VOL_Y - 6, 18, 20),
        "cerrar": r(W - MARGEN - CERRAR, MARGEN / 2, CERRAR, CERRAR),
    }


def _dentro(r, x, y) -> bool:
    return bool(r) and r[0] <= x <= r[2] and r[1] <= y <= r[3]


def hit(x: int, y: int, k: float) -> int:
    """Que hay bajo el cursor: 0/1/2 transporte, 3 barra, 4 volumen, 5 altavoz,
    6 cerrar, 7 caratula, -1 nada."""
    z = rects(k)
    for i, c in enumerate(z["controles"]):
        if _dentro(c, x, y):
            return i
    if _dentro(z["barra_zona"], x, y):
        return 3
    if _dentro(z["volumen_zona"], x, y):
        return 4
    if _dentro(z["altavoz"], x, y):
        return 5
    if _dentro(z["cerrar"], x, y):
        return 6
    if _dentro(z["tapa"], x, y):
        return 7
    return -1


def frac_en_barra(x: int, k: float) -> float:
    z = rects(k)["barra"]
    if z[2] <= z[0]:
        return 0.0
    return max(0.0, min(1.0, (x - z[0]) / float(z[2] - z[0])))


def frac_en_volumen(x: int, k: float) -> float:
    z = rects(k)["volumen"]
    if z[2] <= z[0]:
        return 0.0
    return max(0.0, min(1.0, (x - z[0]) / float(z[2] - z[0])))


def render(state, cfg: dict, *, art: Image.Image | None = None, volume=None,
           hover: int = -1, k: float = 1.0, scrub: float | None = None) -> Image.Image:
    """Dibuja el panel completo y devuelve la imagen (RGBA)."""
    SS = max(1, int(cfg.get("supersample", 3)))
    S = k * SS
    Wp, Hp = int(round(W * k)), int(round(H * k))
    img = Image.new("RGBA", (Wp * SS, Hp * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    theme = draw.theme_for_base(cfg, (26, 28, 36))
    # 250 y no 247: con 247 se transparentaba el texto de la ventana de atras y
    # ensuciaba la lectura (visto en la captura del panel en vivo)
    fondo = draw._col(theme, "chip", 250)
    borde = draw._col(theme, "border", 200)
    radio = int(round(12 * S))
    d.rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], radius=radio,
                        fill=fondo, outline=borde, width=max(1, int(round(1 * S))))

    idle = not state.has_session
    dim = 0.6 if idle else 1.0
    tcol = draw._col(theme, "title", int(255 * dim))
    acol = draw._col(theme, "artist", int(255 * dim))
    scol = draw._col(theme, "artist", int(170 * dim))
    icon_col = draw._col(theme, "icon", int(255 * dim))
    icon_dim = draw._col(theme, "icon_dim", int(255 * dim))
    acc = draw._col(theme, "accent_progress", 255)

    # --- caratula -----------------------------------------------------------
    z = rects(k)
    if art is not None:
        img.paste(art, (int(z["tapa"][0] * SS), int(z["tapa"][1] * SS)), art)

    # --- textos -------------------------------------------------------------
    f_titulo = draw._font("title", max(9, int(round(15 * S))))
    f_artista = draw._font("body", max(8, int(round(12 * S))))
    f_chico = draw._font("body", max(7, int(round(9 * S))))
    ancho_texto = (W - TEXTO_X - MARGEN) * S

    def recortar(t, fuente, ancho):
        if not t:
            return ""
        while t and d.textlength(t + "…", font=fuente) > ancho:
            t = t[:-1]
        return (t + "…") if t and d.textlength(t, font=fuente) > ancho else t

    titulo = state.title or ("Sin reproduccion" if idle else "")
    artista = state.display_artist if not idle else ""
    tercera = state.album if (state.album and state.album != artista) else ""
    if not tercera and not idle:
        tercera = state.app_name
    d.text((TEXTO_X * S, TITULO_Y * S), recortar(titulo, f_titulo, ancho_texto),
           font=f_titulo, fill=tcol)
    d.text((TEXTO_X * S, ARTISTA_Y * S), recortar(artista, f_artista, ancho_texto),
           font=f_artista, fill=acol)
    d.text((TEXTO_X * S, TERCERA_Y * S), recortar(tercera, f_chico, ancho_texto),
           font=f_chico, fill=scol)

    # --- barra de progreso ---------------------------------------------------
    zb = z["barra"]
    bh = BARRA_H * S * (1.6 if hover == 3 or scrub is not None else 1.0)
    cy = (zb[1] + zb[3]) / 2.0 * SS
    d.rounded_rectangle([zb[0] * SS, cy - bh / 2, zb[2] * SS, cy + bh / 2],
                        radius=bh / 2, fill=draw._col(theme, "track", 255))
    if state.duration > 0 and not idle:
        pos = scrub if scrub is not None else state.live_position()
        frac = max(0.0, min(1.0, pos / state.duration))
        if frac > 0:
            d.rounded_rectangle([zb[0] * SS, cy - bh / 2,
                                 zb[0] * SS + (zb[2] - zb[0]) * frac * SS, cy + bh / 2],
                                radius=bh / 2, fill=acc)
        if hover == 3 or scrub is not None:
            r_knob = 5.0 * S
            kx = (zb[0] + (zb[2] - zb[0]) * frac) * SS
            d.ellipse([kx - r_knob, cy - r_knob, kx + r_knob, cy + r_knob], fill=acc)
        izq = draw.fmt_time(pos)
        der = draw.fmt_time(state.duration)
        d.text((zb[0] * SS, TIEMPOS_Y * S), izq, font=f_chico, fill=scol)
        ancho_der = d.textlength(der, font=f_chico)
        d.text((zb[2] * SS - ancho_der, TIEMPOS_Y * S), der, font=f_chico, fill=scol)

    # --- controles -----------------------------------------------------------
    kinds = [("prev", state.can_prev), ("pause" if state.playing else "play",
                                        state.can_toggle), ("next", state.can_next)]
    for i, ((x0, y0, x1, y1), (kind, habilitado)) in enumerate(zip(z["controles"], kinds)):
        hot = hover == i and not idle
        cx, cy2 = (x0 + x1) / 2.0 * SS, (y0 + y1) / 2.0 * SS
        if hot:
            r_hl = 19.0 * S
            capa = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(capa).ellipse([cx - r_hl, cy2 - r_hl, cx + r_hl, cy2 + r_hl],
                                         fill=(255, 255, 255, 30))
            img.alpha_composite(capa)
            d = ImageDraw.Draw(img)
        draw._draw_icon(d, cx, cy2, kind, S * 1.5,
                        icon_col if (habilitado and not idle) else icon_dim)

    # --- volumen -------------------------------------------------------------
    zz = z["altavoz"]
    mudo = bool(volume[1]) if volume else False
    disp = bool(volume[3]) if volume else False
    draw._draw_icon(d, (zz[0] + zz[2]) / 2.0 * SS, (zz[1] + zz[3]) / 2.0 * SS,
                    "vol_mute" if mudo else "vol", S,
                    icon_col if disp else icon_dim)
    zv = z["volumen"]
    cyv = (zv[1] + zv[3]) / 2.0 * SS
    d.rounded_rectangle([zv[0] * SS, cyv - 3 * S, zv[2] * SS, cyv + 3 * S],
                        radius=3 * S, fill=draw._col(theme, "track", 255))
    if disp:
        nivel = float(volume[0])
        if mudo:
            nivel = 0.0
        if nivel > 0:
            d.rounded_rectangle([zv[0] * SS, cyv - 3 * S,
                                 zv[0] * SS + (zv[2] - zv[0]) * nivel * SS, cyv + 3 * S],
                                radius=3 * S, fill=acc)

    # --- cerrar --------------------------------------------------------------
    zc = z["cerrar"]
    grosor = max(1, int(round(1.6 * S)))
    ccx, ccy = (zc[0] + zc[2]) / 2.0 * SS, (zc[1] + zc[3]) / 2.0 * SS
    brazo = CERRAR * S * 0.34
    col_x = icon_col if hover == 6 else acol
    d.line([(ccx - brazo, ccy - brazo), (ccx + brazo, ccy + brazo)], fill=col_x, width=grosor)
    d.line([(ccx - brazo, ccy + brazo), (ccx + brazo, ccy - brazo)], fill=col_x, width=grosor)

    return img.resize((Wp, Hp), Image.LANCZOS)
