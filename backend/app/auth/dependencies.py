from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

bearer_scheme = HTTPBearer()


async def sesion_del_token(
    db: AsyncSession, token: str, tipos: tuple[str, ...],
):
    """(payload, sesión, usuario) del token, o 401. La sesión debe seguir viva y el usuario activo."""
    from app.auth import sesiones

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        username: str | None = payload.get("sub")
        sid: str | None = payload.get("sid")
        if username is None or sid is None or payload.get("type") not in tipos:
            raise ValueError
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    encontrado = await sesiones.sesion_y_usuario(db, sid, username)
    if encontrado is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión no válida")
    sesion, user = encontrado
    if not user.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo o no existe")
    motivo = sesiones.motivo_vencida(sesion)
    if motivo is not None:
        if sesion.cerrada_en is None:
            await sesiones.cerrar(db, sesion, motivo)
            await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="La sesión se cerró por inactividad" if motivo == "inactividad"
                            else "La sesión terminó")
    return payload, sesion, user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.auth import sesiones

    _, sesion, user = await sesion_del_token(db, credentials.credentials, ("access",))
    await sesiones.tocar(db, sesion)
    return {"id": user.id, "username": user.username, "rol": user.rol,
            "nombre_completo": user.nombre_completo, "email": user.email, "activo": user.activo,
            "sid": sesion.id}


def require_role(*roles: str):
    """Dependency factory: require_role('administrador', 'logistica')"""
    async def _check(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["rol"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos")
        return current_user
    return _check


async def get_role_page_keys(db: AsyncSession, rol: str) -> set[str]:
    from app.models.roles import Rol, RolPagina

    result = await db.execute(
        select(RolPagina.page_key)
        .join(Rol, Rol.nombre == RolPagina.rol)
        .where(RolPagina.rol == rol, Rol.activo == True)  # noqa: E712
    )
    return {row[0] for row in result.all()}


def require_page(*page_keys: str):
    """Dependency factory: require_page('nomina') — concede acceso si el rol del
    usuario tiene asignada al menos una de las page_keys (semántica OR)."""
    async def _check(
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        allowed = await get_role_page_keys(db, current_user["rol"])
        if not set(page_keys) & allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos")
        return current_user
    return _check
