# Documento técnico – Sistema de selección de personal con IA

**Asignatura:** Desarrollo de Aplicaciones Empresariales · Tercer corte
**Integrantes:** [Nombre 1], [Nombre 2], [Nombre 3]
**Empresa del proyecto:** [Nombre de la empresa]
**Aplicativo desplegado:** [https://seleccion-ia.onrender.com] · **Repositorio:** [https://github.com/usuario/seleccion-ia]

| Usuario de prueba | Contraseña | Rol |
|---|---|---|
| admin | [clave de CLAVE_ADMIN] | Administrador: todo, auditoría, ejecuciones |
| reclutador | [clave de CLAVE_RECLUTADOR] | Sube PDF y fotos, revisa lecturas, usa el asistente |
| consulta | [clave de CLAVE_CONSULTA] | Solo consulta candidatos y usa el asistente |

## 1. Proceso de negocio

El área de Recursos Humanos recibe hojas de vida en PDF y también **fichas de inscripción en papel** que los candidatos
llenan a mano en ferias de empleo o en la recepción. Antes, la información de las fichas se transcribía a mano y los PDF se
procesaban con tres flujos de n8n en la nube. En este corte el sistema:

1. Deja de depender de n8n: los flujos son servicios del propio aplicativo en **Python con FastAPI** (Ruta A).
2. Usa modelos de lenguaje **gratuitos** organizados con **LangChain**: OpenRouter (modelos `:free`), Gemini y Groq, con
   Ollama como opción local.
3. Agrega un **módulo de visión** (caso «lectura de formularios físicos»): la foto de la ficha o de la hoja de vida
   impresa se lee con OCR, la IA la estructura con un nivel de confianza y el resultado **crea el candidato y dispara el
   mismo proceso** que un PDF: puntaje, zona de decisión, estado y aviso por Telegram.

**Decisión que produce el sistema:** el estado del candidato (Preseleccionado con 80 o más puntos, En revisión de 60 a 79,
Descartado con menos de 60). Es una ayuda: la decisión final la toma una persona de Recursos Humanos.

## 2. Arquitectura final

```
                       Navegador (PC o celular)                         Telegram (RR. HH.)
          Panel web: Cargar · Candidatos · Asistente · Ejecuciones             ▲
                                   │ HTTPS                                    │ avisos y resumen diario
┌──────────────────────────────────▼─────────────────────────────────────────┼──────────┐
│ Servidor (Docker en Render)                                                │          │
│  ┌──────────────────────────────────────────────┐                          │          │
│  │ Capa de seguridad (app/seguridad)            │  login · roles · auditoría          │
│  └──────────────────────┬───────────────────────┘                          │          │
│  ┌──────────────────────▼───────────────────────────────────────────────┐  │          │
│  │ Motor de automatización (FastAPI, app/main.py + app/services)        │  │          │
│  │  carga.py   lista.py   chat.py   vision.py   tareas.py (cron)         │──┘          │
│  │      │                    │          │                                              │
│  │      │      decision.py (Switch) · telegram.py · registro.py (log de ejecuciones)    │
│  │      ▼                    ▼          ▼                                              │
│  │  pdf.py (pypdf)    llm.py (LangChain)   lectura.py (Tesseract OCR local)            │
│  │      └── privacidad.py: enmascara datos personales antes de salir del servidor     │
│  └──────────────────────────────┬───────────────────────────────────────┘             │
│      data/imagenes (fotos, nombre aleatorio, sin acceso público)                       │
└─────────────────────────────────┼──────────────────────────────────────────────────────┘
                                  │ solo texto enmascarado
           ┌──────────────────────▼──────────────────────┐        ┌──────────────────────────────┐
           │ IA gratuita con plan B (en orden):           │        │ PostgreSQL en Neon (gratis)  │
           │ OpenRouter :free → Gemini → Groq → (Ollama)  │        │ candidatos · ejecuciones ·   │
           └──────────────────────────────────────────────┘        │ lecturas_vision · usuarios · │
                                                                   │ auditoria                    │
                                                                   └──────────────────────────────┘
```

| Capa | Tecnología (todas gratuitas) |
|---|---|
| Interfaz | HTML, CSS y JavaScript servidos por el mismo servidor; cámara del celular con `capture="environment"` |
| API y motor | Python 3.11, FastAPI, Uvicorn; tareas programadas con un hilo propio (sin servicios de pago) |
| IA | LangChain (`ChatPromptTemplate`, `PydanticOutputParser`, `with_fallbacks`, `InMemoryChatMessageHistory`) |
| Visión | Tesseract OCR 5 con español, Pillow y NumPy para preparar la foto |
| Datos | SQLAlchemy; SQLite en desarrollo, PostgreSQL (Neon) en producción |
| Despliegue | Docker en Render (plan gratuito), HTTPS automático |

## 3. Inventario de flujos migrados

| # | Flujo en n8n | Disparador → ahora | Pasos | Servicios externos | Resultado |
|---|---|---|---|---|---|
| 1 | Selección de personal con IA | Webhook → `POST /api/candidatos` | validar → leer PDF → enmascarar → IA extrae y puntúa → Switch → guardar → Telegram | IA gratuita, Telegram | Candidato con puntaje, zona y estado |
| 2 | Lista de candidatos | Webhook GET → `GET /api/candidatos` | leer tabla | — | Lista para el panel |
| 3 | Chat Selección de Personal | Chat Trigger → `POST /api/chat` | leer tabla y lecturas pendientes → IA con memoria por usuario | IA gratuita | Respuesta en lenguaje natural |
| 4 | (nuevo) Módulo de visión | `POST /api/vision` | ver sección 4 | IA gratuita (solo texto enmascarado), Telegram | Candidato o lectura para revisión humana |
| 5 | (nuevo) Schedule Trigger | hilo cada 30 min + `POST /api/tareas/*` | reintentar fotos sin IA; resumen diario | IA, Telegram | Cola de reintento vacía; resumen enviado |

**Cómo se implementó cada nodo de n8n:**

| Nodo de n8n | Implementación en código |
|---|---|
| Webhook / Chat Trigger | Rutas de FastAPI (`app/main.py`) |
| Extract from File | `pdf.extraer_texto()` con pypdf; detecta PDF escaneado y sugiere subirlo como foto |
| Information Extractor | `llm.extraer_datos()`: prompt + `PydanticOutputParser` que valida y corrige tipos y rangos |
| OpenRouter Chat Model | `llm.obtener_modelos()`: lista de proveedores en `LLM_PROVIDERS`; los que no tienen clave se omiten |
| Switch | `decision.zona()` con umbrales en `UMBRAL_ALTO` y `UMBRAL_MEDIO` |
| Data Table | Tablas `candidatos`, `lecturas_vision`, `ejecuciones` (`app/db.py`) |
| Telegram | `telegram.avisar()` con 3 reintentos; si falla, el candidato igual se guarda |
| Basic LLM Chain | `llm.responder_chat()` con memoria de los últimos 6 turnos por usuario |
| Schedule Trigger | `tareas.py`: hilo programado, sin servicios de pago |
| Pestaña Executions | `registro.ejecucion()`: cada flujo guarda fecha, usuario, entrada, resultado, duración y error |

**Manejo de errores y reintentos.** Cada llamada a la IA se reintenta 3 veces con espera creciente (tenacity); si el
modelo sigue fallando o devuelve un JSON inválido, LangChain pasa al siguiente modelo (`with_fallbacks`). Los errores
esperados (archivo inválido, falta autorización, IA caída) llegan al usuario como un mensaje claro con su código HTTP
(400, 404, 409, 422, 503); los inesperados devuelven 500 sin detalles técnicos y quedan en el log. Ningún flujo se pierde
sin registro: el bloque `with ejecucion(...)` guarda la fila con estado `ok` o `error` en todos los casos.

**Mejoras frente a n8n:** actualiza el estado del candidato según la zona, la carga acepta varios archivos a la vez, el chat
recuerda la conversación, las claves viven en variables de entorno y cada ejecución se consulta en el panel (pestaña
Ejecuciones, solo admin).

## 4. Módulo de visión por computador

**Caso de uso:** lectura de formularios físicos (fichas de inscripción y hojas de vida impresas o escritas a mano).
**Opción técnica:** OCR de código abierto (Tesseract) combinado con un modelo de lenguaje que estructura el texto. Se eligió
porque la imagen **nunca sale del servidor**: solo viaja texto con los datos personales ocultos.

**Captura.** Desde el panel web: arrastrar fotos JPG, PNG o WebP, o el botón «Tomar foto con la cámara», que en el celular
abre la cámara trasera. Se rechazan fotos HEIC con instrucciones para el iPhone y archivos de más de 10 MB.

**Procesamiento** (`app/services/vision.py` y `lectura.py`):

1. Preparación: giro según EXIF, escala de grises, ajuste de tamaño, corrección de sombras (división por el fondo
   estimado con un desenfoque fuerte) y contraste.
2. OCR local con Tesseract (`spa+eng`): texto y **confianza de lectura** (promedio ponderado de la confianza de cada palabra).
3. Si la confianza del OCR es menor a 45 % o hay muy pocas palabras, la foto se **rechaza** sin llamar a la IA y se le
   explica a la persona cómo repetirla.
4. Enmascarado: correo, teléfono, documento, dirección, fecha de nacimiento y el nombre (incluso mal leído por el OCR,
   por similitud) se reemplazan por marcas como `[CORREO]`.
5. La IA devuelve **JSON estructurado** (profesión, años de experiencia, habilidades, educación, certificaciones, puntaje,
   justificación) con la **confianza de cada campo**.
6. **Confianza final por campo = la menor entre** la que reporta la IA, la presencia real del valor en el texto leído
   (detecta datos inventados por la IA) y la calidad del OCR.

**Decisión de la IA y qué pasa cuando se equivoca.** Si el OCR supera 70 %, todos los campos superan 60 % y están la profesión
y las habilidades, el sistema **guarda el candidato solo** y dispara el proceso (zona, estado, Telegram). Si no, la lectura
queda **pendiente de revisión humana**: el panel muestra la foto al lado de los campos, resalta los dudosos con su
porcentaje y la persona corrige y confirma (la IA recalcula el puntaje con los datos corregidos) o descarta (la foto se
borra). Las lecturas pendientes aparecen en la pestaña Candidatos y el asistente sabe cuántas hay.

**Integración con la automatización y el chatbot.** Una foto confirmada llama a `registrar_candidato()`, la misma función del
flujo de PDF: el resultado de la visión dispara el proceso de negocio sin pasos manuales adicionales. El chatbot recibe los
candidatos con su `origen` (pdf o foto) y la lista de lecturas pendientes, así que responde preguntas como «¿qué candidatos
llegaron por foto?» o «¿hay fotos pendientes de revisión?».

**Almacenamiento con control de acceso.** Fotos en `data/imagenes` con nombre aleatorio de 32 caracteres, fuera de la
carpeta pública; solo se entregan por `GET /api/vision/{id}/imagen` a admin y reclutador. La tabla `lecturas_vision` guarda
archivo original, huella SHA-256, **quién la subió y cuándo**, quién la revisó y cuándo, confianza, estado y si hubo correcciones.

## 5. Pruebas y resultados

### 5.1 Pruebas unitarias y de integración (automatizadas)

`pytest` ejecuta **91 pruebas** sin internet ni claves (la IA se simula con LangChain): 91 aprobadas.

| Área | Pruebas | Qué cubren |
|---|---:|---|
| Flujos migrados (`test_flujos.py`) | 25 | carga, zonas, Telegram y reintentos, lista, chat, supresión, registro, plan B, 503 claro |
| Módulo de visión (`test_vision.py`) | 20 | confianza por campo, revisión, ilegible, cola de reintento, enmascarado, fotos inválidas, OCR real |
| Tareas e integración completa | 5 | resumen diario, reintento programado, recorrido con roles: foto → revisión → candidato → chat → auditoría |
| IA y memoria | 16 | extracción, JSON con formato raro, reintentos, cambio de modelo, memoria por usuario |
| Seguridad y privacidad | 23 | contraseñas, tokens, bloqueo, permisos, auditoría sin datos personales, enmascarado de PDF |
| Evaluador de fotos | 2 | cálculo de aciertos |

### 5.2 Pruebas con imágenes reales tomadas con celular

Se tomaron **[N ≥ 20] fotos** con [modelos de celular] de [N] fichas llenadas con datos inventados: [10] en buenas
condiciones, [3] inclinadas, [3] con sombra, [2] con poca luz y [2 o más] escritas a mano. Cada foto se etiquetó con sus
datos reales y se evaluó con `python scripts/evaluar.py evaluacion/fotos_reales` (OCR + IA [modelo]).

> Pegar aquí las tablas de `evaluacion/fotos_reales/resultados_evaluacion.md`.

| Campo | Aciertos | % de acierto |
|---|---:|---:|
| Profesión | [ ] de [ ] | [ ] % |
| Años de experiencia | [ ] de [ ] | [ ] % |
| Habilidades | [ ] de [ ] | [ ] % |
| Educación | [ ] de [ ] | [ ] % |
| Certificaciones | [ ] de [ ] | [ ] % |
| **Todos los campos** | [ ] | **[ ] %** |

- Fotos rechazadas por ilegibles: [ ] · Enviadas a revisión humana: [ ] · Confianza media del OCR: [ ] %
- **Guardadas sin revisión y con todo correcto: [ ] de [ ]** (mide si el sistema se equivoca cuando decide no pedir ayuda).
- Análisis: [qué campos fallan más y por qué; por ejemplo, la letra a mano baja la confianza del OCR y esas fotos van a revisión].

**Comprobación previa con imágenes simuladas** (no sustituye la prueba real): con 6 fotos generadas por computador con
inclinación, sombra, desenfoque y compresión, el OCR leyó correctamente el 93,3 % de los datos (28 de 30) y su confianza
media fue 92,2 % (modo `--solo-ocr`).

### 5.3 Prueba del plan B

| Escenario | Cómo se probó | Resultado |
|---|---|---|
| El primer modelo falla | prueba automática y en Render con clave inválida en `OPENROUTER_API_KEY` | responde el segundo modelo; el panel muestra «Respondió: gemini» |
| Todos los modelos fallan en un PDF | prueba automática | mensaje claro (503) y no se guarda nada a medias |
| Todos los modelos fallan en una foto | prueba automática | la foto queda en la cola de reintento; se procesa sola cuando la IA vuelve |
| Telegram caído | prueba automática | 3 reintentos; el candidato se guarda igual |

## 6. Seguridad y protección de datos personales

**Seguridad aplicada.** Inicio de sesión con contraseñas cifradas (PBKDF2, 200 000 iteraciones); sesión en cookie `HttpOnly`,
`SameSite=Lax` y `Secure` en HTTPS, firmada con `SESION_SECRETO` y con vencimiento a 8 horas; bloqueo de 5 minutos tras
5 intentos fallidos. Permisos por rol:

| Acción | admin | reclutador | consulta |
|---|:-:|:-:|:-:|
| Ver candidatos y lecturas, usar el asistente | sí | sí | sí |
| Subir PDF o fotos, confirmar o descartar lecturas, ver fotos | sí | sí | no |
| Ver ejecuciones y auditoría, crear usuarios, ejecutar tareas | sí | no | no |

Un acceso negado devuelve 403, la petición no llega al motor y queda auditada. La **tabla de auditoría** registra fecha,
usuario, rol, acción, recurso, resultado, IP y si **intervino la IA** (carga de PDF, lectura de fotos, confirmaciones,
chat y reintentos); su detalle solo guarda ids, estados, puntajes y confianzas, nunca nombres ni correos. Las claves de API
y los secretos viven en variables de entorno (`.env` en local, panel de Render en producción); `.env` está en `.gitignore`.

**Ley 1581 de 2012** (detalle en `docs/POLITICA_DATOS.md`):

| Principio | Cómo se cumple |
|---|---|
| Datos que se tratan | nombre, correo, teléfono, documento, dirección y fecha de nacimiento (en el archivo); formación y experiencia; puntaje; foto; usuario e IP de quien opera |
| Finalidad | evaluar la postulación al cargo y apoyar a Recursos Humanos; la decisión final es humana |
| Autorización | casilla obligatoria antes de subir; el servidor rechaza la carga sin ella (error 400) |
| Seguridad | roles, auditoría, HTTPS, fotos sin acceso público, enmascarado antes de la IA externa, OCR local |
| Transferencia | al proveedor de IA solo llega texto enmascarado; con Ollama nada sale del servidor |
| Minimización y supresión | lectura descartada = foto borrada; el registro de ejecuciones no guarda datos personales; `DELETE /api/candidatos/{id}` atiende la supresión |

## 7. Control de costos y despliegue

Todo funciona con planes gratuitos y sin tarjeta: Render (servidor Docker), Neon (PostgreSQL), modelos `:free` de OpenRouter
y niveles gratuitos de Gemini y Groq. Si una cuota se agota, el sistema cambia de modelo solo; si todas se agotan, responde
con un mensaje claro y las fotos esperan en la cola de reintento. Para no depender de cuotas se puede agregar Ollama en un
VPS (Oracle Cloud Free Tier). El despliegue está documentado en `DESPLIEGUE.md` (`Dockerfile` con Tesseract en español y
`render.yaml`). Comprobación: `/_salud` responde `{"estado": "ok"}`.

## 8. Limitaciones conocidas

- El OCR pierde precisión con letra a mano poco clara, fotos movidas o muy inclinadas; esos casos van a revisión humana.
- El enmascarado es por patrones: reduce mucho lo que sale del servidor, pero no garantiza el 100 % (por ejemplo, un
  nombre sin rótulo en medio del texto). El chat sí envía los nombres de los candidatos para poder citarlos.
- La presencia en el texto confirma que un valor existe, no que esté en el campo correcto; por eso la confianza final
  también depende de la IA y del OCR, y la revisión humana es la última barrera.
- En el plan gratuito de Render el disco no es permanente (las fotos se borran al redesplegar; los datos quedan en Neon) y el
  servicio se duerme tras 15 minutos: la primera visita tarda cerca de un minuto y las tareas programadas se pausan.
- Los modelos `:free` cambian de nombre y de cuota cada pocas semanas; por eso se usa `OPENROUTER_MODEL=openrouter/free`, que elige uno vigente. `python scripts/probar_ia.py` diagnostica cada proveedor.
- La memoria del chat vive en el servidor: se pierde al reiniciarlo.
- El puntaje es una estimación del modelo de lenguaje y puede tener sesgos; por eso no reemplaza la decisión de una persona.

## 9. Respuestas para la sustentación

- **¿Qué hacía n8n que ahora hace su código y cómo lo probaron?** Los tres flujos (carga, lista y chat) y sus nodos (Webhook,
  Extract from File, Information Extractor, Switch, Data Table, Telegram, Basic LLM Chain) son servicios en `app/services`.
  Se probaron con 91 pruebas automáticas (IA simulada) y en el sistema desplegado con la IA real.
- **¿Qué decisión toma la IA en el módulo de visión y qué pasa cuando se equivoca?** Estructura los datos de la foto y estima
  su confianza; el sistema decide si guarda solo o pide revisión. Si la IA inventa un dato, la verificación contra el texto
  baja la confianza y la persona lo corrige antes de guardar; al corregir, el puntaje se recalcula.
- **¿Qué datos personales procesa el sistema y cómo los protegen?** Sección 6: OCR local, enmascarado antes de la IA, roles,
  auditoría, fotos sin acceso público y borrado al descartar.
- **¿Qué ocurre si el modelo gratuito deja de responder?** Reintentos, cambio automático al siguiente modelo, mensaje claro si
  todos fallan y cola de reintento para las fotos (sección 5.3).
