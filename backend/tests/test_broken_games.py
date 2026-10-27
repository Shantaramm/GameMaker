"""Сломанные игры: валидатор и плейтест должны находить проблему с точным путём."""

import pytest

from app.engine import simulator
from app.engine.balance import tune_until_winnable
from app.engine.prepare import prepare
from app.engine.simulator import playtest
from app.engine.validator import validate

from .conftest import loc_index, location, obj, obj_path


def error_paths(data) -> dict[str, str]:
    return {i.path: i.message for i in validate(data).errors}


# --- схема ---


def test_schema_error_path_has_no_union_tags(demo):
    obj(demo, "pier", "tim_on_pier")["dialogue"]["nodes"][1]["choices"][0]["effects"][0]["value"] = "maybe"
    path = obj_path(demo, "pier", "tim_on_pier") + ".dialogue.nodes[1].choices[0].effects[0].value"
    assert path in error_paths(demo)


def test_unknown_field_is_rejected(demo):
    demo["hero"]["age"] = 27
    assert "hero.age" in error_paths(demo)


def test_unknown_object_type(demo):
    obj(demo, "alley", "torn_letter")["type"] = "trap"
    assert obj_path(demo, "alley", "torn_letter") in error_paths(demo)


# --- ссылки ---


def test_broken_dialogue_link(demo):
    obj(demo, "pier", "tim_on_pier")["dialogue"]["nodes"][0]["next"] = "n9"
    errors = error_paths(demo)
    assert errors[obj_path(demo, "pier", "tim_on_pier") + ".dialogue.nodes[0].next"] == "неизвестный узел 'n9'"


def test_unknown_exit_target(demo):
    obj(demo, "alley", "alley_to_cliffs")["to"] = "library"
    assert obj_path(demo, "alley", "alley_to_cliffs") + ".to" in error_paths(demo)


def test_unknown_references_inside_objects(demo):
    obj(demo, "alley", "rats")["enemies"][0] = "dragon"
    obj(demo, "alley", "net_crates")["contents"].append({"give_item": "sword"})
    obj(demo, "archive", "efim_at_desk")["dialogue"]["nodes"][1]["choices"][0]["effects"] = [{"learn_skill": "fireball"}]
    obj(demo, "archive", "efim_at_desk")["character"] = "ghost"
    obj(demo, "pier", "marfa_at_stall")["shop"] = "bazaar"
    errors = error_paths(demo)
    assert obj_path(demo, "alley", "rats") + ".enemies[0]" in errors
    assert obj_path(demo, "alley", "net_crates") + ".contents[2].give_item" in errors
    assert obj_path(demo, "archive", "efim_at_desk") + ".dialogue.nodes[1].choices[0].effects[0].learn_skill" in errors
    assert obj_path(demo, "archive", "efim_at_desk") + ".character" in errors
    assert obj_path(demo, "pier", "marfa_at_stall") + ".shop" in errors


def test_undeclared_flag(demo):
    demo["flags"] = [f for f in demo["flags"] if f["id"] != "heard_rumor"]
    errors = error_paths(demo)
    assert obj_path(demo, "alley", "torn_letter") + ".event.options[0].effects[0].set_flag" in errors
    assert "quests[0].stages[1].done.any[1].flag" in errors


def test_defeated_must_reference_enemy_object(demo):
    obj(demo, "lighthouse_foot", "cliffs_to_tower")["requires"] = {"defeated": "oleander_at_door"}
    assert obj_path(demo, "lighthouse_foot", "cliffs_to_tower") + ".requires.defeated" in error_paths(demo)


def test_duplicate_ids(demo):
    demo["items"][1]["id"] = "tonic"
    obj(demo, "archive", "safe")["id"] = "net_crates"
    demo["locations"][1]["id"] = "ending_fog"
    errors = error_paths(demo)
    assert "items[1].id" in errors
    assert obj_path(demo, "archive", "net_crates") + ".id" in errors
    assert "endings[1].id" in errors


# --- зоны и уровни ---


def test_object_in_unknown_zone(demo):
    obj(demo, "pier", "marfa_at_stall")["zone"] = "roof"
    assert error_paths(demo)[obj_path(demo, "pier", "marfa_at_stall") + ".zone"] == "неизвестный зона (локация 'pier') 'roof'"


def test_zone_on_missing_floor(demo):
    location(demo, "pier")["zones"][1]["floor"] = 2
    assert f"locations[{loc_index(demo, 'pier')}].zones[1].floor" in error_paths(demo)


def test_overcrowded_zone(demo):
    tower = location(demo, "tower")
    for i in range(10):
        tower["objects"].append({"type": "chest", "id": f"extra_{i}", "zone": "middle", "look": "barrel",
                                 "contents": [{"give_gold": 1}]})
    errors = error_paths(demo)
    message = errors[f"locations[{loc_index(demo, 'tower')}].zones[1]"]
    assert "не помещаются 11 объект" in message


# --- граф мира ---


def test_key_behind_its_own_door(demo):
    """Ключ от двери архива лежит в самом архиве."""
    crates = obj(demo, "alley", "net_crates")
    crates["contents"] = [c for c in crates["contents"] if c != {"give_item": "archive_key"}]
    obj(demo, "archive", "safe")["contents"].append({"give_item": "archive_key"})
    errors = error_paths(demo)
    assert errors[obj_path(demo, "alley", "alley_to_archive") + ".requires"].startswith("тупик: 'archive_key'")


def test_key_inside_the_chest_it_opens(demo):
    obj(demo, "alley", "net_crates")["requires"] = {"has_item": "archive_key"}
    assert obj_path(demo, "alley", "net_crates") + ".requires" in error_paths(demo)


