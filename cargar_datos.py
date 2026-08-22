import csv
import io
import urllib.parse
import unicodedata
import requests
from database import SessionLocal
import models

SPREADSHEET_ID = "1SNKtgPK2W1adPuyWpPnNTONX_faoje50dQ4n3yyt8vk"
APPS_SCRIPT_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxNHwjdFpXjvk9xRjdqfgHQPLRXBDcQRE1YQ8OvL9Ffv_nDPai2YOKc5PS5b94K1_EHLQ/exec"

MESES_MAP = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
}

def normalizar_texto(texto: str) -> str:
    return " ".join(texto.strip().split()) if texto else ""

def simplificar_nombre(nombre: str) -> set:
    if not nombre:
        return set()
    nombre_limpio = unicodedata.normalize('NFKD', nombre).encode('ASCII', 'ignore').decode('utf-8').lower()
    return set(nombre_limpio.split())

def armar_fecha_iso(mes_str: str, dia_str: str, anio_str: str = "2026") -> str:
    if not mes_str or not dia_str:
        return ""
    m_clean = mes_str.lower().strip()
    mes_num = MESES_MAP.get(m_clean, m_clean.zfill(2) if m_clean.isdigit() else "01")
    dia_num = dia_str.strip().zfill(2)
    anio_num = anio_str.strip() if anio_str and anio_str.strip().isdigit() else "2026"
    return f"{anio_num}-{mes_num}-{dia_num}"

def obtener_filas_pestana(nombre_pestana: str):
    sheet_encoded = urllib.parse.quote(nombre_pestana)
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet={sheet_encoded}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=12)
        res.encoding = 'utf-8'
        if res.status_code == 200:
            return list(csv.reader(io.StringIO(res.text)))
    except Exception as e:
        print(f"Error al descargar '{nombre_pestana}': {e}")
    return []

def extraer_datos_alumno_fila(row):
    """Extrae de forma segura los valores de las columnas del Google Sheet."""
    nombre = normalizar_texto(row[1]) if len(row) > 1 else ""
    cumple = normalizar_texto(row[2]) if len(row) > 2 else ""
    edad = int(row[3].strip()) if len(row) > 3 and row[3].strip().isdigit() else 5
    tutor_nombre = normalizar_texto(row[4]) if len(row) > 4 else ""
    tutor_tel = normalizar_texto(row[5]) if len(row) > 5 else ""
    alergias = normalizar_texto(row[7]) if len(row) > 7 and row[7].strip() else "Ninguna reportada"
    cuidados = normalizar_texto(row[11]) if len(row) > 11 and row[11].strip() else "Ninguno"
    color = normalizar_texto(row[12]) if len(row) > 12 else ""
    personaje = normalizar_texto(row[13]) if len(row) > 13 else ""
    festeja = normalizar_texto(row[16]) if len(row) > 16 and row[16].strip() else "Por confirmar"
    talla = normalizar_texto(row[19]) if len(row) > 19 and row[19].strip() else "Talla 6"
    
    # Extraescolar se ubica comúnmente en la columna 20 o 21 (Columna U)
    extra = ""
    if len(row) > 20 and row[20].strip():
        extra = normalizar_texto(row[20])
    elif len(row) > 19 and row[19].strip() and not row[19].strip().lower().startswith("talla"):
        extra = normalizar_texto(row[19])
    else:
        extra = "Ninguna"

    return {
        "nombre": nombre, "cumpleanos": cumple, "edad": edad,
        "tutor_nombre": tutor_nombre, "tutor_telefono": tutor_tel,
        "alergias": alergias, "cuidados_medicos": cuidados,
        "color_favorito": color, "personaje_favorito": personaje,
        "festeja_escuela": festeja, "talla": talla, "extraescolar": extra
    }

