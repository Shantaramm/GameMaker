"""Клиент GigaChat на подменённом сервере: токен, кэш, ретраи, логи без секретов."""

import asyncio
import json
import time

import httpx
import pytest

from app.config import load_settings
from app.gigachat.client import GigaChatClient, GigaChatError

KEY = "c2VjcmV0LWtleQ=="
TOKEN = "tok-123"


class FakeSber:
    def __init__(self, fail_chat: int = 0, chat_status: int = 503, token_ttl: float = 1800):
        self.requests: list[httpx.Request] = []
        self.fail_chat = fail_chat
        self.chat_status = chat_status
        self.token_ttl = token_ttl
        self.tokens = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/oauth"):
            self.tokens += 1
            return httpx.Response(200, json={"access_token": f"{TOKEN}-{self.tokens}", "expires_at": int((time.time() + self.token_ttl) * 1000)})
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "GigaChat-2"}, {"id": "GigaChat-2-Max"}]})
        if path == "/v1/chat/completions":
            if self.fail_chat:
                self.fail_chat -= 1
                return httpx.Response(self.chat_status, json={"error": "busy"})
            body = json.loads(request.content)
            return httpx.Response(200, json={"model": body["model"], "choices": [{"message": {"role": "assistant", "content": "Москва"}}],
                                             "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})
        return httpx.Response(404)


def client_for(server: FakeSber, tmp_path) -> GigaChatClient:
    settings = load_settings({"GIGACHAT_AUTH_KEY": KEY, "DATA_DIR": str(tmp_path)})
    sleeps: list[float] = []

    async def no_sleep(s):
        sleeps.append(s)

    c = GigaChatClient(settings, transport=httpx.MockTransport(server), sleep=no_sleep)
    c.sleeps = sleeps
    return c


def run(coro):
    return asyncio.run(coro)


def test_token_request_follows_spec(tmp_path):
    server = FakeSber()
    c = client_for(server, tmp_path)
    run(c.token())
    req = server.requests[0]
    assert req.method == "POST" and str(req.url) == "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    assert req.headers["Authorization"] == f"Basic {KEY}"
    assert req.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert len(req.headers["RqUID"]) == 36
    assert req.content == b"scope=GIGACHAT_API_PERS"


def test_token_is_cached_and_refreshed_before_expiry(tmp_path):
    server = FakeSber()
    c = client_for(server, tmp_path)

    async def scenario():
        a = await c.token()
        b = await c.token()
        c._expires_at = time.time() + 30  # осталось меньше 60 секунд — пора обновлять
        d = await c.token()
        return a, b, d

    a, b, d = run(scenario())
    assert a == b == f"{TOKEN}-1" and d == f"{TOKEN}-2"
    assert server.tokens == 2


def test_models_and_chat(tmp_path):
    server = FakeSber()
    c = client_for(server, tmp_path)

    async def scenario():
        models = await c.models()
        reply = await c.chat([{"role": "user", "content": "?"}], "GigaChat-2", step="smoke", game_id="g1", temperature=0)
        return models, reply

    models, reply = run(scenario())
    assert models == ["GigaChat-2", "GigaChat-2-Max"]
    assert reply.text == "Москва" and reply.usage["total_tokens"] == 12
    chat_req = server.requests[-1]
    assert chat_req.headers["Authorization"] == f"Bearer {TOKEN}-1"
    body = json.loads(chat_req.content)
    assert "function_call" not in body and "functions" not in body
    assert body["model"] == "GigaChat-2"


def test_retries_on_5xx_and_429_with_backoff(tmp_path):
    server = FakeSber(fail_chat=2, chat_status=429)
    c = client_for(server, tmp_path)
    reply = run(c.chat([{"role": "user", "content": "?"}], "GigaChat-2"))
    assert reply.text == "Москва"
    assert c.sleeps == [1.0, 2.0]


def test_gives_up_after_three_attempts(tmp_path):
    server = FakeSber(fail_chat=5, chat_status=503)
    c = client_for(server, tmp_path)
    with pytest.raises(GigaChatError, match="после 3 попыток"):
        run(c.chat([{"role": "user", "content": "?"}], "GigaChat-2"))


def test_client_errors_are_not_retried(tmp_path):
    server = FakeSber(fail_chat=1, chat_status=400)
    c = client_for(server, tmp_path)
    with pytest.raises(GigaChatError, match="HTTP 400"):
        run(c.chat([{"role": "user", "content": "?"}], "GigaChat-2"))
    assert c.sleeps == []


def test_log_has_usage_but_no_secrets(tmp_path):
    server = FakeSber()
    c = client_for(server, tmp_path)
    run(c.chat([{"role": "user", "content": "?"}], "GigaChat-2", step="outline", game_id="g42"))
    log = (tmp_path / "logs" / "g42.jsonl").read_text(encoding="utf-8")
    record = json.loads(log.splitlines()[0])
    assert record["step"] == "outline" and record["usage"]["total_tokens"] == 12 and "seconds" in record
    assert KEY not in log and TOKEN not in log


def test_missing_key_and_ca_bundle_fail_loudly(tmp_path):
    with pytest.raises(GigaChatError, match="GIGACHAT_AUTH_KEY"):
        GigaChatClient(load_settings({"DATA_DIR": str(tmp_path)}))
    settings = load_settings({"GIGACHAT_AUTH_KEY": KEY, "GIGACHAT_CA_BUNDLE": str(tmp_path / "nope.cer")})
    with pytest.raises(GigaChatError, match="сертификата"):
        GigaChatClient(settings)


def test_provider_defaults_to_demo_without_key():
    assert load_settings({}).llm_provider == "demo"
    assert load_settings({"GIGACHAT_AUTH_KEY": KEY}).llm_provider == "gigachat"
