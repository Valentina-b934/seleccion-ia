# Archivos de demostración (todos los datos son inventados)

Estos archivos sirven para la demostración y el video. **No son** las 20 fotos reales con celular que exige la guía:
esas van en `evaluacion/fotos_reales/` (ver `evaluacion/LEEME.md`).

Súbelos en la pestaña **Cargar** con el usuario `reclutador`. Marca la autorización de datos y escribe el nombre y el
correo de cada candidato tal como aparecen abajo.

| Archivo | Nombre | Correo | Cargo sugerido | Qué debe pasar |
|---|---|---|---|---|
| 01_PDF_alto_Camila_Restrepo.pdf | Camila Andrea Restrepo Vélez | camila.restrepo@correo.com | Desarrollador de software | Puntaje alto (80 o más) → **Preseleccionado** |
| 02_PDF_medio_Andres_Salazar.pdf | Andrés Felipe Salazar Mora | andres.salazar@correo.com | Desarrollador de software | Puntaje medio (60 a 79) → **En revisión** |
| 03_PDF_bajo_Paula_Ocampo.pdf | Paula Ocampo Giraldo | paula.ocampo@correo.com | Desarrollador de software | Puntaje bajo (menos de 60) → **Descartado** |
| 04_FOTO_buena_Sebastian_Marin.jpg | Sebastián Marín Loaiza | sebastian.marin@correo.com | Analista de datos | Lectura confiable → se guarda solo (Foto · visión) |
| 05_FOTO_revision_Natalia_Gomez.jpg | Natalia Gómez Arango | natalia.gomez@correo.com | Contador | Foto borrosa y con sombra → se abre la **revisión humana** |
| 06_FOTO_ilegible.jpg | Natalia Gómez Arango | natalia.gomez@correo.com | Contador | **Rechazada** con el consejo de repetir la foto (no llama a la IA) |
| 08_FOTO_buena_Mariana_Valencia.jpg | Mariana Valencia Torres | mariana.valencia@correo.com | Desarrollador de software | Lectura confiable → se guarda solo (Foto · visión) |
| 07_PDF_escaneado_sin_texto.pdf | Sebastián Marín Loaiza | sebastian.marin@correo.com | Analista de datos | Error claro: «parece escaneado, súbelo como foto» |

El puntaje lo pone la IA, así que los números pueden variar un poco de una vez a otra.

## Datos correctos para la revisión de la foto 05

En la ventana de revisión, corrige los campos con estos valores y pulsa **Confirmar y guardar**. La IA vuelve a calcular el puntaje:

- Profesión: Contadora pública
- Años de experiencia: 5
- Habilidades: NIIF, Siigo, nómina, impuestos
- Educación: Contaduría Pública, Universidad Libre
- Certificaciones: No indica

## Después, en el Asistente

- ¿Quién tiene el mejor puntaje?
- ¿Y qué estudió? (prueba la memoria del chat)
- ¿Qué candidatos llegaron por foto?
- ¿Hay fotos pendientes de revisión? (usa «Revisar después» en una foto para probarlo)

## Para la prueba con celular

Abre `04_FOTO_buena_Sebastian_Marin.jpg` en la pantalla del computador o imprímela, y tómale una foto con el celular desde
el botón **Tomar foto con la cámara**. Para hacerlo desde el celular, el servidor tiene que estar desplegado en Render o
correr en tu red con `uvicorn app.servidor:app --host 0.0.0.0` (y abrir `http://IP-de-tu-PC:8000` en el celular).
