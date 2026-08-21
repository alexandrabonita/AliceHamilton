from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
import os

import models
from database import engine, get_db, SessionLocal
import auth
import cargar_datos


def inicializar_datos_servidor():
    """Crea los usuarios y sincroniza datos si la BD arranca vacía en Render."""
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    # 1. Crear usuarios por defecto si no existen
    usuarios_iniciales = [
        {"username": "admin", "nombre_completo": "Administrador / Soporte TI", "password": "admin123Kinder*", "rol": "admin"},
        {"username": "maestra", "nombre_completo": "Maestra Titular Kínder 3", "password": "docente123Kinder*", "rol": "docente"},
        {"username": "vocal", "nombre_completo": "Vocal de Grupo", "password": "vocal123Kinder*", "rol": "vocal"},
        {"username": "padre", "nombre_completo": "Papá / Mamá de Familia", "password": "padre123Kinder*", "rol": "padre"}
    ]
    
    for u in usuarios_iniciales:
        existe = db.query(models.Usuario).filter(models.Usuario.username == u["username"]).first()
        if not existe:
            nuevo = models.Usuario(
                username=u["username"],
                nombre_completo=u["nombre_completo"],
                password_hash=auth.get_password_hash(u["password"]),
                rol=u["rol"],
                activo=True
            )
            db.add(nuevo)
    
    db.commit()
    
    # 2. Si no hay alumnos, sincronizar desde Google Sheets
    total_alumnos = db.query(models.Alumno).count()
    db.close()
    
    if total_alumnos == 0:
        print("Base de datos vacía detectada. Sincronizando con Google Sheets...")
        try:
            cargar_datos.sincronizar_base_de_datos()
        except Exception as e:
            print(f"Error en sincronización inicial: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Esto se ejecuta automáticamente al iniciar la aplicación en Render o Local
    inicializar_datos_servidor()
    yield


app = FastAPI(title="Comunidad Alice Hamilton Kinder 3", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key="kinder-secret-key-super-segura-2026")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# --- AUTH ---

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
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

# --- INICIO (DASHBOARD) ---

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

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

# --- MENÚS PRINCIPALES ---

@app.get("/alumnos", response_class=HTMLResponse)
def ver_alumnos(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    alumnos = db.query(models.Alumno).all()
    return templates.TemplateResponse(request=request, name="alumnos.html", context={"alumnos": alumnos, "user": user})

@app.get("/calendario", response_class=HTMLResponse)
def ver_calendario(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    alumnos = db.query(models.Alumno).all()
    return templates.TemplateResponse(request=request, name="calendario.html", context={"alumnos": alumnos, "user": user})

@app.get("/ventas", response_class=HTMLResponse)
def ver_ventas(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    negocios = db.query(models.Emprendimiento).all()
    return templates.TemplateResponse(request=request, name="ventas.html", context={"negocios": negocios, "user": user})

@app.get("/avisos", response_class=HTMLResponse)
def ver_avisos(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    avisos = db.query(models.Aviso).all()
    return templates.TemplateResponse(request=request, name="avisos.html", context={"avisos": avisos, "user": user})

# --- FORMULARIOS ---

@app.post("/publicar-aviso")
def publicar_aviso(request: Request, titulo: str = Form(...), contenido: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol not in ["admin", "docente", "vocal"]:
        return RedirectResponse(url="/login")

    nuevo_aviso = models.Aviso(
        titulo=titulo,
        contenido=contenido,
        fecha=datetime.now().strftime("%d/%m/%Y"),
        autor=f"{user.nombre_completo} ({user.rol.upper()})"
    )
    db.add(nuevo_aviso)
    db.commit()
    return RedirectResponse(url="/avisos", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/publicar-venta")
def publicar_venta(
    request: Request,
    padre_nombre: str = Form(...),
    titulo_producto: str = Form(...),
    giro: str = Form(...),
    descripcion_oferta: str = Form(...),
    taller_que_ofrece: str = Form(""),
    telefono_contacto: str = Form(...),
    db: Session = Depends(get_db)
):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    nueva_venta = models.Emprendimiento(
        padre_nombre=padre_nombre,
        titulo_producto=titulo_producto,
        giro=giro,
        descripcion_oferta=descripcion_oferta,
        taller_que_ofrece=taller_que_ofrece,
        telefono_contacto=telefono_contacto,
        fecha_publicacion=datetime.now().strftime("%d/%m/%Y")
    )
    db.add(nueva_venta)
    db.commit()
    return RedirectResponse(url="/ventas", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/publicar-evento")
def publicar_evento(
    request: Request,
    titulo: str = Form(...),
    fecha: str = Form(...),
    lugar: str = Form(...),
    tipo: str = Form(...),
    descripcion: str = Form(...),
    db: Session = Depends(get_db)
):
    user = auth.get_current_user(request, db)
    if not user or user.rol not in ["admin", "docente", "vocal"]:
        return RedirectResponse(url="/")

    nuevo_evento = models.Evento(
        titulo=titulo,
        fecha=fecha,
        lugar=lugar,
        tipo=tipo,
        descripcion=descripcion
    )
    db.add(nuevo_evento)
    db.commit()
    return RedirectResponse(url="/calendario", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/publicar-curso")
def publicar_curso(
    request: Request,
    titulo: str = Form(...),
    instructor: str = Form(...),
    tipo: str = Form(...),
    descripcion: str = Form(...),
    enlace_recurso: str = Form(""),
    db: Session = Depends(get_db)
):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    nuevo_curso = models.CursoTaller(
        titulo=titulo,
        instructor=instructor,
        tipo=tipo,
        descripcion=descripcion,
        enlace_recurso=enlace_recurso
    )
    db.add(nuevo_curso)
    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

# --- VISTAS PROTEGIDAS POR ROL ---

@app.get("/docentes", response_class=HTMLResponse)
def ver_docentes(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol not in ["admin", "docente"]:
        return RedirectResponse(url="/")
    alumnos = db.query(models.Alumno).all()
    return templates.TemplateResponse(request=request, name="docentes.html", context={"alumnos": alumnos, "user": user})

@app.get("/soporte", response_class=HTMLResponse)
def ver_soporte(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol != "admin":
        return RedirectResponse(url="/")
    usuarios = db.query(models.Usuario).all()
    return templates.TemplateResponse(request=request, name="soporte.html", context={"usuarios": usuarios, "user": user})

@app.get("/sincronizar")
def sincronizar_desde_sheets(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or user.rol not in ["admin", "docente"]:
        return RedirectResponse(url="/")
    cargar_datos.sincronizar_base_de_datos()
    return RedirectResponse(url="/soporte" if user.rol == "admin" else "/", status_code=303)