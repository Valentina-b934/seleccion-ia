"""Mide el acierto del módulo de visión con fotos reales (requisito: 20 o más fotos y % de acierto por campo).

    python scripts/evaluar.py evaluacion\\fotos_reales                 (OCR + IA real de .env)
    python scripts/evaluar.py evaluacion\\fotos_reales --pausa 6       (espera entre fotos si la cuota gratuita se agota)
    python scripts/evaluar.py evaluacion\\fotos_simuladas --solo-ocr   (sin IA: solo mide si el OCR leyó cada dato)

La carpeta debe tener las fotos y un etiquetas.csv con lo que de verdad dice cada foto
(ver evaluacion/LEEME.md). El script no crea candidatos: usa el mismo procesamiento del sistema
(OCR, enmascarado, IA, confianza por campo y regla de revisión) y compara con las etiquetas.

Escribe en la carpeta: resultados_evaluacion.md (resumen para el documento técnico) y resultados_evaluacion.csv.
"""
import argparse
import csv
import difflib
import io
import os
import statistics
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from app.config import settings  # noqa: E402
from app.errores import ServicioIANoDisponible  # noqa: E402
from app.services import lectura, llm, vision  # noqa: E402
from app.services.llm import CAMPOS_VISION  # noqa: E402
from app.services.privacidad import enmascarar_texto  # noqa: E402

EXTENSIONES = (".jpg", ".jpeg", ".png", ".webp")
NOMBRES = vision.NOMBRES_CAMPOS


