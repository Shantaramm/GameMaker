"""Живой мир и темп текста (SPEC §5.11): реплики над головой, длинные реплики и монологи."""

from app.engine.validator import validate

from .conftest import obj, obj_path


def test_bark_condition_refs_are_checked(demo):
    obj(demo, "pier", "marfa_at_stall")["barks"].append({"text": "Эй!", "condition": {"flag": "no_such_flag", "is": True}})
    paths = {i.path for i in validate(demo).errors}
    assert any(p.startswith(obj_path(demo, "pier", "marfa_at_stall") + ".barks[") for p in paths)


def test_silent_npcs_get_a_quality_nudge(demo):
    for loc in demo["locations"]:
        for o in loc["objects"]:
            o.pop("barks", None)
    report = validate(demo)
    assert report.ok and any("barks" in i.path for i in report.quality)


def test_wall_of_text_and_monologue_are_quality_issues(demo):
    d = obj(demo, "pier", "marfa_at_stall")["dialogue"]
    d["nodes"][0]["text"] = "Слово " * 60
    d["nodes"].append({"id": "m1", "speaker": "marfa", "text": "Раз.", "next": "m2"})
    d["nodes"].extend({"id": f"m{i}", "speaker": "marfa", "text": "Дальше.", "next": f"m{i + 1}" if i < 4 else "end"} for i in range(2, 5))
    d["nodes"][0]["choices"].append({"text": "А ещё?", "next": "m1"})
    report = validate(demo)
    assert report.ok
    messages = [i.message for i in report.quality]
    assert any("стена текста" in m for m in messages)
    assert any("4 реплик подряд без выбора" in m for m in messages)


# --- тайники (§5.12) ---

def test_hidden_object_appears_only_for_a_sharp_eye(demo):
    import random

    from app.engine import schema as s
    from app.engine.prepare import prepare
    from app.engine.simulator import Run, World

    game = validate(demo).game
    prepare(game)
    run = Run(game, World(game), random.Random(0), {})
    pier = game.location("pier")
    plank = next(o for o in pier.objects if o.id == "loose_plank")
    run.hero.inner["perception"] = 3          # 3 + 6 < 10
    run.reveal(pier)
    assert not run.present(plank)
    run.hero.inner["perception"] = 4          # 4 + 6 ≥ 10
    xp = run.hero.xp
    run.reveal(pier)
    assert run.present(plank) and run.hero.xp > xp


def test_exits_and_enemies_cannot_be_hidden(demo):
    obj(demo, "alley", "rats")["hidden"] = {"difficulty": "easy", "text": "Шорох."}
    assert obj_path(demo, "alley", "rats") + ".hidden" in {i.path for i in validate(demo).errors}


def test_secrets_feature_without_secrets_is_a_quality_issue(demo):
    for loc in demo["locations"]:
        for o in loc["objects"]:
            o.pop("hidden", None)
    assert any("тайник" in i.message for i in validate(demo).quality)
    demo["profile"] = {"features": []}
    assert not any("тайник" in i.message for i in validate(demo).quality)


# --- улики и выводы (§5.12) ---

def test_deduction_validation(demo):
    d = demo["deductions"][0]
    d["clues"] = ["signed_scrap", "tonic"]
    errors = {i.path: i.message for i in validate(demo).errors}
    assert "не улика" in errors["deductions[0].clues[1]"]
    d["clues"] = ["signed_scrap", "signed_scrap"]
    assert "deductions[0].clues" in {i.path for i in validate(demo).errors}
    demo["items"].append({"id": "lost_clue", "name": "Нигде", "description": "", "icon": "letter", "kind": "clue", "value_tier": 1})
    d["clues"] = ["signed_scrap", "lost_clue"]
    assert "нигде не получить" in {i.path: i.message for i in validate(demo).errors}["deductions[0].clues[1]"]


