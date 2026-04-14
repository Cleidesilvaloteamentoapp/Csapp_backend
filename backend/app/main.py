
"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.tenant import TenantMiddleware
from app.utils.exceptions import (
    AuthenticationError,
    InsufficientPermissionsError,
    InvalidTokenError,
    ResourceNotFoundError,
    SicrediIntegrationError,
    StorageError,
    TenantIsolationError,
)
from app.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    setup_logging(debug=settings.DEBUG)
    logger.info("app_startup", env=settings.APP_ENV)
    yield
    logger.info("app_shutdown")


# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])

app = FastAPI(
    title=settings.APP_NAME,
    description="API REST para sistema de gestão imobiliária multi-tenant especializado em loteamentos.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    redirect_slashes=False,  # CRÍTICO: evita redirect que perde Authorization header
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Middleware (order matters – outermost first)
# ---------------------------------------------------------------------------

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
# CORS deve vir ANTES do TenantMiddleware para processar headers corretamente
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],  # Permitir todos os métodos
    allow_headers=["*"],  # Permitir todos os headers
    expose_headers=["*"],  # Expor todos os headers
    max_age=3600,  # Cache preflight por 1 hora
)
app.add_middleware(TenantMiddleware)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.ALLOWED_HOSTS)
if settings.is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS,
    )


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(TenantIsolationError)
async def tenant_error_handler(request: Request, exc: TenantIsolationError):
    logger.warning("tenant_isolation_violation", path=request.url.path, detail=exc.detail)
    return JSONResponse(status_code=403, content={"detail": exc.detail})


@app.exception_handler(InsufficientPermissionsError)
async def permissions_error_handler(request: Request, exc: InsufficientPermissionsError):
    return JSONResponse(status_code=403, content={"detail": exc.detail})


@app.exception_handler(ResourceNotFoundError)
async def not_found_handler(request: Request, exc: ResourceNotFoundError):
    return JSONResponse(status_code=404, content={"detail": exc.detail})


@app.exception_handler(AuthenticationError)
async def auth_error_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(status_code=401, content={"detail": exc.detail})


@app.exception_handler(InvalidTokenError)
async def token_error_handler(request: Request, exc: InvalidTokenError):
    return JSONResponse(status_code=401, content={"detail": exc.detail})


@app.exception_handler(StorageError)
async def storage_error_handler(request: Request, exc: StorageError):
    return JSONResponse(status_code=400, content={"detail": exc.detail})


@app.exception_handler(SicrediIntegrationError)
async def sicredi_error_handler(request: Request, exc: SicrediIntegrationError):
    logger.error("sicredi_integration_error", detail=exc.detail)
    return JSONResponse(status_code=502, content={"detail": exc.detail})


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health_check():
    """Simple health check for load balancers and Docker."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Mount API router
# ---------------------------------------------------------------------------

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
