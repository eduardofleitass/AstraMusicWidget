#!/usr/bin/env python
"""Punto de entrada del widget de musica para la barra de tareas.

    python main.py                 # en la barra de tareas
    python main.py --no-embed      # ventana flotante (desarrollo)
    python main.py --diagnose      # ver que esta leyendo de SMTC
    python main.py --shot out.png  # volcar el widget a PNG
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from widget import config as cfgmod  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def _demo_state():
    from widget.media import MediaState
    return MediaState(
        has_session=True, app_id="Spotify.exe",
        title="Bohemian Rhapsody (Remastered 2011 - Edicion Deluxe)",
        artist="Queen", album="A Night at the Opera",
        playing=True, position=87.0, duration=355.0, position_at=time.monotonic(),
        art=None, art_key="demo", can_prev=True, can_next=True, can_toggle=True)


def do_shot(cfg, path, demo=False, state_kind="play", no_session=False):
    from widget import draw
    from widget.media import MediaPoller
    if demo:
        st = _demo_state()
        if state_kind == "idle":
            from widget.media import MediaState
            st = MediaState()
    else:
        p = MediaPoller(interval=0.3)
        p.start()
        p.wait_ready(6.0)
        time.sleep(1.6)
        st = p.state()
        if no_session:
            from widget.media import MediaState
            st = MediaState()
        p.stop()
    k = 1.0
    SS = max(1, int(cfg.get("supersample", 3)))
    art = draw.get_art(st.art, st.art_key, int(round(draw.ART * k * SS)),
                       int(round(draw.ART_RADIUS * k * SS)))
    img = draw.render(st, cfg, art=art, hover=-1, marquee=0.0, k=k,
                      base=(28, 30, 38), height=40)
    img.convert("RGB").save(path)
    print(f"ok -> {path}  ({img.size[0]}x{img.size[1]})")
    print(f"   titulo: {st.title!r}  artista: {st.artist!r}  suena: {st.playing}"
          f"  caratula: {'si' if st.art else 'no'} ({len(st.art or b'')} bytes)")
    return 0


def do_diagnose(cfg, cmd=None):
    from widget.media import MediaPoller
    p = MediaPoller(interval=0.4)
    p.start()
    if not p.wait_ready(6.0):
        print("SMTC no respondio")
        return 1
    for _ in range(6):
        st = p.state()
        if st.has_session:
            break
        time.sleep(0.5)
    st = p.state()
    print("--- estado SMTC ---")
    print(f"sesion activa : {st.has_session}")
    print(f"app           : {st.app_name}  ({st.app_id})")
    print(f"titulo        : {st.title!r}")
    print(f"artista       : {st.artist!r}")
    print(f"album         : {st.album!r}")
    print(f"sonando       : {st.playing}   detenido: {st.stopped}")
    print(f"posicion      : {st.live_position():.1f}s / {st.duration:.1f}s")
    print(f"caratula      : {len(st.art) if st.art else 0} bytes  clave {st.art_key!r}")
    print(f"controles     : prev={st.can_prev} toggle={st.can_toggle} next={st.can_next}")
    if st.art:
        import io
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(st.art))
            print(f"caratula decodificada: {im.size} {im.format}")
        except Exception as exc:
            print("caratula NO decodifica:", exc)
    if cmd:
        print(f"--- enviando comando: {cmd} ---")
        ok = {"toggle": p.toggle, "next": p.next_track, "prev": p.prev_track}[cmd]()
        print("despachado:", ok)
        time.sleep(1.2)
        st2 = p.state()
        print(f"despues -> titulo {st2.title!r}  sonando {st2.playing}"
              f"  posicion {st2.live_position():.1f}s")
    p.stop()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Widget de musica para la barra de tareas")
    ap.add_argument("--no-embed", action="store_true",
                    help="ventana flotante en vez de incrustar en la barra")
    ap.add_argument("--diagnose", action="store_true", help="mostrar datos de SMTC y salir")
    ap.add_argument("--cmd", choices=["toggle", "next", "prev"], help="con --diagnose: probar un comando")
    ap.add_argument("--shot", metavar="PNG", help="volcar el widget a un PNG y salir")
    ap.add_argument("--demo", action="store_true", help="con --shot: usar datos de ejemplo")
    ap.add_argument("--idle", action="store_true", help="con --shot: forzar estado sin reproduccion")
    ap.add_argument("--config", metavar="JSON", help="ruta alternativa de configuracion")
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)

    if args.diagnose:
        return do_diagnose(cfg, args.cmd)
    if args.shot:
        return do_shot(cfg, args.shot, demo=args.demo,
                       state_kind="idle" if args.idle else "play", no_session=args.idle)

    log_path = os.path.join(HERE, cfg.get("log_file", "widget.log"))
    from widget.app import run
    return run(cfg, embed=not args.no_embed, log_path=log_path)


if __name__ == "__main__":
    raise SystemExit(main())
