import hashlib
import os
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
import models

def get_password_hash(password: str) -> str:
    """Genera un hash SHA-256 con salt seguro."""
    salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}${hashed}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si la contraseña coincide con el hash almacenado."""
    try:
        salt, stored_hash = hashed_password.split("$")
        calculated_hash = hashlib.sha256((salt + plain_password).encode('utf-8')).hexdigest()
        return calculated_hash == stored_hash
    except Exception:
        return False

def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Obtiene el usuario autenticado desde la sesión cookie."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.query(models.Usuario).filter(models.Usuario.id == user_id, models.Usuario.activo == True).first()
    return user