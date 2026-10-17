"""Capa de datos: lee la reproduccion actual desde SMTC (System Media Transport Controls).

SMTC es el bus de medios de Windows: cualquier reproductor que respete el sistema
(Spotify, Chrome/Edge/Brave, VLC, Groove, foobar2000 con plugin, etc.) publica ahi
titulo, artista, caratula, estado y posicion. Tambien acepta comandos
(play/pausa/siguiente/anterior), asi que no hace falta hablar con cada reproductor.

Todo el acceso WinRT vive en un hilo propio con su propio event loop asyncio:
los objetos de winsdk pertenecen al apartamento que los creo, por lo que los
comandos se despachan con run_coroutine_threadsafe.
"""
from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from dataclasses import dataclass, replace

from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager,
)
from winsdk.windows.storage.streams import DataReader

# Valores de GlobalSystemMediaTransportControlsSessionPlaybackStatus
ST_CLOSED = 0
ST_OPENED = 1
ST_CHANGING = 2
ST_STOPPED = 3
ST_PLAYING = 4
ST_PAUSED = 5

# Unidad de la API de seek: 100 ns por tick. winsdk ENTREGA timedelta al leer el
# timeline, pero try_change_playback_position_async espera un ENTERO de ticks
# (pasarle un timedelta revienta con TypeError).
TICKS = 10_000_000

# Cuanto se ignora el timeline despues de un salto pedido por el usuario: el
# reproductor puede tardar en reportar la posicion nueva.
SEEK_GRACE_S = 2.0


@dataclass(frozen=True)
class MediaState:
    """Foto inmutable de lo que esta sonando. Se reemplaza entera, nunca se muta."""

    has_session: bool = False
    app_id: str = ""
    title: str = ""
    artist: str = ""
    album: str = ""
    subtitle: str = ""
    playing: bool = False
    stopped: bool = False
    position: float = 0.0
    duration: float = 0.0
    position_at: float = 0.0
    art: bytes | None = None
    art_key: str = ""
    can_prev: bool = True
    can_next: bool = True
    can_toggle: bool = True
    # Salto de posicion: un stream en vivo (sin fin) no lo admite.
    can_seek: bool = False
    min_seek: float = 0.0
    max_seek: float = 0.0
    error: str = ""

    def live_position(self, now: float | None = None) -> float:
        """Posicion interpolada: SMTC solo reporta cada ~1s; extrapolamos para que
        la barra de progreso no vaya a saltos."""
        now = time.monotonic() if now is None else now
        if not self.playing or not self.duration:
            return max(0.0, min(self.position, self.duration or self.position))
        pos = self.position + max(0.0, now - self.position_at)
        if self.duration:
            pos = min(pos, self.duration)
        return max(0.0, pos)

    @property
    def display_artist(self) -> str:
        # Cadena de respaldo: artista -> album -> subtitulo -> nombre de la app. En
        # videos de YouTube el campo de artista suele venir vacio (el canal va en el
        # subtitulo) y sin respaldo el renglon quedaba en blanco; el nombre de la app
        # como ultimo recurso al menos dice de donde viene el sonido.
        for valor in (self.artist, self.album, self.subtitle):
            if valor:
                return valor
        return self.app_name

    @property
    def app_name(self) -> str:
        raw = (self.app_id or "").split("!")[0]
        raw = raw.split("\\")[-1]
        if raw.lower().endswith(".exe"):
            raw = raw[:-4]
        return raw


def _fmt_timedelta(td) -> float:
    try:
        return max(0.0, td.total_seconds())
    except Exception:
        return 0.0


def _flag(obj, name: str, default: bool = True) -> bool:
    try:
        return bool(getattr(obj, name))
    except Exception:
        return default


