# Widget de musica para la barra de tareas

Muestra lo que esta sonando **dentro** de la barra de tareas de Windows 10:
caratula, titulo, artista, barra de progreso y botones de anterior / play-pausa /
siguiente. Se ve como una parte nativa de la barra y reserva su propio espacio.

```
[ Inicio ][ buscar ][ tareas... ][ ▣ Bohemian Rhapsody  ▁█▃▅ ][ ⏮ ⏸ ⏭ ][ 19°C ][ reloj ]
                                  [   Queen         ▂▂▂▂▂▂▂▂ ]
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
| Mostrar / ocultar sin cerrarlo | `Ctrl + Alt + M` (la misma tecla lo vuelve a mostrar) |
| Atrasarlo o adelantarlo | clic en la barra de progreso, o la rueda del mouse (±10 s) |
| Ondas de sonido (animacion) | clic derecho > *Ondas de sonido* |
| Color de la barra o de las ondas | clic derecho > *Color de la barra* / *Color de las ondas* |
| Fondo transparente | clic derecho > *Fondo* |
| Moverlo a otra parte de la barra | arrastralo con el boton izquierdo, o clic derecho > *Mover / Centrar* |
| Menu (ondas, fondo, adelantar/atrasar, mover, ancho, salir) | clic derecho sobre el widget |
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
  posicion cada varios segundos (ver *Interpolacion del tiempo*), y que ademas
  **se puede mover**: clic o arrastre para saltar a cualquier parte del tema.
- **Botones** que se iluminan al pasar el mouse. Cuando un reproductor no ofrece
  algun control, el boton se dibuja atenuado.
- **Ondas de sonido** (opcional): barras que bailan entre el texto y los botones.
  Se prenden y apagan desde el menu contextual.
- **Sin reproduccion**: estado apagado con una nota musical y los controles
  inactivos, en vez de desaparecer.
- **Fondo regulable**: de chip solido a *sin fondo*, donde el widget queda
  flotando sobre la barra y solo se ven la caratula, los textos y los botones.
- **Posicion libre**: se lo puede arrastrar a cualquier parte de la barra donde
  entre, y no vuelve solo a su lugar.



## Fondo transparente

Clic derecho > *Fondo*, con cuatro niveles: **solido** (por defecto),
**translucido**, **muy transparente** y **sin fondo**.

No es un truco de color: la ventana se crea con `WS_EX_LAYERED` y se presenta con
`UpdateLayeredWindow`, asi que el alpha de cada pixel del chip se compone contra
lo que hay de verdad detras. Medido comparando la misma franja de pantalla con el
widget encima y con esa zona pelada: con *sin fondo* la diferencia es **0,00** (o
sea, el widget es invisible y se ve la barra tal cual), y con los niveles
intermedios 8,5 y 13,9, contra 19,1 del chip solido.

Ese estilo servia solo para ventanas de nivel superior hasta Windows 7; desde
Windows 8 tambien vale para ventanas **hijas**, que es lo que permite hacerlo
dentro de la barra.

Como el fondo ya no es fijo, los colores del tema se eligen solos segun la barra:
si el fondo es claro, el texto y los iconos pasan a oscuros (`auto_contrast`), asi
que tambien se lee bien con el tema claro de Windows.

Si preferis el metodo clasico (mezclar el chip contra un color muestreado de la
barra, sin alpha real), `"bg_mode": "opaque"` en `config.json`.


## Mover el widget por la barra

Se arrastra con el boton izquierdo desde cualquier parte que no sea un boton
(sobre el titulo o la caratula). Mientras se arrastra el cursor cambia a ↔.
Tambien esta el menu: *Mover a la izquierda*, *Mover a la derecha* (20 px por
vez), *Centrar en la barra* y *Volver al extremo derecho*. La posicion se guarda
en `config.json` (`position_frac`) y se respeta al arrancar.

El widget reserva su espacio dentro del tramo libre de la barra (entre la lista
de tareas y el bloque de la bandeja) y le pide a la lista de tareas el ancho que
corresponda, asi que se mueve **junto con** los botones, no por encima.

Dos cosas que Windows impone y conviene saber:

- **La lista de tareas tiene un ancho minimo propio.** Si la dejariamos mas
  angosta de lo que Windows tolera (~500 px con 10 ventanas abiertas), Windows la
  estira sola — y esa lista estirada **tapa** el widget. El widget no adivina ese
  minimo: cuando lo detecta, busca por biseccion la posicion libre mas cercana y
  la usa como limite. O sea que el recorrido real es *desde donde la lista de
  tareas conserva su espacio* hasta el borde del bloque de la bandeja: unos 450 px
  de recorrido en 1920x1080, mas si tenes pocas ventanas abiertas.
- **No se puede quedar por encima de la lista de tareas.** Una ventana hija de la
  barra nace debajo de esa lista, y aunque se la suba con `HWND_TOP`, explorer la
  vuelve a poner arriba en cuanto se toca la barra. Por eso la posicion siempre se
  elige de forma que la lista de tareas no lo tape: es preferible respetar la
  esquina que quedar invisible.

Si el widget queda en el medio, el tramo entre el y el bloque de la bandeja queda
como fondo de barra vacio. Es el precio de poder moverlo; *Volver al extremo
derecho* deja la barra prolija otra vez.


## Atrasar y adelantar

Tres formas, todas por SMTC (o sea, sirven con cualquier reproductor que respete
el sistema, igual que los botones):

- **Clic en la barra de progreso**: salta a esa parte del tema. La zona clicable
  es una franja mas alta que la barra (que mide 2,5 px, imposible de acertar) y
  termina donde empiezan los botones; al pasar el mouse la barra se engrosa.
- **Arrastrar sobre la barra**: mientras se arrastra muestra a donde va a saltar
  (el renglon del artista pasa a decir `2:35 / 4:20`) y recien manda el salto al
  soltar. Si te arrepentis, no hay salto: soltar fuera del widget o abortar el
  arrastre no toca la reproduccion.
- **Rueda del mouse** sobre el widget: adelanta o atrasa `seek_step_s` segundos
  (10 por defecto). El menu contextual tiene los mismos dos items.

Detalles que costaron encontrar:

- **La API de salto pide enteros, no tiempos.** `try_change_playback_position_async`
  espera **ticks de 100 ns** (`int`): pasarle un `timedelta` —que es lo que
  devuelve el timeline al leer— explota con `TypeError`. Y el techo real lo da el
  propio timeline: `min_seek_time` / `max_seek_time`.
- **El reproductor informa la posicion con atraso.** Justo despues de un salto
  puede seguir informando la posicion vieja (medido: ~1 s en YouTube via Brave).
  Si se adoptara ese reporte, la barra volveria sola y despues saltaria de nuevo.
  Por eso hay una *ventana de gracia*: durante 2 s despues de un salto pedido por
  el usuario se ignora un reporte que no coincida con la posicion esperada. El
  ancla local, ademas, se mueve al instante (de forma optimista) para que la barra
  no rebote.
- **Un stream en vivo no admite saltos** (no tiene fin): ahi la barra no se
  dibuja y el clic no hace nada. Los botones siguen funcionando igual.
- **Con el fondo transparente, Windows decide el mouse por el alfa de cada pixel.**
  Las zonas vacias del widget (los huecos entre iconos, el espacio libre) se
  volvian "agujeros": `WindowFromPoint` devolvia `Shell_TrayWnd` y el clic, la
  rueda y el arrastre se los quedaba la barra de tareas. Se arregla con un piso de
  alfa de 2/255 por pixel (`hit_alpha_floor`), invisible (0,8% de mezcla) pero
  suficiente para que toda la superficie reciba el mouse. Medido: la
  transparencia del fondo sigue dando 0,00 de diferencia contra la barra pelada.
- **La barra dibujada y la clicable tienen que terminar en el mismo lugar.** Si la
  barra corre por debajo de los botones (como corria antes, hasta el borde
  derecho), el clic cae en una x y el indicador aparece en otra: se clickea al 50%
  y salta al 60%. Ahora las dos terminan donde empiezan los botones.


## Ondas de sonido

Opcional, apagado por defecto. Clic derecho sobre el widget > *Ondas de sonido*, o
`"show_waves": true` en `config.json`. Son unas barras redondeadas que bailan entre
el texto y los botones:

- **Bailan solo cuando hay musica**: en pausa quedan planas y apagadas (no siguen
  saltando de adorno), y sin reproduccion ni se dibujan.
- **El texto se recorta antes de llegar**: el titulo y el artista dejan la franja
  libre, asi que nunca pasan por debajo de la animacion. Con el widget muy angosto
  las ondas no se dibujan (mejor el texto que el adorno).
- **Cantidad de barras**: `wave_bars` (4 por defecto, hasta 12).

Que son y que no son, para no vender humo: **es una animacion, no un analisis del
audio**. SMTC expone titulo, artista, estado y posicion, pero **no niveles de
sonido**, asi que las alturas se generan con el reloj (cada barra con su frecuencia
y una envolvente lenta encima, para que no se vean como un metronomo). Que la
musica suene o este en pausa si lo sabe, y por eso se comporta distinto. Para que
reaccionen al sonido real habria que capturar el audio del sistema (WASAPI
loopback), que agrega dependencia, permisos y CPU: no entra en este diseno.

### Por que la animacion no cuesta nada

Animar es repintar, y repintar el chip entero cuesta: **4,4 ms por cuadro** medidos
(Pillow en lienzo x3, reduccion LANCZOS, premultiplicado). A 20 cuadros por segundo
eso daria ~9% de un nucleo solo para mover cuatro barras.

La animacion no repinta el chip: el chip completo se dibuja una vez y **se cachea**
(firma sin las ondas), y en cada cuadro solo se dibuja la **tira de las ondas** (24x20
px, a 4x) y se pega encima. Medido: **0,08 ms** copiar la base y pegar la tira, contra
4,4 ms del render completo. Resultado medido en el proceso real: **0,78% de un nucleo**
con las ondas a 20 fps, contra 8,59% repintando todo. Con las ondas apagadas el widget
sigue en ~0% (solo se repinta cuando cambia algo visible).

La frecuencia se puede bajar con `wave_fps` (20 por defecto) si te importa la CPU:
es lo unico que hace que el widget repinte mas seguido que el texto.


## Colores

La barra de progreso y las ondas tienen **su propio color**, independiente del tema.
Se cambian con clic derecho > *Color de la barra* / *Color de las ondas*, que traen
una paleta corta (verde, celeste, violeta, rosa, naranja, amarillo, blanco) y
*Color del tema* para volver al de acento del tema.

Para cualquier otro color, se escribe a mano en `config.json`:

```json
"progress_color": "#56B6FF",
"waves_color": [255, 120, 180]
```

Se acepta `"#RRGGBB"`, `"#RGB"` o `[r, g, b]`, y `null` (por defecto) es *el color
del tema*. Si el color no se entiende, se usa el del tema en vez de fallar.

Dos cosas a tener en cuenta:

- **El auto-contraste no los toca.** Los colores de texto e iconos se adaptan al
  fondo de la barra, pero si vos elegis un color, se usa ese tal cual: uno muy
  oscuro sobre una barra oscura no se va a ver. El menu muestra
  `Personalizado (#RRGGBB)` cuando el color no es de la paleta.
- **El color de la barra** pinta el relleno del progreso, el indicador del arrastre
  y la hora destino que aparece mientras arrastras. **El de las ondas** pinta las
  barras del visualizador (que siguen quedando planas y apagadas en pausa).

Ninguno de los dos cambia el chip, la caratula ni los textos.


## Como funciona

Tres piezas bien separadas:

| Archivo | Responsabilidad |
|---|---|
| `widget/media.py` | Lee el SMTC en un hilo propio con su propio event loop asyncio. Publica una foto inmutable (`MediaState`) y despacha los comandos. |
| `widget/draw.py` | Dibuja el widget con Pillow en un lienzo ampliado x3 y lo reduce con LANCZOS: asi los bordes redondeados, los iconos vectoriales y el texto salen suaves sin depender de GDI+ ni de un framework de UI. Con el fondo transparente la reduccion se hace en espacio premultiplicado, para que no quede un halo oscuro en los bordes. Las ondas de sonido se dibujan aparte, en su propia tira, para poder animarlas sin repintar el chip. |
| `widget/app.py` + `taskbarwin.py` | Ventana Win32, superficie de doble buffer (DIB + `BitBlt`, o en capas con `UpdateLayeredWindow` cuando el fondo es transparente), entrada de mouse, arrastre, anclaje y posicion en la barra. |

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
- **El color de fondo se muestrea solo en modo opaco**: en `bg_mode: "opaque"` el
  chip es levemente translucido, asi que se lee el color real de la barra con
  `GetPixel` y se mezcla ahi. En `layered` (por defecto) no hay nada que muestrear:
  la transparencia se resuelve con el alfa de cada pixel.
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
de 3 minutos, asi que no tiene sentido repintar 10 veces por segundo. Con las ondas
de sonido encendidas hay **dos firmas**: la del chip (sin las alturas) cachea el
dibujo completo, y la animacion solo vuelve a dibujar y pegar su tira. Medido:
0,78% de un nucleo a 20 cuadros por segundo, contra 8,59% si se repintara todo.


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

49 de 49 pruebas pasan (`python tools\selftest.py` con el widget en marcha):
anclaje, reconstruccion forzada, recuperacion de espacio, pixeles realmente
pintados, transparencia del fondo medida contra la barra, recorrido completo del
movimiento (que nunca quede tapado), la barra de progreso (que su zona clicable
no pise los botones, que el arrastre llegue al destino y muestre la hora, que al
abortar no se mande ningun salto), que el widget reciba el mouse en toda su
superficie con el fondo transparente, las ondas de sonido (que su franja entre
entre el texto y los botones, que apagadas no pinten nada, que encendidas cambien
de cuadro —8 de 8 distintos— que el texto quede recortado antes y que las barras
no se salgan de su franja), los colores elegidos (que se entiendan en hex, lista y
corto; que la barra tome el suyo —medido en rojo puro— que las ondas tomen el suyo
—medido en azul— y que ninguno tome el del otro) y 30 muestras de vigilancia del
pintado (30/30 cuadros correctos). Y 12 de 12 de interaccion real
(`python tools\clicktest.py`): el hover ilumina los tres botones, un clic de verdad
cambia el estado de reproduccion, el segundo clic lo restaura, un clic en la
caratula no dispara nada, un clic en la barra de progreso salta a esa posicion
(medido: pedido 157 s, informado 157 s) sin mover el widget, el salto se puede
devolver a donde estaba, y la rueda adelanta y atrasa el paso configurado
(medido: -9,9 s para un paso de -10 s).

En `clicktest.py`, si una lista de reproduccion cambia de tema justo mientras se
mide, el comando se pierde y la prueba lo informa como `SALTA` (interferencia) en
vez de inventar un fallo que no existe.

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
| `min_tasklist_free` | 140 | Piso de la lista de tareas cuando el widget se mueve libre (el limite real lo descubre el propio widget) |
| `seek_step_s` | 10 | Cuantos segundos adelanta/atrasa la rueda del mouse y el menu. La barra de progreso se puede clickear en cualquier caso |
| `hit_alpha_floor` | 2 | Alfa minimo por pixel en modo transparente, para que toda la superficie reciba el mouse (invisible; 0 lo desactiva, pero con el fondo sin nada los huecos se vuelven "agujeros" y los clics van a la barra de tareas) |
| `show_waves` | false | Ondas de sonido animadas entre el texto y los botones (menu > *Ondas de sonido*) |
| `wave_bars` | 4 | Cuantas barras tienen las ondas (1 a 12) |
| `wave_fps` | 20 | Cuadros por segundo de la animacion. El unico motivo por el que el widget repinta mas seguido que el texto |
| `progress_color` | `null` | Color de la barra de progreso (relleno, indicador de arrastre y hora destino). `null` = el del tema; tambien `"#RRGGBB"` o `[r, g, b]` |
| `waves_color` | `null` | Color de las ondas de sonido. Mismas formas que `progress_color` |
| `position_frac` | `null` | `null` = pegado al extremo derecho. `0..1` = posicion libre dentro del tramo util |
| `drag_to_move` | true | Permite moverlo arrastrando con el boton izquierdo |
| `chip_alpha` | 232 | Transparencia del fondo: 232 solido, 170 translucido, 100 muy transparente, 0 sin fondo |
| `bg_mode` | `"layered"` | `"layered"` = alpha real con `UpdateLayeredWindow`; `"opaque"` = mezcla contra el color muestreado de la barra |
| `auto_contrast` | true | Elige texto e iconos claros u oscuros segun el color de la barra |
| `poll_interval_ms` | 500 | Cada cuanto se consulta el SMTC |
| `timer_playing_ms` / `timer_idle_ms` | 100 / 500 | Cada cuanto se revisa si hay que redibujar |
| `marquee_speed` / `marquee_gap` | 32 / 40 | Velocidad y separacion del bucle del titulo |
| `supersample` | 3 | Factor de suavizado. Bajalo a 2 si te importa la CPU |
| `show_art` / `show_controls` / `show_progress` | true | Que elementos se dibujan |
| `corner_radius` / `chip_alpha` | 7 / 232 | Forma y transparencia del chip |
| `theme` | ver archivo | Colores del chip, borde, textos, acento, pista e iconos |
| `right_click_menu` / `log_file` | true / `widget.log` | Menu contextual y archivo de log |

Si te gusta mas ancho o mas angosto: clic derecho sobre el widget > *Más ancho* /
*Más angosto*. Y el fondo, en el submenu *Fondo*.


## Herramientas de desarrollo

```bash
python main.py --no-embed        # ventana flotante, sin tocar la barra
python main.py --diagnose        # ver que esta leyendo del SMTC
python main.py --diagnose --cmd next   # probar un comando contra el reproductor
python main.py --diagnose --seek 120   # probar un salto y ver cuanto se movio
python main.py --shot prev.png   # volcar el widget a un PNG
python main.py --shot s.png --scrub 210   # como se ve el arrastre de la barra
python main.py --shot w.png --waves       # como se ven las ondas de sonido
python tools\watch.py            # estado en vivo, muestreado cada 0,5 s
python tools\preview.py hoja.png # hoja con todas las variantes visuales
python tools\selftest.py         # suite de verificacion (widget en marcha)
python tools\clicktest.py        # prueba de clic real con el mouse (restaura el estado)
python tools\startup.py --status # ver si el arranque automatico esta activo
python tools\stop.py             # cierre ordenado
python tools\debug_mouse.vbs     # arranca con cada mensaje de mouse anotado en el log
python tools\testrig.py          # banco de pruebas: reproductor simulado con 3 pistas
```

Para depurar la entrada de mouse, arrancar con `tools\debug_mouse.vbs`: cada
`WM_MOUSEMOVE`, `WM_LBUTTONDOWN` y `WM_LBUTTONUP` queda anotado en `widget.log`
con sus coordenadas, que devolvio el analisis de zonas (`hit`) y si el punto cae
dentro de la franja de la barra.

`testrig.py` es el mas util para desarrollar: levanta un reproductor falso en
`http://127.0.0.1:8765/` con tres pistas, caratulas distintas y los manejadores
de play / pause / next / prev / **seekto**, asi se prueba todo el circuito
—incluido el salto de posicion— sin depender de Spotify ni de YouTube. La pista
actual y la posicion quedan en `tools/_rig_state.json` para poder comprobar desde
afuera que un clic realmente cambio de tema o movio la reproduccion.


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
- El recorrido del movimiento depende de cuantas ventanas tengas abiertas: cuanto
  mas angosta necesite ser la lista de tareas, mas a la derecha empieza el tramo
  donde el widget puede vivir. Con pocas ventanas el recorrido es mas largo.
- Si el widget queda en el medio, el tramo que queda entre el y el bloque de la
  bandeja es fondo de barra vacio (no hay forma de partirlo: la lista de tareas es
  una sola ventana del sistema).
- La caratula la entrega el reproductor ya reducida (YouTube via Edge da 150x150,
  Spotify da 300x300), asi que en pantallas con escalado alto puede verse algo
  blanda: se muestran a 32 px logicos, no hace falta mas.
