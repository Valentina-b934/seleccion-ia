# Despliegue gratuito (Neon + Render)

Resultado: el panel, la API, el motor de flujos y el módulo de visión corriendo en una dirección pública con HTTPS,
por ejemplo `https://seleccion-ia.onrender.com`. Todo con planes gratuitos, sin tarjeta.

## 1. Base de datos en Neon (PostgreSQL gratuito)

1. Entra a neon.tech, crea una cuenta y un proyecto (región más cercana: AWS US East).
2. En **Connection details** copia la cadena de conexión. Se ve así:
   `postgresql://usuario:clave@ep-xxxx.us-east-2.aws.neon.tech/neondb?sslmode=require`
3. Cámbiale el inicio por `postgresql+psycopg://` (la capa de seguridad lo hace sola, pero `app/db.py` puede necesitarlo):
   `postgresql+psycopg://usuario:clave@ep-xxxx.us-east-2.aws.neon.tech/neondb?sslmode=require`

Las tablas (`candidatos`, `ejecuciones`, `lecturas_vision`, `usuarios`, `auditoria`) se crean solas al arrancar.

Para probar la conexión desde tu computador antes de desplegar: pon esa cadena en `DATABASE_URL` de tu `.env`,
ejecuta `pip install "psycopg[binary]"` y arranca con `uvicorn app.servidor:app`.

## 2. Subir el código a GitHub (con commits de todos los integrantes)

La guía exige **historial de commits de todos los integrantes**. Si ya tienen el repositorio de las semanas anteriores,
copien estos archivos encima y hagan commits separados por tema; si no, créenlo así:

```powershell
cd seleccion-ia
git init
git add .
git commit -m "Motor de automatización en código (reemplaza n8n)"
git branch -M main
git remote add origin https://github.com/USUARIO/seleccion-ia.git
git push -u origin main
```

Luego **cada integrante**, desde su propio computador y con su usuario de GitHub (`git config user.name` y `user.email`),
clona el repositorio y sube al menos un commit propio de la parte que va a explicar en la sustentación. Por ejemplo:
uno los resultados de la evaluación (`docs/DOCUMENTO_TECNICO.md`, sección 5), otro el enlace del despliegue y las
credenciales, otro los datos de la empresa en `docs/POLITICA_DATOS.md`.

`.gitignore` ya excluye `.env`, `data/` y `evaluacion/fotos_reales/`: las claves y las fotos nunca se suben.
El repositorio debe tener `Dockerfile` y `render.yaml` en la raíz de `seleccion-ia`.

## 3. Servidor en Render

1. Entra a render.com con tu cuenta de GitHub.
2. **New > Blueprint** y elige el repositorio. Render lee `render.yaml` y crea el servicio `seleccion-ia` con Docker.
   (Si el código está en una subcarpeta, usa **New > Web Service**, *Runtime* Docker, y en *Root Directory* escribe `seleccion-ia`.)
3. Llena las variables marcadas como manuales:

| Variable | Valor |
|---|---|
| `DATABASE_URL` | la cadena de Neon del paso 1 |
| `OPENROUTER_API_KEY` | tu clave de OpenRouter |
| `GOOGLE_API_KEY` | tu clave de Gemini (plan B) |
| `GROQ_API_KEY` | opcional, tercer modelo |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | opcional, los mismos de n8n |
| `CLAVE_ADMIN`, `CLAVE_RECLUTADOR`, `CLAVE_CONSULTA` | las claves de los usuarios de prueba que entregarán al docente |

`SESION_SECRETO` lo genera Render solo y `COOKIE_SEGURA` ya viene en `true`.

4. **Apply**. La primera construcción tarda de 5 a 10 minutos (instala Tesseract y las librerías).
5. Cuando diga *Live*, abre la dirección: debe aparecer el inicio de sesión.

## 4. Comprobación final

1. `https://tu-servicio.onrender.com/_salud` responde `{"estado": "ok"}`.
2. Entra como `reclutador`, sube un PDF de prueba y una foto tomada con el celular desde la misma dirección.
3. Pregunta algo en el Asistente y luego una pregunta de seguimiento («¿y qué estudió?»).
4. Entra como `consulta`: no debe aparecer la pestaña Cargar.
5. Entra como `admin` y abre **Auditoría**: deben verse los pasos anteriores con usuario, hora y la marca IA.
6. Para el plan B, cambia `OPENROUTER_API_KEY` por un valor inválido en Render, guarda y pregunta en el Asistente:
   debe responder con Gemini. Luego deja la clave buena.

## 5. Límites del plan gratuito (para el documento técnico)

- El servicio gratuito de Render **se duerme tras 15 minutos sin uso**; la primera visita tarda cerca de un minuto.
  Ábranlo unos minutos antes de la sustentación.
- El disco del servicio gratuito **no es permanente**: al reiniciar o volver a desplegar se borran las fotos de
  `data/imagenes`. Los datos (candidatos, lecturas, auditoría) sí quedan en Neon. Para la demostración basta;
  para conservar las fotos, usar un VPS (por ejemplo Oracle Cloud Free Tier) con la opción del punto 6.
- Mientras el servicio duerme, las **tareas programadas** (resumen diario y cola de reintento) no corren; se ponen al día
  en la siguiente visita (el resumen se envía una vez por día aunque sea tarde). En la demostración usen los botones de la
  pestaña Ejecuciones. En un VPS (punto 6) corren sin pausa.
- 512 MB de memoria: no alcanza para Ollama. El plan B en Render es Gemini o Groq; Ollama queda para correr en local.

## 6. Alternativa: VPS propio u Oracle Cloud Free Tier (disco permanente)

```bash
sudo apt update && sudo apt install -y docker.io
git clone <url-del-repositorio> && cd seleccion-ia
cp .env.example .env && nano .env        # claves, DATABASE_URL, COOKIE_SEGURA=true si hay HTTPS
sudo docker build -t seleccion-ia .
sudo docker run -d --name seleccion-ia --restart unless-stopped -p 80:8000 \
  --env-file .env -v $(pwd)/data:/app/data seleccion-ia
```

El volumen `-v $(pwd)/data:/app/data` conserva las fotos y la base SQLite si no usan Neon.
