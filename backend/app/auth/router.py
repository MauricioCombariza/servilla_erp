from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import claves, mfa, sesiones
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
    MfaCodigoRequest,
    MfaConfiguracion,
    MfaPendiente,
    MfaReconfiguracion,
    MfaTokenRequest,
    RefreshRequest,
    TokenResponse,
    UserMe,
)
from app.config import settings
from app.database import get_db
from app.models.usuarios import Sesion, Usuario, UsuarioMfaRespaldo

router = APIRouter(prefix="/api/auth", tags=["auth"])

_BOGOTA = ZoneInfo("America/Bogota")
# Tiempo para escribir el código del celular después de la clave
_MFA_MINUTOS = 10


def _create_token(data: dict, expira: datetime) -> str:
    return jwt.encode(data | {"exp": expira}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# Refresh token en cookie HttpOnly (S3): el JavaScript de la página no lo puede leer, así
# que un XSS no se lleva la sesión. Solo viaja a /api/auth y nunca desde otro sitio.
COOKIE_REFRESH = "servilla_refresh"
_RUTA_COOKIE = "/api/auth"


def _con_cookie(tokens: TokenResponse, expira: datetime) -> JSONResponse:
    refresh, tokens.refresh_token = tokens.refresh_token, None
    respuesta = JSONResponse(tokens.model_dump(mode="json"))
    respuesta.set_cookie(COOKIE_REFRESH, refresh, expires=expira, path=_RUTA_COOKIE,
                         httponly=True, secure=settings.cookie_segura, samesite="strict")
    return respuesta


def _sin_cookie(respuesta: Response) -> Response:
    respuesta.delete_cookie(COOKIE_REFRESH, path=_RUTA_COOKIE, httponly=True,
                            secure=settings.cookie_segura, samesite="strict")
    return respuesta


def _cookie_borrada() -> str:
    """Encabezado Set-Cookie que borra la cookie (para respuestas de error)."""
    return _sin_cookie(Response()).headers["set-cookie"]


def _make_tokens(user: Usuario, sesion: Sesion, page_keys: list[str],
                 codigos_respaldo: list[str] | None = None) -> JSONResponse:
    # Clave vencida o temporal: el token de acceso solo sirve para cambiarla
    # (get_current_user y el servicio flujo exigen type "access")
    cambio = claves.requiere_cambio(user)
    base = {"sub": user.username, "rol": user.rol, "sid": sesion.id}
    acceso_vence = min(datetime.now(UTC) + timedelta(minutes=settings.jwt_access_expire_minutes),
                       sesion.expira_en)
    access = _create_token(base | {"type": "cambio_clave" if cambio else "access"}, acceso_vence)
    refresh = _create_token(base | {"type": "refresh"}, sesion.expira_en)
    return _con_cookie(TokenResponse(
        access_token=access,
        refresh_token=refresh,
        role=user.rol,
        nombre_completo=user.nombre_completo,
        page_keys=[] if cambio else page_keys,
        debe_cambiar_clave=cambio,
        dias_para_vencer=claves.dias_para_vencer(user),
        inactividad_minutos=settings.sesion_inactividad_minutos,
        codigos_respaldo=codigos_respaldo,
    ), sesion.expira_en)


async def _rechazar_si_bloqueada(db: AsyncSession, user: Usuario, ip: str | None) -> None:
    if not sesiones.bloqueada(user):
        return
    await sesiones.registrar_evento(db, "login_bloqueado", usuario=user, ip=ip)
    await db.commit()
    hora = user.bloqueado_hasta.astimezone(_BOGOTA).strftime("%I:%M %p").lstrip("0")
    raise HTTPException(
        status_code=status.HTTP_423_LOCKED,
        detail=f"Cuenta bloqueada por intentos fallidos. Intenta de nuevo después de las {hora}.",
    )


async def _fallo(db: AsyncSession, user: Usuario, ip: str | None, detalle_401: str) -> None:
    """Cuenta el intento fallido (clave o código) y responde 401, o 423 si quedó bloqueada."""
    if await sesiones.intento_fallido(db, user, ip):
        await sesiones.cerrar_todas(db, user.id, "bloqueo")
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Cuenta bloqueada por {settings.login_max_intentos} intentos fallidos. "
                   f"Intenta de nuevo en {settings.login_bloqueo_minutos} minutos.",
        )
    await db.commit()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detalle_401)


