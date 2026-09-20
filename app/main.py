from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.gateway.router import router as webhook_router, init_gateway_dependencies
from app.admin.router import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Redis connections, adapters, and gateway
    await init_gateway_dependencies()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    description="Enterprise Bot Product Factory for WhatsApp, Telegram, and Chatwoot",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(admin_router)


@app.get("/healthz", tags=["System"])
async def healthz():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/readyz", tags=["System"])
async def readyz():
    return {"status": "ready"}
