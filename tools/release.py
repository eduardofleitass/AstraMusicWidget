"""Publica una version: compila, arma el instalador y la sube a GitHub.

    python tools\\release.py                 compila, arma el instalador y sube todo
    python tools\\release.py --sin-compilar  usa lo que ya esta en dist/ (no recompila)
    python tools\\release.py --sin-subir     compila y arma el instalador; no toca GitHub
    python tools\\release.py --borrador      sube como prerelease (no cambia "latest")

Por que existe esto: la version vivia escrita a mano en cuatro lugares
(`widget/__init__.py`, `instalador/version.iss`, `instalador/version_info.txt` y el
manifiesto de winget) y el link de descarga cambiaba con cada numero, porque los archivos
de la release llevan la version en el nombre. Esto hace las dos cosas de una:

1. propaga la version desde un solo lugar antes de compilar (lo hace `build_exe.py`), y
2. sube **una copia con nombre FIJO** ademas de la versionada, asi el link de "ultima
   version" no cambia nunca:

       .../releases/latest/download/Astra-Music-widget-setup.exe
       .../releases/latest/download/Astra-Music-widget.exe

Es la forma barata de tener un link estable: GitHub resuelve `latest` al ultimo release
publicado y el nombre del archivo es siempre el mismo. La alternativa (una carpeta en el
repo con los .exe adentro) mete 58 MB por version en el historial de git para siempre, y
este repo justamente ignora `dist/`, `build/` e `instalador/*.exe`.

Requiere: PyInstaller e Inno Setup 6 (y `gh`, que se baja solo la primera vez).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from widget import __version__  # noqa: E402

REPO = "eduardofleitass/AstraMusicWidget"
NOMBRE = "Astra-Music-widget"
EXE = os.path.join(RAIZ, "dist", NOMBRE + ".exe")
ISCC = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
GH = os.path.expandvars(r"%LOCALAPPDATA%\Temp\gh\bin\gh.exe")
SETUP = os.path.join(RAIZ, "instalador", f"{NOMBRE}-{__version__}-setup.exe")
NOTAS = os.path.join(RAIZ, "instalador", "notas-del-release.md")
TAG = "v" + __version__
BASE = f"https://github.com/{REPO}/releases"
ESTABLES = {"setup": f"{NOMBRE}-setup.exe", "portatil": f"{NOMBRE}.exe"}


# --------------------------------------------------------------------------- gh
def _token() -> str:
    """El token del Gestor de Credenciales (el mismo que usa `git push`)."""
    salida = subprocess.run(["git", "credential", "fill"], cwd=RAIZ,
                            input="protocol=https\nhost=github.com\n\n",
                            capture_output=True, text=True, timeout=60).stdout
    token = next((l.split("=", 1)[1].strip() for l in salida.splitlines()
                  if l.startswith("password=")), None)
    if not token:
        raise SystemExit("no pude leer el token de GitHub del Gestor de Credenciales")
    return token


def gh(*args: str) -> tuple[int, str]:
    entorno = dict(os.environ, GH_TOKEN=_token())
    r = subprocess.run([GH, *args], env=entorno, cwd=RAIZ, capture_output=True,
                       text=True, timeout=1800)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def hay_gh() -> bool:
    if os.path.exists(GH):
        return True
    print("falta gh: bajandolo a %LOCALAPPDATA%\\Temp\\gh ...")
    destino = os.path.dirname(os.path.dirname(GH))
    os.makedirs(destino, exist_ok=True)
    zip_path = os.path.join(destino, "gh.zip")
    urllib.request.urlretrieve(
        "https://github.com/cli/cli/releases/download/v2.63.2/gh_2.63.2_windows_amd64.zip",
        zip_path)
    shutil.unpack_archive(zip_path, destino)
    carpeta = os.path.join(destino, "bin")
    for raiz, _dirs, archivos in os.walk(destino):
        if "gh.exe" in archivos and os.path.basename(raiz) == "bin":
            carpeta = raiz
            break
    os.makedirs(os.path.dirname(GH), exist_ok=True)
    shutil.copy2(os.path.join(carpeta, "gh.exe"), GH)
    return os.path.exists(GH)


# ----------------------------------------------------------------------- pasos
def compilar() -> None:
    print("1. ejecutable (PyInstaller, puede tardar un par de minutos)")
    r = subprocess.call([sys.executable, os.path.join(RAIZ, "tools", "build_exe.py")],
                        cwd=RAIZ)
    if r != 0 or not os.path.exists(EXE):
        raise SystemExit("fallo la compilacion")


def instalador() -> None:
    print("2. instalador (Inno Setup)")
    if not os.path.exists(ISCC):
        raise SystemExit(f"no encuentro Inno Setup en {ISCC}")
    r = subprocess.call([ISCC, os.path.join(RAIZ, "instalador", NOMBRE + ".iss")], cwd=RAIZ)
    if r != 0 or not os.path.exists(SETUP):
        raise SystemExit("fallo el instalador")


def subir(borrador: bool) -> None:
    print(f"3. release {TAG}")
    if not os.path.exists(EXE) or not os.path.exists(SETUP):
        raise SystemExit("faltan los binarios (correr sin --sin-compilar)")
    if not hay_gh():
        raise SystemExit("no pude preparar gh")

    titulo = f"{NOMBRE} {__version__}"
    notas = ["--notes-file", NOTAS] if os.path.exists(NOTAS) else ["--notes", titulo]
    extra = ["--prerelease"] if borrador else []
    rc, out = gh("release", "create", TAG, "--repo", REPO, "--title", titulo,
                 *notas, *extra)
    if rc != 0:
        if "already exists" in out:
            print("   ya existia: actualizo titulo y notas")
            gh("release", "edit", TAG, "--repo", REPO, "--title", titulo, *notas)
        else:
            raise SystemExit("no pude crear la release:\n" + out.strip()[:600])

    # La copia con nombre fijo es la que hace que el link no cambie de una version a otra.
    # Se sube con --clobber: si quedo una copia de una version anterior, se reemplaza.
    fija = os.path.join(os.path.dirname(SETUP), ESTABLES["setup"])
    shutil.copy2(SETUP, fija)
    for archivo in (EXE, SETUP, fija):
        print("   subiendo", os.path.basename(archivo),
              f"({os.path.getsize(archivo) / 1e6:.1f} MB)")
        rc, out = gh("release", "upload", TAG, archivo, "--clobber", "--repo", REPO)
        if rc != 0:
            raise SystemExit("fallo la subida de %s:\n%s"
                             % (os.path.basename(archivo), out.strip()[:400]))


def verificar() -> None:
    """Comprueba contra el servidor que los dos links estables bajan el tamano correcto.

    No alcanza con que `gh` diga que subio: lo que importa es que la URL que esta en el
    README entregue el archivo. Y de paso queda el SHA256 publicado, que es el que pide
    winget (se mide bajando, nunca copiando el del archivo local).
    """
    print("4. verificacion de los links fijos")
    esperado = {ESTABLES["setup"]: os.path.getsize(SETUP),
                ESTABLES["portatil"]: os.path.getsize(EXE)}
    for nombre, tam in esperado.items():
        url = f"{BASE}/latest/download/{nombre}"
        with urllib.request.urlopen(url, timeout=120) as resp:
            datos = resp.read()
        igual = len(datos) == tam
        print(f"   {url}\n      {len(datos)} bytes (local {tam}) -> "
              f"{'OK' if igual else 'NO COINCIDE'}")
        if nombre == ESTABLES["setup"]:
            print("      SHA256 del instalador publicado: "
                  + hashlib.sha256(datos).hexdigest().upper())


def main() -> int:
    argv = sys.argv[1:]
    print(f"{NOMBRE} {__version__}")
    if "--sin-compilar" not in argv:
        compilar()
    instalador()
    if "--sin-subir" in argv:
        print(f"listo: {EXE}\n       {SETUP}\n(sin tocar GitHub)")
        return 0
    subir("--borrador" in argv)
    verificar()
    print(f"\nrelease: {BASE}/tag/{TAG}")
    print("falta: python tools\\winget_pr.py (el SHA sale de la verificacion de arriba)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