async def _abrir_sesion(db: AsyncSession, user: Usuario, request: Request,
                        codigos_respaldo: list[str] | None = None) -> JSONResponse:
    sesiones.desbloquear(user)
    user.ultimo_acceso = datetime.now(UTC)
    sesion = await sesiones.crear(db, user, request)
    await sesiones.registrar_evento(db, "login", usuario=user, ip=sesiones.ip_de(request))
    await db.commit()
    page_keys = sorted(await get_role_page_keys(db, user.rol))
    return _make_tokens(user, sesion, page_keys, codigos_respaldo)


@router.post("/login", response_model=TokenResponse | MfaPendiente)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Sin distinguir mayúsculas ni espacios: el teclado del celular pone "Mariela"
    username = body.username.strip().lower()
    ip = sesiones.ip_de(request)
    user = await db.scalar(select(Usuario).where(func.lower(Usuario.username) == username))

    if user is not None:
        await _rechazar_si_bloqueada(db, user, ip)

    if user is None or not claves.verificar_clave(body.password, user.password_hash):
        if user is None:
            await sesiones.registrar_evento(db, "login_fallido", username=username, ip=ip,
                                            detalle="usuario no existe")
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Usuario o contraseña incorrectos")
        await _fallo(db, user, ip, "Usuario o contraseña incorrectos")
    if not user.activo:
        await sesiones.registrar_evento(db, "login_fallido", usuario=user, ip=ip, detalle="usuario inactivo")
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")

    # Clave correcta: falta el código del celular (o configurarlo la primera vez)
    if user.mfa_activo or settings.mfa_obligatorio:
        paso = "verificar" if user.mfa_activo else "configurar"
        token = _create_token({"sub": user.username, "type": "mfa", "paso": paso},
                              datetime.now(UTC) + timedelta(minutes=_MFA_MINUTOS))
        return MfaPendiente(mfa_paso=paso, mfa_token=token, nombre_completo=user.nombre_completo)

    return await _abrir_sesion(db, user, request)


