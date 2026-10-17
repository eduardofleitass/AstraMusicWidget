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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from widget import __version__  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONO = os.path.join(HERE, "assets", "icono.ico")
VERSION = os.path.join(HERE, "instalador", "version_info.txt")
DEFINE = os.path.join(HERE, "instalador", "version.iss")
NOMBRE = "Astra-Music-widget"


def escribir_version() -> None:
    """Deja la version que pide el ejecutable y el define que lee el instalador.

    Asi el numero vive en un solo lugar (`widget/__init__.py`): antes estaba escrito a
    mano en el .iss, en el version_info.txt y en el README, y era cuestion de tiempo que
    la 1.1 saliera con el instalador diciendo 1.0.
    """
    v4 = tuple(int(x) for x in (__version__.split(".") + ["0", "0", "0"])[:4])
    texto = f'''# Generado por tools/build_exe.py desde widget/__init__.py. No editar a mano.
VSVersionInfo(
  ffi=FixedFileInfo(filevers={v4}, prodvers={v4}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040a04b0', [
        StringStruct('CompanyName', 'Eduardo Fleitas'),
        StringStruct('FileDescription', 'Astra-Music-widget'),
        StringStruct('FileVersion', '{__version__}'),
        StringStruct('InternalName', 'Astra-Music-widget'),
        StringStruct('OriginalFilename', 'Astra-Music-widget.exe'),
        StringStruct('ProductName', 'Astra-Music-widget'),
        StringStruct('ProductVersion', '{__version__}'),
        StringStruct('LegalCopyright', 'Uso libre')])]),
    VarFileInfo([VarStruct('Translation', [1034, 1200])])
  ]
)
'''
    with open(VERSION, "w", encoding="utf-8") as fh:
        fh.write(texto)
    with open(DEFINE, "w", encoding="utf-8") as fh:
        # OJO: en Inno Setup el comentario es ';'. Con '#' al principio de linea el
        # preprocesador lo lee como directiva y el .iss no compila ("Unknown
        # preprocessor directive").
        fh.write(f'; Generado por tools/build_exe.py. No editar a mano.\n'
                 f'#define MiVersion "{__version__}"\n')
    print(f"version {__version__} propagada al ejecutable y al instalador")


def main() -> int:
    escribir_version()
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
    if os.path.exists(VERSION):
        # version del .exe: es la que se ve en Propiedades y la que compara el instalador
        cmd += ["--version-file", VERSION]
    cmd.append(os.path.join(HERE, "main.py"))
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=HERE)


if __name__ == "__main__":
    raise SystemExit(main())
