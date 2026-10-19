"""Ventana de Ajustes: geometria, dibujo y zonas clicables (sin ventana).

La ventana la crea `app.py`; aca vive todo lo que se puede verificar sin abrir nada:
el dibujo (`render`), las zonas clicables (`rects`, `hit`) y el mapeo de los
deslizadores a valores (`valor_slider`, `frac_slider`).

Misma idea que `panel.py`: el dibujo se hace con Pillow y las zonas se calculan aparte,
asi las pruebas comprueban las dos cosas por separado. Todo esta en unidades LOGICAS y
se escala por k (alto de la barra / 40), igual que el widget y el panel.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from . import draw

# ------------------------------------------------------------------ medidas logicas
W, H = 452, 372
NAV = (12, 116, 118, 162)          # x, y, ancho, alto de la barra de secciones
NAV_FILA = 40
CONT_X = 148
CONT_X1 = 434

SECCIONES = ("Apariencia", "Posicion", "Panel", "Atajos")

# deslizadores: nombre -> (minimo, maximo, sufijo)
RANGOS = {
    "widget_alpha": (40, 255, "%"),
    "width": (150, 520, " px"),
    "panel_alpha": (60, 255, "%"),
    "panel_bg_alpha": (0, 255, "%"),
}

APARIENCIA = [
    ("label", "Fondo", 120),
    ("seg", "chip_alpha", [("Solido", 232), ("Translucido", 170),
                           ("Muy transp.", 100), ("Sin fondo", 0)], 140, 26),
    ("label", "Opacidad de todo el widget", 178),
    ("slider", "widget_alpha", 198),
    ("label", "Color del widget", 220),
    ("swatches", "chip_color", 240),
    ("toggle", "waves", "Ondas de sonido", 284),
    ("label", "Ancho", 312),
    ("slider", "width", 332),
]

PANEL = [
    ("toggle", "panel_mode", "Modo gaming (chico y sin robar el foco)", 120),
    ("toggle", "panel_clics", "Dejar pasar los clics al juego", 154),
    ("label", "Tamano", 192),
    ("seg", "panel_size", [("Normal", "normal"), ("Chico", "chico"),
                           ("Tira", "tira")], 212, 26),
    ("label", "Opacidad del panel", 252),
    ("slider", "panel_alpha", 272),
    ("label", "Fondo del panel", 302),
    ("slider", "panel_bg_alpha", 322),
]

ATAJOS = [
    ("toggle", "hotkeys", "Atajos globales", 120),
]

NOTAS_ATAJOS = (
    "Rueda sobre el widget: busca. Sobre el altavoz: volumen.",
    "Ctrl+rueda: pasos finos (1 s / 1%).",
)


def filas_atajos(lista: list[str] | None) -> list[tuple]:
    """Filas de la seccion Atajos con la lista REAL que pasa la app.

    Se arman desde la tabla `HOTKEYS` de app.py y no a mano: la seccion mostraba
    combinaciones que no eran las registradas (Ctrl+Alt+Espacio cuando el play/pausa es
    Ctrl+Alt+P), que es peor que no mostrar nada. Las notas van DESPUES de la lista
    (antes estaban en y fija y se pisaban con la novena combinacion).
    """
    out = []
    for i, texto in enumerate(lista or []):
        out.append(("nota", texto, 152 + i * 18))
    base = 152 + 18 * len(lista or []) + 16
    for i, texto in enumerate(NOTAS_ATAJOS):
        out.append(("nota", texto, base + i * 18))
    return out

CHIP_COLORES = (("auto", "auto", None), ("accent", "acento", None),
                ("light", "claro", (232, 234, 240)), ("dark", "oscuro", (26, 28, 36)))


def _paleta(cfg: dict) -> dict:
    tema = cfg.get("theme") or {}
    acc = tema.get("accent") or (96, 205, 145)
    return {"fondo": (24, 26, 33), "caja": (30, 33, 42), "linea": (48, 52, 64),
            "txt": (232, 235, 242), "dim": (150, 156, 172),
            "acc": tuple(int(v) for v in acc[:3]), "sel": (44, 60, 50)}


def seccion_valida(nombre: str) -> str:
    for s in SECCIONES:
        if s.lower() == str(nombre or "").lower():
            return s
    return SECCIONES[0]


# ---------------------------------------------------------------------- zonas
def _r(x, y, w, h, k):
    return (int(round(x * k)), int(round(y * k)),
            int(round((x + w) * k)), int(round((y + h) * k)))


def _seg_anchos(items) -> list[float]:
    """Ancho de cada boton del segmentado, repartidos en el ancho del contenido."""
    total = CONT_X1 - CONT_X
    hueco = 6
    disp = total - hueco * (len(items) - 1)
    peso = [max(56, 18 + 7.2 * len(str(t[0]))) for t in items]
    escala = disp / float(sum(peso))
    return [p * escala for p in peso]


def rects(k: float, cfg: dict, seccion: str = SECCIONES[0],
          monitores: list | None = None, atajos: list | None = None) -> dict:
    """Zonas en px reales (coordenadas del cliente de la ventana).

    `monitores` es la lista de `app._monitor_opciones()` con `nombre` y `rect` (y
    `tildado` en el que esta en uso): la seccion Posicion arma las filas con eso.
    """
    seccion = seccion_valida(seccion)
    z = {"cerrar": _r(W - 30, 12, 16, 16, k), "preview": _r(18, 44, CONT_X1 - 18, 58, k),
         "nav": [], "filas": []}
    nx, ny, nw, nh = NAV
    for i, _s in enumerate(SECCIONES):
        z["nav"].append(_r(nx, ny + i * NAV_FILA, nw, 30, k))
    if seccion == "Atajos":
        filas = [f for f in ATAJOS if f[0] == "toggle"] + filas_atajos(atajos)
    else:
        filas = {"Apariencia": APARIENCIA, "Panel": PANEL}.get(seccion)
    if filas:
        for f in filas:
            tipo = f[0]
            if tipo == "label":
                z["filas"].append({"tipo": "label", "texto": f[1],
                                   "rect": _r(CONT_X, f[2], CONT_X1 - CONT_X, 16, k)})
            elif tipo == "nota":
                z["filas"].append({"tipo": "nota", "texto": f[1],
                                   "rect": _r(CONT_X, f[2], CONT_X1 - CONT_X, 16, k)})
            elif tipo == "seg":
                y, alto = f[3], f[4]
                x = CONT_X
                botones = []
                for (texto, valor), an in zip(f[2], _seg_anchos(f[2])):
                    botones.append({"texto": texto, "valor": valor,
                                    "rect": _r(x, y, an, alto, k)})
                    x += an + 6
                z["filas"].append({"tipo": "seg", "accion": f[1], "botones": botones,
                                   "rect": _r(CONT_X, y, CONT_X1 - CONT_X, alto, k)})
            elif tipo == "slider":
                z["filas"].append({
                    "tipo": "slider", "accion": f[1],
                    "rect": _r(CONT_X, f[2], CONT_X1 - CONT_X, 22, k),
                    "track": _r(CONT_X, f[2] + 8, CONT_X1 - CONT_X - 46, 6, k)})
            elif tipo == "swatches":
                yy = f[2]
                z["filas"].append({
                    "tipo": "swatches", "accion": f[1],
                    "rect": _r(CONT_X, yy - 4, CONT_X1 - CONT_X, 44, k),
                    "botones": [{"valor": v, "texto": t, "color": c,
                                 "rect": _r(CONT_X + i * 52, yy, 18, 18, k)}
                                for i, (v, t, c) in enumerate(CHIP_COLORES)]})
            elif tipo == "toggle":
                z["filas"].append({"tipo": "toggle", "accion": f[1], "texto": f[2],
                                   "rect": _r(CONT_X, f[3] - 4, CONT_X1 - CONT_X, 30, k)})
    if seccion == "Posicion":
        mons = monitores or []
        z["filas"].append({"tipo": "label", "texto": "Monitor",
                           "rect": _r(CONT_X, 120, CONT_X1 - CONT_X, 16, k)})
        for i, op in enumerate(mons):
            z["filas"].append({"tipo": "radio", "indice": i, "texto": op.get("nombre", ""),
                               "detalle": "%dx%d" % (op["rect"][2] - op["rect"][0],
                                                     op["rect"][3] - op["rect"][1]),
                               "tildado": bool(op.get("tildado")),
                               "rect": _r(CONT_X, 140 + i * 32, CONT_X1 - CONT_X, 28, k)})
        base = 140 + 32 * len(mons) + 12
        z["filas"].append({"tipo": "boton", "accion": "extremo",
                           "texto": "Volver al extremo derecho",
                           "rect": _r(CONT_X, base, 200, 30, k)})
        z["filas"].append({"tipo": "boton", "accion": "refrescar",
                           "texto": "Refrescar el fondo del panel",
                           "rect": _r(CONT_X, base + 40, 220, 30, k)})
    return z


def hit(x: int, y: int, k: float, cfg: dict, seccion: str,
        monitores: list | None = None) -> tuple | None:
    """Que hay en ese punto: (accion, valor) o None.

    Las acciones son las que despues aplica `app.py`; aca solo se decide que se toco,
    igual que `panel.hit()`. En los deslizadores el valor todavia no se calcula: se
    devuelve ("slider", nombre) y el que llama usa `valor_slider()` con la x.
    """
    z = rects(k, cfg, seccion, monitores)
    if _dentro(z["cerrar"], x, y):
        return ("cerrar", None)
    for i, r in enumerate(z["nav"]):
        if _dentro(r, x, y):
            return ("seccion", SECCIONES[i])
    for f in z["filas"]:
        if not _dentro(f["rect"], x, y):
            continue
        tipo = f["tipo"]
        if tipo == "seg":
            for b in f["botones"]:
                if _dentro(b["rect"], x, y):
                    return (f["accion"], b["valor"])
        elif tipo == "slider":
            return ("slider", f["accion"])
        elif tipo == "swatches":
            for b in f["botones"]:
                if _dentro(b["rect"], x, y):
                    return (f["accion"], b["valor"])
        elif tipo == "toggle":
            return (f["accion"], None)
        elif tipo == "radio":
            return ("monitor", f["indice"])
        elif tipo == "boton":
            return (f["accion"], None)
    return None


def _dentro(r, x, y) -> bool:
    return bool(r) and r[0] <= x <= r[2] and r[1] <= y <= r[3]


def frac_slider(nombre: str, x: int, k: float, seccion: str = SECCIONES[0]) -> float:
    """0..1 segun donde esta la x sobre la pista del deslizador."""
    z = rects(k, {}, seccion)
    for f in z["filas"]:
        if f["tipo"] == "slider" and f["accion"] == nombre:
            t = f["track"]
            if t[2] <= t[0]:
                return 0.0
            return max(0.0, min(1.0, (x - t[0]) / float(t[2] - t[0])))
    return 0.0


def valor_slider(nombre: str, frac: float) -> int:
    lo, hi, _suf = RANGOS.get(nombre, (0, 100, ""))
    return int(round(lo + max(0.0, min(1.0, frac)) * (hi - lo)))


# ---------------------------------------------------------------------- dibujo
def _swatch(d, caja, color, sel, k):
    d.rounded_rectangle(caja, radius=int(4 * k), fill=color,
                        outline=(255, 255, 255) if sel else (96, 103, 120),
                        width=max(1, int((2 if sel else 1) * k)))


def _check(d, x, y, k, color):
    d.line([(x, y), (x + 3 * k, y + 3.5 * k), (x + 9 * k, y - 4 * k)], fill=color,
           width=max(1, int(1.9 * k)), joint="curve")


def render(cfg: dict, seccion: str, preview: Image.Image | None, k: float,
           hover: str | None = None, monitores: list | None = None,
           atajos: list | None = None) -> Image.Image:
    """Dibuja la ventana completa. `monitores` y `atajos` los pasa la app."""
    seccion = seccion_valida(seccion)
    P = _paleta(cfg)
    im = Image.new("RGB", (int(round(W * k)), int(round(H * k))), P["fondo"])
    d = ImageDraw.Draw(im)
    z = rects(k, cfg, seccion, monitores, atajos)

    ftit = draw._font("title", int(15 * k))
    frow = draw._font("body", int(11 * k))
    frowb = draw._font("title", int(11 * k))
    fsm = draw._font("body", int(9 * k))

    d.text((int(18 * k), int(10 * k)), "Ajustes", font=ftit, fill=P["txt"])
    # cruz de cerrar
    cx0, cy0, cx1, cy1 = z["cerrar"]
    d.line([cx0 + 3 * k, cy0 + 3 * k, cx1 - 3 * k, cy1 - 3 * k], fill=P["dim"],
           width=max(1, int(1.4 * k)))
    d.line([cx1 - 3 * k, cy0 + 3 * k, cx0 + 3 * k, cy1 - 3 * k], fill=P["dim"],
           width=max(1, int(1.4 * k)))
    # vista previa
    px0, py0, px1, py1 = z["preview"]
    d.rounded_rectangle([px0, py0, px1, py1], radius=int(8 * k), fill=(18, 20, 26),
                        outline=P["linea"])
    if preview is not None:
        pv = preview
        if pv.width > (px1 - px0) - int(12 * k) or pv.height > (py1 - py0) - int(10 * k):
            esc = min(((px1 - px0) - 12 * k) / float(pv.width),
                      ((py1 - py0) - 10 * k) / float(pv.height))
            pv = pv.resize((max(1, int(pv.width * esc)), max(1, int(pv.height * esc))),
                           Image.LANCZOS)
        im.paste(pv, (px0 + int(6 * k), py0 + ((py1 - py0) - pv.height) // 2))
    # navegacion
    nx, ny, nw, nh = NAV
    d.rounded_rectangle([int(nx * k), int(ny * k), int((nx + nw) * k), int((ny + nh) * k)],
                        radius=int(8 * k), fill=P["caja"])
    for i, nombre in enumerate(SECCIONES):
        r = z["nav"][i]
        sel = nombre == seccion
        if sel or hover == "nav%d" % i:
            d.rounded_rectangle(r, radius=int(6 * k),
                                fill=P["sel"] if sel else (38, 42, 52))
        d.text((r[0] + int(14 * k), r[1] + int(8 * k)), nombre, font=frowb if sel else frow,
               fill=P["acc"] if sel else P["dim"])
    # contenido
    for f in z["filas"]:
        tipo = f["tipo"]
        if tipo in ("label", "nota"):
            r = f["rect"]
            d.text((r[0], r[1]), f["texto"], font=frowb if tipo == "label" else fsm,
                   fill=P["txt"] if tipo == "label" else P["dim"])
        elif tipo == "seg":
            for b in f["botones"]:
                r = b["rect"]
                on = _seg_activo(cfg, f["accion"], b["valor"])
                d.rounded_rectangle(r, radius=int(6 * k),
                                    fill=P["sel"] if on else P["caja"],
                                    outline=P["acc"] if on else P["linea"],
                                    width=max(1, int((1.6 if on else 1) * k)))
                d.text((r[0] + (r[2] - r[0]) / 2, r[1] + int(7 * k)), b["texto"],
                       font=fsm, fill=P["txt"] if on else P["dim"], anchor="ma")
        elif tipo == "slider":
            r, t = f["rect"], f["track"]
            valor, lo, hi = _valor_actual(cfg, f["accion"])
            frac = 0.0 if hi <= lo else max(0.0, min(1.0, (valor - lo) / float(hi - lo)))
            d.rounded_rectangle([t[0], t[1] + 2 * k // 2, t[2], t[3]],
                                radius=int(3 * k), fill=(52, 56, 68))
            xm = int(t[0] + frac * (t[2] - t[0]))
            d.rounded_rectangle([t[0], t[1] + 2 * k // 2, xm, t[3]],
                                radius=int(3 * k), fill=P["acc"])
            cy = (t[1] + t[3]) // 2
            d.ellipse([xm - int(7 * k), cy - int(7 * k), xm + int(7 * k), cy + int(7 * k)],
                      fill=P["txt"])
            _lo, _hi, suf = RANGOS.get(f["accion"], (0, 100, ""))
            etiqueta = ("%d%%" % round(valor / 2.55)) if suf == "%" else ("%d%s" % (valor, suf))
            d.text((r[2], t[1] - int(3 * k)), etiqueta, font=frow, fill=P["txt"],
                   anchor="ra")
        elif tipo == "swatches":
            actual = str(cfg.get("chip_color") or "auto")
            for b in f["botones"]:
                r = b["rect"]
                col = b["color"] or _color_aprox(cfg, b["valor"], P)
                _swatch(d, r, col, b["valor"] == actual, k)
                d.text((r[0], r[3] + int(2 * k)), b["texto"], font=fsm, fill=P["dim"])
        elif tipo == "toggle":
            on = _toggle_activo(cfg, f["accion"])
            r = f["rect"]
            d.text((r[0], r[1] + int(6 * k)), f["texto"], font=frow, fill=P["txt"])
            xx = r[2] - int(22 * k)
            caja = [xx, r[1] + int(7 * k), xx + int(26 * k), r[1] + int(21 * k)]
            d.rounded_rectangle(caja, radius=int(7 * k),
                                fill=P["acc"] if on else (56, 60, 72))
            kx = caja[2] - int(7 * k) if on else caja[0] + int(7 * k)
            d.ellipse([kx - int(5 * k), caja[1] + int(2 * k), kx + int(5 * k),
                       caja[3] - int(2 * k)], fill=(18, 20, 26))
        elif tipo == "radio":
            r = f["rect"]
            if hover == "radio%d" % f["indice"]:
                d.rounded_rectangle(r, radius=int(6 * k), fill=(38, 42, 52))
            if f["tildado"]:
                _check(d, r[0] + int(4 * k), r[1] + int(15 * k), k, P["acc"])
            d.text((r[0] + int(22 * k), r[1] + int(6 * k)), f["texto"], font=frow,
                   fill=P["txt"])
            d.text((r[2], r[1] + int(8 * k)), f["detalle"], font=fsm, fill=P["dim"],
                   anchor="ra")
        elif tipo == "boton":
            r = f["rect"]
            d.rounded_rectangle(r, radius=int(6 * k), fill=P["caja"], outline=P["linea"])
            d.text((r[0] + (r[2] - r[0]) / 2, r[1] + int(8 * k)), f["texto"], font=frow,
                   fill=P["txt"], anchor="ma")
    return im


def _color_aprox(cfg: dict, valor: str, P: dict) -> tuple:
    """Color que se muestra en el swatch 'auto'/'accent'."""
    if valor == "accent":
        return P["acc"]
    return (52, 56, 68)


def _seg_activo(cfg: dict, accion: str, valor) -> bool:
    if accion == "chip_alpha":
        return int(cfg.get("chip_alpha", 232)) == int(valor)
    if accion == "panel_size":
        from . import panel as panel_mod
        return panel_mod.normalizar(cfg.get("panel_size", "normal")) == valor
    return False


def _toggle_activo(cfg: dict, accion: str) -> bool:
    if accion == "waves":
        return bool(cfg.get("show_waves", False))
    if accion == "panel_mode":
        return str(cfg.get("panel_mode", "normal")).lower() == "gaming"
    if accion == "panel_clics":
        return bool(cfg.get("panel_clics_al_juego", False))
    if accion == "hotkeys":
        return bool(cfg.get("hotkeys", True))
    return False


def _valor_actual(cfg: dict, accion: str) -> tuple[int, int, int]:
    """(valor, minimo, maximo) del deslizador, con el valor que tiene la config."""
    lo, hi, _s = RANGOS.get(accion, (0, 100, ""))
    try:
        valor = int(cfg.get(accion))
    except (TypeError, ValueError):
        valor = lo
    return max(lo, min(hi, valor)), lo, hi


def size(k: float) -> tuple[int, int]:
    return int(round(W * k)), int(round(H * k))