def detectar_discrepancias():
    """Compara SQLite vs Google Sheets campo por campo sin filtros excluyentes."""
    db = SessionLocal()
    discrepancias = []

    # 1. Comparar Alumnos
    filas_directorio = obtener_filas_pestana("Directorio y Ficha Alumnos")
    todos_alumnos = db.query(models.Alumno).all()

    for row in filas_directorio:
        if len(row) < 2 or not row[1].strip() or "Nombre Completo" in row[1] or "DATOS BÁSICOS" in row[0]:
            continue

        sheet_data = extraer_datos_alumno_fila(row)
        tokens_sheet = simplificar_nombre(sheet_data["nombre"])
        alumno_bd = next((a for a in todos_alumnos if simplificar_nombre(a.nombre) == tokens_sheet), None)

        if alumno_bd:
            campos_a_comparar = [
                ("extraescolar", "Actividad Extraescolar"),
                ("tutor_telefono", "Teléfono de Contacto"),
                ("tutor_nombre", "Nombre del Tutor"),
                ("cuidados_medicos", "Cuidados Médicos"),
                ("alergias", "Alergias"),
                ("talla", "Talla de Uniforme")
            ]

            for campo, etiqueta in campos_a_comparar:
                val_bd = (getattr(alumno_bd, campo) or "").strip()
                val_sheet = (sheet_data[campo] or "").strip()

                if val_bd.lower() != val_sheet.lower():
                    discrepancias.append({
                        "tipo": "alumno",
                        "id": alumno_bd.id,
                        "identificador": alumno_bd.nombre,
                        "campo": campo,
                        "etiqueta": etiqueta,
                        "valor_bd": val_bd if val_bd else "(Vacío)",
                        "valor_sheet": val_sheet if val_sheet else "(Vacío)"
                    })

    # 2. Comparar Eventos
    filas_eventos = obtener_filas_pestana("Calendario Eventos")
    for row in filas_eventos:
        if len(row) < 4 or "Título Evento" in row[3] or "CRONOGRAMA" in row[0]:
            continue
        titulo = normalizar_texto(row[3])
        if not titulo:
            continue
        resp_sheet = normalizar_texto(row[5]) if len(row) > 5 else ""
        lugar_sheet = normalizar_texto(row[6]) if len(row) > 6 else ""

        evento_bd = db.query(models.Evento).filter(models.Evento.titulo == titulo).first()
        if evento_bd:
            if resp_sheet and evento_bd.responsable.strip().lower() != resp_sheet.lower():
                discrepancias.append({
                    "tipo": "evento",
                    "id": evento_bd.id,
                    "identificador": evento_bd.titulo,
                    "campo": "responsable",
                    "etiqueta": "Responsable del Evento",
                    "valor_bd": evento_bd.responsable or "(Vacío)",
                    "valor_sheet": resp_sheet or "(Vacío)"
                })
            if lugar_sheet and evento_bd.lugar.strip().lower() != lugar_sheet.lower():
                discrepancias.append({
                    "tipo": "evento",
                    "id": evento_bd.id,
                    "identificador": evento_bd.titulo,
                    "campo": "lugar",
                    "etiqueta": "Lugar del Evento",
                    "valor_bd": evento_bd.lugar or "(Vacío)",
                    "valor_sheet": lugar_sheet or "(Vacío)"
                })

    db.close()
    return discrepancias

def enviar_cambio_a_sheet(payload):
    """Envía la actualización a Google Sheets vía Apps Script Webhook."""
    if not APPS_SCRIPT_WEBHOOK_URL:
        return
    try:
        res = requests.post(APPS_SCRIPT_WEBHOOK_URL, json=payload, timeout=10)
        print(f"Respuesta del Webhook Google Apps Script: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Error enviando cambio a Google Sheet: {e}")

def sincronizar_base_de_datos():
    """Actualización e inserción directa desde Google Sheets a SQLite."""
    db = SessionLocal()
    filas_directorio = obtener_filas_pestana("Directorio y Ficha Alumnos")
    todos_alumnos = db.query(models.Alumno).all()

    for row in filas_directorio:
        if len(row) < 2 or not row[1].strip() or "Nombre Completo" in row[1] or "DATOS BÁSICOS" in row[0]:
            continue

        d = extraer_datos_alumno_fila(row)
        tokens_sheet = simplificar_nombre(d["nombre"])
        alumno = next((a for a in todos_alumnos if simplificar_nombre(a.nombre) == tokens_sheet), None)

        if alumno:
            alumno.cumpleanos = d["cumpleanos"] or alumno.cumpleanos
            alumno.edad = d["edad"]
            alumno.tutor_nombre = d["tutor_nombre"] or alumno.tutor_nombre
            alumno.tutor_telefono = d["tutor_telefono"] or alumno.tutor_telefono
            alumno.alergias = d["alergias"] or alumno.alergias
            alumno.cuidados_medicos = d["cuidados_medicos"] or alumno.cuidados_medicos
            alumno.color_favorito = d["color_favorito"] or alumno.color_favorito
            alumno.personaje_favorito = d["personaje_favorito"] or alumno.personaje_favorito
            alumno.festeja_escuela = d["festeja_escuela"] or alumno.festeja_escuela
            alumno.talla = d["talla"] or alumno.talla
            alumno.extraescolar = d["extraescolar"] or alumno.extraescolar
        else:
            db.add(models.Alumno(**d))

    db.commit()
    db.close()