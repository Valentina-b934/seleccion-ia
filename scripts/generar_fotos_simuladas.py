"""Genera fotos SIMULADAS de fichas de candidato (datos inventados) para comprobar que el evaluador funciona.

    python scripts/generar_fotos_simuladas.py

Crea evaluacion/fotos_simuladas/ con 6 imágenes y su etiquetas.csv. Imitan problemas de una foto de celular
(inclinación, sombra, desenfoque, ruido, compresión JPG), pero NO sustituyen las 20 fotos reales que exige la guía.
"""
import csv
import io
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

DESTINO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evaluacion", "fotos_simuladas")

FICHAS = [
    dict(nombre="Valentina Ríos Cárdenas", correo="valentina.rios@correo.com", cargo="Analista de datos",
         profesion="Estadística", experiencia_anios=3, habilidades="Python, SQL, Power BI, Excel",
         educacion="Estadística, Universidad Nacional", certificaciones="Google Data Analytics"),
    dict(nombre="Juan Camilo Ortiz", correo="jc.ortiz@correo.com", cargo="Desarrollador de software",
         profesion="Ingeniero de sistemas", experiencia_anios=5, habilidades="Java, Spring Boot, Docker, PostgreSQL",
         educacion="Ingeniería de Sistemas, UTP", certificaciones="Oracle Java SE 11"),
    dict(nombre="Luisa Fernanda Mejía", correo="luisa.mejia@correo.com", cargo="Auxiliar administrativo",
         profesion="Técnica en gestión administrativa", experiencia_anios=2,
         habilidades="Excel, atención al cliente, archivo, facturación", educacion="Técnico SENA en gestión administrativa",
         certificaciones="No indica"),
    dict(nombre="Santiago Herrera Duque", correo="s.herrera@correo.com", cargo="Técnico de soporte",
         profesion="Tecnólogo en redes", experiencia_anios=4, habilidades="Windows Server, redes, soporte técnico, Linux",
         educacion="Tecnología en Redes, SENA", certificaciones="CCNA"),
    dict(nombre="Daniela Castaño Gil", correo="daniela.castano@correo.com", cargo="Contador",
         profesion="Contadora pública", experiencia_anios=6, habilidades="NIIF, Siigo, impuestos, nómina",
         educacion="Contaduría Pública, Universidad del Quindío", certificaciones="Revisoría fiscal"),
    dict(nombre="Mateo Giraldo Pérez", correo="mateo.giraldo@correo.com", cargo="Asesor comercial",
         profesion="Administrador de empresas", experiencia_anios=1, habilidades="Ventas, negociación, CRM, servicio al cliente",
         educacion="Administración de Empresas, UCP", certificaciones="No indica"),
]
CAMPOS = ["archivo", "nombre", "correo", "cargo", "profesion", "experiencia_anios", "habilidades", "educacion",
          "certificaciones"]


def _fuente(tam):
    # Fuentes con tildes y eñes: DejaVu (Linux), Arial (Windows) o Liberation. Si no hay, la de Pillow.
    for nombre in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(nombre, tam)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:
        return ImageFont.load_default()


def hoja(f: dict) -> Image.Image:
    img = Image.new("RGB", (1240, 1600), (250, 249, 244))
    d = ImageDraw.Draw(img)
    d.text((80, 70), "FICHA DE INSCRIPCIÓN DE CANDIDATO", fill=(20, 20, 20), font=_fuente(44))
    d.line((80, 135, 1160, 135), fill=(60, 60, 60), width=3)
    filas = [
        ("Nombre", f["nombre"]), ("Correo", f["correo"]), ("Celular", f"31{random.randint(0, 9)} {random.randint(100, 999)} {random.randint(1000, 9999)}"),
        ("Cédula", f"{random.randint(10, 99)}.{random.randint(100, 999)}.{random.randint(100, 999)}"),
        ("Cargo al que aplica", f["cargo"]), ("Profesión", f["profesion"]),
        ("Años de experiencia", f"{f['experiencia_anios']} años"), ("Habilidades", f["habilidades"]),
        ("Educación", f["educacion"]), ("Certificaciones", f["certificaciones"]),
    ]
    y = 180
    for etiqueta, valor in filas:
        d.text((80, y), f"{etiqueta}:", fill=(40, 40, 40), font=_fuente(34))
        d.text((480, y), str(valor), fill=(15, 15, 60), font=_fuente(34))
        d.line((470, y + 46, 1160, y + 46), fill=(170, 170, 170), width=1)
        y += 110
    d.text((80, y + 30), "Autorizo el tratamiento de mis datos personales (Ley 1581 de 2012).", fill=(60, 60, 60),
           font=_fuente(26))
    return img


def como_foto(img: Image.Image, nivel: int) -> bytes:
    """nivel 0 = foto buena; 5 = foto difícil."""
    fondo = Image.new("RGB", (img.width + 300, img.height + 300), (90, 80, 70))
    fondo.paste(img, (150, 150))
    img = fondo.rotate(random.uniform(-2, 2) * (1 + nivel / 2), resample=Image.BICUBIC, fillcolor=(90, 80, 70))
    if nivel >= 2:  # sombra lateral
        sombra = Image.linear_gradient("L").rotate(90).resize(img.size)
        img = Image.composite(img, Image.new("RGB", img.size, (40, 40, 40)), sombra.point(lambda p: 255 - p * (0.25 + nivel * 0.05)))
    if nivel >= 3:
        img = img.filter(ImageFilter.GaussianBlur(0.6 + (nivel - 3) * 0.5))
    img = img.resize((int(img.width * 0.8), int(img.height * 0.8)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=max(45, 90 - nivel * 8))
    return buf.getvalue()


def main():
    random.seed(7)
    os.makedirs(DESTINO, exist_ok=True)
    with open(os.path.join(DESTINO, "etiquetas.csv"), "w", newline="", encoding="utf-8") as archivo:
        w = csv.DictWriter(archivo, fieldnames=CAMPOS)
        w.writeheader()
        for i, f in enumerate(FICHAS):
            nombre = f"simulada_{i + 1:02d}.jpg"
            with open(os.path.join(DESTINO, nombre), "wb") as salida:
                salida.write(como_foto(hoja(f), nivel=i))
            w.writerow({"archivo": nombre, **f})
    print(f"Listo: {len(FICHAS)} fotos simuladas en {DESTINO}")


if __name__ == "__main__":
    sys.exit(main())
