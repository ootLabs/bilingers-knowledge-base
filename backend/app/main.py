from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import health

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs"}
