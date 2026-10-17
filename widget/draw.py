"""Renderizado del widget con Pillow.

Estrategia: se dibuja todo el widget en un lienzo ampliado (supersampling x3 por
defecto) y se reduce con LANCZOS. Eso da bordes redondeados, iconos vectoriales y
texto suaves, sin depender de GDI+ ni de un framework de UI.

El resultado final es RGBA opaco: la semitransparencia del "chip" se resuelve
mezclandola contra el color real de la barra de tareas, muestreado con GDI.
"""
from __future__ import annotations

import io
import os
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFont

FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
FONT_CANDIDATES = {
    "title": ["seguisb.ttf", "segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf"],
    "body": ["segoeui.ttf", "segoeuisl.ttf", "arial.ttf", "tahoma.ttf"],
}

# --- metricas en unidades logicas (barra de tareas de 40 px de alto) ---------
REF_H = 40
PAD = 4
ART = 32
ART_RADIUS = 5
TEXT_X = 44
ICON_CELL = 21
ICON_BOX = 11
RIGHT_PAD = 5
TITLE_SIZE = 12
ARTIST_SIZE = 10
TITLE_Y = 5.5
ARTIST_Y = 20.0
LINE_H = 14.0
PROG_Y = 34.5
PROG_H = 2.5
FADE_W = 12.0
# La barra mide 2.5 px de alto: inacertable con el mouse. La zona clicable es una
# franja mas alta alrededor suyo, que ademas se corta donde empiezan los botones.
PROG_HIT_TOP = 29.5
PROG_HIT_BOTTOM = 40.0
KNOB_R = 3.2
# Ondas de sonido: una franja angosta entre el texto y los botones.
WAVE_GAP = 5.0        # aire entre las ondas y los botones
WAVE_BAR_W = 4.0      # ancho de cada barra
WAVE_BAR_GAP = 2.5    # separacion entre barras
WAVE_CY = 18.0        # centro vertical (entre el titulo y el artista)
WAVE_MAX_H = 19.0     # alto maximo de una barra
WAVE_MIN_H = 2.5      # alto de una barra en silencio
WAVE_MIN_TEXT = 40.0  # si el texto quedaria mas angosto que esto, no hay ondas
WAVE_SS = 4           # suavizado propio de la tira de ondas (se dibuja aparte)

_art_cache: dict[tuple[str, int], Image.Image] = {}


@lru_cache(maxsize=32)
def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for name in FONT_CANDIDATES[kind]:
        path = os.path.join(FONT_DIR, name)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _col(theme: dict, key: str, alpha: int = 255) -> tuple:
    rgb = theme.get(key) or (255, 255, 255)
    return (int(rgb[0]), int(rgb[1]), int(rgb[2]), alpha)


def _lum(c: tuple) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def parse_color(v) -> tuple | None:
    """Interpreta un color elegido a mano: "#RRGGBB", "#RGB", [r, g, b] o None.

    Se aceptan las dos formas porque el menu guarda hex y a mano es comodo escribir
    una lista. Lo que no se entiende (o None) significa "el color del tema".
    """
    if v is None:
        return None
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        try:
            return tuple(max(0, min(255, int(c))) for c in v[:3])
        except Exception:
            return None
    s = str(v).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) == 6:
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except ValueError:
            return None
    return None


def hex_color(c: tuple) -> str:
    return "#%02X%02X%02X" % (int(c[0]), int(c[1]), int(c[2]))


# Colores para una barra de tareas clara (tema claro de Windows): si el fondo es
# claro, el texto blanco desaparece. Con el fondo transparente esto deja de ser
# un caso raro y pasa a ser algo que hay que resolver.
LIGHT_THEME = {
    "chip": [243, 244, 248],
    "border": [170, 174, 186],
    "title": [20, 22, 28],
    "artist": [84, 90, 106],
    "icon": [28, 30, 38],
    "icon_dim": [146, 150, 162],
    "track": [188, 192, 202],
}


