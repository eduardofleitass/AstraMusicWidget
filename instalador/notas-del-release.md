# Astra-Music-widget 1.2.1

Widget de musica que vive **dentro** de la barra de tareas de Windows: muestra lo que esta
sonando (caratula, titulo, artista, barra de progreso clicable, controles y el volumen de
la app) sin abrir ninguna ventana aparte. Anda con cualquier reproductor que respete el
sistema (Spotify, VLC, Groove, y lo que suene en Chrome/Edge/Brave), porque lee la sesion
de multimedia de Windows, no un reproductor en particular.

## Novedades de esta version

- **Icono nuevo.** El anterior era un ecualizador de cuatro barras sobre un cuadrado oscuro:
  se veia como cualquier app de audio y no decia nada del nombre. Ahora es una **estrella
  astral con la onda de sonido** debajo, en violeta sobre degradado oscuro: *Astra* (el
  astro) y *Music* (la onda) en una sola silueta que se sigue leyendo en la barra de tareas
  a 24 y 16 px. Se aplica al ejecutable, al instalador y a los accesos directos.
- Los cuatro disenos que se evaluaron (nota estelar, estrella con onda, constelacion y halo
  astral) quedan en `tools/iconos_astra.py`, y el icono se regenera con
  `tools/make_icon.py --elegido N`.

## Lo de la 1.2.0, que sigue valiendo

- **Seccion de donaciones, opcional y sin molestar.** El programa sigue siendo gratis y
  completo: nada se bloquea ni se degrada si no donas. Hay tres lugares donde aparece el
  link de PayPal, y ninguno interrumpe:
    * el menu contextual, en *Apoyar el proyecto...*;
    * una seccion nueva en la ventana de Ajustes (*Apoyar*), con el QR para escanear desde
      el telefono;
    * el instalador, con una casilla **destildada** que, si la tildas, abre la pagina al
      terminar.
- **Recordatorio medido, estilo "apoya el proyecto" y no estilo WinRAR.** Aparece recien
  despues de 7 dias de uso (o 20 arranques), como maximo 3 veces en la vida y nunca mas de
  una vez cada 30 dias. Tiene *Donar*, *Ahora no* y *No volver a mostrar*; esta ultima se
  respeta para siempre. No bloquea el arranque (el widget se dibuja primero y el cartel
  sale 8 segundos despues), no aparece en modo gaming y no sale si el widget esta oculto.
- **El link y el QR salen de la configuracion** (`donation_link` en `config.json`), asi que
  se puede cambiar sin recompilar.

## Lo de la 1.1.0, que sigue valiendo

- **Ventana de Ajustes.** Clic derecho -> *Ajustes...* abre una ventana propia, con la
  **vista previa del widget arriba** y todo lo que antes habia que buscar en submenus, con
  controles de verdad: deslizadores de opacidad y ancho, botones de fondo, muestras de color,
  interruptores, la lista de monitores y los atajos. Cada cambio se ve en el momento en la
  vista previa. Cuatro secciones: Apariencia, Posicion, Panel y Atajos. Los deslizadores
  aplican al mover y guardan al soltar, para no escribir la configuracion en cada pixel.
- **El menu contextual paso de 15 filas a 6**: *Ocultar/Mostrar*, *Panel*, *Apariencia*,
  *Posicion*, *Ajustes...* y *Salir*. Lo fino (fondos, opacidades, colores, ancho) vive
  adentro de *Apariencia* y *Posicion*; el ancho dejo de ser una fila apagada que no hacia
  nada y ahora es *Mas ancho* / *Mas angosto* / *Restablecer*.
- **La ventana de Ajustes va en morado** sobre fondo oscuro: barras, contornos de botones e
  interruptores. Los colores salen de una sola tabla (`PALETA` en `widget/ajustes.py`), asi
  que se cambian en un lugar.
- **Las dos ventanas no se pisan**: si Ajustes esta abierta y abris el panel (o al reves), la
  otra se cierra sola. Antes quedaban encimadas en el mismo lugar y los clics caian en la
  ventana equivocada.

## Arreglos de esta version

- **Elegir monitor ahora mueve el widget.** En el modo de Windows 11 la opcion se tildaba y
  se guardaba, pero la ventana no se movia (ni al arrancar se respetaba): el widget flotante
  pedia siempre el monitor principal. Ahora se mueve, y arrastrarlo de un monitor a otro
  queda guardado.
- **"Fondo del widget" volvio a mandar sobre el fondo del widget.** El submenu estaba armado
  con la variable de la opacidad del panel, asi que elejia el nivel del panel y el fondo del
  widget quedaba como un control muerto.
- **El altavoz (volumen de la app) funciona.** No hacia nada con las apps que no informan el
  nombre del ejecutable con extension (Brave manda `Brave`, la sesion de audio es
  `brave.exe`): ahora se comparan sin `.exe`. Con eso andan la rueda, el clic de silencio y
  la barra de volumen del panel.
- **La portada en la vista previa se ve como en la barra.** Se pedia la caratula a un tercio
  del tamano y aparecia como una tapita con un marco oscuro alrededor.
