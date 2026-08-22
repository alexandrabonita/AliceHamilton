from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, Form, UploadFile, File, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
import json
import re
import os

import models
from database import engine, get_db, SessionLocal
import auth
import cargar_datos

MESES_MAP = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
}

def parsear_fecha_cumple(texto_cumple, anio_actual=2026):
    if not texto_cumple:
        return None
    texto = texto_cumple.lower().strip()
    match = re.search(r'(\d{1,2})\s*(?:de)?\s*([a-záéíóú]+)', texto)
    if match:
        dia = int(match.group(1))
        mes_nombre = match.group(2)
        mes = MESES_MAP.get(mes_nombre, "01")
        return f"{anio_actual}-{mes}-{dia:02d}"
    return None

def inicializar_datos_servidor():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    usuarios_iniciales = [
        {"username": "admin", "nombre_completo": "Administrador / Soporte TI", "email": "soporte@alicehamilton.edu", "password": "admin123Kinder*", "rol": "admin"},
        {"username": "maestra", "nombre_completo": "Maestra Titular Kínder 3", "email": "docente@alicehamilton.edu", "password": "docente123Kinder*", "rol": "docente"},
        {"username": "vocal", "nombre_completo": "Vocal de Grupo", "email": "vocal@alicehamilton.edu", "password": "vocal123Kinder*", "rol": "vocal"},
        {"username": "padre", "nombre_completo": "Papá / Mamá de Familia", "email": "padres@alicehamilton.edu", "password": "padre123Kinder*", "rol": "padre"}
    ]
    
    for u in usuarios_iniciales:
        user_db = db.query(models.Usuario).filter(models.Usuario.username == u["username"]).first()
        if not user_db:
            nuevo = models.Usuario(
                username=u["username"],
                nombre_completo=u["nombre_completo"],
                email=u["email"],
                password_hash=auth.get_password_hash(u["password"]),
                rol=u["rol"],
                activo=True,
                requiere_cambio_pass=False
            )
            db.add(nuevo)
    
    db.commit()
    total_alumnos = db.query(models.Alumno).count()
    db.close()
    
    if total_alumnos == 0:
        try:
            cargar_datos.sincronizar_base_de_datos()
        except Exception as e:
            print(f"Error en sincronización inicial: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    inicializar_datos_servidor()
    yield

app = FastAPI(title="Comunidad Alice Hamilton Kinder 3", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key="kinder-secret-key-super-segura-2026")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# --- AUTH & SESIONES ---

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if user:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(request=request, name="login.html", context={"user": None, "error": None})

@app.post("/login", response_class=HTMLResponse)
def login_post(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter(models.Usuario.username == username.strip()).first()
    if not user or not auth.verify_password(password, user.password_hash):
        return templates.TemplateResponse(request=request, name="login.html", context={"user": None, "error": "Usuario o contraseña incorrectos"})
    
    request.session["user_id"] = user.id
    request.session["user_rol"] = user.rol
    
    if user.requiere_cambio_pass:
        return RedirectResponse(url="/perfil?forzar=1", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

# --- PERFIL DE USUARIO ---

@app.get("/perfil", response_class=HTMLResponse)
def ver_perfil(request: Request, forzar: int = 0, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        request=request,
        name="perfil.html",
        context={"user": user, "forzar": forzar or user.requiere_cambio_pass, "mensaje": None, "error": None}
    )

@app.post("/perfil/actualizar-datos")
def actualizar_datos_perfil(
    request: Request,
    nombre_completo: str = Form(...),
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    user_db = db.query(models.Usuario).filter(models.Usuario.id == user.id).first()
    user_db.nombre_completo = nombre_completo.strip()
    user_db.email = email.strip()
    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="perfil.html",
        context={"user": user_db, "forzar": user_db.requiere_cambio_pass, "mensaje": "Datos personales actualizados correctamente.", "error": None}
    )

@app.post("/perfil/cambiar-password")
def cambiar_password(
    request: Request,
    pass_actual: str = Form(""),
    pass_nuevo: str = Form(...),
    pass_confirm: str = Form(...),
    db: Session = Depends(get_db)
):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    user_db = db.query(models.Usuario).filter(models.Usuario.id == user.id).first()

    if not user_db.requiere_cambio_pass:
        if not auth.verify_password(pass_actual, user_db.password_hash):
            return templates.TemplateResponse(
                request=request, name="perfil.html",
                context={"user": user_db, "forzar": False, "mensaje": None, "error": "La contraseña actual es incorrecta."}
            )

    if pass_nuevo != pass_confirm:
        return templates.TemplateResponse(
            request=request, name="perfil.html",
            context={"user": user_db, "forzar": user_db.requiere_cambio_pass, "mensaje": None, "error": "Las nuevas contraseñas no coinciden."}
        )

    if len(pass_nuevo) < 6:
        return templates.TemplateResponse(
            request=request, name="perfil.html",
            context={"user": user_db, "forzar": user_db.requiere_cambio_pass, "mensaje": None, "error": "La contraseña debe tener al menos 6 caracteres."}
        )

    user_db.password_hash = auth.get_password_hash(pass_nuevo)
    user_db.requiere_cambio_pass = False
    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="perfil.html",
        context={"user": user_db, "forzar": False, "mensaje": "¡Contraseña actualizada con éxito! Ya puedes navegar libremente.", "error": None}
    )

# --- VISTAS GENERALES ---

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if user.requiere_cambio_pass:
        return RedirectResponse(url="/perfil?forzar=1")

    alumnos = db.query(models.Alumno).all()
    ventas = db.query(models.Emprendimiento).all()
    eventos = db.query(models.Evento).all()
    cursos = db.query(models.CursoTaller).all()
    extraescolares = sorted(list(set([a.extraescolar for a in alumnos if a.extraescolar and a.extraescolar != "Ninguna"])))

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "alumnos": alumnos,
            "ventas": ventas,
            "eventos": eventos,
            "cursos": cursos,
            "extraescolares": extraescolares
        }
    )