class MediaPoller(threading.Thread):
    """Hilo demonio que sondea SMTC y publica un MediaState."""

    def __init__(self, interval: float = 0.5, log=None):
        super().__init__(daemon=True, name="smtc-poller")
        self.interval = interval
        self._log = log or (lambda *a, **k: None)
        self._lock = threading.Lock()
        self._state = MediaState()
        self._stop = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._manager = None
        self._session = None
        self._art_key: str | None = None
        self._art_bytes: bytes | None = None
        self._pending_seek: tuple[float, float] | None = None
        self._ready = threading.Event()

    # ---------------------------------------------------------------- lectura
    def state(self) -> MediaState:
        with self._lock:
            return self._state

    def wait_ready(self, timeout: float = 6.0) -> bool:
        return self._ready.wait(timeout)

    # --------------------------------------------------------------- comandos
    def _submit(self, action: str, arg: float | None = None) -> bool:
        loop = self._loop
        if loop is None or loop.is_closed():
            return False
        try:
            asyncio.run_coroutine_threadsafe(self._command(action, arg), loop)
            return True
        except Exception as exc:
            self._log("no se pudo despachar %s: %r", action, exc)
            return False

    def toggle(self) -> bool:
        return self._submit("toggle")

    def next_track(self) -> bool:
        return self._submit("next")

    def prev_track(self) -> bool:
        return self._submit("prev")

    def seek(self, seconds: float) -> bool:
        """Salta a una posicion absoluta (segundos).

        El ancla local se mueve ya, de forma optimista: SMTC tarda en reportar el
        salto, y sin esto la barra vuelve sola a la posicion vieja por un instante.
        Si el reproductor rechaza el salto, el sondeo siguiente manda de nuevo.
        """
        st = self.state()
        if not st.has_session:
            self._log("salto descartado: no hay sesion de medios")
            return False
        if not st.can_seek:
            self._log("salto descartado: esta sesion no admite saltos (%s)", st.app_id)
            return False
        if st.duration <= 0:
            self._log("salto descartado: no se conoce la duracion")
            return False
        top = st.max_seek or st.duration
        target = max(st.min_seek, min(float(seconds), top))
        if not self._submit("seek", target):
            self._log("salto a %.1f s no despachado: el hilo de SMTC no responde", target)
            return False
        with self._lock:
            cur = self._state
            if cur.has_session:
                self._state = replace(cur, position=target, position_at=time.monotonic())
            self._pending_seek = (target, time.monotonic())
        return True

    def seek_by(self, delta: float) -> bool:
        """Adelanta (+) o atrasa (-) respecto de la posicion actual."""
        st = self.state()
        if not st.has_session or not st.can_seek:
            return False
        return self.seek(st.live_position() + float(delta))

    async def _command(self, action: str, arg: float | None = None) -> None:
        session = self._manager.get_current_session() if self._manager else None
        if session is None:
            session = self._session
        if session is None:
            return
        try:
            if action == "toggle":
                await session.try_toggle_play_pause_async()
            elif action == "next":
                await session.try_skip_next_async()
            elif action == "prev":
                await session.try_skip_previous_async()
            elif action == "seek" and arg is not None:
                ok = await session.try_change_playback_position_async(
                    int(round(arg * TICKS)))
                if not ok:
                    self._log("el reproductor rechazo el salto a %.1f s", arg)
                    with self._lock:
                        self._pending_seek = None
        except Exception as exc:
            self._log("comando %s fallo: %r", action, exc)
        # refrescar sin esperar al proximo ciclo para que el boton responda ya
        try:
            await self._tick()
        except Exception:
            pass

    # ------------------------------------------------------------------ ciclo
    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except Exception as exc:
            self._log("poller termino con error: %r", exc)
        finally:
            try:
                loop.close()
            except Exception:
                pass

    async def _main(self) -> None:
        try:
            self._manager = await SessionManager.request_async()
        except Exception as exc:
            self._log("SMTC no disponible: %r", exc)
            with self._lock:
                self._state = MediaState(error=f"SMTC no disponible: {exc}")
            self._ready.set()
            return
        self._ready.set()
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as exc:
                self._log("tick fallo: %r", exc)
            await asyncio.sleep(self.interval)

    async def _pick_session(self):
        """Elige que reproductor mostrar.

        Windows marca una "sesion actual" propia, pero puede quedarse apuntando a
        un reproductor pausado aunque otro este sonando. Como la preferencia es
        "seguir al ultimo que emitio sonido", priorizamos lo que realmente suena,
        con preferencia pegajosa para no saltar entre dos fuentes a la vez.
        """
        try:
            current = self._manager.get_current_session()
        except Exception:
            current = None

        def aid(s):
            try:
                return s.source_app_user_model_id or ""
            except Exception:
                return ""

        playing = []
        try:
            for cand in self._manager.get_sessions():
                try:
                    if cand.get_playback_info().playback_status == ST_PLAYING:
                        playing.append(cand)
                except Exception:
                    continue
        except Exception:
            playing = []

        cur_id = aid(current) if current is not None else None
        sticky_id = aid(self._session) if self._session is not None else None

        if cur_id is not None:
            for s in playing:
                if aid(s) == cur_id:
                    return s
        if sticky_id is not None:
            for s in playing:
                if aid(s) == sticky_id:
                    return s  # sigue donde estaba: no saltamos si ya suena
        if playing:
            return playing[0]
        if current is not None:
            return current  # nada suena: mostrar el actual, aunque este en pausa
        for cand in (self._session,):
            if cand is not None:
                return cand
        return None

    async def _tick(self) -> None:
        session = await self._pick_session()
        if session is None:
            self._session = None
            self._art_key = None
            self._art_bytes = None
            self._publish(MediaState())
            return

        self._session = session
        app_id = session.source_app_user_model_id or ""
        props = await session.try_get_media_properties_async()
        info = session.get_playback_info()
        status = info.playback_status
        controls = getattr(info, "controls", None)
        tl = session.get_timeline_properties()

        title = props.title or ""
        artist = props.artist or props.album_artist or ""
        album = props.album_title or ""
        # El subtitulo es el tercer dato de texto de SMTC (en YouTube suele ser el
        # canal o "Official Video"): no se muestra si hay artista, pero evita el
        # renglon vacio cuando el reproductor no manda ni artista ni album.
        subtitle = props.subtitle or ""
        playing = status == ST_PLAYING
        stopped = status in (ST_CLOSED, ST_STOPPED)

        key = f"{app_id}|{title}|{artist}|{album}"
        if key != self._art_key:
            self._art_key = key
            self._art_bytes = await self._read_thumbnail(props)

        position = _fmt_timedelta(tl.position)
        duration = _fmt_timedelta(tl.end_time)
        min_seek = _fmt_timedelta(tl.min_seek_time)
        max_seek = _fmt_timedelta(tl.max_seek_time)
        # Un stream en vivo no tiene fin (duration 0) y no admite salto. Si el
        # reproductor no informa el techo, se asume la duracion conocida.
        can_seek = duration > 1.0 and (max_seek <= 0 or max_seek > min_seek)
        if max_seek <= 0:
            max_seek = duration

        prev = self.state()
        can_next = _flag(controls, "is_next_enabled") if controls else True
        can_prev = _flag(controls, "is_previous_enabled") if controls else True
        can_toggle = _flag(controls, "is_play_pause_toggle_enabled") if controls else True

        # Anclaje del tiempo: el ancla solo se mueve cuando el reproductor reporta
        # un avance real. Si se moviera en cada ciclo, live_position() nunca
        # acumularia y la barra de progreso quedaria congelada (los reproductores
        # informan la posicion cada varios segundos, no de forma continua).
        same_source = prev.has_session and prev.art_key == key
        delta = position - prev.position
        now = time.monotonic()
        pend = self._pending_seek
        # Justo despues de un salto pedido por el usuario, el reproductor puede
        # seguir informando la posicion vieja (YouTube via Brave tarda ~1 s). Ese
        # reporte es atrasado, no un salto hacia atras: si se adoptara, la barra
        # volveria sola y despues saltaria de nuevo.
        stale = (pend is not None and now - pend[1] < SEEK_GRACE_S
                 and abs(position - prev.live_position(now)) > 2.0)

        if not same_source or playing != prev.playing or stopped != prev.stopped:
            adopt = True
            self._pending_seek = None   # cambio de tema: el salto ya no aplica
        elif stale:
            adopt = False               # reporte atrasado: dejar extrapolar
        elif delta >= 0.1:
            adopt = True            # avance normal
        elif abs(delta) > 2.0:
            adopt = True            # salto hacia atras: el usuario se movio
        else:
            adopt = False           # mismo valor o temblor: dejar extrapolar

        if adopt:
            state = MediaState(
                has_session=True, app_id=app_id, title=title, artist=artist,
                album=album, subtitle=subtitle, playing=playing, stopped=stopped,
                position=position, duration=duration,
                position_at=time.monotonic(), art=self._art_bytes, art_key=key,
                can_next=can_next, can_prev=can_prev, can_toggle=can_toggle,
                can_seek=can_seek, min_seek=min_seek, max_seek=max_seek)
        else:
            state = replace(prev, playing=playing, stopped=stopped,
                            duration=duration or prev.duration,
                            can_next=can_next, can_prev=can_prev,
                            can_toggle=can_toggle, can_seek=can_seek,
                            min_seek=min_seek, max_seek=max_seek)
        self._publish(state)

    async def _read_thumbnail(self, props) -> bytes | None:
        thumb = getattr(props, "thumbnail", None)
        if thumb is None:
            return None
        try:
            stream = await thumb.open_read_async()
            size = stream.size
            if not size:
                return None
            reader = DataReader(stream)
            await reader.load_async(size)
            buf = reader.read_buffer(size)
            return bytes(memoryview(buf))
        except Exception as exc:
            self._log("caratula ilegible: %r", exc)
            return None

    def _publish(self, state: MediaState) -> None:
        with self._lock:
            self._state = state


def art_fingerprint(data: bytes | None) -> str:
    if not data:
        return ""
    return hashlib.blake2b(data, digest_size=8).hexdigest()
