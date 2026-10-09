from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.ai import router as ai_router
from app.api.auth import get_jwt_secret, router as auth_router
from app.api.forecast import router as forecast_router
from app.api.inventory import router as inventory_router
from app.api.main_products import router as main_products_router
from app.api.planning_runs import router as planning_runs_router
from app.api.products import router as products_router
from app.api.shadow import router as shadow_router


logger = logging.getLogger("inventory_intelligence")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate critical configuration on startup
    get_jwt_secret()
    yield


app = FastAPI(
    title="Inventory Intelligence POC",
    version="0.1.0",
    lifespan=lifespan,
)

# Register operational routers
app.include_router(auth_router)
app.include_router(main_products_router)
app.include_router(planning_runs_router)
app.include_router(inventory_router)
app.include_router(forecast_router)
app.include_router(products_router)
app.include_router(shadow_router)
app.include_router(ai_router)


# Note: approvals_router and procurement_router are intentionally unregistered
# while procurement and purchase-order workflows remain outside the current read-only POC scope.

# Configure explicit CORS origins from environment
raw_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
allowed_origins = [
    origin.strip()
    for origin in raw_origins.split(",")
    if origin.strip() and origin.strip() != "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Sanitizes unhandled internal exceptions to prevent credential/query leaking."""
    logger.exception(
        "Unhandled internal server exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please contact the administrator."},
    )


@app.get("/health")
def health_check():
    """Minimal public health check endpoint."""
    return {
        "status": "ok",
        "service": "inventory-intelligence-poc",
    }