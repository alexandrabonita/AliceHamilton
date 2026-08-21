import csv
import io
import requests
from database import SessionLocal
import models

SPREADSHEET_ID = "1SNKtgPK2W1adPuyWpPnNTONX_faoje50dQ4n3yyt8vk"

def obtener_datos_hoja(sheet_name=None):
    if sheet_name:
        url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    else:
        url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv"
    
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    response.encoding = 'utf-8'
    if response.status_code != 200:
        return []
    return list(csv.reader(io.StringIO(response.text)))

def sincronizar_base_de_datos():
    db = SessionLocal()
    filas = obtener_datos_hoja()
    if not filas:
        print("No se pudieron obtener datos del Google Sheet.")
        return

    # Lista de actividades de ejemplo si no están en el sheet
    actividades_ejemplo = [
        "Ballet", "Gimnasia", "Natación", "Arte y pintura", "Danza", 
        "Fútbol", "Taekwondo", "Música", "Robótica / Fútbol", "Patinaje", 
        "Ajedrez infantil", "Natación"
    ]

    for idx, row in enumerate(filas):
        if len(row) < 2 or not row[1].strip() or "Nombre Completo" in row[1] or "DATOS BÁSICOS" in row[0]:
            continue

        nombre = row[1].strip()
        cumpleanos = row[2].strip() if len(row) > 2 else ""
        edad = int(row[3].strip()) if len(row) > 3 and row[3].strip().isdigit() else 5
        tutor_nombre = row[4].strip() if len(row) > 4 else ""
        tutor_telefono = row[5].strip() if len(row) > 5 else ""
        alergias = row[7].strip() if len(row) > 7 and row[7].strip() else "Ninguna reportada"
        cuidados = row[11].strip() if len(row) > 11 and row[11].strip() else "Ninguno"
        color = row[12].strip() if len(row) > 12 else ""
        personaje = row[13].strip() if len(row) > 13 else ""
        festeja = row[16].strip() if len(row) > 16 and row[16].strip() else "Por confirmar"
        talla = row[19].strip() if len(row) > 19 and row[19].strip() else "Talla 6"
        extra = row[20].strip() if len(row) > 20 and row[20].strip() else actividades_ejemplo[idx % len(actividades_ejemplo)]

        alumno = db.query(models.Alumno).filter(models.Alumno.nombre == nombre).first()
        if alumno:
            alumno.cumpleanos = cumpleanos
            alumno.edad = edad
            alumno.tutor_nombre = tutor_nombre
            alumno.tutor_telefono = tutor_telefono
            alumno.alergias = alergias
            alumno.cuidados_medicos = cuidados
            alumno.color_favorito = color
            alumno.personaje_favorito = personaje
            alumno.festeja_escuela = festeja
            alumno.talla = talla
            alumno.extraescolar = extra
        else:
            db.add(models.Alumno(
                nombre=nombre, cumpleanos=cumpleanos, edad=edad,
                tutor_nombre=tutor_nombre, tutor_telefono=tutor_telefono,
                alergias=alergias, cuidados_medicos=cuidados,
                color_favorito=color, personaje_favorito=personaje,
                festeja_escuela=festeja, talla=talla, extraescolar=extra
            ))

    # Sembrar datos iniciales de Eventos y Escuela para Padres si no existen
    if db.query(models.Evento).count() == 0:
        db.add(models.Evento(
            titulo="Festejo de Cumpleaños del Mes",
            fecha="28 de Octubre",
            lugar="Patio Central Kínder",
            tipo="Festejo",
            descripcion="Convivio para los cumpleañeros del mes. Recuerden checar la lista de alergias antes de enviar postres."
        ))
        db.add(models.Evento(
            titulo="Festival de Primavera & Disfraces",
            fecha="15 de Noviembre",
            lugar="Auditorio Escolar",
            tipo="Festival",
            descripcion="Presentación artística de los alumnos. Vestuario y detalles coordinados con vocales."
        ))

    if db.query(models.CursoTaller).count() == 0:
        db.add(models.CursoTaller(
            titulo="Taller: Loncheras Saludables y Nutrición Infantil",
            instructor="Lic. Fernanda Ramírez (Nutrióloga / Mamá del grupo)",
            tipo="Escuela para Padres",
            descripcion="Consejos prácticos para preparar loncheras balanceadas, nutritivas y atractivas para niños de preescolar.",
            enlace_recurso="https://youtube.com"
        ))
        db.add(models.CursoTaller(
            titulo="Taller de Manualidades y Moños con Listón",
            instructor="Jaqueline Orozco (Emprendedora / Mamá del grupo)",
            tipo="Taller Práctico",
            descripcion="Aprende técnicas básicas de creación de accesorios y adornos infantiles para eventos.",
            enlace_recurso="https://drive.google.com"
        ))

    db.commit()
    db.close()
    print("¡Sincronización completa con datos extraescolares, eventos y cursos!")

if __name__ == "__main__":
    sincronizar_base_de_datos()