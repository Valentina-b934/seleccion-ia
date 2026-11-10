"""El texto de los PDF sale hacia la IA externa sin datos personales."""
from app.services.privacidad import enmascarar_texto

HOJA = """Laura Marcela Pérez Gómez
Ingeniera de sistemas
Correo: laura.perez@gmail.com   Celular: 315 678 9012
C.C. 1.098.765.432 de Bucaramanga
Dirección: Calle 45 # 27-30, barrio Sotomayor
Fecha de nacimiento: 12/05/1998
LinkedIn: linkedin.com/in/laura-perez

Perfil: desarrolladora con 4 años de experiencia en Python y SQL.
Experiencia: Analista de datos en Acme S.A.S. (2021 a 2025).
Educación: Ingeniería de Sistemas, UIS (2020).
Referencia: Laura Pérez trabajó con nosotros. Tel. (607) 634 5678
"""


def test_quita_los_datos_personales():
    texto = enmascarar_texto(HOJA)
    for dato in ("laura.perez@gmail.com", "315 678 9012", "1.098.765.432", "Calle 45", "12/05/1998",
                 "linkedin.com/in", "Laura", "Pérez", "634 5678"):
        assert dato not in texto, dato
    for marca in ("[CORREO]", "[TELEFONO]", "[DOCUMENTO]", "[DIRECCION]", "[FECHA_NACIMIENTO]", "[NOMBRE]"):
        assert marca in texto, marca


def test_conserva_lo_que_se_necesita_para_evaluar():
    texto = enmascarar_texto(HOJA)
    for dato in ("Ingeniera de sistemas", "4 años", "Python y SQL", "Analista de datos", "2021 a 2025", "UIS (2020)"):
        assert dato in texto, dato


def test_un_cargo_en_la_primera_linea_no_se_toma_como_nombre():
    texto = enmascarar_texto("INGENIERO DE SISTEMAS\nExperiencia en Java y Spring Boot")
    assert "INGENIERO DE SISTEMAS" in texto and "[NOMBRE]" not in texto


def test_nombre_rotulado_y_texto_vacio():
    assert "Carlos" not in enmascarar_texto("Nombre: Carlos Rojas\nCarlos lideró el equipo")
    assert enmascarar_texto("") == ""
