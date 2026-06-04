from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.routers.clientes import router as clientes_router
from app.routers.facturacion import router as facturacion_router
from app.routers.flujo import router as flujo_router
from app.routers.gastos import router as gastos_router
from app.routers.gestiones import router as gestiones_router
from app.routers.labores import router as labores_router
from app.routers.nomina import router as nomina_router
from app.routers.ordenes import router as ordenes_router
from app.routers.reportes import router as reportes_router
from app.routers.personal import router as personal_router
from app.config import settings
from app.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Servilla ERP",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(clientes_router)
app.include_router(personal_router)
app.include_router(ordenes_router)
app.include_router(facturacion_router)
app.include_router(gestiones_router)
app.include_router(reportes_router)
app.include_router(gastos_router)
app.include_router(nomina_router)
app.include_router(labores_router)
app.include_router(flujo_router)


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.environment}