# ───────────────────────── Comparación de campos ─────────────────────────
def normal(t) -> str:
    t = unicodedata.normalize("NFD", str(t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join("".join(c if c.isalnum() or c in "+#" else " " for c in t).split())


def parecido(a, b) -> float:
    a, b = normal(a), normal(b)
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def lista(t) -> list[str]:
    return [normal(x) for x in str(t or "").replace(";", ",").split(",") if normal(x)]


def cobertura_habilidades(esperado, obtenido) -> float:
    """Qué parte de las habilidades esperadas encontró la IA (tolerando pequeñas diferencias de escritura)."""
    esp, obt = lista(esperado), lista(obtenido)
    if not esp:
        return 1.0 if not obt or vision.vacio(obtenido) else 0.0
    return sum(1 for e in esp if any(parecido(e, o) >= 0.8 or e in o or o in e for o in obt)) / len(esp)


def acierto(campo: str, esperado, obtenido) -> bool:
    if campo == "experiencia_anios":
        try:
            return int(float(esperado)) == int(float(obtenido))
        except (TypeError, ValueError):
            return False
    if vision.vacio(esperado):
        return vision.vacio(obtenido)
    if campo == "habilidades":
        return cobertura_habilidades(esperado, obtenido) >= 0.75
    a, b = normal(esperado), normal(obtenido)
    return parecido(a, b) >= 0.7 or (len(a) >= 4 and a in b)


def leido_por_ocr(campo: str, esperado, texto: str) -> bool:
    """Modo --solo-ocr: ¿el texto del OCR contiene el dato esperado?"""
    if campo == "experiencia_anios":
        return str(esperado).strip() in texto
    if vision.vacio(esperado):
        return True
    return vision.presencia(campo, esperado, texto) >= 0.75


# ───────────────────────── Evaluación ─────────────────────────
def leer_etiquetas(carpeta: str) -> list[dict]:
    ruta = os.path.join(carpeta, "etiquetas.csv")
    if not os.path.exists(ruta):
        sys.exit(f"No encontré {ruta}. Copia evaluacion/etiquetas_plantilla.csv y llénalo (ver evaluacion/LEEME.md).")
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        filas = [{k.strip(): (v or "").strip() for k, v in fila.items()} for fila in csv.DictReader(f)]
    faltan = [f["archivo"] for f in filas if not os.path.exists(os.path.join(carpeta, f["archivo"]))]
    if faltan:
        sys.exit(f"Estas fotos del CSV no están en la carpeta: {', '.join(faltan)}")
    return filas


def evaluar_foto(carpeta: str, et: dict, solo_ocr: bool) -> dict:
    fila = {"archivo": et["archivo"], "estado": "", "confianza_ocr": "", "requiere_revision": "", "modelo": "",
            "segundos": ""}
    inicio = time.perf_counter()
    with open(os.path.join(carpeta, et["archivo"]), "rb") as f:
        imagen = Image.open(io.BytesIO(f.read()))
        imagen.load()
    ocr = lectura.leer(imagen)
    fila["confianza_ocr"] = ocr.confianza
    if ocr.confianza < settings.umbral_ocr_minimo or ocr.palabras < vision.MIN_PALABRAS:
        fila["estado"] = "ilegible"
        for c in CAMPOS_VISION:
            fila[f"{c}_ok"] = 0
        fila["segundos"] = round(time.perf_counter() - inicio, 1)
        return fila

    if solo_ocr:
        fila["estado"] = "leida"
        for c in CAMPOS_VISION:
            fila[f"{c}_esperado"] = et.get(c, "")
            fila[f"{c}_ok"] = int(leido_por_ocr(c, et.get(c, ""), ocr.texto))
    else:
        texto = enmascarar_texto(ocr.texto, nombres_conocidos=[et.get("nombre", "")],
                                 correos_conocidos=[et.get("correo", "")])
        r = vision._interpretar(texto, et.get("cargo") or "Sin cargo", ocr.confianza)
        fila.update(estado="interpretada", requiere_revision=int(bool(r["motivos"])), modelo=r["modelo"])
        for c in CAMPOS_VISION:
            fila[f"{c}_esperado"] = et.get(c, "")
            fila[f"{c}_obtenido"] = r["campos"].get(c, "")
            fila[f"{c}_confianza"] = r["confianza"].get(c, 0)
            fila[f"{c}_ok"] = int(acierto(c, et.get(c, ""), r["campos"].get(c, "")))
        fila["habilidades_cobertura"] = round(cobertura_habilidades(et.get("habilidades"), r["campos"].get("habilidades")), 3)
    fila["segundos"] = round(time.perf_counter() - inicio, 1)
    return fila


def porcentaje(n, total) -> str:
    return f"{(100 * n / total):.1f} %" if total else "—"


def informe(carpeta: str, filas: list[dict], solo_ocr: bool) -> str:
    total = len(filas)
    validas = [f for f in filas if f["estado"] != "ilegible"]
    lineas = [
        "# Resultados de la evaluación del módulo de visión",
        "",
        f"- Carpeta: `{os.path.basename(os.path.normpath(carpeta))}` · Fotos evaluadas: **{total}**",
        f"- Modo: {'solo OCR (sin IA)' if solo_ocr else 'OCR + IA (' + ', '.join(sorted({f['modelo'] for f in validas if f.get('modelo')})) + ')'}",
        f"- Fecha: {time.strftime('%Y-%m-%d %H:%M')}",
        f"- Umbrales: OCR mínimo {settings.umbral_ocr_minimo}, OCR para revisión {settings.umbral_ocr}, campo {settings.umbral_campo}",
        "",
        "## Acierto por campo",
        "",
        "| Campo | Aciertos | % de acierto |",
        "|---|---:|---:|",
    ]
    total_ok = 0
    for c in CAMPOS_VISION:
        ok = sum(int(f.get(f"{c}_ok", 0)) for f in filas)
        total_ok += ok
        lineas.append(f"| {NOMBRES[c].capitalize()} | {ok} de {total} | {porcentaje(ok, total)} |")
    lineas.append(f"| **Todos los campos** | {total_ok} de {total * len(CAMPOS_VISION)} | **{porcentaje(total_ok, total * len(CAMPOS_VISION))}** |")
    lineas += ["", "Las fotos ilegibles cuentan como error en todos sus campos.", "", "## Lectura y decisión", ""]
    ilegibles = total - len(validas)
    confs = [float(f["confianza_ocr"]) for f in filas if f["confianza_ocr"] != ""]
    lineas.append(f"- Fotos rechazadas por ilegibles: {ilegibles} ({porcentaje(ilegibles, total)})")
    if confs:
        lineas.append(f"- Confianza media del OCR: {statistics.mean(confs) * 100:.1f} % "
                      f"(mínima {min(confs) * 100:.1f} %, máxima {max(confs) * 100:.1f} %)")
    if not solo_ocr and validas:
        revision = sum(int(f["requiere_revision"] or 0) for f in validas)
        lineas.append(f"- Enviadas a revisión humana: {revision} de {len(validas)} ({porcentaje(revision, len(validas))})")
        perfectas = [f for f in validas if all(int(f[f"{c}_ok"]) for c in CAMPOS_VISION)]
        auto = [f for f in validas if not int(f["requiere_revision"] or 0)]
        auto_ok = [f for f in auto if all(int(f[f"{c}_ok"]) for c in CAMPOS_VISION)]
        lineas.append(f"- Fotos con todos los campos correctos: {len(perfectas)} ({porcentaje(len(perfectas), len(validas))})")
        lineas.append(f"- Guardadas sin revisión y con todo correcto: {len(auto_ok)} de {len(auto)} "
                      f"({porcentaje(len(auto_ok), len(auto))}). Este es el número clave: mide si el sistema se equivoca "
                      "cuando decide no pedir ayuda.")
        cob = [float(f["habilidades_cobertura"]) for f in validas]
        lineas.append(f"- Cobertura media de habilidades: {statistics.mean(cob) * 100:.1f} %")
        # Calibración: ¿la confianza alta acierta más que la baja?
        altos = [(int(f[f"{c}_ok"])) for f in validas for c in CAMPOS_VISION if float(f[f"{c}_confianza"]) >= settings.umbral_campo]
        bajos = [(int(f[f"{c}_ok"])) for f in validas for c in CAMPOS_VISION if float(f[f"{c}_confianza"]) < settings.umbral_campo]
        lineas += ["", "## Calibración de la confianza", "",
                   f"- Campos con confianza ≥ {settings.umbral_campo}: {len(altos)}, acierto {porcentaje(sum(altos), len(altos))}",
                   f"- Campos con confianza < {settings.umbral_campo}: {len(bajos)}, acierto {porcentaje(sum(bajos), len(bajos))}",
                   "", "Si los campos de confianza baja aciertan casi tanto como los de alta, suban UMBRAL_CAMPO; "
                   "si los de confianza alta fallan seguido, súbanlo también o revisen UMBRAL_OCR."]
    lineas += ["", "## Detalle por foto", "", "| Foto | Estado | OCR | " + " | ".join(NOMBRES[c].capitalize() for c in CAMPOS_VISION) + " |",
               "|---|---|---:|" + "---|" * len(CAMPOS_VISION)]
    for f in filas:
        conf = f"{float(f['confianza_ocr']) * 100:.0f} %" if f["confianza_ocr"] != "" else "—"
        estado = f["estado"] + (" · revisión" if f.get("requiere_revision") == 1 else "")
        lineas.append(f"| {f['archivo']} | {estado} | {conf} | " + " | ".join("✔" if int(f.get(f"{c}_ok", 0)) else "✘" for c in CAMPOS_VISION) + " |")
    if total < 20:
        lineas += ["", f"> Atención: la guía pide al menos 20 fotos reales; aquí hay {total}."]
    return "\n".join(lineas) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Evalúa el módulo de visión con fotos etiquetadas.")
    p.add_argument("carpeta")
    p.add_argument("--pausa", type=float, default=0, help="segundos de espera entre fotos (cuota gratuita)")
    p.add_argument("--solo-ocr", action="store_true", help="no llama a la IA: mide solo la lectura del OCR")
    a = p.parse_args(argv)

    if not lectura.tesseract_disponible():
        sys.exit("Tesseract no está instalado. Ver README, sección 6.1.")
    if not a.solo_ocr and not llm.nombres_modelos():
        sys.exit("No hay claves de IA en .env. Agrega una o usa --solo-ocr.")
    etiquetas = leer_etiquetas(a.carpeta)
    fotos = [f for f in os.listdir(a.carpeta) if f.lower().endswith(EXTENSIONES)]
    sin_etiqueta = sorted(set(fotos) - {e["archivo"] for e in etiquetas})
    if sin_etiqueta:
        print(f"Aviso: estas fotos no están en etiquetas.csv y no se evalúan: {', '.join(sin_etiqueta)}")

    filas = []
    for i, et in enumerate(etiquetas, 1):
        print(f"[{i}/{len(etiquetas)}] {et['archivo']} … ", end="", flush=True)
        for intento in range(3):
            try:
                fila = evaluar_foto(a.carpeta, et, a.solo_ocr)
                break
            except ServicioIANoDisponible:
                espera = max(a.pausa, 20) * (intento + 1)
                print(f"la IA no respondió, espero {espera:.0f} s … ", end="", flush=True)
                time.sleep(espera)
        else:
            sys.exit("\nLa IA no respondió tras varios intentos (cuota agotada). Vuelve a intentarlo más tarde o usa --pausa.")
        ok = sum(int(fila.get(f"{c}_ok", 0)) for c in CAMPOS_VISION)
        print(f"{fila['estado']} · {ok}/{len(CAMPOS_VISION)} campos correctos")
        filas.append(fila)
        if a.pausa and i < len(etiquetas):
            time.sleep(a.pausa)

    texto = informe(a.carpeta, filas, a.solo_ocr)
    with open(os.path.join(a.carpeta, "resultados_evaluacion.md"), "w", encoding="utf-8") as f:
        f.write(texto)
    columnas = list(dict.fromkeys(k for fila in filas for k in fila))
    with open(os.path.join(a.carpeta, "resultados_evaluacion.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)
    print("\n" + texto)
    print(f"Guardado en {os.path.join(a.carpeta, 'resultados_evaluacion.md')} y .csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
