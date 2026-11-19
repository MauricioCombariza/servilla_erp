import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.usuarios import Usuario

# Clave del admin de pruebas. Solo existe en bases de prueba (ENVIRONMENT=test): las
# migraciones ya no siembran usuarios, así que lo crea este fixture con un hash calculado
# al vuelo. Nunca se usa ni se escribe en producción.
ADMIN_PRUEBA = ("admin", "admin123")


@pytest.fixture(scope="session", autouse=True)
async def admin_de_pruebas():
    if settings.environment != "test":
        return  # en otra base no se crea nada; las pruebas que usan admin fallarán solas
    username, clave = ADMIN_PRUEBA
    async with AsyncSessionLocal() as db:
        if await db.scalar(select(Usuario.id).where(Usuario.username == username)) is None:
            db.add(Usuario(username=username, nombre_completo="Administrador (pruebas)",
                           password_hash=bcrypt.hashpw(clave.encode(), bcrypt.gensalt()).decode(),
                           rol="administrador", activo=True))
            await db.commit()


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
