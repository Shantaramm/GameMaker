from app.engine.levels import check_reachability
from app.engine.prepare import prepare
from app.engine.simulator import playtest
from app.engine.validator import validate


def prepared(demo):
    game = validate(demo).game
    assert prepare(game) == []
    return game


def test_demo_passes_validator_without_issues(demo):
    report = validate(demo)
    assert report.ok
    assert report.issues == []


def test_demo_passes_playtest(demo):
    report = playtest(prepared(demo))

    assert report.passed, [str(i) for i in report.issues]
    assert set(report.endings) == {"ending_dawn", "ending_fog"}
    assert report.ending_rate == 1.0
    assert all(b.fights == report.runs and b.win_rate >= 0.7 for b in report.battles)
    assert report.quests_completed["light_the_lamp"] == report.runs
    assert report.quests_completed.get("marfa_nets", 0) > 0
    assert report.avg_final_level > 1


def test_demo_covers_stage_requirements(demo):
    """Требования к демо-игре из SPEC §12, этап 1б."""
    game = validate(demo).game
    assert len(game.locations) == 5
    assert max(loc.floors for loc in game.locations) >= 2
    kinds = [o.type for loc in game.locations for o in loc.objects]
    assert kinds.count("enemy") >= 2
    assert any(o.type == "npc" and o.shop for loc in game.locations for o in loc.objects)
    assert {q.main for q in game.quests} == {True, False}
    slots = {i.equip.slot for i in game.items if i.equip}
    assert slots == {"hand", "body", "trinket"}
    assert any(o.type == "exit" and o.requires and "has_item" in o.requires.model_dump() for loc in game.locations for o in loc.objects)
    assert len(game.endings) == 2
    assert any(c.role == "companion" for c in game.characters)


def test_playtest_is_reproducible(demo):
    game = prepared(demo)
    assert playtest(game).model_dump() == playtest(game).model_dump()


def test_prepare_fills_numbers_and_levels(demo):
    game = prepared(demo)
    assert game.stats_template and game.progression and game.start_gold is not None
    assert all(e.hp and e.attack and e.defense is not None and e.xp and e.gold for e in game.enemies)
    assert all(i.price for i in game.items)
    assert set(game.levels) == {loc.id for loc in game.locations}
    assert all(check_reachability(level) == [] for level in game.levels.values())


def test_dump_round_trips(demo):
    game = prepared(demo)
    again = validate(game.dump())
    assert again.ok
    assert again.game.levels == game.levels