def test_bot_deduces_when_it_holds_all_clues(demo):
    import random

    from app.engine.prepare import prepare
    from app.engine.simulator import Run, World

    game = validate(demo).game
    prepare(game)
    run = Run(game, World(game), random.Random(0), {})
    logic = run.hero.inner["logic"]
    run.hero.inventory["signed_scrap"] += 1
    run.deduce()
    assert not run.hero.deduced
    run.hero.inventory["salt_order"] += 1
    run.deduce()
    assert run.hero.deduced == {"salt_for_the_sea"} and run.hero.flags["oleander_exposed"]
    assert run.hero.inner["logic"] == logic + 1


# --- сбор и ремесло (§5.12) ---

def test_crafting_validation(demo):
    demo["recipes"][1]["station"] = "alchemy"
    assert "нет места для ремесла" in {i.path: i.message for i in validate(demo).errors}["recipes[1].station"]
    demo["recipes"][1]["station"] = "campfire"
    demo["recipes"][0]["inputs"] = [{"item": "harbor_badge"}]
    demo["items"].append({"id": "moon_dust", "name": "Лунная пыль", "description": "", "icon": "gem", "kind": "material", "value_tier": 1})
    demo["recipes"][0]["inputs"] = [{"item": "moon_dust"}]
    assert "нигде не добыть" in {i.path: i.message for i in validate(demo).errors}["recipes[0].inputs[0].item"]


def test_bot_gathers_and_crafts(demo):
    import random

    from app.engine.prepare import prepare
    from app.engine.simulator import Run, World

    game = validate(demo).game
    prepare(game)
    run = Run(game, World(game), random.Random(0), {})
    crust = next(o for o in game.location("pier").objects if o.id == "salt_crust")
    salt = run.hero.inventory["salt_pouch"]
    run.hero.inner["perception"] = 4        # 4 + 6 ≥ 10 — на одну соль больше
    run.interact(crust)
    assert run.hero.inventory["sea_salt"] == 3 and not run.present(crust)
    run.craft("anywhere")
    assert run.hero.inventory["salt_pouch"] == salt + 1 and run.hero.inventory["sea_salt"] == 1
    assert "make_salt_pouch" in run.hero.crafted


# --- слабости врагов (§5.12) ---

def test_weakness_multiplies_damage_when_known_and_with_bane():
    import random

    from app.engine import schema as s
    from app.engine.tactics import Unit, weak_bonus

    hero = Unit(id="hero", name="Г", side="party", kind="hero", hp=10, max_hp=10, attack=5, defense=1, focus=0, max_focus=0,
                move=3, range=1, pos=(0, 0), facing=(1, 0))
    foe = Unit(id="e0", name="В", side="enemy", kind="enemy", hp=10, max_hp=10, attack=5, defense=1, focus=0, max_focus=0,
               move=3, range=1, pos=(1, 0), facing=(-1, 0), weak="salt")
    assert weak_bonus(hero, foe) == 0
    foe.weak_known = True
    assert weak_bonus(hero, foe) == 0.25
    assert weak_bonus(hero, foe, "salt") == 0.75
    hero.bane = "salt"
    assert weak_bonus(hero, foe) == 0.75 and weak_bonus(foe, hero) == 0


def test_weakness_is_learned_from_dialogue_or_recalled(demo):
    import random

    from app.engine.prepare import prepare
    from app.engine.simulator import Run, World, recall_weaknesses

    game = validate(demo).game
    prepare(game)
    run = Run(game, World(game), random.Random(0), {})
    foe = next(o for o in game.location("lighthouse_foot").objects if o.id == "guardians")
    assert recall_weaknesses(foe, run.hero, run.world) == []          # Знания 2: 2 + 6 < 12
    run.hero.inner["knowledge"] = 6
    assert {e.id for e in recall_weaknesses(foe, run.hero, run.world)} <= {"cultist", "shade"} and run.hero.bestiary


def test_bane_only_on_weapons_and_bombs(demo):
    demo["items"][0]["bane"] = "salt"            # tonic лечит, а не бьёт
    assert "items[0].bane" in {i.path for i in validate(demo).errors}
