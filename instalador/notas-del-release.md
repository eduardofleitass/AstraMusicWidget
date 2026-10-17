# Astra-Music-widget 1.0.2

Widget de musica que vive **dentro** de la barra de tareas de Windows: muestra lo que esta
sonando (caratula, titulo, artista, barra de progreso clicable, controles y el volumen de
la app) sin abrir ninguna ventana aparte. Anda con cualquier reproductor que respete el
sistema (Spotify, VLC, Groove, y lo que suene en Chrome/Edge/Brave), porque lee la sesion
de multimedia de Windows, no un reproductor en particular.

## Novedades de esta version

- **Ahora, si el programa no puede arrancar, lo dice**: aparece un cartel con la causa y el
  detalle queda escrito en el log. Antes, cualquier fallo de arranque era invisible (el
  ejecutable no tiene consola) y el programa parecia "no hacer nada". Esa mejora vale para
  todas las versiones, pero no podia faltar antes de que lo pruebe gente en otras maquinas.
- **Si ya hay otra copia corriendo y no se la puede traer al frente, tambien avisa**: antes el
  segundo intento salia en silencio total, asi que parecia que el programa estaba roto.

Lo de la version anterior, que sigue valiendo:

- Si la **barra de tareas no esta abajo** (a un costado o arriba del monitor), el widget ya no
  intenta incrustarse ahi: pasa solo al **modo flotante**, que no le toca la barra. La decision
  se toma **midiendo** el rectangulo de la barra contra el del monitor, asi que no depende de
  la version ni del idioma de Windows.

## Si no arranca (para diagnosticar)

1. Abrir una consola en la carpeta del programa y correr:
   `Astra-Music-widget.exe --diagnose`
   Si aparece texto con el estado del reproductor, el programa funciona y el problema es de
   pantalla. Si **no aparece nada**, algo lo esta frenando fuera del programa.
2. Mirar si se creo `astra-widget.log` al lado del ejecutable (o en la carpeta de instalacion).
   Ahi dice que paso, con fecha y hora.
3. Si el archivo ni se creo, revisar **Seguridad de Windows → Proteccion contra virus y
   amenazas → Historial de proteccion**: Windows puede estar bloqueando un ejecutable sin
   firma digital bajado de internet (elegir "Permitir en el dispositivo").

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

Dos opciones, las dos sin Python:

- **Instalador** (`Astra-Music-widget-1.0.2-setup.exe`, 30 MB): instala por usuario en
  `%LOCALAPPDATA%\Programs\Astra-Music-widget`, crea los accesos del menu Inicio y el
  arranque con Windows, y deja un desinstalador en Ajustes → Aplicaciones. No pide
  administrador.
- **Portatil** (`Astra-Music-widget.exe`, 28 MB): un solo archivo, se copia donde quieras
  y se ejecuta. Guarda su `config.json` y su log **al lado del ejecutable**.

> **Windows va a avisar**: sin firma digital, SmartScreen muestra "Windows protegio tu PC"
> la primera vez. Es el *Mas informacion* → *Ejecutar de todas formas*.

## Requisitos y detalles

- Windows 10 1809 o posterior. En **Windows 11** la barra ya no permite incrustar ventanas,
  asi que ahi el widget se dibuja como una **tira propia** pegada al borde de abajo (mismo
  dibujo, mismos clics, mismos atajos; se mueve a lo largo de la franja y se acuerda donde
  lo dejaste).
- Para correrlo desde el codigo: Python 3.11 (`setup.bat` arma el entorno).

## Licencia

MIT: usalo, copialo, modificalo o vendelo si queres, manteniendo el aviso de copyright.
El autor sigue siendo el dueño del codigo y el programa se entrega sin garantia.


## Lo que no hace

- **Sobre un juego en pantalla completa exclusiva no se puede dibujar encima** (Windows le
  entrega la pantalla al juego). Sobre juegos en ventana o pantalla completa sin bordes,
  si: para eso esta el modo gaming del panel.
- Las **ondas son una animacion**, no un analisis de audio: Windows no expone los niveles
  por la via que usa el widget. Esta dicho en la documentacion para no vender humo.
- No se puede mostrar en **dos barras a la vez** (vive en una por vez; se cambia de monitor
  desde el menu).
