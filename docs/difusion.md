# Como darle visibilidad

Notas para el autor (no para quien entra al repo). Lo que ya esta y lo que falta.

## Lo que ya esta hecho

- Repo **publico**, con descripcion, 7 topics, licencia MIT y el release **v1.0.0** con los
  dos adjuntos (portatil + instalador).
- README con **GIF animado**, distintivos (version, descargas, licencia, plataforma) y un
  **resumen en ingles** para el que no lee castellano.
- Paquete de **winget** listo en `winget/manifests/...` (con el SHA256 del archivo publicado).

## 1. Dos clics que solo podes hacer vos

**Imagen social**: GitHub → Settings → **Social preview** → subir `assets/social.png`.
Es la que aparece cuando alguien pega el link en Discord, WhatsApp, X o Reddit: sin eso,
queda un cuadro gris y el link se ve flojo.

Esta hecha a medida (1280x640, que es la medida que pide GitHub), con el estilo de la app:
el icono, el violeta de acento, la tipografia del widget y un **render real** del widget
sobre una franja que simula la barra de tareas. Se regenera con
`python tools/make_social_card.py` (por si cambia el nombre, el color o la frase).

**Pagina web del repo**: ya la puse apuntando al release, pero conviene revisarla en
Settings → General → Website.

## 2. Publicarlo en winget (el canal que trae usuarios solo)

Es lo que hace que alguien escriba `winget search musica` o `winget install
EduardoFleitas.AstraMusicWidget` y lo tenga instalado sin buscar nada raro. Y aparece solo
en sitios que espejan winget (winstall.app, etc.).

Los archivos ya estan en este repo, en `winget/manifests/e/EduardoFleitas/AstraMusicWidget/1.0.0/`.
Para publicarlos:

1. Hacer un **fork** de `microsoft/winget-pkgs`.
2. Copiar la carpeta `winget/manifests/...` dentro del fork, respetando la misma ruta
   (la estructura es `manifests/<letra>/<Publisher>/<Package>/<Version>/`).
3. Abrir un **Pull Request** titulado:
   `New package: EduardoFleitas.AstraMusicWidget version 1.0.0`
4. El robot de winget valida el paquete (que la URL baje, que el hash coincida, que se
   instale en silencio). Tarda unos dias y suele pedir algun ajuste menor.

En cada version nueva: subir el release **y** mandar otro PR con el manifest nuevo (dos
minutos: cambiar la version, la URL y el SHA256).

## 3. Donde publicarlo (con el texto listo)

Regla de oro: **decilo que sos el autor** en el primer renglon y **no pegues el mismo texto
en cinco lugares el mismo dia**. Un solo lugar bien elegido rinde mas que cinco a medias.

**r/Windows11** (y r/Windows10) — el publico exacto. Con el GIF y una captura:

> Hice un widget de musica que vive dentro de la barra de tareas: caratula, titulo,
> controles y el volumen de la app que suena. Anda con Spotify, VLC o lo que suene en el
> navegador (lee la sesion de multimedia de Windows, sin plugins). Es gratis y MIT.
> Lo dejo aca: [link]

**r/Python** — el angulo tecnico, que es el que le interesa a esa comunidad:

> Escribi un widget de Windows en Python sin frameworks de UI: Win32 con pywin32,
> UpdateLayeredWindow para la transparencia real, la via de audio de Windows por ctypes
> para el volumen de la app y la sesion de multimedia (SMTC) para saber que suena.
> Lo que mas me costo: el alpha por pixel decide que ventana recibe el mouse.
> Codigo y explicacion: [link]

**r/software**, **r/coolgithubprojects**, **r/SideProject** — "acabo de publicar".

**Hacker News** (Show HN) — si escribis un post tecnico (ver el punto 5). Es loteria, pero
es donde un proyecto chico de Windows puede aparecer de golpe.

**alternativeto.net** — agregarlo como alternativa a Wallpaper Engine / Rainmeter.

**itch.io** — si queres una vidriera aparte con "pagá lo que quieras".

## 4. El video de 20 segundos (lo que mas rinde para esta app)

Una grabacion de pantalla: musica sonando, el widget con las ondas moviendose y el panel
abriendose encima de un juego en ventana. **Sin hablar**, sin editar, sin musica de fondo.
Eso es lo que se comparte en X, TikTok, Shorts y en los mismos subreddits.

## 5. El post tecnico (el que trae enlaces de verdad)

La historia que hay detras de este proyecto da para un texto lindo, porque casi todo lo
aprendido esta medido y documentado en el skill del repo:

- Incrustar una ventana en la barra de tareas de Windows 10 (y por que en 11 no se puede,
  y como lo resuelve el modo flotante).
- El alpha por pixel decide **que ventana recibe el mouse**: sin piso de alfa, los huecos
  del fondo transparente se los queda la ventana de atras.
- Volumen por aplicacion hablando con la via de audio de Windows directamente por ctypes.
- Que se puede y que no con la sesion de multimedia (SMTC): por que las ondas son una
  animacion y no un analisis de audio.

Publicarlo en un blog o en un gist y mandarlo a HN / r/programming con el link al repo.

## 6. Expectativas honestas

Es una utilidad de escritorio, no un juego: no se hace viral. Lo realista es que, si un post
pega en una comunidad, entren unos cientos de descargas y unas decenas de estrellas. Lo que
si cambia el numero es estar en **winget** (te encuentran sin que los busques) y tener el
**GIF** (es lo que hace que alguien se quede los primeros cinco segundos).