- **El muestrario "acento" de la ventana de Ajustes muestra el color real de Windows**, no el
  morado de la ventana.

## Como se probo

Regresion completa sobre el ejecutable: 114/126 del banco general (las 12 saltadas son las
pruebas de incrustar en la barra de Windows 10, que necesitan esa version), 35/37 de las
pruebas de mouse real (2 saltadas por interferencia), 80/80 de la regresion sin pantalla y
el contrato de monitores entero. Sin fallas.

## Una aclaracion sobre los atajos (Ctrl+Alt+flechas)

Los drivers de video suelen tomar la familia `Ctrl+Alt+flecha` (es el atajo de girar la
pantalla). Medido en Windows 11 en un equipo que las tiene tomadas: `Ctrl+Alt+P` anda,
`Ctrl+Alt+↑` (volumen) tambien, y **`Ctrl+Alt+Shift+↑/↓` (±10 s) no llega al programa** —
Windows entrega el atajo de volumen, que comparte la flecha. No es del widget: pasa igual con
cualquier programa (probado registrando esa combinacion sola en una ventana de prueba). Si te
toca, el ±10 s esta en la **rueda del mouse** (`Ctrl` = 1 s, `Shift` = 60 s, sola = 10 s) y en
la **barra de progreso**, y las teclas se cambian en `widget/app.py` → tabla `HOTKEYS`.

## Lo de las versiones anteriores, que sigue valiendo

- **Los botones no tienen columnas muertas.** Las zonas clicables de anterior / play /
  siguiente se calculaban redondeando los dos bordes de cada celda por separado, y en una
  barra de tareas de 48 px (Windows 11) quedaba una columna de 1 px sin dueno donde el clic no
  hacia nada. Ahora cada celda empieza exactamente donde termina la anterior (verificado a 40,
  48, 50 y 60 px de barra).
- **Con el fondo en *Sin fondo* y el color del widget tomado de Windows, el texto se lee.** El
  juego de colores (claro u oscuro) se elegia por el color del sistema aunque el fondo no se
  dibujara, asi que sobre una barra de tareas clara quedaba texto claro (contraste 5, medido).
  Ahora la eleccion mira el color del chip cuando el chip se dibuja, y lo que hay detras de la
  barra cuando no. Lo mismo para el panel: con su fondo en 0, el texto sigue a lo que tenga
  atras (sobre un juego claro, texto oscuro).
- **El fondo del widget se puede poner del color de Windows**: menu → *Color del widget* →
  *Del tema de Windows*. Toma el color con el que el sistema tiñe la barra de tareas y los
  bordes (el de Ajustes → Personalizacion → Colores; se lee de Windows, no hay que copiarlo a
  mano), asi el widget se ve como parte de la barra. Al lado quedan *Claro* y *Oscuro* para
  forzarlo sin mirar el fondo, y *Automatico*, que es lo que hacia antes (tema claro si lo que
  hay detras es claro).
- **Opacidad de todo el widget**: menu → *Opacidad de todo el widget* (todo nitido / leve /
  translucido / muy transparente). Es distinto de *Fondo del widget*: aquel decide cuanto se ve
  la barra a traves del chip, y este apaga tambien el texto y la caratula, como ya hacia el
  panel. Combinado con *Sin fondo* deja el widget flotando sobre la barra sin caja.
- **Las ondas de sonido ya no congelan el widget en Windows 11.** Con las ondas encendidas, el
  widget se quedaba clavado: seguia corriendo, pero no volvia a dibujarse, asi que el menu
  parecia no hacer nada. La tira de las ondas se pegaba sobre una franja calculada con dos
  cuentas distintas y, con la barra de tareas de 48 px, no caian en el mismo pixel.
- **Los clics en la barra de progreso caen donde uno hace clic** (antes, con la barra de 48 px,
  el final de la barra saltaba al 72% del tema).
- **En Windows 11 ahora se ve.** En esa version el programa arrancaba, el log decia que habia
  arrancado y en pantalla no habia nada: la barra de Windows 11 (24H2/25H2) **sigue teniendo**
  el `ReBarWindow32` y el reloj de siempre, asi que la comprobacion "aca se puede incrustar"
  daba que si, el widget se creaba **dentro** de la barra y Windows 11, que dibuja la barra por
  su cuenta, no lo pintaba nunca. Ahora la comprobacion mira la estructura real de la barra y
  el widget pasa solo al **modo flotante**, que es el que se ve. Medido y arreglado en la build
  26300.
- **El log dice por que**: cuando el widget arranca en modo flotante, el motivo queda escrito
  en `astra-widget.log`, ademas del cartel de error que ya habia.
- **Si el programa no puede arrancar, lo dice**: aparece un cartel con la causa y el detalle
  queda escrito en el log. Antes, cualquier fallo de arranque era invisible (el ejecutable no
  tiene consola) y el programa parecia "no hacer nada".
- **Si ya hay otra copia corriendo y no se la puede traer al frente, tambien avisa**: antes el
  segundo intento salia en silencio total, asi que parecia que el programa estaba roto.
