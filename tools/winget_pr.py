"""Publica el paquete de winget: arma el manifiesto y abre el PR en microsoft/winget-pkgs.

Para la proxima version: actualizar VER y SHA (el SHA se saca bajando el instalador de la
release nueva y midiendolo, nunca copiando el local), y correrlo de nuevo.

winget es el canal que trae descargas sin que nadie promocione nada: `winget install` y
aparece en winstall.app y compania. El PR va a microsoft/winget-pkgs, que es enorme, asi que
no se clona: se crean los archivos por la API sobre una rama nueva del fork.

El paquete apunta al instalador de la release v1.0.3, con el SHA256 que se verifico bajando
el archivo publicado (mismo hash que el local: la release se sube primero, se baja el
instalador y recien despues se corre esto).

Ojo: el PR queda frenado hasta firmar el CLA de Microsoft (el bot lo pide solo en un
comentario). Es un tramite de una vez por cuenta, no de cada version.
"""
import base64
import json
import os
import subprocess

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH = os.path.expandvars(r"%LOCALAPPDATA%\Temp\gh\bin\gh.exe")
TOKEN = subprocess.run(
    ["git", "credential", "fill"], cwd=RAIZ, input="protocol=https\nhost=github.com\n\n",
    capture_output=True, text=True, timeout=60).stdout
TOKEN = next((l.split("=", 1)[1].strip() for l in TOKEN.splitlines()
              if l.startswith("password=")), None)
assert TOKEN, "no pude obtener el token del Gestor de Credenciales"
ENTORNO = dict(os.environ, GH_TOKEN=TOKEN)

VER = "1.0.3"
ID = "EduardoFleitas.AstraMusicWidget"
SHA = "5B92F59754F78A1B5BE028FD5FD0B103F9C58F738CE8A017388F5A2533AAFC05"
URL = ("https://github.com/eduardofleitass/AstraMusicWidget/releases/download/"
       f"v{VER}/Astra-Music-widget-{VER}-setup.exe")
CARPETA = f"manifests/e/EduardoFleitas/AstraMusicWidget/{VER}"

YAML = {
    f"{ID}.yaml": f"""PackageIdentifier: {ID}
PackageVersion: {VER}
DefaultLocale: es-ES
ManifestType: version
ManifestVersion: 1.6.0
""",
    f"{ID}.installer.yaml": f"""PackageIdentifier: {ID}
PackageVersion: {VER}
InstallerLocale: es-ES
Platform:
- Windows.Desktop
MinimumOSVersion: 10.0.17763.0
InstallerType: inno
Scope: user
InstallModes:
- interactive
- silent
- silentWithProgress
UpgradeBehavior: install
AppsAndFeaturesEntries:
- DisplayName: Astra-Music-widget
  Publisher: Eduardo Fleitas
  DisplayVersion: {VER}
Installers:
- Architecture: x64
  InstallerUrl: {URL}
  InstallerSha256: {SHA}
ManifestType: installer
ManifestVersion: 1.6.0
""",
    f"{ID}.locale.es-ES.yaml": f"""PackageIdentifier: {ID}
PackageVersion: {VER}
PackageLocale: es-ES
Publisher: Eduardo Fleitas
PublisherUrl: https://github.com/eduardofleitass
PackageName: Astra-Music-widget
PackageUrl: https://github.com/eduardofleitass/AstraMusicWidget
License: MIT
LicenseUrl: https://github.com/eduardofleitass/AstraMusicWidget/blob/main/LICENSE
ShortDescription: Widget de musica que vive dentro de la barra de tareas de Windows.
Description: |
  Muestra lo que esta sonando dentro de la barra de tareas de Windows: caratula, titulo,
  artista, barra de progreso clicable, controles y el volumen de la app que suena. Lee la
  sesion de multimedia del sistema (SMTC), asi que anda con Spotify, VLC y lo que suene en
  el navegador. Tiene ademas un panel con tres tamanos y un modo pensado para jugar.
Tags:
- music
- taskbar
- widget
- spotify
- smtc
ManifestType: defaultLocale
ManifestVersion: 1.6.0
"""}


