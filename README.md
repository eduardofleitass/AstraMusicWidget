# Widget de musica para la barra de tareas

Muestra lo que esta sonando **dentro** de la barra de tareas de Windows 10:
caratula, titulo, artista, barra de progreso y botones de anterior / play-pausa /
siguiente. Se ve como una parte nativa de la barra y reserva su propio espacio.

```
[ Inicio ][ buscar ][ tareas... ][ ▣ Bohemian Rhapsody        ][ 19°C ][ reloj ]
                                  [   Queen  ⏮ ⏸ ⏭  ▂▂▂▂▂▂▂▂ ]
```

No hay que configurar nada por reproductor: se engancha al **SMTC**, el bus de
medios de Windows. Funciona con Spotify, YouTube y cualquier web en Chrome /
Edge / Brave, VLC, Groove, foobar2000, etc. Cualquier app que respete el sistema
publica ahi titulo, caratula, estado y posicion, y acepta los comandos.

Probado en Windows 10 22H2 (19045), escala 100% y 1920x1080.


## Uso

| Que queres | Como |
|---|---|
| Arrancar el widget | doble clic en `run.vbs` |
| Que arranque solo con Windows | `install_startup.bat` |
| Sacarlo del arranque y detenerlo | `uninstall_startup.bat` |
| Mostrar / ocultar sin cerrarlo | `Ctrl + Alt + M` |
| Menu (ancho, refrescar, salir) | clic derecho sobre el widget |
| Detenerlo | clic derecho > Salir, o `python tools\stop.py` |
| Reinstalar dependencias | `setup.bat` |

Si nunca corriste nada todavia, empeza por `setup.bat`.


## Como se ve

- **Caratula** de la cancion, con esquinas redondeadas.
- **Titulo**: si no entra en el ancho disponible, se desplaza en bucle
  (marquesina) con un desvanecido en el borde. Al cambiar de tema vuelve al
  principio.
- **Artista** recortado con puntos suspensivos.
- **Barra de progreso** que avanza suave aunque el reproductor informe la
  posicion cada varios segundos (ver *Interpolacion del tiempo*).
- **Botones** que se iluminan al pasar el mouse. Cuando un reproductor no ofrece
  algun control, el boton se dibuja atenuado.
- **Sin reproduccion**: estado apagado con una nota musical y los controles
  inactivos, en vez de desaparecer.


## Como funciona

Tres piezas bien separadas:

| Archivo | Responsabilidad |
|---|---|
| `widget/media.py` | Lee el SMTC en un hilo propio con su propio event loop asyncio. Publica una foto inmutable (`MediaState`) y despacha los comandos. |
| `widget/draw.py` | Dibuja el widget con Pillow en un lienzo ampliado x3 y lo reduce con LANCZOS: asi los bordes redondeados, los iconos vectoriales y el texto salen suaves sin depender de GDI+ ni de un framework de UI. |
| `widget/app.py` + `taskbarwin.py` | Ventana Win32, doble buffer, entrada de mouse y el anclaje en la barra. |

### La incrustacion en la barra

Windows 10 no tiene API de "bandas" (se elimino despues de Vista), pero acepta
ventanas hijas de `Shell_TrayWnd`. El procedimiento:

1. crear la ventana como hija de `Shell_TrayWnd` con `WS_CHILD`
2. apoyarla contra el borde izquierdo del bloque de noticias o de la bandeja
3. encoger `ReBarWindow32` (la lista de tareas) para liberar exactamente ese ancho
4. devolver a la lista su **ancho natural** al salir

Detalles que costaron encontrar:

- **Coordenadas**: en ventanas hijas, `SetWindowPos` usa coordenadas relativas al
  **cliente del padre**, no a la pantalla. Mezclarlas manda la barra fuera de
  lugar. Pasa igual al leer con `GetWindowRect`, que devuelve coordenadas de
  pantalla.
