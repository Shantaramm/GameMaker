"""Сломанные игры: валидатор и плейтест должны находить проблему с точным путём."""

import pytest

from app.engine import simulator
from app.engine.balance import apply_balance, tune_until_winnable
from app.engine.simulator import playtest
from app.engine.validator import validate

from .conftest import event, scene


def error_paths(data) -> dict[str, str]:
    return {i.path: i.message for i in validate(data).errors}


# --- схема ---


def test_schema_error_path_has_no_union_tags(demo):
    event(demo, "pier", "meet_tim")["nodes"][1]["choices"][0]["effects"][0]["value"] = "maybe"
    errors = error_paths(demo)
    assert "scenes[0].events[1].nodes[1].choices[0].effects[0].value" in errors


def test_unknown_field_is_rejected(demo):
    demo["hero"]["age"] = 27
    assert "hero.age" in error_paths(demo)


def test_unknown_event_type(demo):
    scene(demo, "pier")["events"][0]["type"] = "cutscene"
    assert "scenes[0].events[0]" in error_paths(demo)


# --- ссылки ---


def test_broken_dialogue_link(demo):
    event(demo, "pier", "meet_tim")["nodes"][0]["next"] = "n9"
    errors = error_paths(demo)
    assert errors["scenes[0].events[1].nodes[0].next"] == "неизвестный узел 'n9'"


def test_unknown_goto_target(demo):
    scene(demo, "alley")["events"][-1]["to"] = "library"
    assert "scenes[1].events[2].to" in error_paths(demo)


def test_unknown_enemy_item_skill_speaker(demo):
    event(demo, "alley", "rats")["enemies"][0] = "dragon"
    event(demo, "alley", "rats")["on_win"] = [{"give_item": "sword"}]
    event(demo, "archive", "talk_efim")["nodes"][1]["choices"][0]["effects"] = [{"learn_skill": "fireball"}]
    event(demo, "archive", "talk_efim")["nodes"][0]["speaker"] = "ghost"
    errors = error_paths(demo)
    assert "scenes[1].events[0].enemies[0]" in errors
    assert "scenes[1].events[0].on_win[0].give_item" in errors
    assert "scenes[2].events[1].nodes[1].choices[0].effects[0].learn_skill" in errors
    assert "scenes[2].events[1].nodes[0].speaker" in errors


def test_undeclared_flag(demo):
    demo["flags"] = [f for f in demo["flags"] if f["id"] != "found_ledger"]
    errors = error_paths(demo)
    assert "scenes[2].events[0].options[0].effects[1].set_flag" in errors
    assert "scenes[2].events[1].nodes[1].choices[0].condition.flag" in errors


def test_duplicate_ids(demo):
    demo["items"][1]["id"] = "tonic"
    demo["scenes"][1]["id"] = "ending_fog"
    errors = error_paths(demo)
    assert "items[1].id" in errors
    assert "endings[1].id" in errors


# --- структура сцен и диалогов ---


def test_scene_without_final_goto(demo):
    scene(demo, "alley")["events"].pop()
    errors = error_paths(demo)
    assert "scenes[1].events" in errors
    assert "scenes[2]" in errors  # архив стал недостижим


def test_events_after_unconditional_goto(demo):
    events = scene(demo, "pier")["events"]
    events.insert(1, {"type": "goto", "to": "alley"})
    assert "scenes[0].events[2]" in error_paths(demo)


def test_orphan_and_looping_nodes(demo):
    nodes = event(demo, "archive", "talk_efim")["nodes"]
    nodes[2]["next"] = "n3b"  # n3 ↔ n3b — цикл без выхода
    nodes.append({"id": "n3b", "speaker": "efim", "text": "Соль, соль…", "next": "n3"})
    nodes.append({"id": "n5", "speaker": "efim", "text": "Сюда никто не попадёт.", "next": "end"})

    errors = error_paths(demo)
    assert "не достижим 'end'" in errors["scenes[2].events[1].nodes[2]"]
    assert "не достижим 'end'" in errors["scenes[2].events[1].nodes[4]"]
    assert errors["scenes[2].events[1].nodes[5]"] == "узел 'n5' недостижим из start_node"