- Si la **barra de tareas no esta abajo** (a un costado o arriba del monitor), el widget pasa
  solo al **modo flotante**, que no le toca la barra. La decision se toma **midiendo** el
  rectangulo de la barra contra el del monitor, asi que no depende de la version ni del idioma
  de Windows.

## Si no arranca (para diagnosticar)

1. Abrir una consola en la carpeta del programa y correr:
   `Astra-Music-widget.exe --diagnose`
   Si aparece texto con el estado del reproductor, el programa funciona y el problema es de
   pantalla. Si **no aparece nada**, algo lo esta frenando fuera del programa.
2. Mirar si se creo `astra-widget.log` al lado del ejecutable (o en la carpeta de instalacion).
   Ahi dice que paso, con fecha y hora: incluye el modo que eligio y por que.
3. Si el archivo ni se creo, revisar **Seguridad de Windows → Proteccion contra virus y
   amenazas → Historial de proteccion**: Windows puede estar bloqueando un ejecutable sin
   firma digital bajado de internet (elegir "Permitir en el dispositivo"). El primer arranque
   de un ejecutable recien bajado tambien puede tardar: Windows lo esta revisando.

## Que se puede hacer

- **La barra**: play/pausa, siguiente y anterior, atrasar y adelantar (clic en la barra o
  rueda del mouse, con `Ctrl` de a 1 s y con `Shift` de a 60 s), y el **volumen de la app**
  en la celda del altavoz (clic = silenciar, rueda = 5%, arrastrar = nivel exacto).
- **Moverlo**: se arrastra a cualquier parte del tramo libre de la barra, o se manda a la
  barra de otro monitor.
- **Personalizarlo**: color de la barra de progreso y de las ondas, ancho, fondo (de
  solido a *sin fondo* de verdad) y ondas de sonido animadas.
- **El panel** (clic en la caratula): caratula grande, titulo, artista, album, tiempos,
  transporte y volumen, en tres tamaños (normal, chico y tira fina de una sola fila).
  Con el modo gaming no le roba el foco al juego, se queda fijo donde lo dejes y puede
  dejar pasar los clics.
- **Atajos globales**: `Ctrl+Alt+P` play/pausa, flechas siguiente y anterior, `+`/`-`
  volumen, `Ctrl+Alt+Shift+flechas` para adelantar y atrasar, `Ctrl+Alt+O` el panel y
  `Ctrl+Alt+M` para ocultarlo (y volver a mostrarlo).

## Como se instala

Dos opciones, las dos sin Python. Los dos links son fijos (siempre la ultima version):

- **Instalador** ([`Astra-Music-widget-setup.exe`](https://github.com/eduardofleitass/AstraMusicWidget/releases/latest/download/Astra-Music-widget-setup.exe),
  30 MB): instala por usuario en `%LOCALAPPDATA%\Programs\Astra-Music-widget`, crea los
  accesos del menu Inicio y el arranque con Windows, y deja un desinstalador en Ajustes →
  Aplicaciones. No pide administrador.
- **Portatil** ([`Astra-Music-widget.exe`](https://github.com/eduardofleitass/AstraMusicWidget/releases/latest/download/Astra-Music-widget.exe),
  28 MB): un solo archivo, se copia donde quieras y se ejecuta. Guarda su `config.json` y su
  log **al lado del ejecutable**.

En la release quedan ademas las copias con el numero en el nombre
(`Astra-Music-widget-1.0.9-setup.exe`), por si hace falta quedarse en una version puntual: las
versiones anteriores no se borran nunca.

> **Windows va a avisar**: sin firma digital, SmartScreen muestra "Windows protegio tu PC"
> la primera vez. Es el *Mas informacion* → *Ejecutar de todas formas*.

## Requisitos y detalles

- Windows 10 1809 o posterior. En **Windows 11** la barra nueva no admite ventanas propias,
  asi que ahi el widget se dibuja como una **tira propia** pegada al borde de abajo (mismo
  dibujo, mismos clics, mismos atajos; se mueve a lo largo de la franja y se acuerda donde
  lo dejaste). Lo comprueba solo al arrancar, mirando la estructura de la barra.
- Verificado en: **Windows 10 22H2 (build 19045)** con el widget incrustado en la barra, y
  **Windows 11 24H2/25H2 (build 26300)** en modo flotante. El mismo ejecutable sirve para los
  dos: el modo se elige al arrancar, midiendo la barra.
- Para correrlo desde el codigo: Python 3.11 (`setup.bat` arma el entorno).

## Licencia

MIT: usalo, copialo, modificalo o vendelo si queres, manteniendo el aviso de copyright.
El autor sigue siendo el dueño del codigo y el programa se entrega sin garantia.


## Lo que no hace

- **Sobre un juego en pantalla completa exclusiva no se puede dibujar encima** (Windows le
  entrega la pantalla al juego). Sobre juegos en ventana o pantalla completa sin bordes, si:
  para eso esta el modo gaming del panel.
- Las **ondas son una animacion**, no un analisis de audio: Windows no expone los niveles
  por la via que usa el widget. Esta dicho en la documentacion para no vender humo.
- No se puede mostrar en **dos barras a la vez** (vive en una por vez; se cambia de monitor
  desde el menu).