@app.get("/alumnos", response_class=HTMLResponse)
def ver_alumnos(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if user.requiere_cambio_pass:
        return RedirectResponse(url="/perfil?forzar=1")
    alumnos = db.query(models.Alumno).all()
    return templates.TemplateResponse(request=request, name="alumnos.html", context={"alumnos": alumnos, "user": user})

@app.get("/calendario", response_class=HTMLResponse)
def ver_calendario(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if user.requiere_cambio_pass:
        return RedirectResponse(url="/perfil?forzar=1")
    
    alumnos = db.query(models.Alumno).all()
    eventos_db = db.query(models.Evento).all()
    eventos_calendario = []
    
    for a in alumnos:
        fecha_iso = parsear_fecha_cumple(a.cumpleanos)
        if fecha_iso:
            eventos_calendario.append({
                "title": f"🎂 {a.nombre}",
                "start": fecha_iso,
                "color": "#f59e0b",
                "textColor": "#ffffff",
                "extendedProps": {
                    "tipo": "Cumpleaños",
                    "responsable": a.tutor_nombre or "Padre / Tutor",
                    "tutor": a.tutor_nombre or "No especificado",
                    "telefono": a.tutor_telefono or "Sin registrar",
                    "festeja": a.festeja_escuela or "Por confirmar",
                    "gustos": f"{a.personaje_favorito} ({a.color_favorito})" if (a.personaje_favorito or a.color_favorito) else "No especificado",
                    "notas": "Festejo escolar de cumpleaños"
                }
            })
            
    for ev in eventos_db:
        fecha_final = ev.fecha if "-" in ev.fecha else (parsear_fecha_cumple(ev.fecha) or "2026-09-01")
        eventos_calendario.append({
            "title": f"📌 {ev.titulo}",
            "start": fecha_final,
            "color": "#2563eb",
            "textColor": "#ffffff",
            "extendedProps": {
                "tipo": ev.tipo or "Evento General",
                "responsable": ev.responsable or "Comité Organizador",
                "lugar": ev.lugar or "Colegio",
                "descripcion": ev.descripcion or "",
                "notas": ev.notas or ""
            }
        })
        
    return templates.TemplateResponse(request=request, name="calendario.html", context={"user": user, "eventos_json": json.dumps(eventos_calendario)})

@app.get("/ventas", response_class=HTMLResponse)
def ver_ventas(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if user.requiere_cambio_pass:
        return RedirectResponse(url="/perfil?forzar=1")
    negocios = db.query(models.Emprendimiento).all()
    return templates.TemplateResponse(request=request, name="ventas.html", context={"negocios": negocios, "user": user})

@app.get("/avisos", response_class=HTMLResponse)
def ver_avisos(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if user.requiere_cambio_pass:
        return RedirectResponse(url="/perfil?forzar=1")
    avisos = db.query(models.Aviso).all()
    return templates.TemplateResponse(request=request, name="avisos.html", context={"avisos": avisos, "user": user})

@app.get("/docentes", response_class=HTMLResponse)
def ver_docentes(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol not in ["admin", "docente"]:
        return RedirectResponse(url="/")
    if user.requiere_cambio_pass:
        return RedirectResponse(url="/perfil?forzar=1")
    alumnos = db.query(models.Alumno).all()
    return templates.TemplateResponse(request=request, name="docentes.html", context={"alumnos": alumnos, "user": user})

# --- FORMULARIOS PÚBLICOS ---

@app.post("/publicar-aviso")
def publicar_aviso(request: Request, titulo: str = Form(...), contenido: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol not in ["admin", "docente", "vocal"]:
        return RedirectResponse(url="/login")

    nuevo = models.Aviso(
        titulo=titulo,
        contenido=contenido,
        fecha=datetime.now().strftime("%d/%m/%Y"),
        autor=f"{user.nombre_completo} ({user.rol.upper()})"
    )
    db.add(nuevo)
    db.commit()
    return RedirectResponse(url="/avisos", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/publicar-venta")
def publicar_venta(
    request: Request, padre_nombre: str = Form(...), titulo_producto: str = Form(...),
    giro: str = Form(...), descripcion_oferta: str = Form(...), taller_que_ofrece: str = Form(""),
    telefono_contacto: str = Form(...), db: Session = Depends(get_db)
):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    nuevo = models.Emprendimiento(
        padre_nombre=padre_nombre,
        titulo_producto=titulo_producto,
        giro=giro,
        descripcion_oferta=descripcion_oferta,
        taller_que_ofrece=taller_que_ofrece,
        telefono_contacto=telefono_contacto,
        fecha_publicacion=datetime.now().strftime("%d/%m/%Y")
    )
    db.add(nuevo)
    db.commit()
    return RedirectResponse(url="/ventas", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/publicar-evento")
def publicar_evento(
    request: Request, titulo: str = Form(...), fecha: str = Form(...),
    responsable: str = Form(""), lugar: str = Form(""), tipo: str = Form("Evento General"),
    descripcion: str = Form(""), notas: str = Form(""), db: Session = Depends(get_db)
):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    nuevo = models.Evento(
        titulo=titulo, fecha=fecha, responsable=responsable,
        lugar=lugar, tipo=tipo, descripcion=descripcion, notas=notas
    )
    db.add(nuevo)
    db.commit()
    return RedirectResponse(url="/calendario", status_code=status.HTTP_303_SEE_OTHER)

# =========================================================================
# PANEL DE SOPORTE TI: CRUD, RESET, GESTIÓN MASIVA, EXPORT E IMPORT
# =========================================================================

MODEL_MAP = {
    "alumnos": models.Alumno,
    "usuarios": models.Usuario,
    "eventos": models.Evento,
    "emprendimientos": models.Emprendimiento,
    "avisos": models.Aviso,
    "cursos": models.CursoTaller
}

@app.get("/soporte", response_class=HTMLResponse)
def ver_soporte(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol != "admin":
        return RedirectResponse(url="/")

    alumnos = db.query(models.Alumno).all()
    tutores_dict = {}
    for a in alumnos:
        if a.tutor_nombre and a.tutor_nombre.strip():
            tutores_dict[a.tutor_nombre.strip()] = a.tutor_telefono or ""

    return templates.TemplateResponse(
        request=request,
        name="soporte.html",
        context={
            "user": user,
            "usuarios": db.query(models.Usuario).all(),
            "alumnos": alumnos,
            "eventos": db.query(models.Evento).all(),
            "emprendimientos": db.query(models.Emprendimiento).all(),
            "avisos": db.query(models.Aviso).all(),
            "cursos": db.query(models.CursoTaller).all(),
            "tutores_json": json.dumps(tutores_dict)
        }
    )

@app.get("/admin/reset-password/{user_id}")
def admin_reset_password_usuario(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol != "admin":
        return RedirectResponse(url="/login")

    target = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if target:
        target.password_hash = auth.get_password_hash(target.username)
        target.requiere_cambio_pass = True
        db.commit()

    return RedirectResponse(url="/soporte#tab-usuarios", status_code=303)

@app.post("/admin/guardar-registro")
async def admin_guardar_registro(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol != "admin":
        return RedirectResponse(url="/login")

    form_data = await request.form()
    tabla = form_data.get("tabla", "").strip().lower()
    item_id = int(form_data.get("id", 0))

    if tabla == "usuarios":
        username = form_data.get("username", "").strip()
        email = form_data.get("email", "").strip()
        nombre_completo = form_data.get("nombre_completo", "").strip()
        rol = form_data.get("rol", "padre").strip()
        password = form_data.get("password", "").strip()

        if item_id > 0:
            usuario = db.query(models.Usuario).filter(models.Usuario.id == item_id).first()
            if usuario:
                usuario.username = username
                usuario.email = email
                usuario.nombre_completo = nombre_completo
                usuario.rol = rol
                if password:
                    usuario.password_hash = auth.get_password_hash(password)
                    usuario.requiere_cambio_pass = False
        else:
            pass_final = password if password else username
            usuario = models.Usuario(
                username=username,
                email=email,
                nombre_completo=nombre_completo,
                password_hash=auth.get_password_hash(pass_final),
                rol=rol,
                activo=True,
                requiere_cambio_pass=True if not password else False
            )
            db.add(usuario)
        db.commit()
        return RedirectResponse(url="/soporte#tab-usuarios", status_code=status.HTTP_303_SEE_OTHER)

    model_class = MODEL_MAP.get(tabla)
    if not model_class:
        return RedirectResponse(url="/soporte")

    if item_id > 0:
        item = db.query(model_class).filter(model_class.id == item_id).first()
    else:
        item = model_class()
        db.add(item)

    if item:
        for key, val in form_data.items():
            if key in ["tabla", "id"]:
                continue
            val_str = str(val).strip()
            if hasattr(item, key):
                if key == "edad":
                    setattr(item, key, int(val_str) if val_str.isdigit() else 5)
                else:
                    setattr(item, key, val_str)
        db.commit()

    return RedirectResponse(url=f"/soporte#tab-{tabla}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/eliminar-masivo")
async def admin_eliminar_masivo(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol != "admin":
        return RedirectResponse(url="/login")

    form_data = await request.form()
    tabla = form_data.get("tabla", "").strip().lower()
    ids_raw = form_data.getlist("ids[]")

    model_class = MODEL_MAP.get(tabla)
    if model_class and ids_raw:
        for item_id in [int(i) for i in ids_raw if str(i).isdigit()]:
            item = db.query(model_class).filter(model_class.id == item_id).first()
            if item:
                if tabla == "usuarios" and getattr(item, "username", "") == "admin":
                    continue
                db.delete(item)
        db.commit()

    return RedirectResponse(url=f"/soporte#tab-{tabla}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/eliminar/{tabla}/{item_id}")
def admin_eliminar_registro(tabla: str, item_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol != "admin":
        return RedirectResponse(url="/login")

    model_class = MODEL_MAP.get(tabla.lower())
    if model_class:
        item = db.query(model_class).filter(model_class.id == item_id).first()
        if item:
            if tabla == "usuarios" and getattr(item, "username", "") == "admin":
                pass
            else:
                db.delete(item)
                db.commit()

    return RedirectResponse(url=f"/soporte#tab-{tabla}", status_code=303)

@app.get("/admin/reset-db")
def reset_database(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol != "admin":
        return RedirectResponse(url="/login")

    db.query(models.Alumno).delete()
    db.query(models.Evento).delete()
    db.query(models.Emprendimiento).delete()
    db.commit()
    db.close()

    cargar_datos.sincronizar_base_de_datos()
    return RedirectResponse(url="/soporte", status_code=303)

# --- SINCRONIZACIÓN Y RESOLUCIÓN DE DISCREPANCIAS ---

@app.get("/sincronizar", response_class=HTMLResponse)
def sincronizar_vista_discrepancias(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol not in ["admin", "docente"]:
        return RedirectResponse(url="/login")

    discrepancias = cargar_datos.detectar_discrepancias()
    
    if not discrepancias:
        cargar_datos.sincronizar_base_de_datos()
        return templates.TemplateResponse(
            request=request,
            name="sincronizar.html",
            context={"user": user, "discrepancias": [], "mensaje": "Todo está al día. La base de datos y Google Sheets coinciden al 100%."}
        )

    return templates.TemplateResponse(
        request=request,
        name="sincronizar.html",
        context={"user": user, "discrepancias": discrepancias, "mensaje": None}
    )

@app.post("/sincronizar/resolver")
async def resolver_sincronizacion(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol not in ["admin", "docente"]:
        return RedirectResponse(url="/login")

    form_data = await request.form()
    for key, decision in form_data.items():
        if key.startswith("decision_"):
            partes = key.split("_")
            tipo = partes[1]
            item_id = int(partes[2])
            campo = partes[3]
            valor_sheet = form_data.get(f"val_sheet_{tipo}_{item_id}_{campo}", "")

            if tipo == "alumno":
                alumno = db.query(models.Alumno).filter(models.Alumno.id == item_id).first()
                if alumno:
                    if decision == "sheet":
                        setattr(alumno, campo, valor_sheet)
                    elif decision == "bd":
                        valor_actual_bd = getattr(alumno, campo)
                        cargar_datos.enviar_cambio_a_sheet({
                            "accion": "actualizar_alumno",
                            "nombre": alumno.nombre,
                            campo: valor_actual_bd
                        })

            elif tipo == "evento":
                evento = db.query(models.Evento).filter(models.Evento.id == item_id).first()
                if evento:
                    if decision == "sheet":
                        setattr(evento, campo, valor_sheet)
                    elif decision == "bd":
                        valor_actual_bd = getattr(evento, campo)
                        cargar_datos.enviar_cambio_a_sheet({
                            "accion": "actualizar_evento",
                            "titulo": evento.titulo,
                            campo: valor_actual_bd
                        })

    db.commit()
    cargar_datos.sincronizar_base_de_datos()
    return RedirectResponse(url="/soporte", status_code=303)

# --- EXPORTACIÓN INDIVIDUAL POR TABLA (CONSERVA HASH DE CONTRASEÑA) ---

@app.get("/admin/exportar-tabla/{tabla}")
def exportar_tabla_individual(tabla: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol != "admin":
        return RedirectResponse(url="/login")

    model_class = MODEL_MAP.get(tabla.lower())
    if not model_class:
        return JSONResponse(status_code=404, content={"error": "Tabla no encontrada"})

    def modelo_a_dict(obj):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

    registros = [modelo_a_dict(row) for row in db.query(model_class).all()]
    json_str = json.dumps({tabla.lower(): registros}, indent=2, ensure_ascii=False)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{tabla.lower()}_{timestamp}.json"

    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- IMPORTACIÓN ROBUSTA ---

@app.post("/admin/importar")
async def importar_base_datos(request: Request, archivo_json: UploadFile = File(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol != "admin":
        return RedirectResponse(url="/login")

    contenido = await archivo_json.read()
    try:
        data = json.loads(contenido.decode("utf-8"))
        if isinstance(data, dict):
            for t_name, registros in data.items():
                m_cls = MODEL_MAP.get(t_name.lower())
                if not m_cls or not isinstance(registros, list):
                    continue

                for r in registros:
                    if not isinstance(r, dict):
                        continue

                    r.pop("id", None)

                    if t_name.lower() == "usuarios":
                        username = r.get("username", "").strip()
                        if not username:
                            continue

                        pass_hash = r.get("password_hash")
                        if not pass_hash or pass_hash == "PROTEGIDO":
                            r["password_hash"] = auth.get_password_hash("admin123Kinder*" if username == "admin" else username)

                        usuario_existente = db.query(models.Usuario).filter(models.Usuario.username == username).first()
                        if usuario_existente:
                            usuario_existente.nombre_completo = r.get("nombre_completo", usuario_existente.nombre_completo)
                            usuario_existente.email = r.get("email", usuario_existente.email)
                            usuario_existente.rol = r.get("rol", usuario_existente.rol)
                            usuario_existente.password_hash = r["password_hash"]
                            usuario_existente.requiere_cambio_pass = r.get("requiere_cambio_pass", False)
                        else:
                            db.add(m_cls(**r))
                    else:
                        db.add(m_cls(**r))

            db.commit()
    except Exception as e:
        print(f"Error al importar JSON: {e}")

    return RedirectResponse(url="/soporte", status_code=303)