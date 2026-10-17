"""Empaqueta el widget en un .exe: se puede usar sin Python ni el entorno virtual.

    python tools/build_exe.py            # deja dist/Astra-Music-widget.exe
    python tools/build_exe.py --dir      # una carpeta en vez de un solo archivo

Detalles que importan:

- `--windowed`: nada de consola (es un adorno del escritorio).
- `--collect-all winsdk`: los datos de WinRT (los .winmd) no los encuentra solo; sin eso
  el ejecutable arranca y no lee ninguna sesion de multimedia.
- El config y el log se crean **al lado del .exe** en el primer arranque (no van
  empaquetados): `widget/config.py` resuelve la carpeta con `sys.frozen`.
- El icono lo hace `tools/make_icon.py` (una sola vez; queda en `assets/`).
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONO = os.path.join(HERE, "assets", "icono.ico")
NOMBRE = "Astra-Music-widget"


def main() -> int:
    if not os.path.exists(ICONO):
        print("no esta el icono: generandolo...")
        subprocess.run([sys.executable, os.path.join(HERE, "tools", "make_icon.py")],
                       cwd=HERE, check=False)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--windowed", "--name", NOMBRE,
           "--collect-all", "winsdk",
           "--distpath", os.path.join(HERE, "dist"),
           "--workpath", os.path.join(HERE, "build"),
           "--specpath", os.path.join(HERE, "build")]
    if "--dir" not in sys.argv:
        cmd.append("--onefile")
    if os.path.exists(ICONO):
        cmd += ["--icon", ICONO]
    cmd.append(os.path.join(HERE, "main.py"))
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=HERE)


if __name__ == "__main__":
    raise SystemExit(main())
