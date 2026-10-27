"""HTTP API на демо-провайдере: бриф, генерация в фоне, статусы, лимиты."""

import time

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.llm import DemoLLM, ScriptedLLM
from app.main import create_app

BRIEF = "Туманный портовый город, погас маяк, пропадают люди. Нужен детектив с мистикой."


@pytest.fixture
def client(tmp_path):
    settings = load_settings({"DATA_DIR": str(tmp_path), "GAMES_PER_HOUR_PER_IP": "2"})
    with TestClient(create_app(settings, llm=DemoLLM())) as c:
        yield c


def wait_ready(client, game_id, timeout=30):
    seen = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get(f"/api/games/{game_id}/status").json()
        seen.append(st["status"])
        if st["status"] in ("ready", "failed"):
            return st, seen
        time.sleep(0.05)
    raise AssertionError(f"генерация не закончилась: {seen[-5:]}")


def test_brief(client):
    r = client.post("/api/brief", json={"idea": "детектив в порту"})
    assert r.status_code == 200
    body = r.json()
    assert body["brief_markdown"].startswith("#") and body["questions"] and body["provider"] == "demo"


def test_generation_flow(client):
    r = client.post("/api/games", json={"brief": BRIEF})
    assert r.status_code == 200
    game_id = r.json()["game_id"]
    assert len(game_id) >= 12  # неугадываемый

    st, seen = wait_ready(client, game_id)
    assert st["status"] == "ready" and st["progress"] == 1.0 and st["error"] is None
    assert st["outline"]["characters"][0]["name"] == "Арина Стрельцова"
    game = client.get(f"/api/games/{game_id}").json()
    assert game["schema_version"] == "2" and game["levels"] and game["stats_template"]


def test_game_not_ready_and_unknown(client):
    assert client.get("/api/games/nope/status").status_code == 404
    assert client.get("/api/games/nope").status_code == 404


def test_rate_limit_and_brief_length(client):
    assert client.post("/api/games", json={"brief": "x" * 8001}).status_code == 422
    for _ in range(2):
        assert client.post("/api/games", json={"brief": BRIEF}).status_code == 200
    r = client.post("/api/games", json={"brief": BRIEF})
    assert r.status_code == 429 and "игр в час" in r.json()["detail"]


def test_failed_generation_reports_error(tmp_path):
    settings = load_settings({"DATA_DIR": str(tmp_path)})
    llm = ScriptedLLM(lambda step, messages: "никакого JSON")
    with TestClient(create_app(settings, llm=llm)) as c:
        game_id = c.post("/api/games", json={"brief": BRIEF}).json()["game_id"]
        st, _ = wait_ready(c, game_id)
        assert st["status"] == "failed" and "JSON" in st["error"]
        assert c.get(f"/api/games/{game_id}").status_code == 409


def test_interrupted_generations_are_failed_on_restart(tmp_path):
    from app.storage import Storage

    storage = Storage(tmp_path / "games.sqlite")
    storage.create("abc", BRIEF, "1.2.3.4", "demo")
    storage.update("abc", status="locations")
    settings = load_settings({"DATA_DIR": str(tmp_path)})
    with TestClient(create_app(settings, llm=DemoLLM())) as c:
        st = c.get("/api/games/abc/status").json()
        assert st["status"] == "failed" and "перезапускался" in st["error"]


def test_pixelart_library_endpoint(client):
    bundle = client.get("/api/pixelart/library").json()
    assert "palettes.json" in bundle and "portrait/hair.json" in bundle and "tiles/tileset.json" in bundle


def test_info_reports_provider(client):
    assert client.get("/api/info").json() == {"provider": "demo", "max_brief": 8000}