async def _usuario_mfa(db: AsyncSession, mfa_token: str, paso: str) -> tuple[Usuario, dict]:
    """Usuario del token del paso intermedio (clave ya verificada, falta el código)."""
    try:
        payload = jwt.decode(mfa_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "mfa" or payload.get("paso") != paso or not payload.get("sub"):
            raise ValueError
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Se venció el tiempo para el código. Ingresa de nuevo usuario y contraseña.")
    user = await db.scalar(select(Usuario).where(Usuario.username == payload["sub"]))
    if user is None or not user.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")
    return user, payload


@router.post("/mfa/configurar", response_model=MfaConfiguracion)
async def mfa_configurar(body: MfaTokenRequest, db: AsyncSession = Depends(get_db)):
    """Primer ingreso con MFA: genera el secreto para el QR (aún no queda activo)."""
    user, _ = await _usuario_mfa(db, body.mfa_token, "configurar")
    if user.mfa_activo:
        raise HTTPException(status_code=409, detail="El segundo factor ya está configurado")
    secreto = mfa.nuevo_secreto()
    user.mfa_secreto = mfa.cifrar(secreto)
    user.mfa_ultimo_paso = None
    await db.commit()
    return MfaConfiguracion(secreto=secreto, uri=mfa.uri_otpauth(secreto, user.username))


@router.post("/mfa/activar", response_model=TokenResponse)
async def mfa_activar(body: MfaCodigoRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Confirma el primer código de la app: activa el MFA, entrega los códigos de respaldo."""
    user, _ = await _usuario_mfa(db, body.mfa_token, "configurar")
    ip = sesiones.ip_de(request)
    await _rechazar_si_bloqueada(db, user, ip)
    secreto = mfa.descifrar(user.mfa_secreto) if user.mfa_secreto else None
    if user.mfa_activo or secreto is None:
        raise HTTPException(status_code=409, detail="Vuelve a empezar la configuración")
    paso = mfa.verificar_totp(secreto, body.codigo, None)
    if paso is None:
        await _fallo(db, user, ip, "El código no coincide. Revisa la hora del celular y escribe el código que se ve ahora.")
    user.mfa_activo = True
    user.mfa_ultimo_paso = paso
    codigos = await _nuevos_respaldos(db, user)
    await sesiones.registrar_evento(db, "mfa_activado", usuario=user, ip=ip)
    return await _abrir_sesion(db, user, request, codigos_respaldo=codigos)


async def _segundo_factor_ok(db: AsyncSession, user: Usuario, codigo: str, ip: str | None) -> bool:
    """Código de la app o uno de respaldo sin usar. Deja marcado lo usado (falta el commit)."""
    secreto = mfa.descifrar(user.mfa_secreto) if user.mfa_secreto else None
    if not user.mfa_activo or secreto is None:
        raise HTTPException(status_code=409, detail="El segundo factor no está configurado. Pide al administrador que lo reinicie.")

    paso = mfa.verificar_totp(secreto, codigo, user.mfa_ultimo_paso)
    if paso is not None:
        user.mfa_ultimo_paso = paso
        return True

    if mfa.parece_respaldo(codigo):
        pendientes = (await db.scalars(select(UsuarioMfaRespaldo).where(
            UsuarioMfaRespaldo.usuario_id == user.id, UsuarioMfaRespaldo.usado_en.is_(None)))).all()
        for respaldo in pendientes:
            if mfa.coincide_respaldo(codigo, respaldo.codigo_hash):
                respaldo.usado_en = datetime.now(UTC)
                await sesiones.registrar_evento(db, "mfa_respaldo_usado", usuario=user, ip=ip,
                                                detalle=f"quedan {len(pendientes) - 1}")
                return True
    return False


async def _nuevos_respaldos(db: AsyncSession, user: Usuario) -> list[str]:
    """Reemplaza los códigos de respaldo; los nuevos se muestran una sola vez."""
    codigos = mfa.nuevos_codigos_respaldo()
    await db.execute(delete(UsuarioMfaRespaldo).where(UsuarioMfaRespaldo.usuario_id == user.id))
    db.add_all(UsuarioMfaRespaldo(usuario_id=user.id, codigo_hash=mfa.hash_respaldo(c)) for c in codigos)
    return codigos


@router.post("/mfa/verificar", response_model=TokenResponse)
async def mfa_verificar(body: MfaCodigoRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Código de la app (o uno de respaldo) después de la clave."""
    user, _ = await _usuario_mfa(db, body.mfa_token, "verificar")
    ip = sesiones.ip_de(request)
    await _rechazar_si_bloqueada(db, user, ip)
    if await _segundo_factor_ok(db, user, body.codigo, ip):
        return await _abrir_sesion(db, user, request)
    await _fallo(db, user, ip, "Código incorrecto")


@router.post("/mfa/reconfigurar", response_model=MfaReconfiguracion)
async def mfa_reconfigurar(body: MfaCodigoRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Cambio de celular: con el código actual (o uno de respaldo) entrega un QR nuevo.

    El secreto nuevo viaja cifrado en el token y solo reemplaza al viejo cuando la
    persona confirma el primer código (mfa/reactivar): si no termina, el celular viejo
    sigue sirviendo.
    """
    user, _ = await _usuario_mfa(db, body.mfa_token, "verificar")
    ip = sesiones.ip_de(request)
    await _rechazar_si_bloqueada(db, user, ip)
    if not await _segundo_factor_ok(db, user, body.codigo, ip):
        await _fallo(db, user, ip, "Código incorrecto")
    secreto = mfa.nuevo_secreto()
    token = _create_token({"sub": user.username, "type": "mfa", "paso": "reconfigurar",
                           "pendiente": mfa.cifrar(secreto)},
                          datetime.now(UTC) + timedelta(minutes=_MFA_MINUTOS))
    await sesiones.registrar_evento(db, "mfa_qr_nuevo", usuario=user, ip=ip)
    await db.commit()
    return MfaReconfiguracion(mfa_token=token, secreto=secreto,
                              uri=mfa.uri_otpauth(secreto, user.username))


@router.post("/mfa/reactivar", response_model=TokenResponse)
async def mfa_reactivar(body: MfaCodigoRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Confirma el primer código del celular nuevo: cambia el secreto y los códigos de respaldo."""
    user, payload = await _usuario_mfa(db, body.mfa_token, "reconfigurar")
    ip = sesiones.ip_de(request)
    await _rechazar_si_bloqueada(db, user, ip)
    secreto = mfa.descifrar(payload.get("pendiente") or "")
    actual = mfa.descifrar(user.mfa_secreto) if user.mfa_secreto else None
    # Sin MFA activo (lo reiniciaron) o ese QR ya quedó puesto: hay que volver a empezar
    if secreto is None or not user.mfa_activo or actual == secreto:
        raise HTTPException(status_code=409, detail="Vuelve a empezar: ingresa de nuevo usuario y contraseña.")
    paso = mfa.verificar_totp(secreto, body.codigo, None)
    if paso is None:
        await _fallo(db, user, ip, "El código no coincide. Revisa la hora del celular y escribe el código que se ve ahora.")
    user.mfa_secreto = mfa.cifrar(secreto)
    user.mfa_ultimo_paso = paso
    codigos = await _nuevos_respaldos(db, user)
    await sesiones.registrar_evento(db, "mfa_reconfigurado", usuario=user, ip=ip)
    return await _abrir_sesion(db, user, request, codigos_respaldo=codigos)


def _refresh_de(request: Request, cuerpo: str | None) -> str | None:
    # El del cuerpo primero: solo lo mandan las sesiones viejas (localStorage) una vez
    return cuerpo or request.cookies.get(COOKIE_REFRESH)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, body: RefreshRequest | None = Body(None),
                  db: AsyncSession = Depends(get_db)):
    token = _refresh_de(request, body.refresh_token if body else None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No hay sesión")
    try:
        _, sesion, user = await sesion_del_token(db, token, ("refresh",))
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail,
                            headers={"set-cookie": _cookie_borrada()}) from None
    await sesiones.tocar(db, sesion, forzar=True)
    page_keys = sorted(await get_role_page_keys(db, user.rol))
    return _make_tokens(user, sesion, page_keys)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, body: LogoutRequest | None = Body(None),
                 db: AsyncSession = Depends(get_db)):
    """Cierra la sesión del refresh token (cookie). No falla si ya estaba cerrada o vencida."""
    body = body or LogoutRequest()
    listo = _sin_cookie(Response(status_code=status.HTTP_204_NO_CONTENT))
    token = _refresh_de(request, body.refresh_token)
    try:
        payload = jwt.decode(token or "", settings.jwt_secret,
                             algorithms=[settings.jwt_algorithm], options={"verify_exp": False})
    except JWTError:
        return listo
    sid, username = payload.get("sid"), payload.get("sub")
    if payload.get("type") != "refresh" or not sid or not username:
        return listo
    encontrado = await sesiones.sesion_y_usuario(db, sid, username)
    if encontrado is not None:
        sesion, user = encontrado
        if sesion.cerrada_en is None:
            await sesiones.cerrar(db, sesion, body.motivo)
            await sesiones.registrar_evento(db, "logout", usuario=user, ip=sesiones.ip_de(request),
                                            detalle=body.motivo)
            await db.commit()
    return listo


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
