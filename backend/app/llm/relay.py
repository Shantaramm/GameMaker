"""Ретранслятор: эмулятор GigaChat, на запросы которого отвечает оператор (человек или другой агент).

Нужен, чтобы прогнать настоящую генерацию без ключа: каждый запрос пишется файлом
data/relay/<game_id>/NNN-<step>.request.md, провайдер ждёт рядом файл NNN-<step>.response.md.

    LLM_PROVIDER=relay uvicorn app.main:app
    python -m app.llm.relay            # список запросов без ответа
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path

from ..config import load_settings

POLL_SECONDS = 0.5


def _slug(step: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", step)[:60]


class RelayLLM:
    name = "relay"

    def __init__(self, root: Path, timeout: float = 3600) -> None:
        self.root = root
        self.timeout = timeout
        self._lock = asyncio.Lock()

    async def complete(self, messages, *, step: str, quality="text", game_id: str | None = None,
                       temperature: float = 0.7) -> str:
        folder = self.root / (game_id or "_no_game")
        async with self._lock:
            folder.mkdir(parents=True, exist_ok=True)
            n = len(list(folder.glob("*.request.md"))) + 1
            base = folder / f"{n:03}-{_slug(step)}"
            text = f"<!-- step: {step}; quality: {quality}; temperature: {temperature} -->\n\n"
            text += "\n\n".join(f"===== {m['role']} =====\n{m['content']}" for m in messages)
            base.with_suffix(".request.md").write_text(text, encoding="utf-8")
        answer = base.with_suffix(".response.md")
        deadline = time.monotonic() + self.timeout
        while not answer.exists():
            if time.monotonic() > deadline:
                raise TimeoutError(f"нет ответа на {base.name}")
            await asyncio.sleep(POLL_SECONDS)
        await asyncio.sleep(0.2)  # файл мог ещё дописываться
        return answer.read_text(encoding="utf-8")


def pending(root: Path) -> list[Path]:
    return sorted(p for p in root.glob("*/*.request.md")
                  if not p.with_name(p.name.replace(".request.md", ".response.md")).exists())


if __name__ == "__main__":
    root = load_settings().data_dir / "relay"
    items = pending(root)
    print("\n".join(str(p) for p in items) or "нет запросов без ответа")
    sys.exit(0)
