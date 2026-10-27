"""Пайплайн генерации на сценарном и демо-провайдерах (без сети)."""

import asyncio
import copy
import json

import pytest

from app.engine.validator import validate
from app.generation.fragments import assemble, dump, referenced_ids, split_game
from app.generation.json_utils import JsonError, extract_json, parse_json, try_parse
from app.generation.pipeline import GenerationFailed, Pipeline, generate_brief, split_brief
from app.llm import DemoLLM, ScriptedLLM, _demo_fragments

from .conftest import DEMO_PATH


def run(coro):
    return asyncio.run(coro)


def demo_responses():
    outline, contents, items = _demo_fragments()
    return {"outline": dump(outline), **{f"location:{k}": dump(v) for k, v in contents.items()}, "items": dump(items)}


def scripted(overrides=None, fix=None):
    """Отвечает фрагментами демо-игры; overrides[step] — очередь подменных ответов; fix(step, fragment) — ответ на починку."""
    base = demo_responses()
    queues = {k: list(v) for k, v in (overrides or {}).items()}

    def responder(step, messages):
        if step.startswith("fix:"):
            fragment = try_parse(messages[-1]["content"])
            return json.dumps(fix(step, fragment) if fix else fragment, ensure_ascii=False)
        if step.startswith("repair_json:"):
            return json.dumps(base[step.split(":", 1)[1]], ensure_ascii=False)
        if queues.get(step):
            r = queues[step].pop(0)
            return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        if step == "brief":
            return "# Бриф\n\nТекст.\n\n## Уточняющие вопросы\n- Первый?\n- Второй?\n"
        return json.dumps(base[step], ensure_ascii=False)

    return ScriptedLLM(responder)


def generate(llm):
    statuses = []
    result = run(Pipeline(llm, "бриф", "g1", on_status=lambda st, p, info: statuses.append((st, p, info))).run())
    return result, statuses


# --- json_utils ---


def test_extract_json_handles_fences_text_and_braces_in_strings():
    text = 'Вот ответ:\n```json\n{"a": "скобка } внутри", "b": {"c": [1, 2]}}\n```\nГотово.'
    assert json.loads(extract_json(text)) == {"a": "скобка } внутри", "b": {"c": [1, 2]}}
    assert try_parse('{"q": "кавычка \\" и {"}') == {"q": 'кавычка " и {'}
    with pytest.raises(JsonError, match="не закрыт"):
        extract_json('{"a": {"b": 1}')
    with pytest.raises(JsonError, match="нет JSON"):
        extract_json("просто текст")


def test_parse_json_asks_for_one_repair():
    llm = ScriptedLLM(lambda step, m: '{"fixed": true}')
    assert run(parse_json('{"a": 1,,}', llm, step="outline")) == {"fixed": True}
    assert [c[0] for c in llm.calls] == ["repair_json:outline"]
    broken = ScriptedLLM(lambda step, m: "всё ещё не JSON")
    with pytest.raises(JsonError, match="даже после починки"):
        run(parse_json("{oops", broken, step="items"))


# --- бриф ---


def test_brief_questions_are_split_off():
    body, questions = split_brief("# Игра\n\nТекст\n\n## Уточняющие вопросы\n- Мрачно?\n2. Компаньон в бою?\n")
    assert body == "# Игра\n\nТекст" and questions == ["Мрачно?", "Компаньон в бою?"]
    result = run(generate_brief("идея", DemoLLM()))
    assert result["brief_markdown"].startswith("# Погасший маяк") and len(result["questions"]) == 2


# --- фрагменты ---


def test_split_and_assemble_round_trip_demo():
    game = validate(json.loads(DEMO_PATH.read_text(encoding="utf-8"))).game
    outline, contents, items = split_game(game)
    again = validate(assemble(outline, contents, items))
    assert again.ok and again.issues == []
    assert again.game.dump() == game.dump()


def test_referenced_ids():
    _, contents, _ = _demo_fragments()
    refs = referenced_ids(contents)
    assert {"archive_key", "ledger", "tonic", "harbor_badge"} <= set(refs["items"])
    assert refs["skills"] == ["salt_ward"] and refs["shops"] == ["marfa_stall"]


# --- пайплайн ---


def test_demo_provider_generates_playable_game():
    result, statuses = generate(DemoLLM())
    assert result.report.passed and len(result.game.locations) == 5
    assert result.game.levels and result.game.stats_template
    steps = [st for st, _, _ in statuses]
    for step in ("outline", "locations", "items", "validate", "balance", "levels", "playtest", "ready"):
        assert step in steps
    assert [p for _, p, _ in statuses] == sorted(p for _, p, _ in statuses)
    preview = next(info["outline"] for st, _, info in statuses if "outline" in info)
    assert preview["title"] == "Погасший маяк" and preview["characters"][0]["appearance"]["hair"] == "long_braid"


def test_fragment_schema_error_is_fixed():
    bad = copy.deepcopy(demo_responses()["outline"])
    bad["hero"]["role"] = "protagonist"
    llm = scripted({"outline": [bad]}, fix=lambda step, f: {**f, "hero": {**f["hero"], "role": "hero"}})
    result, _ = generate(llm)
    assert result.game.hero.role == "hero"
    assert "fix:outline" in [c[0] for c in llm.calls]


def test_game_error_is_routed_to_its_location():
    """Выход переулка ведёт в несуществующую локацию — чинится только фрагмент переулка."""
    alley = copy.deepcopy(demo_responses()["location:alley"])
    exit_ = next(o for o in alley["objects"] if o["id"] == "alley_to_cliffs")
    exit_["to"] = "lighthouse"

    def fix(step, fragment):
        for o in fragment.get("objects", []):
            if o.get("to") == "lighthouse":
                o["to"] = "lighthouse_foot"
        return fragment

    llm = scripted({"location:alley": [alley]}, fix=fix)
    result, statuses = generate(llm)
    assert result.report.passed
    fixes = [c[0] for c in llm.calls if c[0].startswith("fix:")]
    assert "fix:location:alley" in fixes and "fix:outline" not in fixes
    assert any(st == "fix" for st, _, _ in statuses)


def test_unknown_art_falls_back_to_default_after_three_rounds():
    bad = copy.deepcopy(demo_responses()["outline"])
    bad["hero"]["appearance"]["hair"] = "dreadlocks"
    llm = scripted({"outline": [bad]})  # починка возвращает фрагмент без изменений
    result, _ = generate(llm)
    assert result.game.hero.appearance.hair == "short_messy"
    assert any("dreadlocks" in w.message for w in result.warnings)
    assert len([c for c in llm.calls if c[0] == "fix:outline"]) == 3


def test_unfixable_game_fails_with_readable_error():
    alley = copy.deepcopy(demo_responses()["location:alley"])
    alley["objects"] = [o for o in alley["objects"] if o["id"] != "alley_to_cliffs"]  # маяк недостижим
    llm = scripted({"location:alley": [alley]})
    with pytest.raises(GenerationFailed) as exc:
        generate(llm)
    assert "не удалось починить" in str(exc.value)
    assert any("недостижима" in i.message for i in exc.value.issues)


def test_broken_json_fragment_is_repaired():
    llm = scripted({"items": ['```json\n{"items": [ oops']})
    result, _ = generate(llm)
    assert "repair_json:items" in [c[0] for c in llm.calls]
    assert result.report.passed
