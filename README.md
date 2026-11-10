# Selección de personal con IA: motor propio en código, módulo de visión y seguridad (tercer corte)

Reemplaza a n8n: los flujos ahora son servicios de una API en **Python (FastAPI)**,
con la IA organizada en **LangChain** sobre modelos gratuitos (OpenRouter, Groq y Gemini, con Ollama como opción local).
El panel web se sirve desde el mismo servidor.

| Flujo en n8n | Ahora | Archivo |
|---|---|---|
| Selección de personal con IA (carga) | `POST /api/candidatos` | `app/services/carga.py` |
| Lista de candidatos | `GET /api/candidatos` | `app/services/lista.py` |
| Chat Selección de Personal | `POST /api/chat` | `app/services/chat.py` |
| (nuevo) Módulo de visión | `POST /api/vision` y revisión humana | `app/services/vision.py`, `lectura.py` |
| (nuevo) Schedule Trigger: resumen diario y cola de reintento | hilo programado y `POST /api/tareas/...` | `app/services/tareas.py` |
| Pestaña Executions | `GET /api/ejecuciones` y pestaña **Ejecuciones** del panel (admin) | `app/services/registro.py` |
| Nodo Switch | función `zona()` | `app/services/decision.py` |
| Nodo Telegram | función `avisar()` | `app/services/telegram.py` |
| Information Extractor / Basic LLM Chain | `extraer_datos()` / `responder_chat()` | `app/services/llm.py` |

La **semana 3** agrega un cuarto flujo, el **módulo de visión**: se sube la foto de un formulario u hoja de vida,
se lee con OCR local, se ocultan los datos personales, una IA ordena los datos en campos con su nivel de confianza
y, según esa confianza, se guarda el candidato o se pide a una persona que revise (ver sección 6).

Además hace lo que faltaba en n8n: **actualiza el estado** del candidato según la zona
(80 o más: Preseleccionado, 60 a 79: En revisión, menos de 60: Descartado).

## 1. Instalación (Windows, PowerShell)

Necesitas Python 3.10 o superior (`python --version`).

```powershell
cd seleccion-ia
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
```

Si PowerShell bloquea la activación, ejecuta una vez:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 2. Claves de IA gratuitas

Abre `.env` y pon **al menos una** clave:

- `OPENROUTER_API_KEY`: créala en openrouter.ai (Settings, Keys) y elige en `OPENROUTER_MODEL` un modelo que termine en `:free`.
- `GROQ_API_KEY`: créala en la consola de Groq.
- `GOOGLE_API_KEY`: créala en Google AI Studio (Gemini).

Si pones varias, se usan en el orden de `LLM_PROVIDERS` (por defecto OpenRouter y, si falla, Gemini: ese es el plan B). Los proveedores sin clave se omiten. Verifica en cada servicio
las cuotas gratuitas vigentes y que los nombres de modelo (`GROQ_MODEL`, `GEMINI_MODEL`) sigan disponibles.
Para Telegram copia el token y el chat ID que ya usabas en n8n (opcional).

## 3. Ejecutar

```powershell
uvicorn app.servidor:app --reload
```

Abre http://127.0.0.1:8000 : primero aparece el inicio de sesión y luego el mismo panel (Cargar, Candidatos, Asistente).
Usuarios de prueba (se crean solos la primera vez; las claves salen de `.env`):

| Usuario | Contraseña | Puede |
|---|---|---|
| `admin` | `Admin.2026` | todo, incluida la auditoría, las ejecuciones, los usuarios y `/docs` |
| `reclutador` | `Recluta.2026` | subir PDF y fotos, revisar lecturas, ver candidatos y fotos, usar el asistente |
| `consulta` | `Consulta.2026` | ver candidatos y usar el asistente (no sube ni ve fotos) |

`app.servidor:app` es la aplicación de `app/main.py` envuelta con la seguridad. `app.main:app` sigue funcionando
igual que antes, pero **sin inicio de sesión**: úsalo solo para depurar en tu computador.
La documentación interactiva de la API está en http://127.0.0.1:8000/docs (solo `admin`).
Arriba a la derecha del panel debe decir **Conectado al servidor**.

