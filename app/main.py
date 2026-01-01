import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middlewares import register_exception_handlers
from app.api.v1 import api_router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    debug=settings.api_debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router, prefix="/v1")

@app.get("/health")
async def health_check() -> dict:
    return {"status": "healthy"}