- **El color de fondo se muestrea**: el chip del widget es levemente translucido,
  asi que se lee el color real de la barra con `GetPixel` y se mezcla ahi. Asi se
  ve integrado sin depender de `UpdateLayeredWindow`.
- **`DynamicContent2` se mueve solo**: el bloque del clima cambia de tamano por su
  cuenta. Por eso el layout se recalcula periodicamente y el widget sigue a su
  ancla en lugar de quedar desalineado.
- **`SetWindowPos` antes de crear**: la ventana se reserva y se crea ya en su
  sitio. Si naciera en `(0,0)` parpadearia un instante encima del boton Inicio.

### Interpolacion del tiempo

Los reproductores informan la posicion cada varios segundos, no de forma
continua. Si se usara ese valor directo, la barra de progreso avanzaria a saltos.
`MediaState.live_position()` extrapola usando el reloj, y el ancla temporal solo
se mueve cuando el reproductor reporta un **avance real**. Si el ancla se moviera
en cada ciclo de sondeo, la extrapolacion nunca acumularia tiempo y la barra
quedaria congelada (fue un bug real, medido: posicion clavada en 49,1 s durante
6 s con la musica sonando).

### Que reproductor se muestra

Windows marca una "sesion actual" propia, pero puede quedarse apuntando a un
reproductor **pausado** aunque otro este sonando. Como la preferencia es seguir
al ultimo que emitio sonido, el widget prioriza lo que realmente suena, con
preferencia *pegajosa* para no saltar entre dos fuentes a la vez:

1. la sesion que Windows marca como actual, **si esta sonando**
2. la que ya venia mostrando, si sigue sonando
3. cualquier otra que este sonando
4. si nada suena, la que Windows marque como actual (asi una cancion en pausa se
   sigue viendo)

### Por que no se repinta de mas

Cada ciclo se calcula una *firma* de lo visible (caratula, titulo, estado,
progreso redondeado al pixel de la barra, hover, posicion de la marquesina). Solo
se redibuja si la firma cambia. En reposo el consumo medido es **0,00% de CPU** y
unos **5 MB de RAM**; la barra de progreso cambia de pixel cada ~1,3 s en un tema
de 3 minutos, asi que no tiene sentido repintar 10 veces por segundo.


## Resiliencia

Esta disenado para **nunca dejar la barra de tareas rota**, que es el peor modo de
falla posible de esta tecnica:

- Al arrancar, primero **sanea**: devuelve la lista de tareas a su ancho natural
  antes de reservar. Si una ejecucion anterior murio sin limpiar, se corrige y no
  se acumula el encogimiento.
- Si `explorer.exe` se reinicia, la ventana controladora sobrevive (es de nivel
  superior, no hija de la barra), recibe `TaskbarCreated` y reconstruye el widget.
- Si la ventana del widget muere por cualquier motivo, un chequeo periodico la
  reconstruye y la vuelve a anclar.
- Si la barra se reacomoda y le roba el espacio, el widget lo recupera solo.
- El atajo `Ctrl+Alt+M` es la salida de emergencia: si algo saliera mal, oculta el
  widget sin depender del mouse.
- `python tools\stop.py --force` mata el proceso y repara la barra si quedo
  inconsistente.

16 de 16 pruebas de anclaje y recuperacion pasan (`python tools\selftest.py` con el
widget en marcha), incluidas la reconstruccion forzada y la recuperacion de
espacio. Y 7 de 7 de interaccion real (`python tools\clicktest.py`): el hover
ilumina los tres botones, un clic de verdad cambia el estado de reproduccion, el
segundo clic lo restaura, y un clic en la caratula no dispara nada.

`clicktest.py` mueve el cursor de verdad, asi que **si estas usando el mouse
mientras corre tus movimientos compiten con los que inyecta**. La prueba lo
detecta, lo informa como `SALTA` en vez de inventar un fallo, y te dice que sueltes
el mouse y la corras de nuevo.

