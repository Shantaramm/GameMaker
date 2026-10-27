from app.engine.balance import apply_balance
from app.engine.simulator import playtest
from app.engine.validator import validate


def test_demo_passes_validator_without_issues(demo):
    report = validate(demo)
    assert report.ok
    assert report.issues == []


def test_demo_passes_playtest(demo):
    game = apply_balance(validate(demo).game)
    report = playtest(game)

    assert report.passed, [str(i) for i in report.issues]
    assert set(report.endings) == {"ending_dawn", "ending_fog"}
    assert report.ending_rate == 1.0
    assert all(b.fights == report.runs and b.win_rate >= 0.7 for b in report.battles)


def test_playtest_is_reproducible(demo):
    game = apply_balance(validate(demo).game)
    assert playtest(game).model_dump() == playtest(game).model_dump()


def test_balance_fills_all_stats(demo):
    game = apply_balance(validate(demo).game)
    assert game.stats_template is not None
    assert all(e.hp and e.attack and e.defense is not None for e in game.enemies)


def test_dump_round_trips(demo):
    game = validate(demo).game
    assert validate(game.dump()).ok
