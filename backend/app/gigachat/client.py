"""Клиент GigaChat REST API (SPEC §8).

- OAuth-токен кэшируется и обновляется за 60 секунд до expires_at.
- 3 попытки с экспоненциальной задержкой на 429, 5xx и таймаут.
- Каждый запрос пишется в data/logs/{game_id}.jsonl: шаг, модель, длительность, usage. Ключ и токен — никогда.
- TLS проверяется сертификатом НУЦ Минцифры (GIGACHAT_CA_BUNDLE); отключить проверку нельзя.
- function_call в запросы не передаётся: встроенная генерация картинок не используется.

Проверка доступа: python -m app.gigachat.client --smoke
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings, load_settings

TOKEN_REFRESH_MARGIN = 60  # секунд
RETRIES = 3
BACKOFF = 1.0  # секунд: 1, 2, 4
CHAT_TIMEOUT = 120.0
RETRY_STATUSES = {429, 500, 502, 503, 504}


class GigaChatError(RuntimeError):
    pass


@dataclass
class ChatResult:
    text: str
    model: str
    usage: dict[str, int]
    seconds: float


class GigaChatClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None, sleep=asyncio.sleep) -> None:
        if not settings.gigachat_auth_key:
            raise GigaChatError("не задан GIGACHAT_AUTH_KEY")
        self.settings = settings
        self._sleep = sleep
        verify: Any = True
        if transport is None:
            ca = settings.ca_bundle_path
            if not ca.exists():
                raise GigaChatError(f"нет корневого сертификата НУЦ Минцифры: {ca} (GIGACHAT_CA_BUNDLE); проверку TLS отключать нельзя")
            verify = str(ca)
        self._http = httpx.AsyncClient(transport=transport, verify=verify, timeout=CHAT_TIMEOUT)
        self._token: str | None = None
        self._expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- токен ---

    async def token(self) -> str:
        async with self._token_lock:
            if self._token and time.time() < self._expires_at - TOKEN_REFRESH_MARGIN:
                return self._token
            response = await self._request(
                "POST", self.settings.gigachat_oauth_url,
                headers={
                    "Authorization": f"Basic {self.settings.gigachat_auth_key}",
                    "RqUID": str(uuid.uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"scope": self.settings.gigachat_scope},
            )
            body = response.json()
            self._token = body["access_token"]
            expires = float(body.get("expires_at", 0))
            self._expires_at = expires / 1000 if expires > 1e11 else expires or time.time() + 1800
            return self._token

    # --- запросы ---

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(RETRIES):
            try:
                response = await self._http.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = exc
            else:
                if response.status_code not in RETRY_STATUSES:
                    if response.is_error:
                        raise GigaChatError(f"{method} {url}: HTTP {response.status_code}: {response.text[:300]}")
                    return response
                last = GigaChatError(f"{method} {url}: HTTP {response.status_code}")
            if attempt < RETRIES - 1:
                await self._sleep(BACKOFF * 2 ** attempt)
        raise GigaChatError(f"{method} {url}: не удалось после {RETRIES} попыток: {last}")

    async def _api(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {"Authorization": f"Bearer {await self.token()}", "Accept": "application/json"}
        return await self._request(method, f"{self.settings.gigachat_base_url}{path}", headers=headers, **kwargs)

    async def models(self) -> list[str]:
        response = await self._api("GET", "/v1/models")
        return [m["id"] for m in response.json().get("data", [])]

    async def chat(self, messages: list[dict[str, str]], model: str, *, temperature: float = 0.7,
                   step: str = "", game_id: str | None = None, max_tokens: int | None = None) -> ChatResult:
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        started = time.monotonic()
        response = await self._api("POST", "/v1/chat/completions", json=payload)
        seconds = round(time.monotonic() - started, 2)
        body = response.json()
        text = body["choices"][0]["message"]["content"]
        usage = {k: int(v) for k, v in (body.get("usage") or {}).items() if isinstance(v, (int, float))}
        result = ChatResult(text=text, model=body.get("model", model), usage=usage, seconds=seconds)
        self._log(game_id, step, result)
        return result

    def _log(self, game_id: str | None, step: str, result: ChatResult) -> None:
        logs = self.settings.data_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        record = {"ts": round(time.time(), 3), "step": step, "model": result.model, "seconds": result.seconds, "usage": result.usage}
        with (logs / f"{game_id or 'no_game'}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def _smoke(settings: Settings) -> None:
    client = GigaChatClient(settings)
    try:
        await client.token()
        print("токен получен")
        models = await client.models()
        print("модели:", ", ".join(models) or "(пусто)")
        reply = await client.chat([{"role": "user", "content": "Ответь одним словом: столица России?"}],
                                  settings.gigachat_model_fast, step="smoke", temperature=0)
        print(f"чат ({reply.model}, {reply.seconds} с, {reply.usage}): {reply.text.strip()}")
    finally:
        await client.aclose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Клиент GigaChat")
    parser.add_argument("--smoke", action="store_true", help="токен → список моделей → короткий чат")
    args = parser.parse_args(argv)
    if not args.smoke:
        parser.print_help()
        return 0
    try:
        asyncio.run(_smoke(load_settings()))
    except GigaChatError as exc:
        print(f"ошибка: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
