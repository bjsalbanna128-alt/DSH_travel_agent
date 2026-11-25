"""FastAPI application entry point for AI Travel Planner Agent."""

import os
from pathlib import Path

# ── MUST be the absolute first thing: load .env into os.environ ──
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)
print(f"[Main] Loaded env from {_ENV_PATH}, DEEPSEEK_API_KEY={'SET' if os.environ.get('DEEPSEEK_API_KEY') else 'MISSING'}")

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.deps import require_operator
from app.api.itinerary_templates import reader_router as template_reader_router
from app.api.recommendations import reader_router as recommendation_reader_router
from app.api.routes import router as api_router
from app.api.sse import router as sse_router
from app.api.chat import router as chat_router
from app.api.ws import router as ws_router
from app.api.auth import router as auth_router
from app.api.support import tourist_router as support_router
from app.config import settings
from app.db import database
from app.db.database import init_db
from app.services.notifications import notification_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print(f"[TravelAgent] Starting in {settings.app_env} mode")
    print(f"[TravelAgent] DeepSeek: {settings.deepseek_base_url}")
    print(f"[TravelAgent] DeepSeek API Key from settings: {'SET' if settings.deepseek_api_key else 'MISSING'}")
    print(f"[TravelAgent] DeepSeek API Key from env: {'SET' if os.environ.get('DEEPSEEK_API_KEY') else 'MISSING'}")
    print(f"[TravelAgent] Database: {settings.database_url[:50]}...")
    await init_db()

    # Init ChromaDB + warm up embedding model (non-blocking)
    try:
        from app.services.chroma_store import get_chroma_store
        store = get_chroma_store()
        print(f"[TravelAgent] ChromaDB initialized at {settings.chroma_persist_path}")
        print(f"[TravelAgent] ChromaDB attractions: {store.collection_count('attractions')} items")

        from app.services.embeddings import get_embedding_provider
        emb = get_embedding_provider()
        dim = emb.dimension
        print(f"[TravelAgent] Embedding model ready (dim={dim})")
    except Exception as e:
        print(f"[TravelAgent] Warning: ChromaDB/Embeddings init failed: {e}")
        print("[TravelAgent] Semantic search will be unavailable. Amap API will be used.")

    # Init Redis (optional — system works without it)
    try:
        from app.services.redis_cache import _get_redis
        await _get_redis()
        print("[TravelAgent] Redis ready")
    except Exception:
        print("[TravelAgent] Redis unavailable — caching disabled")

    async with notification_worker(database.async_session):
        yield
    print("[TravelAgent] Shutting down")


app = FastAPI(
    title="AI 旅游规划 Agent",
    description="Multi-Agent 智能旅游规划系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sse_router, prefix="/api")
app.include_router(api_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(template_reader_router, prefix="/api")
app.include_router(recommendation_reader_router, prefix="/api")
app.include_router(support_router, prefix="/api")
app.include_router(admin_router, prefix="/api", dependencies=[Depends(require_operator)])
app.include_router(ws_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