def test_unreachable_location(demo):
    obj(demo, "alley", "alley_to_cliffs")["to"] = "pier"
    errors = error_paths(demo)
    assert f"locations[{loc_index(demo, 'lighthouse_foot')}]" in errors
    assert f"locations[{loc_index(demo, 'tower')}]" in errors


def test_no_reachable_ending(demo):
    lens = obj(demo, "tower", "great_lens")
    for choice in lens["event"]["nodes"][0]["choices"]:
        choice["effects"] = []
    assert error_paths(demo)["endings"].startswith("ни одна концовка не достижима")


def test_location_without_exit(demo):
    tower = location(demo, "tower")
    tower["objects"] = [o for o in tower["objects"] if o["type"] != "exit" and o["id"] != "great_lens"]
    assert f"locations[{loc_index(demo, 'tower')}].objects" in error_paths(demo)


def test_too_few_locations(demo):
    demo["locations"] = demo["locations"][:4]
    assert "locations" in error_paths(demo)


# --- предметы, экипировка, квесты ---


def test_start_equipment_in_wrong_slot(demo):
    demo["start_equipment"] = {"hand": "city_coat"}
    assert "start_equipment.hand" in error_paths(demo)


def test_item_kind_consistency(demo):
    items = {i["id"]: i for i in demo["items"]}
    del items["fishing_knife"]["equip"]
    items["tonic"]["effect"] = []
    items["archive_key"]["equip"] = {"slot": "trinket", "bonus": {}}
    errors = error_paths(demo)
    idx = {i["id"]: n for n, i in enumerate(demo["items"])}
    assert f"items[{idx['fishing_knife']}].equip" in errors
    assert f"items[{idx['tonic']}].effect" in errors
    assert f"items[{idx['archive_key']}].equip" in errors


def test_main_quest_required(demo):
    demo["quests"][0]["main"] = False
    assert error_paths(demo)["quests"] == "нужен основной квест (main: true)"


def test_goto_inside_item_effect_is_forbidden(demo):
    demo["items"][0]["effect"].append({"goto": "ending_dawn"})
    assert error_paths(demo)["items[0].effect[1]"] == "эффект 'goto' здесь недопустим"


# --- диалоги и персонажи ---


def test_orphan_and_looping_nodes(demo):
    nodes = obj(demo, "archive", "efim_at_desk")["dialogue"]["nodes"]
    nodes[2]["next"] = "n3b"  # n3 ↔ n3b — цикл без выхода
    nodes.append({"id": "n3b", "speaker": "efim", "text": "Соль, соль…", "next": "n3"})
    nodes.append({"id": "n5", "speaker": "efim", "text": "Сюда никто не попадёт.", "next": "end"})
    base = obj_path(demo, "archive", "efim_at_desk") + ".dialogue"
    errors = error_paths(demo)
    assert "не достижим 'end'" in errors[base + ".nodes[2]"]
    assert "не достижим 'end'" in errors[base + ".nodes[4]"]
    assert errors[base + ".nodes[5]"] == "узел 'n5' недостижим из start_node"


def test_all_options_conditional_is_softlock(demo):
    options = obj(demo, "alley", "torn_letter")["event"]["options"]
    options[0]["condition"] = {"gold": ">=", "value": 1000}
    assert obj_path(demo, "alley", "torn_letter") + ".event.options" in error_paths(demo)


def test_main_characters_must_look_different(demo):
    tim = demo["characters"][0]["appearance"]
    hero = demo["hero"]["appearance"]
    tim.update(hair=hero["hair"], hair_color=hero["hair_color"], outfit=hero["outfit"])
    assert "characters[0].appearance" in error_paths(demo)


# --- плейтест ---


def prepared(demo):
    game = validate(demo).game
    assert prepare(game) == []
    return game


def test_unwinnable_battle(demo):
    game = prepared(demo)
    shade = next(e for e in game.enemies if e.id == "shade")
    shade.hp, shade.attack = 999, 60

    report = playtest(game)
    assert not report.passed
    issue = next(i for i in report.issues if i.path == obj_path(demo, "lighthouse_foot", "guardians"))
    assert "выигран в 0%" in issue.message
    assert report.outcomes == {"game_over": report.runs}


def test_tuning_fixes_overtuned_battle(demo):
    game = prepared(demo)
    for enemy in game.enemies:
        if enemy.id in ("cultist", "shade"):
            enemy.hp, enemy.attack = round(enemy.hp * 2.2), round(enemy.attack * 2.2)
    assert not playtest(game).passed

    report = tune_until_winnable(game)
    assert report.passed, [str(i) for i in report.issues]


def test_impossible_main_quest(demo):
    demo["quests"][0]["stages"][0]["done"] = {"gold": ">=", "value": 999}  # столько золота в игре не набрать
    report = playtest(prepared(demo))
    assert any(i.path == "quests[0]" and i.severity == "error" for i in report.issues)


def test_runtime_dead_end(demo):
    """Выход с пристани открыт, только если Тимофей пошёл с Ариной: в остальных прохождениях тупик."""
    obj(demo, "pier", "pier_to_alley")["requires"] = {"flag": "tim_joined", "is": True}
    assert validate(demo).ok  # статически это не ловится — только плейтестом
    report = playtest(prepared(demo))
    assert report.outcomes.get("dead_end")
    assert any("тупик" in i.message for i in report.issues)


def test_step_limit_detects_endless_wandering(demo, monkeypatch):
    game = prepared(demo)
    monkeypatch.setattr(simulator, "STEP_LIMIT", 15)
    report = playtest(game)
    assert report.outcomes.get("step_limit")
    assert any("зацикливание" in i.message for i in report.issues)


def test_playtest_requires_balance(demo):
    with pytest.raises(ValueError, match="not balanced"):
        playtest(validate(demo).game)
