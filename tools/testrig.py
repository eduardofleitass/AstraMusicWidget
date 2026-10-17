"""Banco de pruebas local: simula un reproductor con SMTC completo.

Levanta un servidor HTTP con tres pistas, caratulas distintas y metadatos de
MediaSession, e implementa los manejadores de play / pause / next / prev. Asi el
widget se puede probar de punta a punta (titulo, artista, caratula, progreso y
botones) sin depender de Spotify ni de YouTube.

    python tools/testrig.py            # y abrir la URL que imprime
    python tools/testrig.py --no-open  # solo servir

El estado actual de la pista queda en tools/_rig_state.json para poder comprobar
desde afuera que un clic en el widget realmente cambio de tema.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import struct
import sys
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "_rig_state.json")
PORT = 8765
_last = {}

TRACKS = [
    ("Astra Test Track One", "Astra Dev", (60, 120, 220), (250, 210, 90)),
    ("Segunda Pista de Prueba Con Un Nombre Bastante Largo", "Astra Dev",
     (200, 70, 90), (255, 240, 200)),
    ("Third Track", "Astra Dev", (30, 170, 140), (240, 240, 240)),
]


def tone_wav(seconds: int = 150) -> bytes:
    sr = 22050
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(sr * seconds):
            # acorde suave para que se note que hay audio
            t = i / sr
            v = sum(math.sin(2 * math.pi * f * t) for f in (220.0, 277.18, 329.63))
            frames += struct.pack("<h", int(2600 * v / 3))
        w.writeframes(bytes(frames))
    return buf.getvalue()


def cover_png(idx: int) -> bytes:
    from PIL import Image, ImageDraw
    _, _, c1, c2 = TRACKS[idx]
    size = 512
    img = Image.new("RGB", (size, size), c1)
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        d.line([(0, y), (size, y)],
               fill=(int(c1[0] + (c2[0] - c1[0]) * t),
                     int(c1[1] + (c2[1] - c1[1]) * t),
                     int(c1[2] + (c2[2] - c1[2]) * t)))
    d.ellipse([110, 110, 402, 402], outline=(255, 255, 255), width=10)
    d.text((236, 244), str(idx + 1), fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Astra Test Track One</title></head>
<body style="background:#111;color:#eee;font-family:Segoe UI,sans-serif;padding:24px">
<h2 id="now">...</h2>
<p>Banco de pruebas del widget. Usa el widget o estos botones; todo pasa por SMTC.</p>
<audio id="a" src="/tone.wav" loop></audio>
<button onclick="audio.play()">play</button>
<button onclick="audio.pause()">pause</button>
<button onclick="jump(1)">next</button>
<button onclick="jump(-1)">prev</button>
<script>
const TRACKS = __TRACKS__;
let i = 0;
const audio = document.getElementById("a");
function report() {
  document.getElementById("now").textContent = "Sonando: " + TRACKS[i].title;
  try { fetch("/log?track=" + i + "&t=" + Date.now()); } catch (e) {}
}
function apply() {
  const t = TRACKS[i];
  if ("mediaSession" in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: t.title, artist: t.artist, album: t.album,
      artwork: [{ src: t.cover, sizes: "512x512", type: "image/png" }]
    });
    try { navigator.mediaSession.playbackState = "playing"; } catch (e) {}
  }
  document.title = t.title;
}
function jump(d) { i = (i + d + TRACKS.length) % TRACKS.length; apply(); report(); audio.play(); }
function logTime(extra) {
  try { fetch("/log?track=" + i + "&time=" + audio.currentTime.toFixed(2) + (extra || "")); } catch (e) {}
}
if ("mediaSession" in navigator) {
  navigator.mediaSession.setActionHandler("play", () => audio.play());
  navigator.mediaSession.setActionHandler("pause", () => audio.pause());
  navigator.mediaSession.setActionHandler("nexttrack", () => jump(1));
  navigator.mediaSession.setActionHandler("previoustrack", () => jump(-1));
  // El widget mueve la barra con try_change_playback_position_async, que el
  // navegador entrega a este manejador (o al <audio> si no hay manejador).
  navigator.mediaSession.setActionHandler("seekto", (d) => {
    if (d && d.seekTime != null) audio.currentTime = d.seekTime;
    logTime("&seek=1");
  });
}
apply(); report();
audio.play().catch(e => { document.getElementById("now").textContent = "autoplay bloqueado: " + e; });
// Muestreo continuo: publica la posicion real para poder comprobarla desde afuera.
setInterval(() => {
  if ("setPositionState" in navigator.mediaSession && audio.duration) {
    try {
      navigator.mediaSession.setPositionState({
        duration: audio.duration, playbackRate: audio.playbackRate,
        position: audio.currentTime
      });
    } catch (e) {}
  }
  logTime("");
}, 400);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p == "/":
            tracks = [{"title": t[0], "artist": t[1], "album": "Widget Test Rig",
                       "cover": f"/cover/{n}.png"} for n, t in enumerate(TRACKS)]
            html = PAGE.replace("__TRACKS__", json.dumps(tracks, ensure_ascii=False))
            self._send(html.encode("utf-8"), "text/html; charset=utf-8")
        elif p == "/tone.wav":
            self._send(tone_wav(), "audio/wav")
        elif p.startswith("/cover/"):
            try:
                idx = int(p.split("/")[2].split(".")[0]) % len(TRACKS)
            except Exception:
                idx = 0
            self._send(cover_png(idx), "image/png")
        elif p == "/log":
            q = parse_qs(u.query)
            data = {"track": int(q.get("track", ["0"])[0]),
                    "time": float(q.get("time", ["0"])[0])}
            if q.get("seek"):
                data["seek"] = True
            try:
                with open(STATE_FILE, "w", encoding="utf-8") as fh:
                    json.dump(data, fh)
            except Exception:
                pass
            # Solo se habla cuando cambia de tema o cuando alguien pide un salto:
            # el muestreo de posicion escribe el archivo 2 veces por segundo.
            if data["track"] != _last.get("track") or data.get("seek"):
                print(f"[rig] pista {data['track']}: {TRACKS[data['track']][0]}"
                      f"  t={data['time']:.1f}s" + ("  (salto pedido)" if data.get("seek") else ""))
                _last["track"] = data["track"]
            self._send(b"ok", "text/plain")
        else:
            self._send(b"no", "text/plain", 404)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"[rig] sirviendo en {url}")
    print(f"[rig] pistas: {[t[0] for t in TRACKS]}")
    if not args.no_open:
        import webbrowser
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
