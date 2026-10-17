"""panel.py: tercer tamano "tira fina" + nombre canonico del tamano."""
import io

P = "widget/panel.py"
s = io.open(P, encoding="utf-8", newline="").read().replace("\r\n", "\n")


def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('''- **chico**: la mitad de alto (una fila de caratula y texto, otra de controles, barra y
  volumen), sin la tercera linea y con los tiempos en el renglon del artista. Pensado
  para jugar: tapa menos pantalla.''',
    '''- **chico**: la mitad de alto (una fila de caratula y texto, otra de controles, barra y
  volumen), sin la tercera linea y con los tiempos en el renglon del artista. Pensado
  para jugar: tapa menos pantalla.
- **tira**: una sola fila de 34 px (caratula de 24, titulo y artista, una barra fina de
  2 px, los tres controles, el altavoz y la cruz), del ancho de la barra de tareas.
  Pensado para jugar en ventana sin tapar nada.''')

rep('''    "chico": {''',
    '''    "tira": {
        "W": 320, "H": 34,
        "margen": 6,
        "tapa": (6, 5, 24), "tapa_radio": 5,
        # el ancho del texto se corta bien antes de los controles (146 de reserva)
        "texto_x": 36, "titulo_y": 4, "titulo_px": 11, "texto_margen_extra": 146,
        "artista_y": 19, "artista_px": 9, "tercera_y": None, "tercera_px": 9,
        "tiempos_en_texto": True,
        "barra": (36, 29, 138, 2), "barra_zona_alto": 8, "tiempos_y": 19,
        "ctrls": (186, 5, 24, 24, 3), "icono_escala": 1.0,
        "vol_icono": (266, 11, 14, 16), "vol_barra": (284, 16, 14, 4),
        "vol_zona": (264, 9, 36, 20),
        "cerrar": (308, 5, 10, 10),
    },
    "chico": {''')

rep('''def layout(cfg: dict) -> dict:
    """El tamano elegido. Acepta "chico"/"compacto" o "normal"."""
    nombre = str(cfg.get("panel_size", "normal")).strip().lower()
    return LAYOUTS["chico" if nombre.startswith(("chi", "com", "min")) else "normal"]''',
    '''def normalizar(nombre: str) -> str:
    """Nombre canonico del tamano: normal / chico / tira.

    Un solo lugar decide que variante pidio el usuario, para que el menu, la config y
    el dibujo no discrepen (se aceptan los nombres que uno escribe de memoria).
    """
    n = str(nombre or "").strip().lower()
    if n.startswith(("tir", "fin", "str")):
        return "tira"
    if n.startswith(("chi", "com", "min")):
        return "chico"
    return "normal"


def layout(cfg: dict) -> dict:
    """El tamano elegido (normal / chico / tira)."""
    return LAYOUTS[normalizar(cfg.get("panel_size", "normal"))]''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("panel.py: tira fina agregada")
