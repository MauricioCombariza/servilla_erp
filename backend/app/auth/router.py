from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import claves
from app.auth.dependencies import bearer_scheme, get_current_user, get_role_page_keys
from app.auth.schemas import CambioClaveRequest, LoginRequest, RefreshRequest, TokenResponse, UserMe
from app.config import settings
from app.database import get_db
from app.models.usuarios import Usuario

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data | {"exp": datetime.now(UTC) + expires_delta}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _make_tokens(user: Usuario, page_keys: list[str]) -> TokenResponse:
    # Clave vencida o temporal: el token de acceso solo sirve para cambiarla
    # (get_current_user y el servicio flujo exigen type "access")
    cambio = claves.requiere_cambio(user)
    base = {"sub": user.username, "rol": user.rol}
    access = _create_token(base | {"type": "cambio_clave" if cambio else "access"},
                           timedelta(minutes=settings.jwt_access_expire_minutes))
    refresh = _create_token(base | {"type": "refresh"},
                            timedelta(days=settings.jwt_refresh_expire_days))
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        role=user.rol,
        nombre_completo=user.nombre_completo,
        page_keys=[] if cambio else page_keys,
        debe_cambiar_clave=cambio,
        dias_para_vencer=claves.dias_para_vencer(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Usuario).where(Usuario.username == body.username))
    user = result.scalar_one_or_none()

    if user is None or not claves.verificar_clave(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Usuario o contraseña incorrectos")
    if not user.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")

    await db.execute(
        update(Usuario).where(Usuario.id == user.id)
        .values(ultimo_acceso=datetime.now(UTC))
    )
    await db.commit()

    page_keys = sorted(await get_role_page_keys(db, user.rol))
    return _make_tokens(user, page_keys)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(body.refresh_token, settings.jwt_secret,
                             algorithms=[settings.jwt_algorithm])
        username: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if username is None or token_type != "refresh":
            raise ValueError
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido")

    result = await db.execute(select(Usuario).where(Usuario.username == username))
    user = result.scalar_one_or_none()

    if user is None or not user.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")

    page_keys = sorted(await get_role_page_keys(db, user.rol))
    return _make_tokens(user, page_keys)


@router.get("/me", response_model=UserMe)
async def me(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    page_keys = sorted(await get_role_page_keys(db, current_user["rol"]))
    user = await db.get(Usuario, current_user["id"])
    return UserMe(**current_user, page_keys=page_keys, dias_para_vencer=claves.dias_para_vencer(user))


async def _usuario_para_cambio(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    """Acepta el token normal y también el de "cambio_clave" (clave vencida o temporal)."""
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret,
                             algorithms=[settings.jwt_algorithm])
        username = payload.get("sub")
        if username is None or payload.get("type") not in ("access", "cambio_clave"):
            raise ValueError
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    user = await db.scalar(select(Usuario).where(Usuario.username == username))
    if user is None or not user.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")
    return user


@router.post("/cambiar-clave", response_model=TokenResponse)
async def cambiar_clave(
    body: CambioClaveRequest,
    user: Usuario = Depends(_usuario_para_cambio),
    db: AsyncSession = Depends(get_db),
):
    if not claves.verificar_clave(body.clave_actual, user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")
    await claves.poner_clave(db, user, body.clave_nueva, temporal=False)
    await db.commit()
    await db.refresh(user)
    page_keys = sorted(await get_role_page_keys(db, user.rol))
    return _make_tokens(user, page_keys)
