# Matt's Newsletter

Una newsletter semanal en inglés hecha para Matthew: cuestionarios de neuropsicología, casos diagnósticos de salud mental, neurociencia, psicoterapia, irlandés A2/B1 y teoría musical básica, seguidos de noticias de Irlanda. Diseño en blanco y negro, sin imágenes remotas, con versión HTML y texto plano.

El proyecto adapta el enfoque del `newsletter.py` original: contenido editable en TXT, noticias RSS, envío SMTP por Gmail y archivo estático de ediciones. No necesita una API de IA ni servicios de pago para generar los ejercicios.

## Ver el resultado

- [Previsualización del correo](vista_previa.html).
- [El mismo correo en texto plano](vista_previa.txt).
- [Historial de ejemplo: cuatro ediciones](previews/archive/index.html).
- [Archivo real](docs/index.html), inicialmente vacío hasta el primer envío.

Descarga la carpeta y abre los HTML en un navegador. La vista de archivos de GitHub muestra el código HTML, no el correo renderizado. Las cuatro ediciones del historial de ejemplo están marcadas como DEMO y nunca se han enviado. No se presentan como un historial real del cliente.

También puedes ver capturas directamente desde GitHub: [correo en escritorio](previews/email-preview.png), [correo en móvil](previews/mobile-preview.png), [archivo de ediciones](previews/archive-preview.png) y [soluciones con el enunciado completo](previews/answers-preview.png). Son capturas parciales; los HTML contienen la edición completa.

## Qué recibe Matt

Cada semana, en este orden:

1. **Neuropsychology case files**: tres preguntas sobre casos ficticios, con síntomas, redes cerebrales, diagnóstico probable y pruebas que ayudan a distinguirlos.
2. **Mental health case files**: tres casos diagnósticos ficticios de depresión, ansiedad, pánico, fobias, PTSD, OCD, bipolaridad y otros cuadros. Cada caso indica **DSM-5-TR** o **ICD-11**; sus reglas no se mezclan.
3. **Neuroscience**: tres preguntas sobre neurotransmisores, regiones, memoria, aprendizaje o métodos de estudio del cerebro.
4. **Psychotherapy toolkit**: tres preguntas sobre métodos, historia y términos de CBT, DBT, psicoanálisis y otras escuelas.
5. **A little Gaeilge**: tres ejercicios prácticos de irlandés A2/B1, con instrucciones en inglés y frases en irlandés.
6. **Music theory, finally**: tres ejercicios de ritmo, lectura, intervalos, escalas y acordes, con términos británicos/irlandeses y sus equivalentes estadounidenses cuando ayudan.
7. **Ireland’s News**: hasta cinco noticias fechadas de los últimos siete días, con medio y enlace.

Todas las preguntas tienen **cuatro opciones, A–D**, y una respuesta correcta. Al final, la clave de respuestas repite **el enunciado completo**, seguido de la opción correcta, explicación y ejemplo resuelto o práctica adicional. Matt puede revisar cada solución sin volver al cuestionario. Se han retirado los enlaces «Explore the topic» tanto del HTML como del texto plano para ahorrar espacio. Las referencias siguen disponibles en los TXT y en `CONTENT_SOURCES.md`.

Hay **720 preguntas con explicación y ejemplo/práctica adicional**, **120 por materia**. Las cinco categorías originales han pasado de 30 a 120 cada una: cuatro veces su tamaño anterior, más 120 preguntas nuevas de salud mental. Con tres por materia son **18 preguntas por edición y 40 semanas sin repetir**, aproximadamente nueve meses. Al agotar el banco, se recuperan primero las preguntas utilizadas hace más tiempo.

La ampliación combina casos nuevos, preguntas de diagnóstico o discriminación clínica y ejercicios de aplicación. Algunos casos de neuropsicología se revisitan más adelante para preguntar por otra capacidad, prueba o distinción; no se consideran el mismo enunciado. Las preguntas antiguas conservan su `ID` y su respuesta correcta para que el historial siga reconociéndolas.

