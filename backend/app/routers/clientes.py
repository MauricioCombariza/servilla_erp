from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.clientes import Cliente, PrecioCliente
from app.schemas.clientes import (
    ClienteCreate, ClienteRead, ClienteUpdate, ClienteWithPrecios,
    PrecioClienteCreate, PrecioClienteRead, PrecioClienteUpdate,
)

router = APIRouter(prefix="/api/clientes", tags=["clientes"])
_auth = Depends(require_role("administrador", "logistica"))


# ── Clientes ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ClienteRead])
async def list_clientes(
    activo: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(Cliente).order_by(Cliente.nombre_empresa)
    if activo is not None:
        q = q.where(Cliente.activo == activo)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=ClienteRead, status_code=status.HTTP_201_CREATED)
async def create_cliente(body: ClienteCreate, db: AsyncSession = Depends(get_db), _=_auth):
    cliente = Cliente(**body.model_dump())
    db.add(cliente)
    await db.commit()
    await db.refresh(cliente)
    return cliente


@router.get("/{cliente_id}", response_model=ClienteWithPrecios)
async def get_cliente(cliente_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    cliente = result.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return cliente


@router.put("/{cliente_id}", response_model=ClienteRead)
async def update_cliente(
    cliente_id: int, body: ClienteUpdate, db: AsyncSession = Depends(get_db), _=_auth
):
    result = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    cliente = result.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(cliente, field, value)
    await db.commit()
    await db.refresh(cliente)
    return cliente


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cliente(cliente_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    cliente = result.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    cliente.activo = False
    await db.commit()


# ── Precios ───────────────────────────────────────────────────────────────────

@router.get("/{cliente_id}/precios", response_model=list[PrecioClienteRead])
async def list_precios(
    cliente_id: int,
    solo_activos: bool = True,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(PrecioCliente).where(PrecioCliente.cliente_id == cliente_id)
    if solo_activos:
        q = q.where(PrecioCliente.activo == True)  # noqa: E712
    q = q.order_by(PrecioCliente.tipo_servicio, PrecioCliente.ambito, PrecioCliente.vigencia_desde.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/{cliente_id}/precios", response_model=PrecioClienteRead, status_code=201)
async def create_precio(
    cliente_id: int,
    body: PrecioClienteCreate,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    # Verificar que el cliente existe
    exists = await db.execute(select(Cliente.id).where(Cliente.id == cliente_id))
    if exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    precio = PrecioCliente(cliente_id=cliente_id, **body.model_dump())
    db.add(precio)
    await db.commit()
    await db.refresh(precio)
    return precio


@router.put("/{cliente_id}/precios/{precio_id}", response_model=PrecioClienteRead)
async def update_precio(
    cliente_id: int,
    precio_id: int,
    body: PrecioClienteUpdate,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    result = await db.execute(
        select(PrecioCliente).where(
            PrecioCliente.id == precio_id,
            PrecioCliente.cliente_id == cliente_id,
        )
    )
    precio = result.scalar_one_or_none()
    if precio is None:
        raise HTTPException(status_code=404, detail="Precio no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(precio, field, value)
    await db.commit()
    await db.refresh(precio)
    return precio


@router.delete("/{cliente_id}/precios/{precio_id}", status_code=204)
async def delete_precio(
    cliente_id: int,
    precio_id: int,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    result = await db.execute(
        select(PrecioCliente).where(
            PrecioCliente.id == precio_id,
            PrecioCliente.cliente_id == cliente_id,
        )
    )
    precio = result.scalar_one_or_none()
    if precio is None:
        raise HTTPException(status_code=404, detail="Precio no encontrado")
    precio.activo = False
    await db.commit()
