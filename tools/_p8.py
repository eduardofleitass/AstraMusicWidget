"""Modo flotante: host sin barra, ventana propia, flag --flotante y autodeteccion."""
import io


def rep(P, a, b, n=1):
    s = io.open(P, encoding="utf-8", newline="").read().replace("\r\n", "\n")
    assert s.count(a) == n, (P, a[:70], s.count(a))
    io.open(P, "w", encoding="utf-8", newline="").write(s.replace(a, b))
    print("ok:", P)


# --- taskbarwin: saber si hay una barra usable (en Windows 11 no la hay) --------
rep("widget/taskbarwin.py",
    "class TaskbarHost:",
    '''def barras_usables() -> bool:
    """True si hay una barra donde incrustar el widget.

    Windows 11 conserva `Shell_TrayWnd` pero **sin `ReBarWindow32`** ni ventanas hijas,
    asi que el host se queda sin contenedor ni ancla: ahi hay que pasar al modo flotante
    (una ventana propia pegada al borde). Se comprueba de verdad, no por version.
    """
    try:
        h = TaskbarHost()
        return bool(h.refresh() and h.container and h.anchor)
    except Exception:
        return False


class TaskbarHost:''')

# --- app: elegir host, ventana propia y guardas del modo flotante --------------
rep("widget/app.py",
    '''    def __init__(self, cfg: dict, embed: bool = True, log_path: str | None = None):
        self.cfg = cfg
        self.embed = embed
        self.host = TaskbarHost(log=self.log, monitor=cfg.get("taskbar_monitor"))''',
    '''    def __init__(self, cfg: dict, embed: bool = True, log_path: str | None = None,
                 flotante: bool = False):
        self.cfg = cfg
        self.embed = embed
        if flotante:
            # Sin barra que lo aloje (Windows 11): el widget vive como ventana propia
            # pegada al borde de abajo. Mismo contrato, otro respaldo.
            self.host = FloatingHost(log=self.log, monitor=cfg.get("taskbar_monitor"),
                                     reserva_derecha=int(cfg.get("flotante_reserva_derecha",
                                                                 300)))
        else:
            self.host = TaskbarHost(log=self.log, monitor=cfg.get("taskbar_monitor"))''')

rep("widget/app.py",
    "from . import config as cfgmod\nfrom . import draw",
    "from . import config as cfgmod\nfrom . import draw\nfrom .flotante import FloatingHost")

rep("widget/app.py",
    "        self.layered = str(cfg.get(\"bg_mode\", \"layered\")).lower() == \"layered\"",
    '''        self.layered = str(cfg.get("bg_mode", "layered")).lower() == "layered"
        if getattr(self.host, "flotante", False):
            # Sin barra no hay color que muestrear para mezclar: alpha real (ULW), que es
            # lo que deja ver el escritorio de atras (y es lo que ya usa el panel).
            self.layered = True''')

# la ventana: en flotante es de nivel superior (sin padre) y siempre arriba
rep("widget/app.py",
    '''        x_rel = self._reserve_x()
        hinst = win32api.GetModuleHandle(None)
        self.hwnd_widget = win32gui.CreateWindowEx(''',
    '''        x_rel = self._reserve_x()
        hinst = win32api.GetModuleHandle(None)
        if getattr(self.host, "flotante", False):
            # Ventana propia: sin padre, popup, siempre arriba y fuera de Alt+Tab (es un
            # adorno del sistema, no una aplicacion). Nace ya en su franja para que no
            # parpadee en (0,0).
            self.hwnd_widget = win32gui.CreateWindowEx(
                win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW
                | (WS_EX_LAYERED if self.layered else 0),
                WIDGET_CLASS, "gorus-widget", win32con.WS_POPUP,
                x_rel, self.host.strip_y(), self.width_px, self.height_px,
                0, None, hinst, None)
            if not self.hwnd_widget:
                self.log("no se pudo crear la ventana del widget (flotante)")
                return False
            self._needs_show = True
            self.dib = None
            self._ensure_surface()
            self._sig = None
            return True
        self.hwnd_widget = win32gui.CreateWindowEx(''')

# nada tapa al widget flotante (esta arriba de todo) y no hay barras por las que mudarse
rep("widget/app.py",
    '''    def _covered(self) -> bool:
        """True si la lista de tareas quedo por encima del widget (la tapa)."""
        try:''',
    '''    def _covered(self) -> bool:
        """True si la lista de tareas quedo por encima del widget (la tapa)."""
        if getattr(self.host, "flotante", False):
            return False           # en flotante esta por encima de todo
        try:''')

rep("widget/app.py",
    '''def run(cfg: dict, embed: bool = True, log_path: str | None = None) -> int:
    return WidgetApp(cfg, embed=embed, log_path=log_path).run()''',
    '''def run(cfg: dict, embed: bool = True, log_path: str | None = None,
        flotante: bool = False) -> int:
    return WidgetApp(cfg, embed=embed, log_path=log_path, flotante=flotante).run()''')

# --- main.py: flag y autodeteccion -------------------------------------------
rep("main.py",
    '''    ap.add_argument("--config", metavar="JSON", help="ruta alternativa de configuracion")''',
    '''    ap.add_argument("--config", metavar="JSON", help="ruta alternativa de configuracion")
    ap.add_argument("--flotante", action="store_true",
                    help="forzar el modo flotante (ventana propia sobre el borde, sin "
                         "barra). Es lo que se usa solo en Windows 11")''')

rep("main.py",
    "    return run(cfg, embed=not args.no_embed, log_path=log_path)",
    '''    # Modo flotante: si la barra no sirve para incrustar (Windows 11), se pasa solo.
    # Con --flotante se fuerza en cualquier Windows, que es como se prueba en 10.
    flotante = args.flotante or not taskbarwin.barras_usables()
    if flotante and not args.no_embed:
        log("modo flotante: %s",
            "pedido con --flotante" if args.flotante else
            "la barra de tareas no admite incrustar (Windows 11)")
    return run(cfg, embed=not args.no_embed, log_path=log_path, flotante=flotante)''')
