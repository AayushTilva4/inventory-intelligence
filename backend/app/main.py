from fastapi import FastAPI
from app.api.inventory import router as inventory_router
from fastapi.middleware.cors import CORSMiddleware
from app.api.forecast import router as forecast_router
from app.api.ai import router as ai_router
from app.api.auth import router as auth_router
from app.api.products import router as products_router
from app.api.main_products import router as main_products_router

app = FastAPI(
    title="Inventory Intelligence POC",
    version="0.1.0",
)
app.include_router(inventory_router)
app.include_router(forecast_router)
app.include_router(ai_router)
app.include_router(auth_router)
app.include_router(products_router)
app.include_router(main_products_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "inventory-intelligence-poc",
    }