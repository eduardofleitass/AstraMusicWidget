"""Donaciones: el cartel del "apoyá el proyecto" y sus reglas.

Igual que `panel.py` y `ajustes.py`, aca vive todo lo que se puede verificar SIN abrir una
ventana: el dibujo (`render`), las zonas clicables (`rects`, `hit`) y, sobre todo, la
decision de mostrarlo o no (`debe_mostrar`), que es lo que evita que el cartel se vuelva
un WinRAR molesto.

Reglas (a proposito conservadoras):

- nunca antes de DIAS_MINIMOS dias desde el primer arranque (o ARRANQUES_MIN arranques);
- como maximo MAX_VECES veces en la vida;
- como minimo DIAS_ENTRE dias entre una y otra;
- "No volver a mostrar" gana siempre y no se puede deshacer desde el cartel;
- en modo gaming no aparece nunca;
- no bloquea el arranque: el widget se dibuja primero y el cartel sale despues (lo maneja
  `app.py` con un temporizador).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from PIL import Image, ImageDraw

from . import draw

# El link de PayPal.Me: acepta cualquier monto y no necesita cuenta de comercio ni API.
LINK = "https://paypal.me/damflou26?locale.x=es_XC&country.x=CO"
LINK_CORTO = "paypal.me/damflou26"

# El QR del link, embebido: PyInstaller --onefile no incluye assets/, asi que leyendo el
# archivo el cartel del .exe mostraba un cuadrado blanco (medido). El PNG de assets/ sigue
# siendo la fuente: con `segno` se regenera y se vuelve a pegar esta cadena.
QR_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAbwAAAG8AQMAAACffoKcAAAABlBMVEUSEhr////OQ09UAAACDUlE"
    "QVR42u2cQY7DIBAEUT7A/3/JD7ybBTM9kL1YkZpDWZHlONQFtTrNeHC5nh2tAAICAgL+B5Z51HTn"
    "9zrO67BXeXgAAj483iKsQ7lTq12fXZb95riIYcwqoEerSZZ/XhquK1qVYcwqoFur3Tn71xIS3STN"
    "rAKe4at3MBg/oVXA8/Jqv5Mi63RX8iqgXaubJj9/qAMAurW6VLFUwONO3YtdzCqgKQO0Mhb7os+4"
    "X6Q4gFYBrRlgmGeLr+NCzslm0Sqg0Vfn2n9m16UCoIsstApoyastPUjVslUspu66K74K6NWqalIf"
    "US09A13V5FVAYx0gMqrUpnSRpWkBXwV01qykCKCpVRPCDLH4KqD3uVWcc/0qsuv9E1oF9PqqLqxS"
    "Y0DOsWgV0KzVj83bLSWEYapoFdBbB6jRCjitVTPA1O09hlkFdORVqanGSqrGgmsdgK8CevtXdaXf"
    "Svrrv641LaBVQFMGSLLU9f51aYMrGQDQngHWJX82WC0L0GsNeIqvttzNModpxyAZANC+30oiqzav"
    "7qJFq4AeX5Vj71cZ6r2zARkA0J5Xw0tzq9XafEU/AKA1A8Q+1rz/Onlp6hlgVgGtebVuFar8RIC8"
    "CniOVtMrLGre2apvCUCrgAf4anrMuv37s98K8JC8upRbi+xbiYZAfBXwhPeulLKVp3KUpXcF0KdV"
    "XqQMCAgI+D3wB2xiStuhCSFhAAAAAElFTkSuQmCC"
)

DIAS_MINIMOS = 7
ARRANQUES_MIN = 20
DIAS_ENTRE = 30
MAX_VECES = 3

# ------------------------------------------------------------------ medidas logicas
W, H = 430, 214
QR = 92                     # lado del QR, en unidades logicas
QR_X, QR_Y = W - QR - 18, 46

TITULO = "Apoya el proyecto"
TEXTO = (
    "Este widget es gratis y sin anuncios.",
    "Si te sirve todos los dias y queres invitarme un cafe,",
    "aca esta el link. Si no, segui tranquilo: no cambia nada.",
)
BOTONES = (
    ("donar", "Donar", 16, 160, 104, 32),
    ("ahora_no", "Ahora no", 128, 160, 104, 32),
    ("nunca", "No volver a mostrar", 240, 166, 150, 22),
)


def size(k: float) -> tuple[int, int]:
    return (int(round(W * k)), int(round(H * k)))


def _r(x, y, w, h, k):
    return (int(round(x * k)), int(round(y * k)),
            int(round((x + w) * k)), int(round((y + h) * k)))


def rects(k: float) -> dict:
    z = {"cerrar": _r(W - 30, 12, 16, 16, k), "qr": _r(QR_X, QR_Y, QR, QR, k),
         "botones": [], "texto": _r(16, 44, QR_X - 28, 76, k)}
    for accion, etiqueta, x, y, w, h in BOTONES:
        z["botones"].append({"accion": accion, "texto": etiqueta,
                             "rect": _r(x, y, w, h, k)})
    return z


def hit(x: int, y: int, k: float) -> tuple | None:
    """("donar"|"ahora_no"|"nunca"|"cerrar"|"qr", None) o None."""
    z = rects(k)
    for b in z["botones"]:
        r = b["rect"]
        if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            return (b["accion"], None)
    for nombre in ("cerrar", "qr"):
        r = z[nombre]
        if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            return (nombre, None)
    return None


def _paleta(cfg: dict) -> dict:
    """Los mismos colores que la ventana de Ajustes (una sola estetica)."""
    from . import ajustes as ajustes_mod
    return ajustes_mod._paleta(cfg)


def qr_image() -> Image.Image | None:
    """El QR del link: el archivo de assets/ si esta, y si no el PNG embebido."""
    import base64
    import io
    import os
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets", "qr_paypal.png")
    try:
        return Image.open(ruta).convert("RGB")
    except Exception:
        pass
    try:
        return Image.open(io.BytesIO(base64.b64decode(QR_PNG_B64))).convert("RGB")
    except Exception:
        return None


def render(cfg: dict, k: float, hover: str | None = None,
           qr: Image.Image | None = None) -> Image.Image:
    P = _paleta(cfg)
    im = Image.new("RGB", size(k), P["fondo"])
    d = ImageDraw.Draw(im)
    z = rects(k)

    f_tit = draw._font("title", int(14 * k))
    f_row = draw._font("body", int(10.5 * k))
    f_sm = draw._font("body", int(9 * k))

    d.text((int(16 * k), int(14 * k)), TITULO, font=f_tit, fill=P["txt"])
    # cruz de cerrar
    cx0, cy0, cx1, cy1 = z["cerrar"]
    d.line([cx0 + 3 * k, cy0 + 3 * k, cx1 - 3 * k, cy1 - 3 * k], fill=P["dim"],
           width=max(1, int(1.4 * k)))
    d.line([cx1 - 3 * k, cy0 + 3 * k, cx0 + 3 * k, cy1 - 3 * k], fill=P["dim"],
           width=max(1, int(1.4 * k)))

    # texto
    y = 48
    for linea in TEXTO:
        d.text((int(16 * k), int(y * k)), linea, font=f_row, fill=P["dim"])
        y += 17

    # QR sobre fondo blanco (el margen es parte del codigo: sin el no se escanea)
    qx0, qy0, qx1, qy1 = z["qr"]
    d.rounded_rectangle([qx0 - int(4 * k), qy0 - int(4 * k),
                         qx1 + int(4 * k), qy1 + int(4 * k)],
                        radius=int(6 * k), fill=(255, 255, 255))
    if qr is not None:
        im.paste(qr.resize((qx1 - qx0, qy1 - qy0), Image.LANCZOS), (qx0, qy0))
    d.text(((qx0 + qx1) // 2, qy1 + int(7 * k)), LINK_CORTO, font=f_sm, fill=P["dim"],
           anchor="ma")

    # botones
    for b in z["botones"]:
        r = b["rect"]
        ac = b["accion"]
        if ac == "donar":
            d.rounded_rectangle(r, radius=int(7 * k), fill=P["acc"])
            d.text(((r[0] + r[2]) / 2, r[1] + int(9 * k)), b["texto"], font=f_row,
                   fill=P["sobre_acc"], anchor="ma")
        elif ac == "ahora_no":
            d.rounded_rectangle(r, radius=int(7 * k), fill=P["caja"], outline=P["linea"])
            d.text(((r[0] + r[2]) / 2, r[1] + int(9 * k)), b["texto"], font=f_row,
                   fill=P["txt"], anchor="ma")
        else:
            d.text(((r[0] + r[2]) / 2, r[1] + int(5 * k)), b["texto"], font=f_sm,
                   fill=P["acc"] if hover == "nunca" else P["dim"], anchor="ma")
    return im


# ------------------------------------------------------------------------ reglas
def _fecha(valor) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None


def debe_mostrar(cfg: dict, ahora: datetime | None = None) -> bool:
    """Si corresponde mostrar el cartel AHORA. Todo lo decide la config, sin estado oculto."""
    if cfg.get("donation_no_mostrar"):
        return False
    if str(cfg.get("panel_mode", "normal")).lower() == "gaming":
        return False
    if not cfg.get("donation_link", LINK):
        return False                      # sin link no hay nada que pedir
    ahora = ahora or datetime.now()
    primera = _fecha(cfg.get("donation_primera"))
    if primera is None:
        return False                      # recien instalado: todavia no corresponde
    try:
        veces = int(cfg.get("donation_veces") or 0)
        arranques = int(cfg.get("donation_arranques") or 0)
    except (TypeError, ValueError):
        veces, arranques = 0, 0
    if veces >= MAX_VECES:
        return False
    if (ahora - primera) < timedelta(days=DIAS_MINIMOS) and arranques < ARRANQUES_MIN:
        return False
    ultima = _fecha(cfg.get("donation_ultima"))
    if ultima is not None and (ahora - ultima) < timedelta(days=DIAS_ENTRE):
        return False
    return True


def marcar_mostrado(cfg: dict, ahora: datetime | None = None) -> None:
    """Anota que se mostro (cuenta para el intervalo y para el maximo de veces)."""
    ahora = ahora or datetime.now()
    try:
        cfg["donation_veces"] = int(cfg.get("donation_veces") or 0) + 1
    except (TypeError, ValueError):
        cfg["donation_veces"] = 1
    cfg["donation_ultima"] = ahora.isoformat(timespec="seconds")


def arranque(cfg: dict, ahora: datetime | None = None) -> bool:
    """Anota el primer arranque y suma uno al contador. Devuelve True si hubo cambios."""
    ahora = ahora or datetime.now()
    cambio = False
    if not cfg.get("donation_primera"):
        cfg["donation_primera"] = ahora.isoformat(timespec="seconds")
        cambio = True
    try:
        cfg["donation_arranques"] = int(cfg.get("donation_arranques") or 0) + 1
    except (TypeError, ValueError):
        cfg["donation_arranques"] = 1
    return True