El registro de cada ejecución (fecha, entrada y resultado) está en http://127.0.0.1:8000/api/ejecuciones.

## 4. Pruebas automáticas

```powershell
pytest
```

Resultado esperado: **93 pruebas aprobadas** (las que usan Tesseract se omiten solas si no está instalado).

| Archivo | Qué prueba |
|---|---|
| `test_flujos.py` | carga de PDF, zonas de decisión, Telegram con reintentos, lista, chat, supresión, registro de ejecuciones, plan B y error 503 claro |
| `test_vision.py` | confianza por campo, revisión humana, foto ilegible, cola de reintento cuando la IA cae, enmascarado, fotos inválidas, OCR real |
| `test_tareas_e_integracion.py` | resumen diario, reintento programado y un recorrido completo con login, roles, visión → candidato → chat y auditoría |
| `test_evaluar.py` | el evaluador de fotos cuenta bien los aciertos |
| `test_llm.py`, `test_memoria_chat.py` | extracción con LangChain, reintentos, cambio de modelo (plan B), memoria del chat |
| `test_seguridad.py`, `test_almacen_sql.py`, `test_privacidad.py` | sesión, bloqueo, permisos, auditoría, enmascarado de PDF |

Las pruebas no usan internet ni claves: simulan la IA (y el OCR en la mayoría de los casos de visión). Cubren las zonas de
decisión, los reintentos, el cambio al segundo modelo (plan B), los flujos, los errores, el registro de ejecuciones, el
enmascarado de datos personales, la confianza por campo y la revisión humana de las fotos.
Las de la semana 4 (`test_seguridad.py`, `test_almacen_sql.py`, `test_privacidad.py`, `test_memoria_chat.py`) cubren el
inicio de sesión, el bloqueo tras 5 intentos fallidos, los permisos de cada rol, la auditoría de las acciones de la IA,
el enmascarado del texto de los PDF y la memoria del chat. Las dos pruebas con OCR real
se omiten solas si Tesseract no está instalado.

## 5. Probar con la IA real

Si el panel dice «El servicio de IA no está disponible», ejecuta `python scripts/probar_ia.py`: prueba cada proveedor por
separado y dice el error exacto (clave inválida, modelo que ya no existe, ajuste de privacidad de OpenRouter o límite de uso).
La terminal del servidor también muestra una línea «Proveedor X falló: …» por cada modelo.


1. Con la clave puesta en `.env`, arranca el servidor.
2. Sube una hoja de vida de prueba en la pestaña Cargar.
3. Mira el resultado en Candidatos y pregúntale algo en Asistente.
4. Para probar el plan B, pon una clave inválida en `OPENROUTER_API_KEY` (con `LLM_PROVIDERS=openrouter,gemini`):
   el sistema debe responder con Gemini.
   Si quitas las dos claves, el panel muestra un mensaje claro en lugar de fallar.

## 6. Módulo de visión (semana 3)

### 6.1 Instalar Tesseract (el lector de imágenes)

Los paquetes de Python (`pytesseract`, `pillow`, `numpy`) se instalan con `pip install -r requirements.txt`,
pero **Tesseract es un programa aparte**. Sin él, las fotos devuelven el mensaje
«El lector de imágenes (Tesseract) no está instalado en el servidor».

**Windows**
1. Descarga el instalador de Tesseract para Windows (64 bits) de UB Mannheim: https://github.com/UB-Mannheim/tesseract/wiki
2. En el instalador, en *Additional language data*, marca **Spanish** (y deja English). Sin español lee mal tildes y eñes.
3. Instala en la carpeta por defecto (`C:\Program Files\Tesseract-OCR`). El sistema la encuentra solo.
   Si usaste otra carpeta, escribe la ruta de `tesseract.exe` en `TESSERACT_CMD` dentro de `.env`.
4. Reinicia el servidor (`uvicorn app.servidor:app --reload`).

Para comprobarlo, en una terminal nueva: `"C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs` debe mostrar `eng` y `spa`.

**Linux / servidor** (Debian o Ubuntu): `sudo apt install tesseract-ocr tesseract-ocr-spa`.

