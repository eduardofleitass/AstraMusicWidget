"""Corre TODAS las suites de verificacion y resume el resultado.

    python tools\\tests.py              todas
    python tools\\tests.py selftest     solo una (selftest, clicktest, hotkeytest, flotante)

Requiere el widget andando (menos `flotante`, que arranca el suyo y lo deja como estaba).
Aviso: `clicktest` mueve el mouse de verdad y `hotkeytest` manda teclas reales, asi que no
toques el mouse ni el teclado mientras corren: si interferis, las pruebas que dependen del
teclado/raton lo informan como SALTA en vez de inventar un fallo.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(HERE)
PY = os.path.join(RAIZ, ".venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable

SUITES = [
    ("selftest", "selftest.py", "todo el widget: anclaje, dibujo, fondos, ondas, colores, panel"),
    ("flotante", "flotante_test.py", "el modo flotante (el que se ve en Windows 11)"),
    ("hotkeys", "hotkeytest.py", "atajos globales con teclas reales y rueda con modificadores"),
    ("clics", "clicktest.py", "clics de verdad con el mouse (caratula, play, barra, volumen)"),
]
RESUMEN = re.compile(r"(\d+)\s*/\s*(\d+)\s+pruebas pasaron(?:,\s*(\d+)\s+saltadas)?")


def correr(script: str) -> tuple:
    print("\n" + "=" * 78)
    print("== %s" % script)
    print("=" * 78, flush=True)
    proc = subprocess.run([PY, os.path.join(HERE, script)], cwd=RAIZ,
                          capture_output=True, text=True, errors="replace")
    salida = (proc.stdout or "") + (proc.stderr or "")
    print(salida, flush=True)
    # quedarse con la ultima linea de resumen y con los fallos, para el cuadro final
    pasaron = total = saltadas = None
    for m in RESUMEN.finditer(salida):
        pasaron, total = int(m.group(1)), int(m.group(2))
        saltadas = int(m.group(3) or 0)
    fallos = [l.strip() for l in salida.splitlines() if l.strip().startswith("FALLA")]
    return pasaron, total, saltadas, fallos, proc.returncode


def main() -> int:
    pedidas = sys.argv[1:]
    suites = [s for s in SUITES if not pedidas or s[0] in pedidas]
    if not suites:
        print("no conozco esa suite. Opciones: %s" % ", ".join(s[0] for s in SUITES))
        return 2
    resultados = []
    for nombre, script, que in suites:
        if not os.path.exists(os.path.join(HERE, script)):
            print("falta tools/%s" % script)
            continue
        resultados.append((nombre, que, correr(script)))

    print("\n" + "=" * 78)
    print("RESUMEN")
    print("=" * 78)
    fallaron = 0
    for nombre, que, (pasaron, total, saltadas, fallos, code) in resultados:
        if total is None:
            estado = "sin resumen (salida distinta; mirar arriba, codigo %s)" % code
            fallaron += 1
        else:
            bien = total - (pasaron or 0) - (saltadas or 0)
            estado = ("%d/%d pasaron" % (pasaron, total)
                      + (", %d saltadas" % saltadas if saltadas else "")
                      + ("" if bien == 0 else ", %d FALLAN" % bien))
            fallaron += bien
        print("  %-9s %-62s %s" % (nombre, que[:62], estado))
        for f in fallos:
            print("      %s" % f)
    print()
    if fallaron:
        print("hay %d comprobaciones que fallan (arriba esta el detalle)" % fallaron)
    else:
        print("todas las comprobaciones pasan (las SALTA estan justificadas: modo flotante, "
              "reproductor sin sesion de audio, interferencia del teclado/mouse, etc.)")
    return 1 if fallaron else 0


if __name__ == "__main__":
    raise SystemExit(main())
