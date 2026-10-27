"""Внутренние навыки и проверки (SPEC §5.10): шанс, броски, белые и красные проверки, голоса, профиль игры."""

import random

import pytest

from app.engine import inner
from app.engine import schema as s
from app.engine.prepare import prepare
from app.engine.simulator import Run, World, _Over, new_hero, start_node
from app.engine.validator import validate

from .conftest import obj, obj_path


def prepared(data):
    game = validate(data).game
    prepare(game)
    return game


def marfa_check(demo, **check):
    """Вариант «Вы чем-то встревожены.» у Марфы становится проверкой Эмпатии."""
    node = obj(demo, "pier", "marfa_at_stall")["dialogue"]["nodes"][0]
    choice = node["choices"][1]
    choice["check"] = {"skill": "empathy", "difficulty": "challenging", "failure": "n2", **check}
    return choice


def test_chance_matches_2d6_with_auto_success_and_failure():
    assert inner.chance(4, 12) == pytest.approx(15 / 36)        # нужно 8+ на 2d6
    assert inner.chance(20, 6) == pytest.approx(35 / 36)        # 1-1 — всегда провал
    assert inner.chance(0, 16) == pytest.approx(1 / 36)         # 6-6 — всегда успех
    assert inner.check_xp("trivial") == 5 and inner.check_xp("legendary") == 15


def test_passive_voice_is_heard_without_roll():
    assert inner.passive_heard(4, "medium")          # 4 + 6 ≥ 10
    assert not inner.passive_heard(3, "challenging")  # 3 + 6 < 12


def test_white_check_reopens_only_after_skill_grows():
    chk = s.SkillCheck(skill="logic", difficulty="medium", failure="end")
    assert inner.check_open(None, chk, 2)
    assert not inner.check_open({"ok": False, "at": 2}, chk, 2)
    assert inner.check_open({"ok": False, "at": 2}, chk, 3)
    red = chk.model_copy(update={"red": True})
    assert not inner.check_open({"ok": False, "at": 2}, red, 5)
    assert inner.check_open({"ok": True, "at": 2}, red, 0)


def test_hero_skills_health_and_morale_from_profile(demo):
    demo["hero"]["strengths"] = ["logic", "empathy"]
    demo["hero"]["weakness"] = "presence"
    demo["inner_skills"] = demo["inner_skills"][:1]            # остальные названия подставит код
    game = prepared(demo)
    assert game.hero_skills["logic"] == 4 and game.hero_skills["presence"] == 1 and game.hero_skills["will"] == 2
    assert [sk.name for sk in game.inner_skills][:2] == ["Логика", "Знания"]
    hero = new_hero(game)
    assert hero.morale == 3 + 2 and hero.hp == game.stats_template.hp            # бой: HP прежние, Дух 3 + Воля


def test_check_in_dialogue_rolls_remembers_and_damages(demo):
    marfa_check(demo, damage="morale")
    game = prepared(demo)
    world = World(game)
    run = Run(game, world, random.Random(3), {})
    dialogue = next(o for loc in game.locations for o in loc.objects if o.id == "marfa_at_stall").dialogue
    choice = dialogue.nodes[0].choices[1]
    morale = run.hero.morale
    nxt = run.resolve_check(dialogue.id, "n1", 1, choice)
    record = run.hero.checks[inner.check_key(dialogue.id, "n1", 1)]
    assert record["at"] == 2 and nxt == ("n3" if record["ok"] else "n2")
    assert run.hero.morale == morale - (0 if record["ok"] else 1)
    assert run.checks_stats == [1, int(record["ok"])]


def test_failed_check_on_last_morale_is_game_over(demo):
    marfa_check(demo, damage="morale", difficulty="legendary")
    game = prepared(demo)
    run = Run(game, World(game), random.Random(1), {})
    run.hero.morale = 1
    dialogue = next(o for loc in game.locations for o in loc.objects if o.id == "marfa_at_stall").dialogue
    with pytest.raises(_Over):
        for seed in range(50):  # legendary на навыке 2 почти наверняка провалится
            run.rng = random.Random(seed)
            run.hero.checks.clear()
            run.resolve_check(dialogue.id, "n1", 1, dialogue.nodes[0].choices[1])