Ademas se probo a mano lo que mas duele: matar el proceso a la fuerza deja la
barra encogida, y el arranque siguiente la sanea sola sin acumular el
encogimiento.


## Configuracion

`config.json`, se aplica al arrancar. Los cambios por menu (ancho) se guardan solos.

| Clave | Por defecto | Que hace |
|---|---|---|
| `width` | 260 | Ancho en px logicos (se escala solo con el DPI) |
| `min_tasklist_width` | 420 | Minimo de lista de tareas que se respeta al reservar espacio |
| `poll_interval_ms` | 500 | Cada cuanto se consulta el SMTC |
| `timer_playing_ms` / `timer_idle_ms` | 100 / 500 | Cada cuanto se revisa si hay que redibujar |
| `marquee_speed` / `marquee_gap` | 32 / 40 | Velocidad y separacion del bucle del titulo |
| `supersample` | 3 | Factor de suavizado. Bajalo a 2 si te importa la CPU |
| `show_art` / `show_controls` / `show_progress` | true | Que elementos se dibujan |
| `corner_radius` / `chip_alpha` | 7 / 232 | Forma y transparencia del chip |
| `theme` | ver archivo | Colores del chip, borde, textos, acento, pista e iconos |

Si te gusta mas ancho o mas angosto: clic derecho sobre el widget > *Mas ancho* /
*Mas angosto*.


## Herramientas de desarrollo

```bash
python main.py --no-embed        # ventana flotante, sin tocar la barra
python main.py --diagnose        # ver que esta leyendo del SMTC
python main.py --diagnose --cmd next   # probar un comando contra el reproductor
python main.py --shot prev.png   # volcar el widget a un PNG
python tools\watch.py            # estado en vivo, muestreado cada 0,5 s
python tools\preview.py hoja.png # hoja con todas las variantes visuales
python tools\selftest.py         # suite de verificacion (widget en marcha)
python tools\clicktest.py        # prueba de clic real con el mouse (restaura el estado)
python tools\startup.py --status # ver si el arranque automatico esta activo
python tools\stop.py             # cierre ordenado
python tools\testrig.py          # banco de pruebas: reproductor simulado con 3 pistas
```

Para depurar la entrada de mouse, arrancar con `GORUS_DEBUG_MOUSE=1`: cada
`WM_MOUSEMOVE` queda anotado en `widget.log` con sus coordenadas y el boton
detectado.

`testrig.py` es el mas util para desarrollar: levanta un reproductor falso en
`http://127.0.0.1:8765/` con tres pistas, caratulas distintas y los manejadores de
play / pause / next / prev, asi se prueba todo el circuito sin depender de Spotify
ni de YouTube. La pista actual queda en `tools/_rig_state.json` para poder
comprobar desde afuera que un clic realmente cambio de tema.


## Requisitos

- Windows 10 1809 o posterior (SMTC necesita esa version).
- Python 3.11. Las dependencias las instala `setup.bat`; son tres:
  `winsdk` (SMTC), `pywin32` (Win32) y `pillow` (dibujo).


## Limitaciones conocidas

- Solo Windows 10. En Windows 11 la barra es otra (`Shell_TrayWnd` cambio de
  estructura) y habria que rehacer el anclaje.
- El widget vive en la barra **principal**. Si tenes varias barras o la moviste a
  otro borde, hay que adaptar el calculo del anclaje.
- Se reserva el ancho de `config.json` de la lista de tareas. Con muchisimas
  ventanas abiertas la lista queda mas corta; `min_tasklist_width` limita cuanto
  puede ceder, y `Ctrl+Alt+M` lo oculta cuando necesites el espacio.
- La caratula la entrega el reproductor ya reducida (YouTube via Edge da 150x150,
  Spotify da 300x300), asi que en pantallas con escalado alto puede verse algo
  blanda: se muestran a 32 px logicos, no hace falta mas.
