"""HTTP API на демо-провайдере: бриф, генерация в фоне, статусы, лимиты."""

import asyncio
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


# --- каталог готовых игр ---


def test_catalog_has_featured_games_and_serves_them(client):
    body = client.get("/api/catalog").json()
    assert [c["id"] for c in body["featured"]] == ["demo", "postman", "museum"]
    postman = body["featured"][1]
    assert postman["title"] == "Последнее письмо перед снегом" and postman["locations"] == 5
    assert [c["role"] for c in postman["characters"]] == ["hero", "companion"]
    assert postman["background"]["far"] == "mountains" and postman["enemy"]["id"] == "yakov_boss"
    assert body["community"] == []
    game = client.get("/api/games/postman").json()
    assert game["arenas"] and game["levels"] and game["meta"]["title"] == postman["title"]


def test_publish_only_by_owner_and_only_when_ready(client):
    r = client.post("/api/games", json={"brief": BRIEF}).json()
    game_id, token = r["game_id"], r["owner_token"]
    assert len(token) >= 20
    wait_ready(client, game_id)
    assert client.post(f"/api/games/{game_id}/publish", json={"owner_token": "чужой-секрет", "published": True}).status_code == 403
    assert client.post("/api/games/nope/publish", json={"owner_token": token, "published": True}).status_code == 404
    assert client.get(f"/api/games/{game_id}/status").json()["published"] is False

    assert client.post(f"/api/games/{game_id}/publish", json={"owner_token": token, "published": True}).json() == {"published": True}
    community = client.get("/api/catalog").json()["community"]
    assert [c["id"] for c in community] == [game_id] and community[0]["published_at"]
    assert client.get(f"/api/games/{game_id}/status").json()["published"] is True

    client.post(f"/api/games/{game_id}/publish", json={"owner_token": token, "published": False})
    assert client.get("/api/catalog").json()["community"] == []


def test_publish_rejects_unfinished_game(tmp_path):
    class Stuck:
        """Генерация, которая не заканчивается, пока идёт тест."""

        name = "stuck"

        async def complete(self, *_args, **_kw):
            await asyncio.sleep(60)

    slow = Stuck()
    settings = load_settings({"DATA_DIR": str(tmp_path)})
    with TestClient(create_app(settings, llm=slow)) as c:
        r = c.post("/api/games", json={"brief": BRIEF}).json()
        resp = c.post(f"/api/games/{r['game_id']}/publish", json={"owner_token": r["owner_token"], "published": True})
        assert resp.status_code == 409


def test_old_database_is_migrated(tmp_path):
    import sqlite3

    from app.storage import SCHEMA, Storage

    db = sqlite3.connect(tmp_path / "games.sqlite")
    db.executescript(SCHEMA)
    db.execute("INSERT INTO games (id, status, brief, created_at, updated_at) VALUES ('old', 'ready', 'b', 0, 0)")
    db.commit()
    db.close()
    storage = Storage(tmp_path / "games.sqlite")
    assert storage.get("old")["published"] == 0


def test_demo_mode_without_combat_builds_dialogue_game(client):
    profile = {"combat": "none", "dialogue": "deep"}
    brief = client.post("/api/brief", json={"idea": "тихая история без драк", "profile": profile}).json()
    assert brief["brief_markdown"].startswith("# Последняя смена")
    game_id = client.post("/api/games", json={"brief": BRIEF, "profile": profile}).json()["game_id"]
    st, _ = wait_ready(client, game_id)
    assert st["status"] == "ready", st
    game = client.get(f"/api/games/{game_id}").json()
    assert game["profile"] == profile and not game.get("enemies") and game["inner_skills"]