### 6.2 Cómo se usa

En la pestaña **Cargar** puedes arrastrar fotos JPG o PNG (o PDF, como antes) o usar **Tomar foto con la cámara**
desde el celular. Escribe nombre y correo de cada candidato, marca la autorización y envía.

- Si la lectura es **confiable**, se crea el candidato igual que con un PDF (puntaje, estado, aviso de Telegram).
- Si **no es confiable**, se abre una pantalla de revisión con la foto al lado y los campos leídos; cada uno muestra su
  confianza y los dudosos aparecen resaltados. La persona corrige y pulsa **Confirmar y guardar**, o **Descartar** (la foto se borra).
  **Revisar después** deja la lectura pendiente con un botón «Revisar» en la lista.
- Si la foto es **ilegible**, se rechaza con el consejo de repetirla y no se llama a la IA.
- Si **la IA no responde** (cuota agotada), la foto no se pierde: queda pendiente en una cola de reintento. Las tareas
  programadas la reintentan solas y una persona también puede completar los campos a mano y confirmar.
- Al confirmar con **correcciones**, la IA vuelve a calcular el puntaje con los datos corregidos.

Consejos para las fotos: de frente (sin ángulo), con luz pareja, sin sombras ni reflejos, el documento completo dentro del
encuadre y la letra nítida. En iPhone elige Ajustes, Cámara, Formatos, «Más compatible» (JPG en vez de HEIC).

### 6.3 Qué pasa por dentro

1. **Preparar la foto**: se gira según los metadatos, se pasa a grises, se corrigen sombras y se ajusta el tamaño.
2. **OCR local** (Tesseract): texto y confianza de lectura. La imagen **no sale del servidor**.
3. **Enmascarar datos personales**: correo, teléfono, documento, dirección y el nombre que escribió el usuario se reemplazan
   por marcas como `[CORREO]` antes de llamar a la IA. Es un enmascarado por patrones: reduce mucho lo que se envía,
   **pero no garantiza el 100 %**; por eso la imagen y su almacenamiento son locales.
4. **IA (LangChain con OpenRouter, Groq o Gemini, con plan B)**: ordena el texto en campos y estima la confianza de cada uno.
5. **Confianza final por campo** = la más baja entre (a) lo que dice la IA, (b) qué parte del valor aparece de verdad en el
   texto leído y (c) la calidad de lectura del OCR. Pasa a revisión si el OCR baja de `UMBRAL_OCR` (0.70), si algún campo baja de
   `UMBRAL_CAMPO` (0.60) o si faltan profesión o habilidades. Si el OCR queda bajo `UMBRAL_OCR_MINIMO` (0.45) se rechaza la foto.

Los umbrales son un punto de partida: se ajustan mirando los resultados del evaluador con tus fotos reales.

### 6.4 Rutas de la API

| Ruta | Para qué |
|---|---|
| `POST /api/vision` | Sube la foto (campos `Imagen`, `Nombre`, `Correo`, `Cargo`, `Autorizacion`). Devuelve `guardado` o `requiere_revision`, los campos y su confianza |
| `GET /api/vision?estado=pendiente` | Lecturas que esperan revisión (aparecen en la pestaña Candidatos) |
| `GET /api/vision/{id}` | Estado de una lectura (campos, confianza, quién subió la foto y cuándo) |
| `GET /api/vision/{id}/imagen` | La foto (solo por la API, no está en una carpeta pública) |
| `POST /api/vision/{id}/confirmar` | Cuerpo `{"campos": {...}}` con las correcciones; guarda el candidato |
| `POST /api/vision/{id}/rechazar` | Descarta la lectura y borra la foto |

### 6.5 Almacenamiento y trazabilidad

- Las fotos se guardan en `IMAGENES_DIR` con **nombre aleatorio** (no el del archivo original) y solo se entregan por la API.
- Cada lectura queda en la tabla `lecturas_vision`: archivo original, huella SHA-256, quién la subió, cuándo, confianza,
  estado (pendiente, guardada o rechazada), si la persona corrigió algo y quién la revisó.