def theme_for_base(cfg: dict, base: tuple) -> dict:
    """Tema efectivo: el configurado, o su version oscura/clara segun el fondo.

    Ademas resuelve los colores elegidos a mano para la barra de progreso y las
    ondas. Son independientes del tema (y del auto-contraste: si el usuario eligio
    un color, se usa ese, aunque en su barra se note poco).
    """
    theme = dict(cfg.get("theme") or {})
    if cfg.get("auto_contrast", True) and _lum(tuple(base)[:3]) > 130:
        theme.update(LIGHT_THEME)
    accent = theme.get("accent") or (96, 205, 145)
    theme["accent_progress"] = parse_color(cfg.get("progress_color")) or tuple(accent)
    theme["accent_waves"] = parse_color(cfg.get("waves_color")) or tuple(accent)
    return theme


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1],
                                           radius=radius, fill=255)
    return mask


def _placeholder_art(size: int) -> Image.Image:
    """Caratula de reemplazo: degradado + nota musical dibujada a mano."""
    img = Image.new("RGB", (size, size), (34, 36, 48))
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        d.line([(0, y), (size, y)],
               fill=(int(38 + 60 * t), int(40 + 44 * t), int(70 + 70 * t)))
    s = size / 32.0
    head = [10 * s, 17 * s, 18 * s, 25 * s]
    d.ellipse(head, fill=(226, 230, 240))
    d.rectangle([16.4 * s, 7 * s, 18.4 * s, 21.5 * s], fill=(226, 230, 240))
    d.polygon([(16.4 * s, 6.5 * s), (25 * s, 9.5 * s), (25 * s, 14 * s),
               (16.4 * s, 11 * s)], fill=(226, 230, 240))
    return img


def get_art(data: bytes | None, key: str, size: int, radius: int) -> Image.Image:
    """Caratula decodificada, escalada y con esquinas redondeadas (con cache)."""
    cache_key = (key or "placeholder", size)
    hit = _art_cache.get(cache_key)
    if hit is not None:
        return hit
    if data:
        try:
            src = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            src = _placeholder_art(size)
    else:
        src = _placeholder_art(size)
    src = src.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(src, (0, 0), _rounded_mask((size, size), radius))
    if len(_art_cache) > 24:
        _art_cache.clear()
    _art_cache[cache_key] = out
    return out


def _draw_icon(d: ImageDraw.ImageDraw, center_x: float, center_y: float, kind: str,
               S: float, color: tuple) -> None:
    """Icono vectorial en una caja de ICON_BOX x ICON_BOX unidades logicas."""
    box = ICON_BOX * S
    h = box / 2.0
    x0, y0 = center_x - h, center_y - h
    x1, y1 = center_x + h, center_y + h
    bar = max(1.0, 1.6 * S)

    if kind == "play":
        d.polygon([(x0 + box * 0.16, y0), (x1, center_y), (x0 + box * 0.16, y1)],
                  fill=color)
    elif kind == "pause":
        w = box * 0.30
        d.rounded_rectangle([x0 + box * 0.10, y0, x0 + box * 0.10 + w, y1],
                            radius=bar * 0.8, fill=color)
        d.rounded_rectangle([x1 - box * 0.10 - w, y0, x1 - box * 0.10, y1],
                            radius=bar * 0.8, fill=color)
    elif kind == "next":
        d.polygon([(x0, y0), (center_x - box * 0.04, center_y), (x0, y1)], fill=color)
        d.polygon([(center_x - box * 0.02, y0), (x1 - bar, center_y),
                   (center_x - box * 0.02, y1)], fill=color)
        d.rectangle([x1 - bar, y0, x1, y1], fill=color)
    elif kind == "prev":
        d.polygon([(x1, y0), (center_x + box * 0.04, center_y), (x1, y1)], fill=color)
        d.polygon([(center_x + box * 0.02, y0), (x0 + bar, center_y),
                   (center_x + box * 0.02, y1)], fill=color)
        d.rectangle([x0, y0, x0 + bar, y1], fill=color)


def control_rects(width: int, k: float, cfg: dict) -> list[tuple[int, int, int, int]]:
    """Zonas clicables (en px reales) de anterior / play-pausa / siguiente."""
    if not cfg.get("show_controls", True):
        return []
    cell = ICON_CELL * k
    start = (width - RIGHT_PAD * k) - 3 * cell
    rects = []
    for i in range(3):
        x = int(round(start + i * cell))
        rects.append((x, 0, int(round(x + cell)), int(round(REF_H * k))))
    return rects


