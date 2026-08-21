from database import SessionLocal, engine
import models
from auth import get_password_hash

# Crear tablas si no existen
models.Base.metadata.create_all(bind=engine)
db = SessionLocal()

usuarios_iniciales = [
    {
        "username": "admin",
        "nombre_completo": "Administrador / Soporte TI",
        "password": "admin123Kinder*",
        "rol": "admin"
    },
    {
        "username": "maestra",
        "nombre_completo": "Maestra Titular Kínder 3",
        "password": "docente123Kinder*",
        "rol": "docente"
    },
    {
        "username": "vocal",
        "nombre_completo": "Vocal de Grupo",
        "password": "vocal123Kinder*",
        "rol": "vocal"
    },
    {
        "username": "padre",
        "nombre_completo": "Papá / Mamá de Familia",
        "password": "padre123Kinder*",
        "rol": "padre"
    }
]

for u in usuarios_iniciales:
    # Si ya existe, le actualizamos la contraseña con el nuevo formato
    usuario_existente = db.query(models.Usuario).filter(models.Usuario.username == u["username"]).first()
    if usuario_existente:
        usuario_existente.password_hash = get_password_hash(u["password"])
        usuario_existente.nombre_completo = u["nombre_completo"]
        usuario_existente.rol = u["rol"]
        usuario_existente.activo = True
        print(f"Contraseña actualizada para: {u['username']}")
    else:
        nuevo = models.Usuario(
            username=u["username"],
            nombre_completo=u["nombre_completo"],
            password_hash=get_password_hash(u["password"]),
            rol=u["rol"],
            activo=True
        )
        db.add(nuevo)
        print(f"Usuario nuevo creado: {u['username']}")

db.commit()
db.close()
print("¡Todos los usuarios quedaron actualizados correctamente!")