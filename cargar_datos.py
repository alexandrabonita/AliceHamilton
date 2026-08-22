import csv
import io
import urllib.parse
import unicodedata
import requests
from database import SessionLocal
import models

SPREADSHEET_ID = "1SNKtgPK2W1adPuyWpPnNTONX_faoje50dQ4n3yyt8vk"

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

def fusionar_textos(texto_orig: str, texto_nuevo: str) -> str:
    orig = (texto_orig or "").strip()
    nuevo = (texto_nuevo or "").strip()
    if not nuevo or nuevo.lower() in orig.lower():
        return orig
    if not orig:
        return nuevo
    return f"{orig} | {nuevo}"

def sincronizar_base_de_datos():
    db = SessionLocal()
    print("Iniciando sincronización limpia con Google Sheets...")

    # 1. DIRECTORIO DE ALUMNOS
    filas_directorio = obtener_filas_pestana("Directorio y Ficha Alumnos")
    for row in filas_directorio:
        if len(row) < 2 or not row[1].strip() or "Nombre Completo" in row[1] or "DATOS BÁSICOS" in row[0]:
            continue

        nombre = normalizar_texto(row[1])
        cumpleanos = normalizar_texto(row[2]) if len(row) > 2 else ""
        edad = int(row[3].strip()) if len(row) > 3 and row[3].strip().isdigit() else 5
        tutor_nombre = normalizar_texto(row[4]) if len(row) > 4 else ""
        tutor_telefono = normalizar_texto(row[5]) if len(row) > 5 else ""
        alergias = normalizar_texto(row[7]) if len(row) > 7 and row[7].strip() else "Ninguna reportada"
        cuidados = normalizar_texto(row[11]) if len(row) > 11 and row[11].strip() else "Ninguno"
        color = normalizar_texto(row[12]) if len(row) > 12 else ""
        personaje = normalizar_texto(row[13]) if len(row) > 13 else ""
        festeja = normalizar_texto(row[16]) if len(row) > 16 and row[16].strip() else "Por confirmar"
        talla = normalizar_texto(row[19]) if len(row) > 19 and row[19].strip() else "Talla 6"
        extra = normalizar_texto(row[20]) if len(row) > 20 and row[20].strip() else "Ninguna"

        tokens_nuevo = simplificar_nombre(nombre)
        todos_alumnos = db.query(models.Alumno).all()
        alumno = next((a for a in todos_alumnos if simplificar_nombre(a.nombre) == tokens_nuevo), None)

        if alumno:
            alumno.cumpleanos = cumpleanos or alumno.cumpleanos
            alumno.tutor_nombre = tutor_nombre or alumno.tutor_nombre
            alumno.tutor_telefono = tutor_telefono or alumno.tutor_telefono
            alumno.alergias = fusionar_textos(alumno.alergias, alergias)
            alumno.cuidados_medicos = fusionar_textos(alumno.cuidados_medicos, cuidados)
            alumno.color_favorito = color or alumno.color_favorito
            alumno.personaje_favorito = personaje or alumno.personaje_favorito
            alumno.festeja_escuela = festeja or alumno.festeja_escuela
            alumno.talla = talla or alumno.talla
            alumno.extraescolar = extra or alumno.extraescolar
        else:
            db.add(models.Alumno(
                nombre=nombre, cumpleanos=cumpleanos, edad=edad,
                tutor_nombre=tutor_nombre, tutor_telefono=tutor_telefono,
                alergias=alergias, cuidados_medicos=cuidados,
                color_favorito=color, personaje_favorito=personaje,
                festeja_escuela=festeja, talla=talla, extraescolar=extra
            ))
            db.commit()

    # 2. CALENDARIO CUMPLEAÑOS
    filas_cumple = obtener_filas_pestana("Calendario Cumpleaños")
    todos_alumnos = db.query(models.Alumno).all()

    for row in filas_cumple:
        if len(row) < 3:
            continue
        mes = normalizar_texto(row[0])
        dia = normalizar_texto(row[1])
        nombre = normalizar_texto(row[2])

        if not nombre or "Nombre del Alumno" in nombre or "CRONOGRAMA" in mes:
            continue

        cumple_formateado = f"{dia} de {mes.lower()}" if (dia and mes) else ""
        tutor_nombre = normalizar_texto(row[3]) if len(row) > 3 else ""
        tutor_telefono = normalizar_texto(row[4]) if len(row) > 4 else ""
        festeja = normalizar_texto(row[5]) if len(row) > 5 else "Por confirmar"
        notas_cumple = normalizar_texto(row[6]) if len(row) > 6 else ""

        tokens_sheet = simplificar_nombre(nombre)
        alumno = next((a for a in todos_alumnos if len(tokens_sheet.intersection(simplificar_nombre(a.nombre))) >= 2), None)
        
        if alumno:
            if cumple_formateado:
                alumno.cumpleanos = cumple_formateado
            alumno.tutor_nombre = tutor_nombre or alumno.tutor_nombre
            alumno.tutor_telefono = tutor_telefono or alumno.tutor_telefono
            alumno.festeja_escuela = festeja or alumno.festeja_escuela
            alumno.cuidados_medicos = fusionar_textos(alumno.cuidados_medicos, notas_cumple)

    # 3. CALENDARIO EVENTOS
    filas_eventos = obtener_filas_pestana("Calendario Eventos")
    for row in filas_eventos:
        if len(row) < 4:
            continue
        mes = normalizar_texto(row[0])
        dia = normalizar_texto(row[1])
        anio = normalizar_texto(row[2]) if len(row) > 2 else "2026"
        titulo = normalizar_texto(row[3]) if len(row) > 3 else ""

        if not titulo or "Título Evento" in titulo or "CRONOGRAMA" in mes:
            continue

        fecha_iso = armar_fecha_iso(mes, dia, anio)
        tipo = normalizar_texto(row[4]) if len(row) > 4 else "Evento General"
        responsable = normalizar_texto(row[5]) if len(row) > 5 else "Dirección / Comité"
        lugar = normalizar_texto(row[6]) if len(row) > 6 else "Colegio"
        descripcion = normalizar_texto(row[7]) if len(row) > 7 else ""
        notas = normalizar_texto(row[8]) if len(row) > 8 else ""

        evento_existente = db.query(models.Evento).filter(
            models.Evento.titulo == titulo,
            models.Evento.fecha == fecha_iso
        ).first()

        if evento_existente:
            evento_existente.tipo = tipo or evento_existente.tipo
            evento_existente.responsable = responsable or evento_existente.responsable
            evento_existente.lugar = lugar or evento_existente.lugar
            evento_existente.descripcion = fusionar_textos(evento_existente.descripcion, descripcion)
            evento_existente.notas = fusionar_textos(evento_existente.notas, notas)
        else:
            db.add(models.Evento(
                titulo=titulo,
                fecha=fecha_iso,
                tipo=tipo,
                responsable=responsable,
                lugar=lugar,
                descripcion=descripcion,
                notas=notas
            ))

    # 4. COMUNIDAD Y RED DE PADRES
    filas_red = obtener_filas_pestana("Comunidad y Red de Padres")
    for row in filas_red:
        if len(row) < 3 or "Nombre" in row[0] or "RED DE" in row[0]:
            continue
        padre_nombre = normalizar_texto(row[0])
        negocio_titulo = normalizar_texto(row[1])
        giro = normalizar_texto(row[2]) if len(row) > 2 else "Comercio General"
        descripcion = normalizar_texto(row[3]) if len(row) > 3 else ""
        taller = normalizar_texto(row[4]) if len(row) > 4 else ""
        telefono = normalizar_texto(row[5]) if len(row) > 5 else ""

        if not negocio_titulo and not padre_nombre:
            continue

        emp = db.query(models.Emprendimiento).filter(
            models.Emprendimiento.padre_nombre == padre_nombre,
            models.Emprendimiento.titulo_producto == negocio_titulo
        ).first()

        if emp:
            emp.giro = giro or emp.giro
            emp.descripcion_oferta = fusionar_textos(emp.descripcion_oferta, descripcion)
            emp.taller_que_ofrece = fusionar_textos(emp.taller_que_ofrece, taller)
            emp.telefono_contacto = telefono or emp.telefono_contacto
        else:
            db.add(models.Emprendimiento(
                padre_nombre=padre_nombre,
                titulo_producto=negocio_titulo or "Emprendimiento Familiar",
                giro=giro,
                descripcion_oferta=descripcion,
                taller_que_ofrece=taller,
                telefono_contacto=telefono,
                fecha_publicacion="2026"
            ))

    db.commit()
    db.close()
    print("Sincronización sin duplicados terminada.")

if __name__ == "__main__":
    sincronizar_base_de_datos()