def progress_span(width: int, cfg: dict) -> tuple[float, float] | None:
    """Extremos de la barra, en px logicos: desde el texto hasta donde empiezan los
    botones. No corre por debajo de ellos; si corriera, la fraccion del clic y el
    lugar donde queda el indicador no coincidirian (se clickea en una x y el
    indicador aparece en otra).
    """
    if not cfg.get("show_progress", True):
        return None
    x0 = float(TEXT_X)
    x1 = float(width - RIGHT_PAD)
    if cfg.get("show_controls", True):
        x1 = min(x1, width - RIGHT_PAD - 3 * ICON_CELL)
    if x1 <= x0:
        return None
    return (x0, x1)


def progress_rect(width: int, k: float, cfg: dict) -> tuple[int, int, int, int] | None:
    """Zona clicable de la barra de progreso (px reales, coordenadas de cliente)."""
    sp = progress_span(width, cfg)
    if not sp:
        return None
    return (int(round(sp[0] * k)), int(round(PROG_HIT_TOP * k)),
            int(round(sp[1] * k)), int(round(PROG_HIT_BOTTOM * k)))


def progress_frac_at(x_real: float, width: int, k: float, cfg: dict) -> float:
    """Que fraccion (0..1) de la barra corresponde a una x del cliente."""
    r = progress_rect(width, k, cfg)
    if not r:
        return 0.0
    span = float(r[2] - r[0])
    if span <= 0:
        return 0.0
    return max(0.0, min(1.0, (x_real - r[0]) / span))


def fmt_time(seconds: float) -> str:
    """mm:ss, o h:mm:ss si pasa de una hora."""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def wave_band(width: int, cfg: dict) -> tuple[float, float] | None:
    """Franja de las ondas, en px logicos: pegada a la izquierda de los botones.

    Devuelve None si el widget es tan angosto que las ondas dejarian el titulo sin
    espacio util; en ese caso no se dibujan (mejor el texto que el adorno).
    """
    n = max(1, min(12, int(cfg.get("wave_bars", 4))))
    ancho = n * WAVE_BAR_W + (n - 1) * WAVE_BAR_GAP
    x1 = float(width - RIGHT_PAD)
    if cfg.get("show_controls", True):
        x1 -= 3 * ICON_CELL
    x1 -= WAVE_GAP
    x0 = x1 - ancho
    if x0 <= TEXT_X + WAVE_MIN_TEXT:
        return None
    return (x0, x1)


def wave_rect(width: int, k: float, cfg: dict) -> tuple[int, int, int, int] | None:
    """Franja de las ondas en px reales (para verificar contra la pantalla)."""
    wb = wave_band(width, cfg)
    if not wb:
        return None
    return (int(round(wb[0] * k)), int(round((WAVE_CY - WAVE_MAX_H / 2) * k)),
            int(round(wb[1] * k)), int(round((WAVE_CY + WAVE_MAX_H / 2) * k)))


def dibujar_ondas(d: ImageDraw.ImageDraw, levels, cfg: dict, S: float, x0: float,
                  cy: float, col: tuple) -> None:
    """Dibuja las barras de las ondas. Lo usan el render completo y la tira suelta."""
    n = max(1, min(12, int(cfg.get("wave_bars", 4))))
    bar_w = WAVE_BAR_W * S
    hueco = WAVE_BAR_GAP * S
    x = x0
    for i in range(n):
        level = float(levels[i]) if i < len(levels) else 0.0
        level = max(0.0, min(1.0, level))
        h = max(WAVE_MIN_H * S, WAVE_MAX_H * S * level)
        d.rounded_rectangle([x, cy - h / 2.0, x + bar_w, cy + h / 2.0],
                            radius=bar_w / 2.0, fill=col)
        x += bar_w + hueco


