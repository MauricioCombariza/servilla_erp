from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import claves, sesiones
from app.auth.dependencies import (
    bearer_scheme,
    get_current_user,
    get_role_page_keys,
    sesion_del_token,
)
from app.auth.schemas import (
    CambioClaveRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
    UserMe,
)
from app.config import settings
from app.database import get_db
from app.models.usuarios import Sesion, Usuario

router = APIRouter(prefix="/api/auth", tags=["auth"])

_BOGOTA = ZoneInfo("America/Bogota")


def _create_token(data: dict, expira: datetime) -> str:
    return jwt.encode(data | {"exp": expira}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _make_tokens(user: Usuario, sesion: Sesion, page_keys: list[str]) -> TokenResponse:
    # Clave vencida o temporal: el token de acceso solo sirve para cambiarla
    # (get_current_user y el servicio flujo exigen type "access")
    cambio = claves.requiere_cambio(user)
    base = {"sub": user.username, "rol": user.rol, "sid": sesion.id}
    acceso_vence = min(datetime.now(UTC) + timedelta(minutes=settings.jwt_access_expire_minutes),
                       sesion.expira_en)
    access = _create_token(base | {"type": "cambio_clave" if cambio else "access"}, acceso_vence)
    refresh = _create_token(base | {"type": "refresh"}, sesion.expira_en)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        role=user.rol,
        nombre_completo=user.nombre_completo,
        page_keys=[] if cambio else page_keys,
        debe_cambiar_clave=cambio,
        dias_para_vencer=claves.dias_para_vencer(user),
        inactividad_minutos=settings.sesion_inactividad_minutos,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Sin distinguir mayúsculas ni espacios: el teclado del celular pone "Mariela"
    username = body.username.strip().lower()
    ip = sesiones.ip_de(request)
    user = await db.scalar(select(Usuario).where(func.lower(Usuario.username) == username))

    if user is not None and sesiones.bloqueada(user):
        await sesiones.registrar_evento(db, "login_bloqueado", usuario=user, ip=ip)
        await db.commit()
        hora = user.bloqueado_hasta.astimezone(_BOGOTA).strftime("%I:%M %p").lstrip("0")
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Cuenta bloqueada por intentos fallidos. Intenta de nuevo después de las {hora}.",
        )

    if user is None or not claves.verificar_clave(body.password, user.password_hash):
        if user is None:
            await sesiones.registrar_evento(db, "login_fallido", username=username, ip=ip,
                                            detalle="usuario no existe")
            await db.commit()
        elif await sesiones.intento_fallido(db, user, ip):
            await sesiones.cerrar_todas(db, user.id, "bloqueo")
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Cuenta bloqueada por {settings.login_max_intentos} intentos fallidos. "
                       f"Intenta de nuevo en {settings.login_bloqueo_minutos} minutos.",
            )
        else:
            await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Usuario o contraseña incorrectos")
    if not user.activo:
        await sesiones.registrar_evento(db, "login_fallido", usuario=user, ip=ip, detalle="usuario inactivo")
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")

    sesiones.desbloquear(user)
    user.ultimo_acceso = datetime.now(UTC)
    sesion = await sesiones.crear(db, user, request)
    await sesiones.registrar_evento(db, "login", usuario=user, ip=ip)
    await db.commit()

    page_keys = sorted(await get_role_page_keys(db, user.rol))
    return _make_tokens(user, sesion, page_keys)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    _, sesion, user = await sesion_del_token(db, body.refresh_token, ("refresh",))
    await sesiones.tocar(db, sesion, forzar=True)
    page_keys = sorted(await get_role_page_keys(db, user.rol))
    return _make_tokens(user, sesion, page_keys)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Cierra la sesión del refresh token. No falla si ya estaba cerrada o vencida."""
    try:
        payload = jwt.decode(body.refresh_token, settings.jwt_secret,
                             algorithms=[settings.jwt_algorithm], options={"verify_exp": False})
    except JWTError:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    sid, username = payload.get("sid"), payload.get("sub")
    if payload.get("type") != "refresh" or not sid or not username:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    encontrado = await sesiones.sesion_y_usuario(db, sid, username)
    if encontrado is not None:
        sesion, user = encontrado
        if sesion.cerrada_en is None:
            await sesiones.cerrar(db, sesion, body.motivo)
            await sesiones.registrar_evento(db, "logout", usuario=user, ip=sesiones.ip_de(request),
                                            detalle=body.motivo)
            await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/actividad", status_code=status.HTTP_204_NO_CONTENT)
async def actividad(_: dict = Depends(get_current_user)):
    """La persona sigue trabajando (escribe o toca la pantalla sin pedir nada al servidor)."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserMe)
async def me(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    page_keys = sorted(await get_role_page_keys(db, current_user["rol"]))
    user = await db.get(Usuario, current_user["id"])
    return UserMe(**current_user, page_keys=page_keys, dias_para_vencer=claves.dias_para_vencer(user))


async def _usuario_para_cambio(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> tuple[Usuario, Sesion]:
    """Acepta el token normal y también el de "cambio_clave" (clave vencida o temporal)."""
    _, sesion, user = await sesion_del_token(db, credentials.credentials, ("access", "cambio_clave"))
    await sesiones.tocar(db, sesion)
    return user, sesion


@router.post("/cambiar-clave", response_model=TokenResponse)
async def cambiar_clave(
    body: CambioClaveRequest,
    request: Request,
    datos: tuple[Usuario, Sesion] = Depends(_usuario_para_cambio),
    db: AsyncSession = Depends(get_db),
):
    user, sesion = datos
    if not claves.verificar_clave(body.clave_actual, user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")
    await claves.poner_clave(db, user, body.clave_nueva, temporal=False)
    # Las demás sesiones (otro equipo, alguien que conocía la clave vieja) se cierran
    await sesiones.cerrar_todas(db, user.id, "cambio_clave", excepto=sesion.id)
    await sesiones.registrar_evento(db, "cambio_clave", usuario=user, ip=sesiones.ip_de(request))
    await db.commit()
    await db.refresh(user)
    page_keys = sorted(await get_role_page_keys(db, user.rol))
    return _make_tokens(user, sesion, page_keys)