def test_entries_choose_first_line_by_state(demo):
    d = obj(demo, "pier", "marfa_at_stall")["dialogue"]
    d["entries"] = [{"condition": {"flag": "heard_rumor", "is": True}, "node": "n2"}]
    game = prepared(demo)
    world = World(game)
    hero = new_hero(game)
    dialogue = next(o for loc in game.locations for o in loc.objects if o.id == "marfa_at_stall").dialogue
    assert start_node(dialogue, hero, world) == "n1"
    hero.flags["heard_rumor"] = True
    assert start_node(dialogue, hero, world) == "n2"


def test_event_condition_skips_event(demo):
    demo["locations"][0]["on_enter"][0]["condition"] = {"flag": "tim_joined", "is": True}
    game = prepared(demo)
    run = Run(game, World(game), random.Random(0), {})
    steps = run.steps
    assert run.run_event(game.locations[0].on_enter[0]) is None and run.steps == steps + 1


def test_examining_and_quests_give_xp_and_skill_points(demo):
    game = prepared(demo)
    run = Run(game, World(game), random.Random(0), {})
    thing = next(o for loc in game.locations for o in loc.objects if isinstance(o, s.Thing))
    run.interact(thing)
    assert run.hero.xp == inner.EXAMINE_XP
    run.interact(thing)  # повторный осмотр опыта не даёт
    assert run.hero.xp == inner.EXAMINE_XP
    run.reward(100)
    assert run.hero.level >= 3 and run.hero.skill_points == 0      # бот сразу потратил очки
    assert sum(run.hero.inner.values()) == sum(game.hero_skills.values()) + run.hero.level - 1


def test_validator_checks_failure_node_voices_and_dead_ends(demo):
    choice = marfa_check(demo)
    choice["check"]["failure"] = "nope"
    node = obj(demo, "pier", "marfa_at_stall")["dialogue"]["nodes"][0]
    node["speaker"] = "skill:charisma"
    errors = {i.path: i.message for i in validate(demo).errors}
    base = obj_path(demo, "pier", "marfa_at_stall") + ".dialogue.nodes[0]"
    assert base + ".choices[1].check.failure" in errors
    assert "charisma" in errors[base + ".speaker"]
    for c in node["choices"]:
        c["check"] = {"skill": "logic", "difficulty": "easy", "failure": "end"}
    assert base + ".choices" in {i.path for i in validate(demo).errors}


def test_no_combat_profile_forbids_fights_and_battle_skills(demo):
    demo["profile"] = {"combat": "none", "dialogue": "deep"}
    errors = {i.path: i.message for i in validate(demo).errors}
    assert obj_path(demo, "alley", "rats") in errors
    assert "enemies[0]" in errors and "skills[0]" in errors and "start_skills" in errors


def test_no_combat_game_uses_health_morale_and_checks():
    """«Последняя смена» из подборки: ни одного боя, всё решают разговоры и навыки."""
    import json

    from app.catalog import FEATURED_DIR
    from app.engine.simulator import playtest

    game = s.Game.model_validate(json.loads((FEATURED_DIR / "museum.json").read_text(encoding="utf-8")))
    assert game.profile.combat == "none" and game.profile.dialogue == "deep"
    assert game.tactics == [] and game.enemies == [] and not game.arenas
    assert validate(game).issues == []
    hero = new_hero(game)
    assert game.hero_skills["knowledge"] == 4 and game.hero_skills["presence"] == 1
    assert hero.hp == 3 + 2 and hero.morale == 3 + 2       # Здоровье 3 + Стойкость, Дух 3 + Воля
    assert World(game).skill(hero, "presence") == 2        # пиджак учителя +1 к Напору
    report = playtest(game)
    assert report.passed and report.checks_attempted > 100
    assert set(report.endings) == {"ending_truth", "ending_return", "ending_silence"}


def test_light_combat_allows_three_fights(demo):
    demo["profile"] = {"combat": "light", "dialogue": "rich"}
    assert validate(demo).ok


def test_deep_profile_asks_for_checks_and_longer_key_talks(demo):
    demo["profile"] = {"combat": "tactical", "dialogue": "deep"}
    for loc in demo["locations"]:
        for o in loc["objects"]:
            for n in o.get("dialogue", {}).get("nodes", []):
                n.get("choices", [])[:] = [c for c in n.get("choices", []) if "check" not in c]
    quality = validate(demo).quality
    assert any("мало проверок" in i.message for i in quality)
    assert any("ключевой разговор" in i.message for i in quality)
