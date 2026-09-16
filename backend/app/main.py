"""Memo — search finds what the world wrote; this finds what you thought."""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import router as v1_router
from .database import Database
from .services.llm import LLMService

load_dotenv()
logging.basicConfig(level=os.getenv("MEMO_LOG_LEVEL", "INFO"))
log = logging.getLogger("memo")


def create_app(db_path: str | None = None, dim: int | None = None) -> FastAPI:
    """Build the app. Tests call this with a temp db; production uses env defaults."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        llm = LLMService()
        app.state.llm = llm

        embed = llm.embed_status
        app.state.db = Database(
            db_path or os.getenv("MEMO_DB_PATH", "memo.db"),
            dim=dim or llm.dim,
            # Only fingerprint a store that will actually hold vectors.
            fingerprint=embed.fingerprint if embed.ok else "",
        )

        if embed.ok:
            log.info("Search: semantic via %s (%s, %d dims)", embed.name, embed.model, embed.dim)
        else:
            log.warning("Search: keyword only. %s", embed.detail)
        if not llm.enabled:
            log.info("Enrichment off (no OPENAI_API_KEY) — notes save without claim/tags.")
        log.info("Memo ready — %d notes in store", app.state.db.count())
        yield

    app = FastAPI(
        title="Memo",
        description="A reading memory. Save a passage and what you thought of it; "
        "find it later by half-remembering the idea.",
        version="2.0.0",
        lifespan=lifespan,
    )

    # Chrome extension origins are opaque ids, so match them by pattern.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(chrome-extension://.*|http://localhost:\d+)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(v1_router)

    @app.get("/")
    def root() -> dict:
        return {"service": "Memo", "version": "2.0.0", "docs": "/docs"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
