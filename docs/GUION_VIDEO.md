# Guion del video de demostración (máximo 8 minutos)

Graben con el **sistema desplegado** (la dirección de Render visible en el navegador). Abran el enlace 2 minutos antes:
el plan gratuito se duerme y la primera visita tarda cerca de un minuto.

**Preparar antes de grabar**
- 2 hojas de vida en PDF de prueba y 3 fotos de fichas tomadas con el celular: una buena, una con sombra o inclinada
  (para que pida revisión) y, si quieren mostrarlo, una muy borrosa (para el rechazo).
- El celular con el enlace abierto y la sesión de `reclutador` iniciada (para la toma de foto en vivo).
- Telegram abierto en el computador o en el celular, en el chat que recibe los avisos.
- En Render, la pestaña Environment lista para cambiar `OPENROUTER_API_KEY` (prueba del plan B).

| Tiempo | Qué se muestra | Qué se dice (idea, no leer) |
|---|---|---|
| 0:00 – 0:40 | Diapositiva o README: problema y arquitectura | «Antes usábamos n8n en la nube; ahora el motor es código Python con FastAPI, la IA son modelos gratuitos con LangChain y agregamos un módulo de visión para las fichas en papel.» |
| 0:40 – 1:10 | Página de login; entrar como `reclutador` | Inicio de sesión con roles; cada acción queda auditada. |
| 1:10 – 2:10 | **Flujo 1:** pestaña Cargar, subir los 2 PDF con nombre y correo, marcar la autorización, enviar | El PDF se lee en el servidor, se ocultan los datos personales y la IA asigna puntaje. Mostrar el resultado: «Guardado como CAN-…, puntaje, estado, IA: openrouter». Mostrar el aviso en **Telegram**. |
| 2:10 – 3:40 | **Visión con el celular:** en el celular, «Tomar foto con la cámara», fotografiar la ficha buena, enviar | OCR local con Tesseract; la imagen no sale del servidor. Lectura confiable → candidato creado y aviso de Telegram: **la visión dispara el proceso**. |
| 3:40 – 4:50 | **Revisión humana:** subir la foto con sombra o inclinada desde el computador | Se abre la revisión: foto al lado, campos con su confianza y los dudosos en rojo. Corregir un campo y «Confirmar y guardar»: la IA recalcula el puntaje. (Opcional: foto borrosa → rechazo con consejo.) |
| 4:50 – 5:30 | Pestaña Candidatos | Filtros, chips de estado, origen «Foto · visión», «Ver foto original». |
| 5:30 – 6:20 | **Chatbot:** «¿Quién tiene el mejor puntaje?» y luego «¿Y qué estudió?»; luego «¿Qué candidatos llegaron por foto?» | El chat recuerda la conversación y **usa el resultado de la visión**. |
| 6:20 – 6:50 | **Plan B:** en Render poner una clave inválida en `OPENROUTER_API_KEY`, guardar (Render reinicia en 1 a 3 minutos: corten la espera) y preguntar de nuevo | El sistema cambia solo a Gemini: debajo de la respuesta dice «Respondió: gemini». (Después dejar la clave buena.) |
| 6:50 – 7:30 | Salir y entrar como `consulta`; luego como `admin` | `consulta` no ve la pestaña Cargar. `admin`: pestaña **Ejecuciones** (fecha, entrada, resultado de cada flujo, «Enviar resumen ahora» → llega el resumen a Telegram) y página **Auditoría** con «Solo acciones de la IA». |
| 7:30 – 8:00 | Terminal con `pytest` (91 aprobadas) y el informe de `scripts/evaluar.py` con las 20 fotos | «Probamos con N fotos reales: X % de acierto por campo. Si la IA gratuita falla, hay reintentos, cambio de modelo y cola de reintento.» |

**Consejos:** graben en 1080p, con el zoom del navegador al 110 %, y corten las esperas de la IA en la edición.
Si una cuota gratuita se agota durante la grabación, aprovéchenlo: es la demostración del plan B.