# --- 0) el mismo paquete, en el repo local -------------------------------------------
LOCAL = os.path.join(RAIZ, "winget", "manifests", "e", "EduardoFleitas", "AstraMusicWidget")
viejo = os.path.join(LOCAL, "1.0.2")
if os.path.isdir(viejo):
    import shutil
    shutil.rmtree(viejo)
    print("0. saque el manifiesto 1.0.2 (el PR anterior quedo cerrado por el bot: la carpeta "
          "habia quedado sin archivos al reemplazarla por API)")
destino = os.path.join(LOCAL, VER)
os.makedirs(destino, exist_ok=True)
for nombre, texto in YAML.items():
    with open(os.path.join(destino, nombre), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)
print("0. escrito winget/manifests/.../%s/ (%d archivos)" % (VER, len(YAML)))


def sh(*args, **kw):
    r = subprocess.run([GH, *args], env=ENTORNO, capture_output=True, text=True,
                       cwd=RAIZ, timeout=300, **kw)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# --- 1) el fork (puede tardar: GitHub lo copia de su lado) --------------------------
print("1. fork de microsoft/winget-pkgs")
sh("repo", "fork", "microsoft/winget-pkgs", "--clone=false")
for intento in range(20):
    rc, out = sh("api", f"/repos/eduardofleitass/winget-pkgs/git/ref/heads/master",
                 "--jq", ".object.sha")
    if rc == 0 and out.strip():
        sha_master = out.strip()
        print("   listo, master en", sha_master[:8])
        break
    import time
    time.sleep(6)
else:
    raise SystemExit("el fork no termino de crearse: " + out.strip()[:200])

# --- 2) rama nueva (el PR no puede salir de master) ---------------------------------
RAMA = f"astra-music-widget-{VER}"
print("2. rama", RAMA)
for ruta in (f"/repos/eduardofleitass/winget-pkgs/git/refs",):
    rc, out = sh("api", "--method", "POST", ruta, "-f", f"ref=refs/heads/{RAMA}",
                 "-f", f"sha={sha_master}")
print("   ", out.strip()[:120] or "creada")

# --- 3) los tres archivos ------------------------------------------------------------
print("3. archivos")
for nombre, texto in YAML.items():
    b64 = base64.b64encode(texto.encode("utf-8")).decode("ascii")
    rc, out = sh("api", "--method", "PUT",
                 f"/repos/eduardofleitass/winget-pkgs/contents/{CARPETA}/{nombre}",
                 "-f", f"message=Add {ID} version {VER}", "-f", f"content={b64}",
                 "-f", f"branch={RAMA}")
    print("   ", nombre, "->", "ok" if rc == 0 else out.strip()[:200])

# --- 4) el PR ------------------------------------------------------------------------
CUERPO = f"""<!-- paquete nuevo, no una actualizacion -->
- [x] Tengo permiso para distribuir este software
- [x] El instalador es de 64 bits y se instala por usuario (sin administrador)
- [x] El enlace de descarga es directo y el SHA256 esta verificado

Astra-Music-widget es un widget de musica que vive dentro de la barra de tareas de Windows
10: caratula, titulo, artista, barra de progreso clicable, controles y el volumen de la app,
leyendo la sesion de multimedia de Windows (SMTC). Hecho en Python con Win32.

- Repositorio: https://github.com/eduardofleitass/AstraMusicWidget
- Release v{VER}: https://github.com/eduardofleitass/AstraMusicWidget/releases/tag/v{VER}
- Licencia: MIT
- Requiere Windows 10 1809 o posterior. En Windows 11 (probado en la build 26300) la barra
  nueva no admite ventanas propias, asi que corre como tira flotante pegada al borde de
  abajo; el programa lo detecta solo al arrancar, midiendo la estructura de la barra.

El instalador es Inno Setup con `PrivilegesRequired=lowest` (por usuario, sin UAC) e instala
en `%LOCALAPPDATA%\\Programs\\Astra-Music-widget`.
"""
print("4. pull request")
rc, out = sh("api", "--method", "POST", "/repos/microsoft/winget-pkgs/pulls",
             "-f", f"title=New package: {ID} version {VER}",
             "-f", f"head=eduardofleitass:{RAMA}", "-f", "base=master",
             "-f", f"body={CUERPO}")
if rc == 0:
    print("   PR creado:", json.loads(out).get("html_url"))
else:
    print("   fallo:", out.strip()[:400])
