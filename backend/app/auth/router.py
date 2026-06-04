from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import LoginRequest, RefreshRequest, TokenResponse, UserMe
from app.config import settings
from app.database import get_db
from app.models.usuarios import Usuario

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data | {"exp": datetime.now(UTC) + expires_delta}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _make_tokens(user: Usuario) -> TokenResponse:
    base = {"sub": user.username, "rol": user.rol}
    access = _create_token(base | {"type": "access"},
                           timedelta(minutes=settings.jwt_access_expire_minutes))
    refresh = _create_token(base | {"type": "refresh"},
                            timedelta(days=settings.jwt_refresh_expire_days))
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        role=user.rol,
        nombre_completo=user.nombre_completo,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Usuario).where(Usuario.username == body.username))
    user = result.scalar_one_or_none()

    if user is None or not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Usuario o contraseña incorrectos")
    if not user.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")

    await db.execute(
        update(Usuario).where(Usuario.id == user.id)
        .values(ultimo_acceso=datetime.now(UTC))
    )
    await db.commit()

    return _make_tokens(user)


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

    return _make_tokens(user)


@router.get("/me", response_model=UserMe)
async def me(current_user: dict = Depends(get_current_user)):
    return current_user
