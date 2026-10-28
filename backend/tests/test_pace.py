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
