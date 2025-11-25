from fastapi import FastAPI
import asyncio
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.db import Base, engine
from app.api import proxy  # noqa: F401
import app.models  # noqa: F401
from .odoo_projects_gateway import router as odoo_projects_router

app = FastAPI(title=settings.PROJECT_NAME)


@app.on_event("startup")
async def on_startup() -> None:
    """Старт апки: чекаємо, поки буде доступна БД, і тоді створюємо таблиці."""
    max_attempts = 10
    delay_seconds = 2

    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print(f"[startup] DB connected, metadata created (attempt {attempt})")
            break
        except Exception as e:
            # можна звузити до OperationalError, але хай ловить усе
            if attempt == max_attempts:
                print(f"[startup] DB connection failed after {attempt} attempts: {e}")
                raise
            print(f"[startup] DB not ready (attempt {attempt}), retrying in {delay_seconds}s...")
            await asyncio.sleep(delay_seconds)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


app.include_router(proxy.router, prefix=settings.API_V1_STR)
app.include_router(odoo_projects_router)