Los casos son educativos y las localizaciones se expresan como regiones o redes plausibles. No son historias clínicas reales ni una herramienta de diagnóstico.

## Estructura

```text
newsletter.py                  Generación, RSS, SMTP e historial
content/
  neuropsychology.txt           120 preguntas sobre casos ficticios
  mental_health.txt             120 casos diagnósticos DSM-5-TR / ICD-11
  neuroscience.txt              120 preguntas
  psychotherapy.txt             120 preguntas
  irish.txt                     120 ejercicios A2/B1
  music.txt                     120 ejercicios básicos
config/news_sources.json        Fuentes RSS y prioridades editoriales
state/history.json              Semanas enviadas y contenido utilizado
docs/                           Archivo real para GitHub Pages
previews/archive/               Cuatro ediciones de demostración
previews/news_snapshot.json     Muestra de noticias fechadas para reproducir la vista previa
vista_previa.html               Correo de muestra
vista_previa.txt                Alternativa en texto plano
tests/test_newsletter.py        Pruebas sin enviar correos ni acceder a Internet
.github/workflows/
  newsletter.yml                Envío semanal y publicación del archivo
  check.yml                     Validación en push y pull request
requirements.txt                Datos de zonas horarias
.env.example                    Nombres de las variables, sin credenciales reales
CONTENT_SOURCES.md              Referencias y criterios de contenido
```

## Ejecutar en tu ordenador

Usa Python 3.12 o posterior y abre una terminal **dentro de `Newsletter-Matthew`**:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python newsletter.py --check
python newsletter.py --preview
```

`--preview`, o ejecutar sin argumentos, genera `vista_previa.html` y `vista_previa.txt`. No envía correo, no publica en `docs/` y no cambia `state/history.json`. Conserva el historial real para seleccionar las siguientes preguntas disponibles.

Para probar sin conexión:

```powershell
python newsletter.py --demo --offline
```

Para reconstruir la demostración entregada, con noticias fechadas al 20 de noviembre de 2026:

```powershell
python newsletter.py --demo --date 2026-11-20 --news-fixture previews/news_snapshot.json
```

La muestra de noticias solo se admite en previsualizaciones y se identifica dentro del correo. Las fechas de las ediciones anteriores sirven para demostrar el archivo: no se reconstruyen noticias de esas semanas. Un `--demo` utiliza su propia rotación temporal, independiente del cliente.

Para cambiar el tamaño de una edición:

```powershell
python newsletter.py --preview --offline --questions 5
```

`--questions` indica preguntas **por materia**. El workflow utiliza tres. La configuración antigua de perfiles diarios, lecciones de otros idiomas y noticias de España se ha sustituido por esta única edición semanal. `MODO_PRUEBA=1` sigue bloqueando cualquier intento de envío; el modo de prueba recomendado es `--preview`.

## Preparar el repositorio de GitHub

Sube **el contenido de `Newsletter-Matthew` a la raíz de su propio repositorio**. Deben quedar `newsletter.py`, `requirements.txt` y `.github/workflows/` directamente en la raíz. Si subes esta carpeta como subdirectorio de otro proyecto, GitHub no descubrirá el workflow que está dentro.

1. Crea un repositorio para el proyecto y sube los archivos, incluida la carpeta oculta `.github`.
2. En **Settings → Secrets and variables → Actions → Secrets**, añade estos tres secretos:

| Secret | Valor |
| --- | --- |
| `EMAIL_REMITENTE` | La cuenta Gmail que enviará el correo |
| `EMAIL_PASSWORD` | Una contraseña de aplicación de esa cuenta |
| `EMAIL_DESTINATARIOS` | La dirección de Matthew; se admiten varias separadas por comas |

3. En **Settings → Actions → General**, permite que el workflow escriba en el repositorio. El trabajo de envío utiliza `contents: write` para guardar estado y ediciones. Si la rama está protegida, configura una vía permitida para esos commits antes de activar el envío.
4. En **Settings → Pages → Build and deployment**, selecciona **GitHub Actions** como origen.
5. En la pestaña **Variables** de Actions, crea `URL_WEB`, por ejemplo `https://TU-USUARIO.github.io/TU-REPOSITORIO`. Para un dominio propio, utiliza su URL base. Si no la defines, el correo omitirá los enlaces web; el archivo se seguirá generando.
6. En **Actions → Matt's weekly newsletter → Run workflow**, elige primero `preview`. Descarga el artefacto del resultado y revisa el HTML. Esta ejecución no necesita credenciales de correo.
7. Con los secretos configurados y el resultado revisado, ejecuta el mismo workflow con `send` para realizar el primer envío. Las siguientes ejecuciones quedan programadas semanalmente.

