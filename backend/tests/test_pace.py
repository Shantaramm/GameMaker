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
