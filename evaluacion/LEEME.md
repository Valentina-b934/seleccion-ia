# Evaluación del módulo de visión con fotos reales

La guía exige probar con **20 o más imágenes reales tomadas con celular** y reportar el **% de acierto por campo**.
Esta carpeta trae todo para hacerlo en unos 40 minutos.

## 1. Preparar las fichas (15 min)

1. Imprime `ficha_en_blanco.pdf` unas 10 veces (o usa hojas de vida de prueba impresas).
2. Llénalas **a mano o en computador** con **datos inventados** (nunca datos reales de personas).
   Varíen: letra de distintos integrantes, profesiones, habilidades y si tienen o no certificaciones.

## 2. Tomar las fotos (10 min)

Con el celular, **20 fotos o más** (pueden ser 2 fotos por ficha en condiciones distintas). Para que la prueba sea honesta,
mezclen fotos buenas y difíciles:

| Tipo | Cuántas | Cómo |
|---|---|---|
| Buena | 10 | de frente, buena luz, hoja completa |
| Inclinada | 3 | con algo de ángulo |
| Con sombra | 3 | la mano o el celular hacen sombra |
| Poca luz o algo movida | 2 | de noche o con pulso |
| Letra a mano | 2 o más | ficha llenada con esfero |

En iPhone: Ajustes > Cámara > Formatos > «Más compatible» (JPG). Pasen las fotos al computador.

## 3. Etiquetar (10 min)

1. Creen la carpeta `evaluacion/fotos_reales/` y pongan ahí las fotos (`foto_01.jpg`, `foto_02.jpg`…).
2. Copien `etiquetas_plantilla.csv` como `evaluacion/fotos_reales/etiquetas.csv` y escriban **una fila por foto** con
   lo que **de verdad** dice la ficha (es la «respuesta correcta»). Ábranlo con Excel o un editor de texto y guárdenlo como CSV UTF-8.
   - `experiencia_anios`: solo el número.
   - `habilidades`: separadas por comas.
   - `certificaciones` o `educacion` vacías: escriban `No indica`.

Las fotos, `etiquetas.csv` y los resultados **sí se suben al repositorio**: son la evidencia de la prueba con imágenes reales.
Por eso las fichas deben llevar **solo datos inventados** (nunca datos reales de personas).

## 4. Ejecutar

```powershell
python scripts/evaluar.py evaluacion\fotos_reales            # OCR + IA (usa la cuota gratuita)
python scripts/evaluar.py evaluacion\fotos_reales --pausa 6  # si la cuota se agota (espera entre fotos)
python scripts/evaluar.py evaluacion\fotos_reales --solo-ocr # sin IA: solo mide la lectura
```

El script escribe `resultados_evaluacion.md` (tablas listas para pegar en el documento técnico) y
`resultados_evaluacion.csv` (detalle por foto y campo).

## Cómo se cuenta un acierto

| Campo | Es acierto si… |
|---|---|
| Profesión, educación, certificaciones | el texto se parece al esperado en 70 % o más (sin tildes ni mayúsculas) o lo contiene |
| Años de experiencia | el número es exactamente igual |
| Habilidades | la IA encontró al menos el 75 % de las habilidades esperadas |
| «No indica» | la IA también dijo que no aparece |

Una foto rechazada por ilegible cuenta como error en todos sus campos.

El informe también muestra **cuántas fotos fueron a revisión humana** y el dato más importante para la sustentación:
**de las fotos que el sistema guardó solo, cuántas tenían todo correcto** (si se equivoca, ¿lo detecta?).
Con esa cifra pueden ajustar `UMBRAL_OCR` y `UMBRAL_CAMPO` en `.env`.

## 5. Subir la evidencia

```powershell
git add evaluacion/fotos_reales
git commit -m "Evaluación con 20 fotos reales tomadas con celular"
git push
```

Luego copien las tablas de `resultados_evaluacion.md` en la sección 5.2 de `docs/DOCUMENTO_TECNICO.md`.

## archivos_demo/

PDF y fotos de demostración para el video (ver su LEEME). No reemplazan las fotos reales.

## fotos_simuladas/

6 imágenes generadas por computador (`python scripts/generar_fotos_simuladas.py`) con datos inventados, solo para
comprobar que el evaluador funciona. **No sustituyen las fotos reales.**
