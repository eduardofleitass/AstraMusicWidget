# Kit de difusion

Notas para el autor. Lo que ya esta hecho, el orden en que conviene moverse, y los textos
listos para pegar.

---

## Lo que ya esta hecho

- Repo publico con **descripcion, 7 topics, pagina web apuntando al release y licencia MIT**.
- **Links de descarga fijos** (no cambian con la version): el README apunta a
  `releases/latest/download/Astra-Music-widget-setup.exe` y `.../Astra-Music-widget.exe`.
  Cada release sube ademas una copia con nombre fijo; lo hace `tools\release.py`.
- Release **v1.0.7** con los tres adjuntos (portatil de 28,7 MB, instalador de 30,4 MB y la
  copia del instalador con nombre fijo). Verificado con las suites: el .exe publicado da
  115/119 con 4 saltadas (nada sonando) en Windows 10, y el modo flotante 16/16.
- README con **GIF animado**, distintivos (version, descargas, licencia), link de descarga
  arriba de todo y un **resumen en ingles**.
- Tarjeta social **a medida** en `assets/social.png` (1280x640), lista para subir.
- Paquete de **winget** en `winget/manifests/...` y el PR **#454943** abierto en
  `microsoft/winget-pkgs` (lo unico que falta ahi es firmar el CLA, ver abajo).

---

## El orden importa

### Paso 1 — La imagen social (2 clics, 30 segundos)

GitHub → **Settings** → **Social preview** → subir `assets/social.png`.

No es cosmetico: **cada vez que alguien pegue el link** en Discord, WhatsApp, X, Reddit o
un grupo, se ve esa imagen o un cuadro gris. Es el multiplicador de todo lo demas.

### Paso 2 — Publicarlo en winget (el canal que trae descargas sin que te busquen)