El archivo `.env.example` documenta los nombres. El programa **no carga automáticamente un `.env`**: en local utiliza variables de entorno y en GitHub los secretos anteriores. No subas contraseñas reales.

Gmail requiere una contraseña de aplicación en una cuenta que admita esta función; normalmente necesitas la verificación en dos pasos. Consulta la [ayuda oficial de Google](https://support.google.com/accounts/answer/185833).

## Horario y funcionamiento semanal

El envío se programa los **lunes a las 08:17 de Irlanda**, con `timezone: Europe/Dublin`, que adapta el horario de verano. En Madrid corresponde a las **09:17**. Se eligió este horario como valor inicial; puedes editar el cron del workflow.

GitHub ejecuta los horarios desde la rama predeterminada y puede retrasarlos. En repositorios públicos sin actividad también puede desactivar ejecuciones programadas. Consulta la [documentación oficial de horarios de Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule) y los [eventos programados](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Cada semana se identifica por año y semana ISO, por ejemplo `2026-W47`. Un segundo `send` en esa misma semana termina sin repetir el correo. Esto también aplica al primer envío manual: si se envía un viernes, el siguiente lunes ya pertenece a otra semana y puede enviarse otra edición. El bloqueo evita duplicados dentro de una semana ISO; no impone 168 horas entre dos envíos manuales.

El workflow guarda `state/` y `docs/` con un commit y publica solamente `docs/` en Pages. El archivo web y el correo contienen las mismas preguntas, respuestas y noticias; los enlaces de navegación se adaptan a cada formato. No borres el estado entre ejecuciones: es lo que permite recordar lo enviado.

El archivo de Pages es público cuando tu configuración de GitHub Pages lo publica como tal. No incluye direcciones ni contraseñas. Los destinatarios se pasan al sobre SMTP y no se muestran en `To`; el remitente aparece en ese encabezado. Matt puede solicitar la baja respondiendo al remitente; la eliminación de su dirección es manual.

## Noticias de Irlanda y criterio editorial

Se consultan los RSS de RTÉ Irlanda, The Journal e Irish Examiner Irlanda. Se priorizan vivienda, alquileres, salarios, sindicatos, pobreza, sanidad, educación, igualdad y clima. La orientación social y de izquierdas se refleja en los asuntos seleccionados y se declara en la sección.

El programa usa titulares originales enlazados, fecha y medio. No inventa resúmenes ni convierte opiniones en hechos: cuando la fuente puede mezclar información y análisis se indica que hay que consultar el artículo. Agrupa titulares similares, limita cada medio a dos noticias, descarta artículos sin fecha verificable o con fecha futura y recuerda los enlaces compartidos. Con `require_priority_match: true`, exige que el titular coincida con algún tema configurado: no rellena huecos con deporte o entretenimiento ajeno a esos temas. El agrupamiento automático es aproximado: titulares muy diferentes sobre el mismo hecho podrían aparecer separados.

Si falla alguna fuente, el correo lo indica. Si fallan todas o no hay noticias recientes disponibles, mantiene los ejercicios e informa de la ausencia de noticias; no recicla titulares antiguos para rellenar. La muestra fechada de `previews/news_snapshot.json` nunca se usa como sustituto automático en producción.

Para cambiar los medios o la prioridad de los temas, edita `config/news_sources.json`. Los valores de `priority_terms` aumentan la prioridad de las coincidencias en titulares; no atribuyen una ideología al lector ni al medio.

## Editar y ampliar los ejercicios

Cada TXT está en UTF-8. Los bloques se separan con una línea `---`. Mantén una línea por campo; los dos puntos dentro del contenido sí están permitidos.

```text
ID: music-121
TITLE: Three notes, one chord
QUESTION: Which notes form a D major triad?
A: D F A
B: D F-sharp A
C: D G A
D: D F-sharp A-flat
ANSWER: B
EXPLANATION: D major contains a major third, F-sharp, and a perfect fifth, A.
EXAMPLE: Compare D-F-sharp-A with D-F-A to hear major versus minor.
SOURCE: https://www.musictheory.net/lessons
```

Todos los campos son obligatorios, incluidas las cuatro opciones A–D, que deben ser distintas. `ANSWER` debe ser `A`, `B`, `C` o `D`; `SOURCE` debe ser un enlace HTTP(S). Cada `ID` debe ser único en todo el proyecto. Conserva los identificadores de las preguntas existentes para que el historial siga reconociéndolas.

```powershell
python newsletter.py --check
python -m unittest discover -s tests -v
```

Las pruebas comprueban la rotación completa de 40 semanas, las cuatro opciones, los enunciados repetidos en las soluciones, el tamaño del correo, fechas de noticias, duplicados, escape de HTML, privacidad de destinatarios, previsualización sin efectos y éxito/error de entrega con SMTP simulado. No envían correos reales. Una validación automática no sustituye la revisión editorial de los contenidos científicos y lingüísticos.

## Si falla un envío

SMTP no ofrece una garantía de entrega exactamente una vez. El programa deja `state/pending.json` antes de contactar con Gmail. Si la conexión se corta en un punto ambiguo, conserva esa marca y bloquea nuevos envíos para evitar duplicarlos. El workflow guarda la marca y los archivos preparados aunque el paso de envío falle; si falla el commit o push, también quedan en el artefacto de recuperación.

Antes de reintentar, comprueba el correo enviado y los registros de Gmail. Descarga el artefacto si necesitas recuperar el estado. No borres la marca sin comprobar la entrega.

- Si confirmas que **no se envió a nadie**, elimina `state/pending.json` y los archivos de esa edición de `docs/editions/`, y quita su entrada de `docs/editions.json`. El siguiente envío regenerará el índice y la edición.
- Si confirmas que **sí se envió**, utiliza la fecha, `question_ids` y `news_keys` de `pending.json` para incorporarlos a los mapas `questions` y `news` de `state/history.json`. Añade la edición a `editions` con `{"date": "AAAA-MM-DD", "status": "sent"}` y después elimina `pending.json`. Así se conserva el bloqueo de esa semana y la rotación.
- Si hubo **entrega parcial**, confirma qué destinatarios lo recibieron antes de decidir cómo reenviar a los restantes. No vuelvas a ejecutar el envío general a ciegas.

Haz commit y push del estado reconciliado antes de volver a ejecutar Actions. Si un envío terminó pero falló la persistencia del estado, recupera esos archivos del artefacto antes de reintentar: perder el historial puede permitir un duplicado.

## Validación de esta entrega

Se generaron el correo de muestra y cuatro ediciones de demostración, con capturas de escritorio, móvil, archivo y soluciones. La vista móvil se comprobó a 390 píxeles sin desbordamiento horizontal. Los 720 bloques pasan el validador y las 26 pruebas pasan con SMTP simulado, incluida la rotación completa de 40 semanas, las cuatro opciones, las soluciones con enunciado y el tamaño de las ediciones. Las tres fuentes RSS se comprobaron mediante lectura en la entrega inicial; esta ampliación reutiliza la muestra fechada para revisar el diseño sin enviar correo. La entrega real con Gmail y la publicación en GitHub requieren configurar los secretos, el repositorio y Pages siguiendo los pasos anteriores.
