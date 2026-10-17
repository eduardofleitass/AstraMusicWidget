"""Vigila el estado SMTC en vivo. Util para depurar la capa de medios.

    python tools/watch.py            # 12 s de muestras cada 0,5 s
    python tools/watch.py --cmd toggle --after 3   # comando a los 3 s
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from widget.media import MediaPoller  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=12)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--cmd", choices=["toggle", "next", "prev"])
    ap.add_argument("--after", type=float, default=3.0)
    args = ap.parse_args()

    p = MediaPoller(interval=0.2, log=lambda m, *a: print("  [log]", m % a if a else m))
    p.start()
    p.wait_ready(6.0)
    t0 = time.monotonic()
    fired = False
    print(f"{'t':>5}  {'app':<14} {'sonando':<8} {'pos':>7} {'dur':>7}  titulo")
    while time.monotonic() - t0 < args.seconds:
        t = time.monotonic() - t0
        st = p.state()
        print(f"{t:5.1f}  {st.app_name:<14} {str(st.playing):<8} "
              f"{st.live_position():7.1f} {st.duration:7.1f}  {st.title[:44]!r}")
        if args.cmd and not fired and t >= args.after:
            fired = True
            print(f"       >>> enviando {args.cmd}")
            {"toggle": p.toggle, "next": p.next_track, "prev": p.prev_track}[args.cmd]()
        time.sleep(args.interval)
    p.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
