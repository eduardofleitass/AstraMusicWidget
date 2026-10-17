"""flotante_test: arranque limpio (esperar a que muera la instancia anterior)."""
import io

P = "tools/flotante_test.py"
s = io.open(P, encoding="utf-8", newline="").read().replace("\r\n", "\n")


def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('''def alto_barra() -> int:''',
    '''def ventanas_widget() -> list:
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


def alto_barra() -> int:''')

rep('''def ancho_lista() -> int:
    try:
        for b in list_bars():
            if b["primario"]:
                cont = b.get("container")
                if cont:
                    return win32gui.GetWindowRect(cont)[2] - b["rect"][0]
    except Exception:
        pass
    return 0''',
    '''def ancho_lista() -> int:
    """Ancho de la lista de tareas de la barra principal (para ver que no se le toca)."""
    try:
        from widget.taskbarwin import TaskbarHost
        h = TaskbarHost()
        if h.refresh() and h.container:
            rb = win32gui.GetWindowRect(h.container)
            return rb[2] - rb[0]
    except Exception:
        pass
    return -1''')

rep('''    subprocess.run([sys.executable, os.path.join(HERE, "tools", "stop.py")],
                   cwd=HERE, capture_output=True)
    time.sleep(1.5)
    lista_antes = ancho_lista()''',
    '''    subprocess.run([sys.executable, os.path.join(HERE, "tools", "stop.py")],
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
    lista_antes = ancho_lista()''')

rep('''    check("el widget flotante arranca y se ve", True, f"hwnd {hex(hp)}")''',
    '''    check("el widget flotante arranca y se ve", True, f"hwnd {hex(hp)}")
    check("es la instancia nueva (una sola ventana de widget)",
          len([h for h in ventanas_widget()
               if win32gui.GetClassName(h) == "GorusTaskbarMusicWnd"]) == 1,
          f"{len([h for h in ventanas_widget() if win32gui.GetClassName(h) == 'GorusTaskbarMusicWnd'])}"
          f" ventanas de widget")''')

rep('''    check("la barra de tareas NO le cede espacio (nada reservado)",
          abs(ancho_lista() - lista_antes) <= 2,
          f"lista {lista_antes} -> {ancho_lista()} px")''',
    '''    check("la barra de tareas NO le cede espacio (nada reservado)",
          lista_antes > 0 and abs(ancho_lista() - lista_antes) <= 2,
          f"lista {lista_antes} -> {ancho_lista()} px")''')

rep('''    try:
        proc.terminate()
        time.sleep(1.2)
    except Exception:
        pass''',
    '''    try:
        proc.terminate()
    except Exception:
        pass
    if not esperar_apagado(10):
        matar_restos()
        esperar_apagado(6)''')

rep("import win32gui  # noqa: E402",
    "import win32gui  # noqa: E402\nimport win32process  # noqa: E402")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("flotante_test: arranque limpio")