def test_all_options_conditional_is_softlock(demo):
    options = event(demo, "archive", "door")["options"]
    options[1]["condition"] = {"stat": "hp", "op": ">=", "value": 100}
    assert "scenes[2].events[0].options" in error_paths(demo)


def test_goto_inside_item_effect_is_forbidden(demo):
    demo["items"][0]["effect"].append({"goto": "ending_dawn"})
    assert error_paths(demo)["items[0].effect[1]"] == "эффект 'goto' здесь недопустим"


def test_skill_cannot_change_hp_stat(demo):
    demo["skills"][0]["effect"] = [{"mod_stat": "hp", "delta": -5}]
    assert "skills[0].effect[0]" in error_paths(demo)


# --- достижимость и размеры ---


def test_no_reachable_ending(demo):
    events = scene(demo, "lamp_room")["events"]
    events[-2]["to"] = "pier"
    events[-1]["to"] = "pier"
    errors = error_paths(demo)
    assert errors["endings"] == "ни одна концовка не достижима из start_scene"


def test_single_unreachable_ending_is_warning(demo):
    scene(demo, "lamp_room")["events"].pop(-2)
    report = validate(demo)
    assert report.ok
    assert [w.path for w in report.warnings] == ["endings[0]"]


def test_unreachable_scene(demo):
    scene(demo, "archive")["events"][-1]["to"] = "lamp_room"
    assert "scenes[3]" in error_paths(demo)


def test_too_few_scenes(demo):
    demo["scenes"] = demo["scenes"][:4]
    assert "scenes" in error_paths(demo)


def test_line_too_long(demo):
    event(demo, "pier", "meet_tim")["nodes"][0]["text"] = "а" * 401
    assert "scenes[0].events[1].nodes[0].text" in error_paths(demo)


def test_main_characters_must_look_different(demo):
    tim = demo["characters"][0]["appearance"]
    hero = demo["hero"]["appearance"]
    tim.update(hair=hero["hair"], hair_color=hero["hair_color"], outfit=hero["outfit"])
    assert "characters[0].appearance" in error_paths(demo)


# --- плейтест ---


def balanced(demo):
    return apply_balance(validate(demo).game)


def test_unwinnable_battle(demo):
    game = balanced(demo)
    shade = next(e for e in game.enemies if e.id == "shade")
    shade.hp, shade.attack = 999, 60

    report = playtest(game)
    assert not report.passed
    issue = next(i for i in report.issues if i.path == "scenes[3].events[1]")
    assert "выигран в 0%" in issue.message
    assert report.outcomes == {"game_over": report.runs}


def test_tuning_fixes_overtuned_battle(demo):
    game = balanced(demo)
    for enemy in game.enemies:
        if enemy.id in ("cultist", "shade"):
            enemy.hp, enemy.attack = round(enemy.hp * 1.6), round(enemy.attack * 1.6)
    assert not playtest(game).passed

    report = tune_until_winnable(game)
    assert report.passed, [str(i) for i in report.issues]


def test_step_limit_detects_endless_loop(demo, monkeypatch):
    # Финал без доверия Тимофея возвращает на пристань: игра выходит только через ending_dawn.
    scene(demo, "lamp_room")["events"][-1]["to"] = "pier"
    game = balanced(demo)
    monkeypatch.setattr(simulator, "STEP_LIMIT", 15)

    report = playtest(game)
    assert report.outcomes.get("step_limit")
    assert any("зацикливание" in i.message for i in report.issues)


def test_playtest_requires_balance(demo):
    with pytest.raises(ValueError, match="not balanced"):
        playtest(validate(demo).game)
