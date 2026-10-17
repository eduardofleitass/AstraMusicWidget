"""Panel del widget: la ventana flotante con la cancion (normal y compacta).

Aparece al hacer clic en la caratula del widget y sirve para escuchar musica sin
buscar el reproductor. Tiene dos tamanos:

- **normal**: caratula grande, titulo, artista, album, barra con tiempos, controles y
  volumen. Pensado para el escritorio.
- **chico**: la mitad de alto (una fila de caratula y texto, otra de controles, barra y
  volumen), sin la tercera linea y con los tiempos en el renglon del artista. Pensado
  para jugar: tapa menos pantalla.

En modo gaming la ventana ademas no le roba el foco al juego (`WS_EX_NOACTIVATE`), se
cierra sola por inactividad y puede dejar pasar los clics (eso lo maneja `app.py`: aca
solo se dibuja y se dice que hay bajo el cursor).

El dibujo vive aca (igual que el del widget, en `draw.py`) para poder verificarlo sin
ventana: `render()` devuelve una imagen y `rects()` las zonas clicables, y las pruebas
comprueban las dos cosas por separado.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from . import draw

# Cada tamano define su geometria en unidades logicas (se escala por k = alto de la
# barra / 40) y los tamanos de fuente. Todo lo que cambia entre tamanos esta aca.
LAYOUTS = {
    "normal": {
        "W": 320, "H": 178,
        "margen": 14,
        "tapa": (16, 16, 92), "tapa_radio": 10,
        "texto_x": 124, "titulo_y": 24, "titulo_px": 15,
        "artista_y": 50, "artista_px": 12, "tercera_y": 72, "tercera_px": 9,
        "tiempos_en_texto": False,
        "barra": (14, 108, 292, 5), "barra_zona_alto": 24, "tiempos_y": 120,
        "ctrls": (81, 140, 46, 38, 3), "icono_escala": 1.5,
        "vol_icono": (226, 152, 18, 20), "vol_barra": (250, 158, 58, 8),
        "vol_zona": (246, 150, 66, 24),
        "cerrar": (293, 7, 13, 13),
    },
    "chico": {
        "W": 280, "H": 84,
        "margen": 8,
        "tapa": (10, 10, 56), "tapa_radio": 8,
        "texto_x": 76, "titulo_y": 18, "titulo_px": 13, "texto_margen_extra": 22,
        "artista_y": 34, "artista_px": 10, "tercera_y": None, "tercera_px": 9,
        "tiempos_en_texto": True,
        "barra": (106, 64, 116, 4), "barra_zona_alto": 16, "tiempos_y": 36,
        "ctrls": (8, 54, 30, 26, 3), "icono_escala": 1.15,
        "vol_icono": (228, 58, 16, 18), "vol_barra": (248, 64, 24, 4),
        "vol_zona": (246, 58, 26, 16),
        "cerrar": (260, 6, 10, 10),
    },
}


def layout(cfg: dict) -> dict:
    """El tamano elegido. Acepta "chico"/"compacto" o "normal"."""
    nombre = str(cfg.get("panel_size", "normal")).strip().lower()
    return LAYOUTS["chico" if nombre.startswith(("chi", "com", "min")) else "normal"]


def size(k: float, cfg: dict) -> tuple[int, int]:
    L = layout(cfg)
    return (int(round(L["W"] * k)), int(round(L["H"] * k)))


def rects(k: float, cfg: dict) -> dict:
    """Zonas del panel en px reales (coordenadas del cliente)."""
    L = layout(cfg)

    def r(x, y, w, h):
        return (int(round(x * k)), int(round(y * k)),
                int(round((x + w) * k)), int(round((y + h) * k)))

    cx, cy, cw, ch, n = L["ctrls"]
    ctrls = [r(cx + i * cw, cy, cw, ch) for i in range(n)]
    bx, by, bw, bh = L["barra"]
    vx, vy, vw, vh = L["vol_barra"]
    ix, iy, iw, ih = L["vol_icono"]
    return {
        "tapa": r(L["tapa"][0], L["tapa"][1], L["tapa"][2], L["tapa"][2]),
        "barra": r(bx, by, bw, bh),
        "barra_zona": r(bx, by - (L["barra_zona_alto"] - bh) / 2.0, bw, L["barra_zona_alto"]),
        "controles": ctrls,
        "volumen": r(vx, vy, vw, vh),
        "volumen_zona": r(L["vol_zona"][0], L["vol_zona"][1],
                          L["vol_zona"][2], L["vol_zona"][3]),
        "altavoz": r(ix, iy, iw, ih),
        "cerrar": r(L["cerrar"][0], L["cerrar"][1], L["cerrar"][2], L["cerrar"][3]),
        # el ancho del texto deja libre la esquina de la cruz (medido: en el panel
        # chico el titulo se metia en la zona del cerrar)
        "texto": r(L["texto_x"], L["titulo_y"],
                   L["W"] - L["texto_x"] - L["margen"] - L.get("texto_margen_extra", 0),
                   max(20, L["H"] * 0.45)),
    }


def _dentro(r, x, y) -> bool:
    return bool(r) and r[0] <= x <= r[2] and r[1] <= y <= r[3]


def hit(x: int, y: int, k: float, cfg: dict) -> int:
    """Que hay bajo el cursor: 0/1/2 transporte, 3 barra, 4 volumen, 5 altavoz,
    6 cerrar, 7 caratula, -1 nada."""
    z = rects(k, cfg)
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


def _frac(x: int, z: tuple) -> float:
    if z[2] <= z[0]:
        return 0.0
    return max(0.0, min(1.0, (x - z[0]) / float(z[2] - z[0])))


def frac_en_barra(x: int, k: float, cfg: dict) -> float:
    return _frac(x, rects(k, cfg)["barra"])


def frac_en_volumen(x: int, k: float, cfg: dict) -> float:
    return _frac(x, rects(k, cfg)["volumen"])


def render(state, cfg: dict, *, art: Image.Image | None = None, volume=None,
           hover: int = -1, k: float = 1.0, scrub: float | None = None) -> Image.Image:
    """Dibuja el panel completo y devuelve la imagen (RGBA)."""
    L = layout(cfg)
    SS = max(1, int(cfg.get("supersample", 3)))
    S = k * SS
    Wp, Hp = int(round(L["W"] * k)), int(round(L["H"] * k))
    img = Image.new("RGBA", (Wp * SS, Hp * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    theme = draw.theme_for_base(cfg, (26, 28, 36))
    # 250 y no 247: con 247 se transparentaba el texto de la ventana de atras y
    # ensuciaba la lectura (visto en la captura del panel en vivo)
    alpha_fondo = int(max(60, min(255, cfg.get("panel_bg_alpha", 250))))
    d.rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1],
                        radius=int(round(12 * S)),
                        fill=draw._col(theme, "chip", alpha_fondo),
                        outline=draw._col(theme, "border", 200),
                        width=max(1, int(round(1 * S))))

    idle = not state.has_session
    dim = 0.6 if idle else 1.0
    # posicion que se muestra: la del arrastre si se esta arrastrando
    pos = 0.0
    if state.duration > 0 and not idle:
        pos = scrub if scrub is not None else state.live_position()
    tcol = draw._col(theme, "title", int(255 * dim))
    acol = draw._col(theme, "artist", int(255 * dim))
    scol = draw._col(theme, "artist", int(170 * dim))
    icon_col = draw._col(theme, "icon", int(255 * dim))
    icon_dim = draw._col(theme, "icon_dim", int(255 * dim))
    acc = draw._col(theme, "accent_progress", 255)
    z = rects(k, cfg)

    # --- caratula -----------------------------------------------------------
    if art is not None:
        img.paste(art, (int(z["tapa"][0] * SS), int(z["tapa"][1] * SS)), art)

    # --- textos -------------------------------------------------------------
    f_titulo = draw._font("title", max(8, int(round(L["titulo_px"] * S))))
    f_artista = draw._font("body", max(7, int(round(L["artista_px"] * S))))
    f_chico = draw._font("body", max(6, int(round(L["tercera_px"] * S))))
    ancho_texto = (z["texto"][2] - z["texto"][0]) * SS

    def recortar(t, fuente, ancho):
        if not t:
            return ""
        if d.textlength(t, font=fuente) <= ancho:
            return t
        while t and d.textlength(t + "…", font=fuente) > ancho:
            t = t[:-1]
        return (t + "…") if t else ""

    titulo = state.title or ("Sin reproduccion" if idle else "")
    artista = state.display_artist if not idle else ""
    tercera = ""
    if L["tercera_y"] is not None:
        tercera = state.album if (state.album and state.album != artista) else ""
        if not tercera and not idle:
            tercera = state.app_name
    # En el panel chico los tiempos comparten el renglon del artista: hay que
    # reservarles su ancho o el nombre se les encima (medido en la captura: "Fuerza
    # Regida y Grupo Fronte" + "0:07 / 3:32" uno sobre el otro).
    texto_tiempos = ""
    if L["tiempos_en_texto"] and state.duration > 0 and not idle:
        texto_tiempos = (f"{draw.fmt_time(scrub if scrub is not None else pos)} / "
                         f"{draw.fmt_time(state.duration)}")
    ancho_artista = ancho_texto
    if texto_tiempos:
        ancho_artista -= d.textlength(texto_tiempos, font=f_chico) + 8 * S
    tx = z["texto"][0] * SS
    d.text((tx, L["titulo_y"] * S), recortar(titulo, f_titulo, ancho_texto),
           font=f_titulo, fill=tcol)
    d.text((tx, L["artista_y"] * S), recortar(artista, f_artista, ancho_artista),
           font=f_artista, fill=acol)
    if L["tercera_y"] is not None:
        d.text((tx, L["tercera_y"] * S), recortar(tercera, f_chico, ancho_texto),
               font=f_chico, fill=scol)

    # --- barra de progreso ---------------------------------------------------
    zb = z["barra"]
    bh = (zb[3] - zb[1]) * (1.6 if hover == 3 or scrub is not None else 1.0)
    cy = (zb[1] + zb[3]) / 2.0 * SS
    d.rounded_rectangle([zb[0] * SS, cy - bh / 2, zb[2] * SS, cy + bh / 2],
                        radius=bh / 2, fill=draw._col(theme, "track", 255))
    if state.duration > 0 and not idle:
        frac = max(0.0, min(1.0, pos / state.duration))
        if frac > 0:
            d.rounded_rectangle([zb[0] * SS, cy - bh / 2,
                                 zb[0] * SS + (zb[2] - zb[0]) * frac * SS, cy + bh / 2],
                                radius=bh / 2, fill=acc)
        if hover == 3 or scrub is not None:
            r_knob = 5.0 * S * (1.0 if L["W"] > 300 else 0.8)
            kx = (zb[0] + (zb[2] - zb[0]) * frac) * SS
            d.ellipse([kx - r_knob, cy - r_knob, kx + r_knob, cy + r_knob], fill=acc)

    # --- tiempos -------------------------------------------------------------
    if state.duration > 0 and not idle:
        izq, der = draw.fmt_time(pos), draw.fmt_time(state.duration)
        if L["tiempos_en_texto"]:
            ancho_t = d.textlength(texto_tiempos, font=f_chico)
            d.text((z["texto"][2] * SS - ancho_t, L["tiempos_y"] * S), texto_tiempos,
                   font=f_chico, fill=scol)
        else:
            d.text((zb[0] * SS, L["tiempos_y"] * S), izq, font=f_chico, fill=scol)
            ancho_d = d.textlength(der, font=f_chico)
            d.text((zb[2] * SS - ancho_d, L["tiempos_y"] * S), der, font=f_chico, fill=scol)

    # --- controles -----------------------------------------------------------
    kinds = [("prev", state.can_prev), ("pause" if state.playing else "play",
                                        state.can_toggle), ("next", state.can_next)]
    for i, ((x0, y0, x1, y1), (kind, habilitado)) in enumerate(zip(z["controles"], kinds)):
        cx2, cy2 = (x0 + x1) / 2.0 * SS, (y0 + y1) / 2.0 * SS
        if hover == i and not idle:
            r_hl = min(x1 - x0, y1 - y0) * 0.62 * SS
            capa = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(capa).ellipse([cx2 - r_hl, cy2 - r_hl, cx2 + r_hl, cy2 + r_hl],
                                         fill=(255, 255, 255, 30))
            img.alpha_composite(capa)
            d = ImageDraw.Draw(img)
        draw._draw_icon(d, cx2, cy2, kind, S * L["icono_escala"],
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
    radio_v = max(1.0, (zv[3] - zv[1]) / 2.0 * SS)
    d.rounded_rectangle([zv[0] * SS, cyv - radio_v, zv[2] * SS, cyv + radio_v],
                        radius=radio_v, fill=draw._col(theme, "track", 255))
    if disp:
        nivel = 0.0 if mudo else float(volume[0])
        if nivel > 0:
            d.rounded_rectangle([zv[0] * SS, cyv - radio_v,
                                 zv[0] * SS + (zv[2] - zv[0]) * nivel * SS,
                                 cyv + radio_v], radius=radio_v, fill=acc)

    # --- cerrar --------------------------------------------------------------
    zc = z["cerrar"]
    grosor = max(1, int(round(1.6 * S)))
    ccx, ccy = (zc[0] + zc[2]) / 2.0 * SS, (zc[1] + zc[3]) / 2.0 * SS
    brazo = (zc[2] - zc[0]) * 0.34 * SS
    col_x = icon_col if hover == 6 else acol
    d.line([(ccx - brazo, ccy - brazo), (ccx + brazo, ccy + brazo)], fill=col_x, width=grosor)
    d.line([(ccx - brazo, ccy + brazo), (ccx + brazo, ccy - brazo)], fill=col_x, width=grosor)

    return img.resize((Wp, Hp), Image.LANCZOS)
