"""HTTP API (SPEC §10). Запуск: uvicorn app.main:app --reload (из /backend)."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .config import Settings, load_settings
from .engine.art import LIBRARY_DIR
from .generation.pipeline import GenerationFailed, Pipeline, generate_brief
from .llm import LLM, make_llm
from .storage import Storage

log = logging.getLogger("rpg")

MAX_BRIEF = 8000
MAX_IDEA = 4000
BRIEFS_PER_HOUR = 30


class IdeaIn(BaseModel):
    idea: str = Field(min_length=3, max_length=MAX_IDEA)


class BriefIn(BaseModel):
    brief: str = Field(min_length=20, max_length=MAX_BRIEF)


def create_app(settings: Settings | None = None, llm: LLM | None = None) -> FastAPI:
    settings = settings or load_settings()
    storage = Storage(settings.data_dir / "games.sqlite")
    semaphore = asyncio.Semaphore(settings.max_concurrent_generations)
    tasks: set[asyncio.Task] = set()
    brief_hits: dict[str, list[float]] = {}
    state: dict[str, Any] = {"llm": llm}

    def get_llm() -> LLM:
        if state["llm"] is None:
            state["llm"] = make_llm(settings)
        return state["llm"]

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        storage.fail_interrupted()
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(title="Генератор RPG", lifespan=lifespan)

    def client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")

    async def worker(game_id: str, brief: str) -> None:
        async with semaphore:
            async def on_status(step: str, progress: float, info: dict[str, Any]) -> None:
                if step == "ready":
                    return  # «готово» ставится только после сохранения игры, ниже
                fields: dict[str, Any] = {"status": step, "step": step, "progress": round(progress, 3)}
                if "outline" in info:
                    fields["preview"] = info["outline"]
                if step == "locations":
                    fields["detail"] = {"done": info.get("done", 0), "total": info.get("total", 0)}
                storage.update(game_id, **fields)

            try:
                result = await Pipeline(get_llm(), brief, game_id, on_status=on_status).run()
            except GenerationFailed as exc:
                storage.update(game_id, status="failed", error=str(exc), detail=[str(i) for i in exc.issues[:20]])
                return
            except Exception as exc:  # noqa: BLE001 — пользователь должен получить статус, а не вечную загрузку
                log.exception("generation %s crashed", game_id)
                storage.update(game_id, status="failed", error=f"Внутренняя ошибка генерации: {type(exc).__name__}")
                return
            storage.update(game_id, status="ready", step="ready", progress=1.0, game=result.game.dump(),
                           report=result.report.model_dump(mode="json"), warnings=[str(w) for w in result.warnings])

    @app.post("/api/brief")
    async def brief(body: IdeaIn, request: Request) -> dict[str, Any]:
        ip = client_ip(request)
        now = asyncio.get_running_loop().time()
        hits = [t for t in brief_hits.get(ip, []) if now - t < 3600]
        if len(hits) >= BRIEFS_PER_HOUR:
            raise HTTPException(429, "Слишком много запросов. Попробуйте через час.")
        brief_hits[ip] = [*hits, now]
        return await generate_brief(body.idea, get_llm()) | {"provider": settings.llm_provider}

    @app.post("/api/games")
    async def create_game(body: BriefIn, request: Request) -> dict[str, str]:
        ip = client_ip(request)
        if storage.count_recent(ip, 3600) >= settings.games_per_hour_per_ip:
            raise HTTPException(429, f"Можно создать не больше {settings.games_per_hour_per_ip} игр в час. Попробуйте позже.")
        game_id = secrets.token_urlsafe(9)  # неугадываемый id: игру видит только тот, у кого ссылка
        storage.create(game_id, body.brief, ip, settings.llm_provider)
        task = asyncio.create_task(worker(game_id, body.brief))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return {"game_id": game_id}

    @app.get("/api/games/{game_id}/status")
    async def status(game_id: str) -> dict[str, Any]:
        row = storage.get(game_id)
        if row is None:
            raise HTTPException(404, "Игра не найдена.")
        out = {k: row[k] for k in ("status", "step", "progress", "error", "provider")}
        out["outline"] = row["preview"]
        out["detail"] = row["detail"]
        if row["status"] == "queued":
            out["queue_position"] = storage.queued_before(game_id)
        return out

    @app.get("/api/games/{game_id}")
    async def get_game(game_id: str) -> dict[str, Any]:
        row = storage.get(game_id)
        if row is None:
            raise HTTPException(404, "Игра не найдена.")
        if row["status"] != "ready":
            raise HTTPException(409, "Игра ещё не готова.")
        return row["game"]

    @app.get("/api/info")
    async def info() -> dict[str, Any]:
        """Что за провайдер: в демо-режиме сайт предупреждает, что игра соберётся из заготовки."""
        return {"provider": settings.llm_provider, "max_brief": MAX_BRIEF}

    @app.get("/api/pixelart/library")
    async def pixelart_library() -> dict[str, Any]:
        return _library_bundle()

    return app


@lru_cache(maxsize=1)
def _library_bundle() -> dict[str, Any]:
    bundle: dict[str, Any] = {}
    for f in sorted(LIBRARY_DIR.rglob("*.json")):
        bundle[str(f.relative_to(LIBRARY_DIR))] = json.loads(f.read_text(encoding="utf-8"))
    return bundle


app = create_app()