Ya esta hecho y automatizado: `python tools\winget_pr.py` escribe el manifiesto en el repo,
lo sube a una rama nueva del fork y abre el PR (el de la 1.0.7 es el **#455490**). La version
sale de `widget/__init__.py` y el SHA se mide bajando el instalador ya publicado en la
release, asi que no hay numeros que copiar a mano.

Lo unico que no resuelve el codigo es el **CLA de Microsoft**: el bot lo pide en un comentario
del PR y hasta que el dueño de la cuenta responda

    @microsoft-github-policy-service agree

el PR no se puede mergear. Es un tramite de una vez por cuenta, y la respuesta es publica (si
el trabajo fuera para un empleador, el texto cambia).

El robot despues valida solo: que la URL baje, que el SHA256 coincida, que se instale en
silencio y que desinstale bien. Tarda unos dias y a veces pide un ajuste menor.

**Por que primero esto y no los posts**: cuando publiques en Reddit, la instruccion mas
fuerte que podes dar es `winget install EduardoFleitas.AstraMusicWidget` (una linea, sin
avisos de SmartScreen, con desinstalador). Un post que dice "bajalo de aca y dale a Mas
informacion" convierte mucho peor.

Y despues aparece solo en los sitios que espejan winget (winstall.app y compania).

### Paso 3 — Un post, bien elegido

Un lugar, un dia. **No pegues el mismo texto en cinco subreddits el mismo dia**: te leen
como spam y te banean. Eleji uno, respondele a todos los comentarios, y si sale bien, tres
o cuatro dias despues publica el siguiente con otro enfoque.

Antes de publicar, revisa que el README abra con el GIF (es lo primero que se ve).

---

## Textos listos para pegar

### r/Windows10 y r/Windows11 — el publico exacto

**Titulo**: `Hice un widget de musica que vive dentro de la barra de tareas (gratis, MIT)`

> Hola. Soy el autor. Hice un widget que muestra lo que esta sonando **dentro** de la barra
> de tareas: caratula, titulo, artista, barra de progreso clicable, controles y el volumen
> de la app.
>
> Anda con cualquier reproductor (Spotify, VLC, y lo que suene en Chrome/Edge/Brave) porque
> lee la sesion de multimedia de Windows, no un reproductor en particular. No necesita
> Python ni instalar nada raro: hay instalador y una version portatil de un solo archivo.
>
> Extras que me gustaron hacer: panel con tres tamaños (incluida una tira fina de una sola
> fila) con un modo para jugar que no le roba el foco al juego, atajos globales, y elegir el
> color de la barra y de las ondas.
>
> Es gratis, licencia MIT, y el codigo esta a la vista: [link al repo]
>
> En Windows 11 la barra ya no permite incrustar ventanas, asi que ahi se dibuja como una
> tira pegada al borde de abajo (mismo dibujo, mismos clics).

### r/Python — el angulo tecnico

**Titulo**: `Escribi un widget de Windows en Python puro (Win32 + ctypes), sin frameworks de UI`

> Soy el autor. Es un widget de musica que se incrusta en la barra de tareas de Windows 10.
> Todo el dibujo es Pillow sobre un lienzo x3 y reduccion LANCZOS; la presentacion es
> `UpdateLayeredWindow` sobre una ventana **hija** de `Shell_TrayWnd` (desde Windows 8 las
> ventanas hijas admiten `WS_EX_LAYERED`, y ahi esta el truco del fondo transparente).
>
> Tres cosas que me costaron y quedaron documentadas en el repo:
>
> 1. **El alpha por pixel decide que ventana recibe el mouse.** Con el fondo totalmente
>    transparente, los huecos son "agujeros" y el clic se lo queda la barra de tareas. Se
>    arregla con un piso de alfa de 2/255 (0,8%, invisible).
> 2. **El volumen por aplicacion** no lo expone SMTC ni pywin32: hay que hablar con la via
>    de audio de Windows (Core Audio) por ctypes, recorriendo las sesiones y emparejando por
>    nombre de ejecutable.
> 3. **Las ondas son una animacion**, no un analisis: SMTC no expone niveles de audio. Esta
>    dicho en la documentacion en vez de venderlo como visualizador real.
>
> Verificacion: hay tres suites (una de ellas mueve el mouse y las teclas de verdad) y el
> ejecutable pasa las mismas que el codigo.
>
> [link al repo]

### r/software, r/coolgithubprojects, r/SideProject

**Titulo**: `Astra-Music-widget: musica en la barra de tareas de Windows (gratis, open source)`

> Acabo de publicar la 1.0. Un adorno para la barra de tareas que muestra lo que suena:
> caratula, titulo, controles y el volumen de la app, mas un panel con modo gaming.
> Gratis y MIT, con instalador o portatil de un solo archivo. [link]

### Hacker News (Show HN)

**Titulo**: `Show HN: A music widget embedded in the Windows taskbar (Python + Win32)`

> Un widget de musica que se incrusta en la barra de tareas de Windows 10. Es Python +
> pywin32 + Pillow, sin framework de UI.
>
> Lo mas interesante del proyecto fueron los detalles: las ventanas hijas en capas y el
> alpha por pixel que decide quien recibe el mouse; el volumen por aplicacion hablando con
> Core Audio por ctypes (SMTC no lo expone); y por que en Windows 11 esto ya no se puede
> incrustar y el widget pasa a ser una tira flotante.
>
> En el repo esta la documentacion con las mediciones de cada trampa. Feliz de contestar.
>
> [link al repo]

### X / Twitter

> Hice un widget de musica que vive en la barra de tareas de Windows: caratula, titulo,
> controles y volumen de la app que suena. Gratis y MIT.
> [GIF] [link]

### alternativeto.net

Agregarlo como alternativa a **Wallpaper Engine** y **Rainmeter** (misma gente: gente que
personaliza su escritorio). Se sube desde su formulario, con la captura y el link.

---

## El video de 20 segundos (lo que mas rinde)

Una grabacion de pantalla, **sin hablar**: musica sonando, el widget con las ondas
moviendose, abris el panel, y que se vea encima de un juego en ventana. Eso se comparte en X,
TikTok, Shorts y en los mismos subreddits (Reddit acepta videos y andan mejor que las
imagenes).

Guion corto:
1. 0-5 s: la barra con el widget y las ondas moviendose (nada mas).
2. 5-12 s: clic en la caratula, se abre el panel, tocas play/pausa y la barra de progreso.
3. 12-20 s: lo mismo con el juego abierto, para mostrar que no le roba el foco.

---

## Un riesgo que conviene tapar antes de publicar

La app asume la barra de tareas **abajo**. Si alguien la tiene a un costado o arriba, el
widget le va a quedar mal ubicado, y ese es el tipo de comentario que arruina un post
("lo probe y me rompio la barra"). Lo tengo documentado como limitacion, pero la salida
elegante es chica: **si la barra no esta abajo, pasar solo al modo flotante** (que ya existe
para Windows 11 y no toca la barra). Son unas diez lineas y una prueba.

---

## Expectativas honestas

Es una utilidad de escritorio, no un juego: no se hace viral. Lo realista si un post pega es
un pico de unos cientos de descargas y unas decenas de estrellas, y despues el goteo lento
que trae winget. Lo que **si** cambia el numero de verdad es estar en winget (te encuentran
buscando) y tener el GIF y la imagen social (hacen que alguien se quede y que el link se vea
bien cuando lo comparten).
