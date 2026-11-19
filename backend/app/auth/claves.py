"""Política de contraseñas del ERP (SER-MNT-PR-02 §20.3).

- Mínimo CLAVE_MIN_LARGO caracteres (12), con letras y números, y sin contener el usuario.
- Vence a los CLAVE_VIGENCIA_DIAS (45) de puesta; al vencer, el login entrega un token que
  solo sirve para cambiarla (tipo "cambio_clave": el resto de la API, también el servicio Go
  flujo, solo acepta tipo "access").
- No se puede repetir ninguna de las últimas CLAVE_HISTORIAL claves.
- Una clave asignada por un administrador (usuario nuevo o restablecida) es temporal: la
  persona debe cambiarla al entrar.
"""
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.usuarios import Usuario, UsuarioClaveAnterior


def hash_clave(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verificar_clave(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:  # hash con formato inválido: nunca coincide
        return False


def errores_fortaleza(clave: str, username: str) -> list[str]:
    errores = []
    if len(clave) < settings.clave_min_largo:
        errores.append(f"debe tener al menos {settings.clave_min_largo} caracteres")
    if not any(c.isalpha() for c in clave):
        errores.append("debe tener letras")
    if not any(c.isdigit() for c in clave):
        errores.append("debe tener números")
    if username and username.lower() in clave.lower():
        errores.append("no puede contener el nombre de usuario")
    return errores


def vence_en(usuario: Usuario) -> datetime:
    return usuario.clave_cambiada_en + timedelta(days=settings.clave_vigencia_dias)


def dias_para_vencer(usuario: Usuario, ahora: datetime | None = None) -> int:
    """Días que le quedan a la clave (0 o negativo: ya venció)."""
    ahora = ahora or datetime.now(UTC)
    return (vence_en(usuario) - ahora).days


def requiere_cambio(usuario: Usuario) -> bool:
    return usuario.debe_cambiar_clave or datetime.now(UTC) >= vence_en(usuario)


async def poner_clave(db: AsyncSession, usuario: Usuario, nueva: str, *, temporal: bool) -> None:
    """Valida y guarda la clave nueva (sin commit). temporal=True: la asignó un
    administrador y la persona debe cambiarla al entrar."""
    errores = errores_fortaleza(nueva, usuario.username)
    if errores:
        raise HTTPException(status_code=422, detail="La contraseña " + ", ".join(errores) + ".")

    if usuario.id is not None:
        anteriores = (await db.scalars(
            select(UsuarioClaveAnterior.password_hash)
            .where(UsuarioClaveAnterior.usuario_id == usuario.id)
            .order_by(UsuarioClaveAnterior.fecha.desc(), UsuarioClaveAnterior.id.desc())
            .limit(settings.clave_historial)
        )).all()
        if any(verificar_clave(nueva, h) for h in [usuario.password_hash, *anteriores]):
            raise HTTPException(
                status_code=422,
                detail=f"La contraseña no puede ser igual a ninguna de las últimas "
                       f"{settings.clave_historial} que ha tenido.")
        db.add(UsuarioClaveAnterior(usuario_id=usuario.id, password_hash=usuario.password_hash))

    usuario.password_hash = hash_clave(nueva)
    usuario.clave_cambiada_en = datetime.now(UTC)
    usuario.debe_cambiar_clave = temporal

    if usuario.id is not None:
        await db.flush()
        viejas = select(UsuarioClaveAnterior.id).where(
            UsuarioClaveAnterior.usuario_id == usuario.id
        ).order_by(UsuarioClaveAnterior.fecha.desc(), UsuarioClaveAnterior.id.desc()
                   ).offset(settings.clave_historial)
        await db.execute(delete(UsuarioClaveAnterior).where(UsuarioClaveAnterior.id.in_(viejas)))