- Cada ejecución aparece en `/api/ejecuciones` (flujos `vision`, `vision_confirmar`, `vision_rechazar`) sin correos ni datos personales.
- Una lectura rechazada borra su foto (minimización de datos).
- Desde la semana 4 «quién» es el usuario con sesión: la capa de seguridad escribe `subido_por` y `revisado_por` en
  `lecturas_vision` y además deja la acción en la tabla `auditoria` (ver sección 7).

### 6.6 Medir el acierto con fotos reales

La guía pide probar con **20 o más fotos reales** y reportar el % de acierto por campo.

```powershell
python scripts/evaluar.py evaluacion\fotos_reales
```

Lee `evaluacion/LEEME.md`: explica cómo tomar las fotos (con datos inventados), cómo escribir `etiquetas.csv` y cómo
cuenta cada campo. El script escribe `resultados_evaluacion.md` (resumen para el informe) y `resultados_evaluacion.csv`.
`evaluacion/fotos_simuladas/` trae 6 imágenes generadas por computador solo para comprobar que todo funciona:
**no sustituyen las fotos reales**. El evaluador usa la IA real de `.env` y gasta cuota gratuita (usa `--pausa 6` si se agota).

## 7. Seguridad, auditoría y memoria del chat (semana 4)

Todo vive en `app/seguridad/` y en `app/servidor.py`, una capa que envuelve a `app/main.py` sin modificarlo.

**Inicio de sesión.** Contraseñas cifradas con PBKDF2 (nunca se guarda la clave), sesión en una cookie `HttpOnly`
y `SameSite=Lax` firmada con `SESION_SECRETO`, que vence a las `SESION_HORAS`. Tras 5 intentos fallidos en 10 minutos
el usuario queda bloqueado 5 minutos. En producción `COOKIE_SEGURA=true` hace que la cookie solo viaje por HTTPS.

**Permisos por rol** (`app/seguridad/permisos.py`):

| Acción | admin | reclutador | consulta |
|---|:-:|:-:|:-:|
| Ver panel, candidatos y lecturas | sí | sí | sí |
| Preguntar al asistente | sí | sí | sí |
| Ver las fotos subidas | sí | sí | no |
| Subir PDF o fotos, confirmar o descartar lecturas | sí | sí | no |
| Ver ejecuciones, auditoría, usuarios y `/docs`; ejecutar tareas programadas | sí | no | no |

Si un rol intenta algo que no puede, recibe 403, la petición no llega a la aplicación y el intento queda auditado.

