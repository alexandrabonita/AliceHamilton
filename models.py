from sqlalchemy import Column, Integer, String, Text, Boolean
from database import Base

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    nombre_completo = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    rol = Column(String, default="padre") # admin, docente, vocal, padre
    activo = Column(Boolean, default=True)

class Alumno(Base):
    __tablename__ = "alumnos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    cumpleanos = Column(String)
    edad = Column(Integer, default=5)
    tutor_nombre = Column(String)
    tutor_telefono = Column(String)
    alergias = Column(String, default="Ninguna reportada")
    cuidados_medicos = Column(Text, default="Ninguno")
    color_favorito = Column(String)
    personaje_favorito = Column(String)
    festeja_escuela = Column(String, default="Por confirmar")
    extraescolar = Column(String, default="Ninguna")
    talla = Column(String, default="Talla 6")

class Emprendimiento(Base):
    __tablename__ = "emprendimientos"
    id = Column(Integer, primary_key=True, index=True)
    padre_nombre = Column(String, nullable=False)
    titulo_producto = Column(String, nullable=False)
    giro = Column(String)
    descripcion_oferta = Column(Text)
    taller_que_ofrece = Column(String)
    telefono_contacto = Column(String)
    fecha_publicacion = Column(String)

class Evento(Base):
    __tablename__ = "eventos"
    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String, nullable=False)
    fecha = Column(String, nullable=False) # Formato YYYY-MM-DD
    responsable = Column(String, default="") # en los cumpleaños el responsable es el padre o tutor
    lugar = Column(String, default="")
    tipo = Column(String, default="Evento General")
    descripcion = Column(Text, default="")
    notas = Column(Text, default="")

class CursoTaller(Base):
    __tablename__ = "cursos_talleres"
    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String, nullable=False)
    instructor = Column(String)
    tipo = Column(String, default="Escuela para Padres") # Escuela para Padres, Taller Práctico, Charla
    descripcion = Column(Text)
    enlace_recurso = Column(String) # Link a video, Drive o PDF