def render_waves(state, cfg: dict, levels, k: float = 1.0, base: tuple = (32, 34, 42),
                 opaque: bool = True) -> Image.Image | None:
    """Dibuja SOLO la tira de las ondas, del tamano exacto de su franja.

    Se hace aparte del resto del widget para poder animar sin repintar todo el chip:
    el render completo cuesta ~4,4 ms y esta tira ~0,1 ms, asi que la animacion a 20
    cuadros por segundo sale casi gratis (medido, ver README). Se dibuja a 4x y se
    reduce con LANCZOS; en modo transparente la reduccion va en espacio
    premultiplicado, igual que el resto del widget.
    """
    r = wave_rect(int(cfg.get("width", 260)), k, cfg)
    if not r or not levels:
        return None
    W, H = r[2] - r[0], r[3] - r[1]
    if W <= 0 or H <= 0:
        return None
    S = k * WAVE_SS
    img = Image.new("RGBA", (W * WAVE_SS, H * WAVE_SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    theme = theme_for_base(cfg, base)
    col = _col(theme, "accent_waves", 255 if state.playing else 110)
    dibujar_ondas(d, levels, cfg, S, 0.0, H * WAVE_SS / 2.0, col)
    if WAVE_SS <= 1:
        return img
    if opaque:
        return img.resize((W, H), Image.LANCZOS)
    pre = ImageChops.multiply(img.convert("RGB"), img.getchannel("A").convert("RGB"))
    pre = pre.resize((W, H), Image.LANCZOS)
    alpha = img.getchannel("A").resize((W, H), Image.LANCZOS)
    return Image.merge("RGBA", (*pre.split(), alpha))


def render(state, cfg: dict, *, art: Image.Image | None = None, hover: int = -1,
           marquee: float = 0.0, k: float = 1.0, base: tuple = (32, 34, 42),
           height: int | None = None, opaque: bool = True,
           scrub: float | None = None, waves: list[float] | None = None) -> Image.Image:
    """Devuelve el widget dibujado como imagen RGBA del tamano exacto a mostrar.

    opaque=True  -> la transparencia se resuelve mezclando contra `base` (el color
                    muestreado de la barra). El resultado es opaco y va a un DIB que
                    se blitea con BitBlt.
    opaque=False -> se conserva el alpha real, para presentarlo con
                    UpdateLayeredWindow sobre lo que haya detras. En este modo los
                    canales RGB vuelven PREMULTIPLICADOS (que es lo que espera
                    AC_SRC_ALPHA), asi que no hay que volver a multiplicar.
    scrub        -> segundos destino mientras se arrastra la barra de progreso: la
                    barra y el texto muestran a donde va a saltar, sin tocar todavia
                    la reproduccion.
    waves        -> alturas (0..1) de las ondas de sonido, una por barra. None = no
                    se dibujan. Es una animacion: quien dibuja no sabe de audio, solo
                    recibe las alturas del momento.
    """
    SS = max(1, int(cfg.get("supersample", 3)))
    theme = theme_for_base(cfg, base)
    W = int(round(cfg.get("width", 260) * k))
    H = int(height if height is not None else round(REF_H * k))
    S = k * SS
    canvas = (W * SS, H * SS)

    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    chip_alpha = max(0, min(255, int(cfg.get("chip_alpha", 232))))
    if chip_alpha > 0:
        radius = cfg.get("corner_radius", 7) * S
        d.rounded_rectangle([0, 1.5 * S, W * SS - 1, H * SS - 2.5 * S], radius=radius,
                            fill=_col(theme, "chip", chip_alpha),
                            outline=_col(theme, "border", min(210, chip_alpha + 40)),
                            width=max(1, round(S)))

    idle = not state.has_session
    dim = 0.55 if idle else 1.0

    # ---------------------------------------------------------------- caratula
    text_x = TEXT_X * S
    if cfg.get("show_art", True):
        a = art if art is not None else get_art(None, "", int(round(ART * S)),
                                               int(round(ART_RADIUS * S)))
        img.paste(a, (int(PAD * S), int(PAD * S)), a)
        text_x = (TEXT_X) * S

    controls = control_rects(W, k, cfg)
    cells_x = controls[0][0] * SS if controls else W * SS - RIGHT_PAD * S
    area_w = max(10.0, cells_x - 6 * S - text_x)
    # Las ondas ocupan su propia franja: el titulo y el artista se recortan antes
    # de llegar ahi, asi el texto nunca pasa por debajo de la animacion.
    wb = wave_band(int(cfg.get("width", 260)), cfg) if waves is not None else None
    if wb:
        area_w = max(10.0, wb[0] * S - 6 * S - text_x)

    # ------------------------------------------------------------------ titulo
    title = state.title or ("Sin reproduccion" if idle else "Desconocido")
    f_title = _font("title", max(8, int(round(TITLE_SIZE * S))))
    f_artist = _font("body", max(7, int(round(ARTIST_SIZE * S))))
    tcol = _col(theme, "title", int(255 * dim)) if not idle else _col(theme, "artist", 200)
    acol = _col(theme, "artist", int(255 * dim))

    tw = d.textlength(title, font=f_title)
    if tw <= area_w:
        d.text((text_x, TITLE_Y * S), title, font=f_title, fill=tcol)
    else:
        # Marquesina: la linea se desplaza en bucle continuo dentro de su recorte,
        # con un desvanecido en el borde derecho para que el corte no se note.
        layer = Image.new("RGBA", (int(area_w), int(LINE_H * S)), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        period = tw + cfg.get("marquee_gap", 40) * S
        off = (marquee * S) % period
        ld.text((-off, 0), title, font=f_title, fill=tcol)
        ld.text((-off + period, 0), title, font=f_title, fill=tcol)
        fade = max(2, int(min(FADE_W * S, area_w * 0.35)))
        ramp = Image.new("L", (fade, 1))
        rp = ramp.load()
        for i in range(fade):
            rp[i, 0] = int(255 * (i / (fade - 1.0)))
        mask = Image.new("L", layer.size, 255)
        mask.paste(ramp.resize((fade, layer.size[1])), (layer.size[0] - fade, 0))
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
        img.paste(layer, (int(text_x), int(TITLE_Y * S)), layer)

    # ------------------------------------------------------------------ artista
    artist = state.display_artist if not idle else "Abrí Spotify, YouTube o tu reproductor"
    if idle:
        artist = "Abrí Spotify, YouTube o tu reproductor"
    elif not artist:
        artist = state.app_name or ""
    elif state.app_name:
        artist = f"{artist}"
    if scrub is not None and state.duration > 0:
        # mientras se arrastra la barra, el renglon del artista dice a donde va
        artist = f"{fmt_time(scrub)} / {fmt_time(state.duration)}"
        acol = _col(theme, "accent_progress", 255)
    f_artist_max = area_w
    if d.textlength(artist, font=f_artist) > f_artist_max:
        while artist and d.textlength(artist + "…", font=f_artist) > f_artist_max:
            artist = artist[:-1]
        artist = (artist + "…") if artist else ""
    d.text((text_x, ARTIST_Y * S), artist, font=f_artist, fill=acol)

    # ------------------------------------------------------------------ iconos
    if controls:
        # El resaltado del hover va en una capa aparte y se compone de verdad:
        # ImageDraw sobre RGBA reemplaza el pixel (no mezcla), asi que dibujar el
        # circulo translucido directo sobre el chip lo dejaria con alpha 26, o sea
        # un agujero casi transparente en vez de un resaltado.
        if hover >= 0 and not idle and hover < len(controls):
            x0, y0, x1, y1 = controls[hover]
            hl = Image.new("RGBA", canvas, (0, 0, 0, 0))
            hd = ImageDraw.Draw(hl)
            r = (ICON_CELL * k * SS) / 2.0
            ccx = (x0 + x1) / 2.0 * SS
            ccy = (y0 + y1) / 2.0 * SS
            hd.ellipse([ccx - r, ccy - r, ccx + r, ccy + r], fill=(255, 255, 255, 26))
            img.alpha_composite(hl)

        icon_col = _col(theme, "icon", int(255 * dim))
        dim_col = _col(theme, "icon_dim", int(255 * dim))
        kinds = ["prev", "pause" if state.playing else "play", "next"]
        for i, ((x0, y0, x1, y1), kind) in enumerate(zip(controls, kinds)):
            cx = (x0 + x1) / 2.0 * SS
            cy = (y0 + y1) / 2.0 * SS
            enabled = (i == 1 and state.can_toggle) or (i == 0 and state.can_prev) \
                or (i == 2 and state.can_next)
            _draw_icon(d, cx, cy, kind, S, icon_col if (enabled and not idle) else dim_col)

    # ------------------------------------------------------------- ondas
    if wb and waves and not idle:
        # Barras tipo "nota de voz": redondeadas, cortas cuando no hay sonido.
        # El alto lo trae quien dibuja (app.py), que es el que tiene el reloj.
        dibujar_ondas(d, waves, cfg, S, wb[0] * S, WAVE_CY * S,
                      _col(theme, "accent_waves", 255 if state.playing else 110))

    # ----------------------------------------------------------------- progreso
    sp = progress_span(int(cfg.get("width", 260)), cfg)
    if sp and not idle and state.duration > 0:
        active = scrub is not None or hover == 3
        # al pasar el mouse la barra se engrosa: avisa que se puede mover sin
        # cambiar el aspecto en reposo
        bar_h = PROG_H * (1.8 if active else 1.0)
        cy = (PROG_Y + PROG_H / 2.0) * S
        x0, x1 = sp[0] * S, sp[1] * S
        y0, y1 = cy - bar_h * S / 2.0, cy + bar_h * S / 2.0
        d.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) / 2.0,
                            fill=_col(theme, "track", 255 if active else 240))
        shown = scrub if scrub is not None else state.live_position()
        frac = max(0.0, min(1.0, shown / state.duration))
        if frac > 0:
            d.rounded_rectangle([x0, y0, x0 + max((y1 - y0), (x1 - x0) * frac), y1],
                                radius=(y1 - y0) / 2.0, fill=_col(theme, "accent_progress", 255))
        if active:
            r = KNOB_R * S
            kx = x0 + (x1 - x0) * frac
            d.ellipse([kx - r, cy - r, kx + r, cy + r], fill=_col(theme, "accent_progress", 255),
                      outline=_col(theme, "chip", 255), width=max(1, int(round(0.6 * S))))

    # --- presentacion: contra el color real de la barra, o con alpha real ------
    if opaque:
        out = Image.alpha_composite(Image.new("RGBA", canvas, tuple(base) + (255,)), img)
        if SS > 1:
            out = out.resize((W, H), Image.LANCZOS)
        return out
    # Alpha real. La reduccion se hace en espacio premultiplicado: reducir el RGBA
    # directo deja que los pixeles transparentes (negros) sangren un halo oscuro
    # en los bordes del chip y de la caratula.
    pre = ImageChops.multiply(img.convert("RGB"), img.getchannel("A").convert("RGB"))
    alpha = img.getchannel("A")
    if SS > 1:
        pre = pre.resize((W, H), Image.LANCZOS)
        alpha = alpha.resize((W, H), Image.LANCZOS)
    # Piso de alpha. Windows decide que ventana recibe el mouse mirando el alpha
    # POR PIXEL en ventanas en capas: con el fondo sin nada, los pixeles vacios
    # son "agujeros" y el clic, la rueda y el arrastre se los queda la barra de
    # tareas. Se ve claro midiendo: sobre el hueco del icono de play/pausa
    # WindowFromPoint devolvia Shell_TrayWnd y el clic no llegaba al widget.
    # Un piso de 2 (0,8% de mezcla, invisible) mantiene toda la superficie
    # sensible al mouse sin ensuciar el fondo.
    piso = int(cfg.get("hit_alpha_floor", 2))
    if piso > 0:
        alpha = alpha.point(lambda v: max(v, piso))
    return Image.merge("RGBA", (*pre.split(), alpha))


def to_bgra(img: Image.Image) -> bytes:
    return img.convert("RGBA").tobytes("raw", "BGRA")


def to_premult_bgra(img: Image.Image) -> bytes:
    """Bytes BGRA premultiplicados, listos para UpdateLayeredWindow (ULW_ALPHA).

    No vuelve a multiplicar: `render(..., opaque=False)` ya entrega el RGB
    premultiplicado. Aca solo se reordena a BGRA.
    """
    r, g, b, a = img.convert("RGBA").split()
    return Image.merge("RGBA", (b, g, r, a)).tobytes()


def title_overflows(state, cfg: dict, k: float, width: int | None = None) -> bool:
    """True si el titulo no cabe y hay que activar la marquesina."""
    SS = 1
    S = k * SS
    W = int(width if width is not None else round(cfg.get("width", 260) * k))
    controls = control_rects(W, k, cfg)
    cells_x = controls[0][0] if controls else W - RIGHT_PAD * k
    text_x = TEXT_X * k
    area_w = max(10.0, cells_x - 6 * k - text_x)
    title = state.title or "Sin reproduccion"
    f = _font("title", max(8, int(round(TITLE_SIZE * k))))
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    return tmp.textlength(title, font=f) > area_w