**Auditoría** (tabla `auditoria`, página http://127.0.0.1:8000/auditoria solo para `admin`): fecha, usuario, rol, acción,
recurso, resultado HTTP, si intervino la IA, detalle e IP. Se registran los inicios y cierres de sesión, los fallidos,
los accesos negados, toda acción que cambia datos, cada consulta de una foto y las acciones de la IA (carga de PDF,
lectura de fotos, confirmaciones y chat). El detalle solo guarda campos sin datos personales (ids, estado, puntaje,
confianza): nunca nombres, correos ni teléfonos.

**Rutas nuevas**

| Ruta | Para qué |
|---|---|
| `GET /login`, `POST /login`, `POST /logout` | Iniciar y cerrar sesión |
| `GET /api/sesion` | Usuario, rol y permisos de la sesión actual |
| `GET /api/auditoria?limite=200&solo_ia=1` | Registro de auditoría (admin) |
| `GET /api/usuarios`, `POST /api/usuarios` | Listar y crear usuarios, cuerpo `{"usuario", "clave", "rol"}` (admin) |
| `POST /api/chat/olvidar` | Borra la memoria de la conversación del usuario |
| `GET /_salud` | Verificación de vida para el servidor de despliegue |

**Privacidad de los PDF.** Antes de enviar el texto de un PDF a la IA externa se ocultan correo, teléfono, documento,
dirección, enlaces a perfiles, fecha de nacimiento y nombre (`app/services/privacidad.py`). Igual que en las fotos,
es un enmascarado por patrones: reduce mucho lo que sale, pero no garantiza el 100 %.

**Memoria del chat.** El asistente recuerda las últimas `CHAT_MEMORIA_TURNOS` preguntas y respuestas de cada usuario
(LangChain `InMemoryChatMessageHistory`), así entiende preguntas como «¿y qué estudió él?». Se borra con el botón
**Nueva conversación**, al cerrar sesión o al reiniciar el servidor. Los datos siempre salen de la tabla actual.

Política de tratamiento de datos (Ley 1581 de 2012): `docs/POLITICA_DATOS.md`.

## 8. Tareas programadas (el «Schedule Trigger» de n8n)

`app/services/tareas.py` corre un hilo que se despierta cada `TAREAS_MINUTOS` (30 por defecto):

- **Cola de reintento**: las fotos que quedaron sin interpretar porque la IA no respondió se vuelven a enviar.
- **Resumen diario por Telegram** desde `RESUMEN_HORA` (8 a. m. de Colombia): candidatos nuevos de las últimas 24 horas
  por zona, mejores puntajes y fotos pendientes. Se envía una sola vez por día aunque el servidor se reinicie.

El admin las puede ejecutar a mano en la pestaña **Ejecuciones** (botones «Enviar resumen ahora» y «Reintentar fotos sin IA»)
o con `POST /api/tareas/resumen` y `POST /api/tareas/reintentar`. Cada ejecución queda registrada.

## 9. Integración entre los componentes

La foto **dispara el mismo proceso de negocio** que un PDF: `registrar_candidato()` (en `carga.py`) aplica la zona,
guarda el candidato con su estado y envía el aviso de Telegram. El **chatbot usa el resultado**: los candidatos que
llegaron por foto tienen `origen = foto` y el asistente también conoce las lecturas que esperan revisión
(pregúntale «¿hay fotos pendientes de revisión?» o «¿qué candidatos llegaron por foto?»).

## 10. Despliegue

Paso a paso en `DESPLIEGUE.md`: base de datos gratuita en Neon, servidor en Render con el `Dockerfile` (ya trae Tesseract
en español) y `render.yaml`, variables de entorno y comprobación final.

## Estructura

```
app/
  main.py            rutas de la API y entrega del panel
  servidor.py        punto de entrada con seguridad (envuelve a main.py)
  config.py          variables de entorno
  db.py              tablas: candidatos, ejecuciones y lecturas_vision
  errores.py         errores con mensaje para el usuario
  services/          carga, lista, chat, llm, pdf, decision, telegram, registro, vision, lectura, privacidad, tareas
  seguridad/         inicio de sesión, permisos por rol, auditoría y páginas de login y auditoría
panel/               página web (HTML, CSS y JavaScript)
scripts/evaluar.py   mide el % de acierto del módulo de visión
scripts/generar_fotos_simuladas.py
evaluacion/          ficha en blanco para imprimir, fotos simuladas, plantilla de etiquetas e instrucciones
docs/                documento técnico, guion del video y política de tratamiento de datos
tests/               pruebas con pytest
Dockerfile, render.yaml, DESPLIEGUE.md
```

## Qué queda por hacer (no es código)

- Tomar las 20 o más fotos reales con celular, correr `scripts/evaluar.py` y pegar los porcentajes en
  `docs/DOCUMENTO_TECNICO.md` (sección 5). Instrucciones en `evaluacion/LEEME.md`.
- Desplegar siguiendo `DESPLIEGUE.md` y escribir el enlace en el documento técnico.
- Que cada integrante haga sus commits (ver `DESPLIEGUE.md`, sección 2).
- Grabar el video siguiendo `docs/GUION_VIDEO.md`.
- Opcional: Ollama como modelo local (`LLM_PROVIDERS=openrouter,gemini,ollama`) si el servidor tiene memoria suficiente.

## Privacidad

Usa solo hojas de vida y fotos de prueba. Al modelo gratuito (OpenRouter, Groq o Gemini, que pueden conservar lo que reciben)
solo llega texto enmascarado, tanto de los PDF como de las fotos; la imagen y el PDF se procesan en el servidor. El chat sí envía
el nombre de los candidatos guardados, porque el asistente debe nombrarlos al responder. El registro de ejecuciones no guarda el correo del candidato.
Los datos personales reales están protegidos por la Ley 1581 de 2012 (Habeas Data).
