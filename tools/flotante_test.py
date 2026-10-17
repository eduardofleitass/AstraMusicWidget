"""Prueba del modo flotante (el camino de Windows 11): ventana propia sin barra.

En Windows 10 la barra si sirve para incrustar, asi que el modo flotante se fuerza con
`--flotante`: es la misma ventana y el mismo dibujo que usaria Windows 11, donde la barra
ya no tiene `ReBarWindow32` ni ventanas hijas.

    python tools/flotante_test.py

Deja el widget flotante apagado y vuelve a levantar el de la barra al terminar.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import win32api  # noqa: E402
import win32con  # noqa: E402
import win32gui  # noqa: E402
import win32process  # noqa: E402

from widget import config as cfgmod, draw, flotante as flotante_mod  # noqa: E402
from widget.media import MediaPoller  # noqa: E402
from widget.taskbarwin import list_bars  # noqa: E402

u32 = ctypes.windll.user32
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS, FAIL, SKIP = "PASA", "FALLA", "SALTA"
resultados = []


def check(nombre, ok, detalle="", skipped=False):
    resultados.append((nombre, bool(ok), skipped))
    estado = SKIP if skipped else (PASS if ok else FAIL)
    print(f"{estado}  {nombre}" + (f"  -> {detalle}" if detalle else ""))


def widget_flotante() -> int:
    return win32gui.FindWindow("GorusTaskbarMusicWnd", None)


def ventanas_widget() -> list:
    """Todas las ventanas de widget/controladora que existan (de cualquier instancia)."""
    fuera = []

    def cb(h, _):
        if win32gui.GetClassName(h) in ("GorusTaskbarMusicWnd", "GorusTaskbarMusicCtl"):
            fuera.append(h)
        return True

    win32gui.EnumWindows(cb, None)
    return fuera


def pid_de(hwnd: int) -> int:
    try:
        return win32process.GetWindowThreadProcessId(hwnd)[1]
    except Exception:
        return 0


def matar_restos() -> list:
    """Mata lo que quedo vivo del widget (por si el script de parada no llego)."""
    muertos = []
    for h in ventanas_widget():
        pid = pid_de(h)
        if not pid:
            continue
        try:
            k32 = ctypes.windll.kernel32
            ph = k32.OpenProcess(0x0001, False, pid)     # PROCESS_TERMINATE
            if ph:
                k32.TerminateProcess(ph, 0)
                k32.CloseHandle(ph)
                muertos.append(pid)
        except Exception:
            pass
    return muertos


def esperar_apagado(timeout: float = 15.0) -> bool:
    fin = time.time() + timeout
    while time.time() < fin:
        if not ventanas_widget():
            return True
        time.sleep(0.4)
    return not ventanas_widget()


def alto_barra() -> int:
    try:
        for b in list_bars():
            if b["primario"]:
                return b["rect"][3] - b["rect"][1]
    except Exception:
        pass
    return 0


def ancho_lista() -> int:
    """Ancho de la lista de tareas de la barra principal (para ver que no se le toca)."""
    try:
        from widget.taskbarwin import TaskbarHost
        h = TaskbarHost()
        if h.refresh() and h.container:
            rb = win32gui.GetWindowRect(h.container)
            return rb[2] - rb[0]
    except Exception:
        pass
    return -1


def main() -> int:
    venv = os.path.join(HERE, ".venv", "Scripts", "pythonw.exe")
    print("-- modo flotante (ventana propia, sin barra) --")
    # 1) apagar la instancia de la barra y levantar la flotante
    subprocess.run([sys.executable, os.path.join(HERE, "tools", "stop.py")],
                   cwd=HERE, capture_output=True)
    # OJO: hay que esperar a que la instancia anterior MUERA de verdad. Antes se lanzaba a
    # los 1,5 s: el mutex seguia tomado, la flotante salia sin arrancar y las pruebas
    # medían el widget de la barra (parecia que el doble clic y el tamano del panel
    # fallaban, y el problema era que se estaba midiendo otra instancia).
    if not esperar_apagado():
        restos = matar_restos()
        apagado = esperar_apagado(8)
        print(f"  (quedaban ventanas del widget: mate {restos} -> apagado={apagado})")
    time.sleep(0.8)
    lista_antes = ancho_lista()
    proc = subprocess.Popen([venv, os.path.join(HERE, "main.py"), "--flotante"], cwd=HERE)
    hp = 0
    for _ in range(30):
        time.sleep(0.5)
        hp = widget_flotante()
        if hp and win32gui.IsWindowVisible(hp):
            break
    if not (hp and win32gui.IsWindowVisible(hp)):
        check("el widget flotante arranca y se ve", False,
              f"ventana {hex(hp or 0)} visible={bool(hp) and win32gui.IsWindowVisible(hp)}")
        proc.terminate()
        return _resumen()
    check("el widget flotante arranca y se ve", True, f"hwnd {hex(hp)}")
    check("es la instancia nueva (una sola ventana de widget)",
          len([h for h in ventanas_widget()
               if win32gui.GetClassName(h) == "GorusTaskbarMusicWnd"]) == 1,
          f"{len([h for h in ventanas_widget() if win32gui.GetClassName(h) == 'GorusTaskbarMusicWnd'])}"
          f" ventanas de widget")

    cfg = cfgmod.load()
    k = (win32gui.GetWindowRect(hp)[3] - win32gui.GetWindowRect(hp)[1]) / 40.0
    pr = win32gui.GetWindowRect(hp)
    check("no tiene padre (no es hijo de la barra)", win32gui.GetParent(hp) == 0,
          f"padre {hex(win32gui.GetParent(hp))}")
    ex = win32gui.GetWindowLong(hp, win32con.GWL_EXSTYLE)
    check("es un adorno: sin Alt+Tab y siempre arriba",
          bool(ex & win32con.WS_EX_TOOLWINDOW) and bool(ex & win32con.WS_EX_TOPMOST),
          f"EXSTYLE {hex(ex)}")
    check("la barra de tareas NO le cede espacio (nada reservado)",
          lista_antes > 0 and abs(ancho_lista() - lista_antes) <= 2,
          f"lista {lista_antes} -> {ancho_lista()} px")

    # geometria: dentro del monitor, apoyado en la franja de abajo, sin pisar el reloj
    mon = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
    mi = win32api.GetMonitorInfo(mon)
    mx0, my0, mx1, my1 = mi["Monitor"]
    franja = my1 - alto_barra() if alto_barra() else my1 - 48
    check("apoya en la franja de abajo del monitor", abs(pr[1] - franja) <= 2,
          f"widget y={pr[1]}, franja {franja} (alto de la barra {alto_barra()})")
    check("queda dentro del monitor y lejos del reloj",
          pr[0] >= mx0 and pr[2] <= mx1 - 150 and pr[3] <= my1,
          f"rect {pr} dentro de {mi['Monitor']}")

    # dibujo real: hay pixeles claros (texto) y del color de acento (barra/caratula)
    from PIL import ImageGrab
    img = ImageGrab.grab(bbox=pr, all_screens=True).convert("RGB")
    claros = sum(1 for p in img.get_flattened_data() if sum(p) > 420)
    check("esta dibujado (texto y contenido, no un rectangulo vacio)", claros > 60,
          f"{claros} pixeles claros")

    # clic real sobre play/pausa, con el mismo camino que usa el usuario
    poller = MediaPoller(interval=0.4)
    poller.start()
    poller.wait_ready(6)
    z = draw.control_rects(pr[2] - pr[0], k, cfg)
    if not (z and poller.state().can_toggle):
        check("el play/pausa del widget flotante responde", False,
              "el reproductor no admite play/pausa", skipped=True)
    else:
        cx = pr[0] + (z[1][0] + z[1][2]) // 2
        cy = pr[1] + (z[1][1] + z[1][3]) // 2
        antes = bool(poller.state().playing)
        u32.SetCursorPos(int(cx), int(cy))
        time.sleep(0.35)
        bajo = win32gui.WindowFromPoint((int(cx), int(cy)))
        if bajo != hp:
            check("el play/pausa del widget flotante responde", False,
                  f"bajo el cursor hay {win32gui.GetClassName(bajo)}", skipped=True)
        else:
            u32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.06)
            u32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(1.0)
            ahora = bool(poller.state().playing)
            check("el play/pausa del widget flotante responde", ahora != antes,
                  f"sonando {antes} -> {ahora}")
            if ahora != antes:
                u32.mouse_event(0x0002, 0, 0, 0, 0)
                time.sleep(0.06)
                u32.mouse_event(0x0004, 0, 0, 0, 0)
                time.sleep(0.7)

    # atajo global y panel: siguen andando sin barra
    ctl = win32gui.FindWindow("GorusTaskbarMusicCtl", None)
    if not ctl:
        check("el panel abre con Ctrl+Alt+O en flotante", False, "no hay controladora",
              skipped=True)
    else:
        antes_p = win32gui.FindWindow("GorusTaskbarMusicPanel", None)
        for t in ("CONTROL", "MENU", "O"):
            u32.keybd_event({"CONTROL": 0x11, "MENU": 0x12, "O": 0x4F}[t], 0, 0, 0)
        time.sleep(0.1)
        for t in ("O", "MENU", "CONTROL"):
            u32.keybd_event({"CONTROL": 0x11, "MENU": 0x12, "O": 0x4F}[t], 0, 2, 0)
        time.sleep(1.4)
        panel = win32gui.FindWindow("GorusTaskbarMusicPanel", None)
        abierto = bool(panel and win32gui.IsWindowVisible(panel))
        check("el panel abre con Ctrl+Alt+O en flotante", abierto,
              f"panel {hex(panel or 0)} visible={abierto}")
        if abierto:
            # los ajustes del panel se manejan en el proc del WIDGET (asi lo hace el
            # banco de siempre): a la controladora no le llegan
            win32gui.PostMessage(hp, win32con.WM_APP + 11, 5, 2)   # tamano tira
            time.sleep(1.0)
            pp = win32gui.FindWindow("GorusTaskbarMusicPanel", None)
            rp = win32gui.GetWindowRect(pp) if pp else (0, 0, 0, 0)
            check("el panel tambien anda en flotante (tira fina)",
                  pp and win32gui.IsWindowVisible(pp) and abs((rp[2] - rp[0]) - 320) <= 3,
                  f"panel {rp[2] - rp[0]}x{rp[3] - rp[1]}")
            win32gui.PostMessage(hp, win32con.WM_APP + 11, 5, 0)
            time.sleep(0.5)
            win32gui.PostMessage(hp, win32con.WM_APP + 10, 0, 1)
            time.sleep(0.6)

    poller.stop()
    try:
        proc.terminate()
    except Exception:
        pass
    if not esperar_apagado(10):
        matar_restos()
        esperar_apagado(6)
    # 2) volver a dejar el widget de la barra como estaba
    vbs = os.path.join(HERE, "run.vbs")
    if os.path.exists(vbs):
        subprocess.run(["wscript.exe", vbs], cwd=HERE, capture_output=True)
        time.sleep(4)
    vuelto = 0
    for _ in range(20):
        for b in list_bars():
            h = win32gui.FindWindowEx(b["tray"], 0, "GorusTaskbarMusicWnd", None)
            if h and win32gui.IsWindowVisible(h):
                vuelto = h
        if vuelto:
            break
        time.sleep(0.5)
    check("vuelve el widget de la barra al terminar", bool(vuelto),
          f"hwnd {hex(vuelto or 0)}")
    return _resumen()


def _resumen() -> int:
    fallas = [n for n, o, s in resultados if not o and not s]
    saltadas = [n for n, o, s in resultados if s]
    for n in fallas:
        print(f"FALLA  {n}")
    print(f"\n{len(resultados) - len(fallas) - len(saltadas)}/{len(resultados)} pruebas "
          f"pasaron, {len(saltadas)} saltadas")
    return 1 if fallas else 0


if __name__ == "__main__":
    raise SystemExit(main())
