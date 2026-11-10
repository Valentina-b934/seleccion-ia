# Política de tratamiento de datos personales del sistema de selección de personal

Marco legal: Ley 1581 de 2012 y Decreto 1377 de 2013 (compilado en el Decreto 1074 de 2015).
Completen los datos entre corchetes con los de la empresa del proyecto.

## Responsable

[Nombre de la empresa], NIT [número], [dirección], correo [correo de contacto para habeas data].

## Datos que trata el sistema

| Dato | Dónde aparece | Tipo |
|---|---|---|
| Nombre y correo del candidato | Formulario de carga, tabla `candidatos` | Personal |
| Teléfono, documento, dirección, fecha de nacimiento | Dentro del PDF o la foto de la hoja de vida | Personal |
| Profesión, experiencia, estudios, habilidades, certificaciones | Extraídos por la IA | Personal (laboral) |
| Puntaje, justificación y estado del proceso | Generados por el sistema | Personal (evaluación) |
| Foto del formulario | Carpeta `data/imagenes`, tabla `lecturas_vision` | Personal |
| Usuario, rol, IP y acciones de quien usa el sistema | Tablas `usuarios` y `auditoria` | Personal (trazabilidad) |

El sistema no pide datos sensibles (salud, origen étnico, orientación, datos biométricos para identificar).
Si una hoja de vida los trae, no se extraen ni se usan para el puntaje.

## Finalidad

Evaluar la postulación del candidato al cargo, ordenar los candidatos por ajuste al perfil, avisar al equipo de
Recursos Humanos y responder sus consultas. El puntaje es una ayuda: **la decisión final la toma una persona**.

## Autorización

Antes de cargar una hoja de vida, quien la sube debe marcar que el candidato autorizó el tratamiento de sus datos
(campo `Autorizacion`); el panel exige esa marca para enviar. La empresa conserva la autorización firmada
por el candidato.

## Seguridad aplicada

- Inicio de sesión con contraseña cifrada (PBKDF2) y permisos por rol (admin, reclutador, consulta).
- Bloqueo temporal tras 5 intentos fallidos y sesiones que vencen a las 8 horas.
- Las fotos se leen con OCR dentro del servidor; se guardan con nombre aleatorio, fuera de la carpeta pública,
  y solo se entregan a usuarios con permiso. Se registra quién las subió, quién las revisó y cuándo.
- Al modelo de IA externo (OpenRouter, Groq o Gemini) solo llega texto con correo, teléfono, documento, dirección,
  fecha de nacimiento y nombre ocultos. El chat sí comparte el nombre de los candidatos guardados.
- Registro de auditoría de cada acción, sin guardar correos, teléfonos ni nombres en el detalle.
- Claves de API y secretos en variables de entorno, nunca en el código. HTTPS en el despliegue.

## Transferencia y transmisión

El texto enmascarado se procesa en servidores de proveedores de IA ubicados fuera de Colombia, que pueden conservarlo
según sus términos. Por eso se ocultan los datos de contacto e identificación antes de enviarlo. Si se requiere que
ningún dato salga del servidor, se configura Ollama como modelo local.

## Conservación

Las lecturas descartadas borran su foto de inmediato. [Definir el plazo: por ejemplo, los datos de candidatos no
seleccionados se eliminan a los 6 meses de cerrado el proceso.]

## Derechos del titular

El candidato puede conocer, actualizar, rectificar y pedir la supresión de sus datos, revocar la autorización y
quejarse ante la Superintendencia de Industria y Comercio. Las solicitudes se reciben en [correo] y se responden en
los plazos de ley: consultas en 10 días hábiles y reclamos en 15 días hábiles.
