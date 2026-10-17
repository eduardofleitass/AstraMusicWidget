"""Actualiza el PR de winget a la version 1.0.2.

El PR #454922 abierto apunta a 1.0.1, que es la version que se queda callada cuando algo
falla. Conviene que la primera version que la gente instale desde winget sea la que avisa.
Se reemplaza la carpeta 1.0.1 por 1.0.2 en la misma rama del fork (asi el PR queda con una
sola version, que es lo que espera el revisor) y se avisa en un comentario.
"""
import base64
import hashlib
import json
import os
import shutil
import subprocess

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH = os.path.expandvars(r"%LOCALAPPDATA%\Temp\gh\bin\gh.exe")
TOKEN = subprocess.run(
    ["git", "credential", "fill"], cwd=RAIZ, input="protocol=https\nhost=github.com\n\n",
    capture_output=True, text=True, timeout=60).stdout
TOKEN = next((l.split("=", 1)[1].strip() for l in TOKEN.splitlines()
              if l.startswith("password=")), None)
assert TOKEN, "sin token"
ENTORNO = dict(os.environ, GH_TOKEN=TOKEN)

VER, VIEJA = "1.0.2", "1.0.1"
ID = "EduardoFleitas.AstraMusicWidget"
USUARIO, RAMA = "eduardofleitass", "astra-music-widget-1.0.1"
INSTALADOR = os.path.join(RAIZ, "instalador", f"Astra-Music-widget-{VER}-setup.exe")

with open(INSTALADOR, "rb") as fh:
    datos = fh.read()
SHA = hashlib.sha256(datos).hexdigest().upper()
print("instalador 1.0.2:", len(datos), "bytes | SHA256", SHA[:16] + "...")

URL = ("https://github.com/eduardofleitass/AstraMusicWidget/releases/download/"
       f"v{VER}/Astra-Music-widget-{VER}-setup.exe")

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


def sh(*args):
    r = subprocess.run([GH, *args], env=ENTORNO, capture_output=True, text=True,
                       errors="replace", cwd=RAIZ, timeout=300)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# --- local: el manifiesto 1.0.2 en el repo --------------------------------------------
LOCAL = os.path.join(RAIZ, "winget", "manifests", "e", "EduardoFleitas", "AstraMusicWidget")
shutil.rmtree(os.path.join(LOCAL, VIEJA), ignore_errors=True)
os.makedirs(os.path.join(LOCAL, VER), exist_ok=True)
for nombre, texto in YAML.items():
    with open(os.path.join(LOCAL, VER, nombre), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)
print("local: winget/manifests/.../%s/ listo (se fue el %s)" % (VER, VIEJA))

# --- remoto: la misma rama del fork --------------------------------------------------
CARPETA_VIEJA = f"manifests/e/EduardoFleitas/AstraMusicWidget/{VIEJA}"
CARPETA = f"manifests/e/EduardoFleitas/AstraMusicWidget/{VER}"
rc, out = sh("api", f"/repos/{USUARIO}/winget-pkgs/contents/{CARPETA_VIEJA}?ref={RAMA}")
viejos = json.loads(out) if rc == 0 else []
for archivo in (viejos if isinstance(viejos, list) else []):
    rc, out = sh("api", "--method", "DELETE",
                 f"/repos/{USUARIO}/winget-pkgs/contents/{CARPETA_VIEJA}/{archivo['name']}",
                 "-f", f"message=Actualizar a {VER}", "-f", f"sha={archivo['sha']}",
                 "-f", f"branch={RAMA}")
    print("  borrado", archivo["name"], "->", "ok" if rc == 0 else out[:120])
for nombre, texto in YAML.items():
    rc, out = sh("api", "--method", "PUT",
                 f"/repos/{USUARIO}/winget-pkgs/contents/{CARPETA}/{nombre}",
                 "-f", f"message=Add {ID} version {VER}", "-f",
                 "content=" + base64.b64encode(texto.encode()).decode(),
                 "-f", f"branch={RAMA}")
    print("  subido ", nombre, "->", "ok" if rc == 0 else out[:120])

rc, out = sh("api", "--method", "PATCH", "/repos/microsoft/winget-pkgs/pulls/454922",
             "-f", f"title=New package: {ID} version {VER}")
print("titulo del PR ->", "ok" if rc == 0 else out[:150])
sh("api", "--method", "POST", "/repos/microsoft/winget-pkgs/issues/454922/comments",
   "-f", f"body=Actualizo el PR a la {VER}: los ejecutables sin firma pueden quedar sin hacer "
         "nada al arrancar en una maquina ajena, asi que esta version avisa en pantalla con "
         "un cartel cuando no puede arrancar, en vez de quedarse callada. El instalador es el "
         "mismo (Inno Setup, por usuario, sin administrador); cambia el SHA256.")
print("comentario -> ok")
