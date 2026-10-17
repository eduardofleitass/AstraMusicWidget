"""Hoja de vistas previas: genera PNG con las variantes visuales del widget.

Sirve para iterar el diseno sin tocar la barra de tareas:
    python tools/preview.py out.png
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402

from widget import config as cfgmod, draw  # noqa: E402
from widget.media import MediaState  # noqa: E402

CFG = cfgmod.load()


def state(title, artist, *, playing=True, pos=87.0, dur=355.0, art=True, session=True):
    return MediaState(
        has_session=session, app_id="Spotify.exe", title=title, artist=artist,
        album="A Night at the Opera", playing=playing, position=pos, duration=dur,
        position_at=time.monotonic(), art=_art() if art else None,
        art_key="demo" if art else "", can_prev=True, can_next=True, can_toggle=True)


def _art():
    import io
    img = Image.new("RGB", (300, 300), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(300):
        t = y / 299
        d.line([(0, y), (300, y)], fill=(int(30 + 120 * t), int(60 + 40 * t), int(140 - 60 * t)))
    d.ellipse([70, 70, 230, 230], fill=(250, 240, 200))
    d.ellipse([105, 105, 195, 195], fill=(30, 40, 80))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


VARIANTS = [
    ("reproduciendo / titulo corto", state("Radio Ga Ga", "Queen"),
     dict(hover=-1, marquee=0)),
    ("reproduciendo / titulo largo (marquesina)", state(
        "Bohemian Rhapsody (Remastered 2011 - Edicion Deluxe)", "Queen"),
     dict(hover=-1, marquee=26)),
    ("pausado", state("Love of My Life", "Queen", playing=False, pos=42),
     dict(hover=-1, marquee=0)),
    ("hover sobre 'siguiente'", state("Radio Ga Ga", "Queen"),
     dict(hover=2, marquee=0)),
    ("transmitiendo en vivo (sin duracion)", state("Radio Nacional", "En vivo", dur=0),
     dict(hover=-1, marquee=0)),
    ("sin reproduccion", MediaState(), dict(hover=-1, marquee=0)),
]


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "preview.png"
    zoom = 3
    pad, gap, label_h = 14, 12, 16
    W = CFG["width"] * zoom
    H = 40 * zoom
    sheet = Image.new("RGB", (W + pad * 2, pad + len(VARIANTS) * (H + label_h + gap)), (11, 12, 16))
    d = ImageDraw.Draw(sheet)
    font = draw._font("body", 13)
    y = pad
    for label, st, kwargs in VARIANTS:
        k = 1.0
        SS = max(1, int(CFG.get("supersample", 3)))
        art = draw.get_art(st.art, st.art_key, int(round(draw.ART * k * SS)),
                           int(round(draw.ART_RADIUS * k * SS))
                           ) if CFG.get("show_art", True) else None
        img = draw.render(st, CFG, art=art, k=k, base=(28, 30, 38), height=40, **kwargs)
        big = img.resize((W, H), Image.LANCZOS)
        sheet.paste(big.convert("RGB"), (pad, y + label_h))
        d.text((pad, y), label, font=font, fill=(150, 158, 180))
        y += H + label_h + gap
    sheet.save(out)
    print(f"hoja de vistas previas -> {os.path.abspath(out)}  {sheet.size}")
    # medidas utiles para depurar el layout
    for label, st, _ in VARIANTS[:2]:
        print(f"  {label}: desborda={draw.title_overflows(st, CFG, 1.0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
