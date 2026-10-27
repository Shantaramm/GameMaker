"""Тактический бой (SPEC §5.9): поле, урон с позиции, кураж, тактики, ИИ врагов, компаньоны."""

import random

from app.engine import schema as s
from app.engine.arenas import SIZE, build_arenas
from app.engine.prepare import prepare
from app.engine.simulator import World, new_hero, party_units, start_battle
from app.engine.tactics import Battle, Unit, direction
from app.engine.validator import validate


def prepared(demo):
    game = validate(demo).game
    prepare(game)
    return game


def flat_arena(cells=None):
    return s.Arena(width=SIZE, height=SIZE, cells=cells or ["0" * SIZE] * SIZE,
                   party=[(0, 3), (0, 2), (0, 4), (1, 3)], enemies=[(6, 3), (6, 2), (6, 4), (5, 3)])


def unit(uid, side, pos, facing=(1, 0), **kw):
    base = dict(id=uid, name=uid, side=side, kind="hero" if uid == "hero" else ("enemy" if side == "enemy" else "companion"),
                hp=30, max_hp=30, attack=10, defense=0, focus=5, max_focus=5, move=3, range=1, pos=pos, facing=facing)
    base.update(kw)
    return Unit(**base)


def battle(party, enemies, arena=None, tactics=(), gold=100):
    wallet = {"gold": gold}

    def w(delta):
        if delta is not None:
            wallet["gold"] += delta
        return wallet["gold"]
    return Battle(arena or flat_arena(), party, enemies, list(tactics), True, random.Random(1), w), wallet


def test_arenas_are_deterministic_and_connected(demo):
    game = prepared(demo)
    again = build_arenas(game)
    assert set(game.arenas) == {"rats", "guardians"}
    for foe_id, arena in game.arenas.items():
        assert arena == again[foe_id]
        assert len(arena.cells) == SIZE and all(len(r) == SIZE for r in arena.cells)
        for x, y in arena.party + arena.enemies:
            assert arena.cells[y][x] != "#"
        assert {(p.x, p.y) for p in arena.props} == {(x, y) for y, r in enumerate(arena.cells) for x, c in enumerate(r) if c == "#"}


def test_direction_from_defender_facing():
    d = unit("e0", "enemy", (3, 3), facing=(-1, 0))  # смотрит влево
    assert direction((2, 3), d) == "front"
    assert direction((3, 2), d) == "flank"
    assert direction((4, 3), d) == "back"
    assert direction((6, 1), d) == "back"   # дальний выстрел из-за спины


def test_back_and_height_multiply_damage():
    cells = ["0" * SIZE] * SIZE
    cells = cells[:3] + ["0" * 4 + "1" + "0" * 2] + cells[4:]
    hero = unit("hero", "party", (4, 3))
    foe = unit("e0", "enemy", (3, 3), facing=(-1, 0))
    b, _ = battle([hero], [foe], flat_arena(cells))
    dmg, side, high = b.strike(hero, foe, 10)
    assert (side, high) == ("back", True) and dmg == 17   # 10 × (1 + 0.5 + 0.2)


def test_points_for_hits_and_kills_and_win():
    hero = unit("hero", "party", (2, 3), attack=100)
    foe = unit("e0", "enemy", (3, 3), facing=(-1, 0), hp=5, max_hp=5)
    b, _ = battle([hero], [foe])
    assert b.attack(hero, foe)
    assert b.points == 1 + 2 and b.result == "win"   # попадание в лоб + убийство


def test_move_respects_range_obstacles_and_height():
    cells = ["0" * SIZE] * SIZE
    cells = cells[:3] + ["0#0" + "0" * 4] + cells[4:]
    cells[2] = "02" + "0" * 5
    hero = unit("hero", "party", (0, 3))
    b, _ = battle([hero], [unit("e0", "enemy", (6, 6))], flat_arena(cells))
    reach = b.moves(hero)
    assert (1, 3) not in reach            # препятствие
    assert (1, 2) not in reach            # высота 2 рядом с 0 — не забраться
    assert (0, 0) in reach and (3, 4) not in reach   # 3 шага, не 4
    assert not b.move(hero, (3, 3)) and b.move(hero, (0, 0)) and hero.facing == (0, -1)


def test_tactics_cost_points_or_gold_once():
    rally = s.Tactic(id="t1", name="Натиск", description="", icon="sword", target="unit", cost=2,
                     effect=[s.EffModStat(mod_stat="attack", delta=4)], duration=1)
    bomb = s.Tactic(id="t2", name="Бомба", description="", icon="bomb", currency="gold", target="enemies", cost=10,
                    effect=[s.EffDamage(damage=3)])
    hero = unit("hero", "party", (0, 3))
    pal = unit("pal", "party", (0, 2))
    b, wallet = battle([hero, pal], [unit("e0", "enemy", (6, 3)), unit("e1", "enemy", (6, 4))], tactics=[rally, bomb])
    assert not b.use_tactic(hero, rally)   # куража ещё нет
    b.points = 3
    assert b.use_tactic(hero, rally) and hero.stat("attack") == 14 and b.points == 1
    assert not b.use_tactic(hero, bomb)    # одна тактика на бойца за ход
    assert b.use_tactic(pal, bomb) and wallet["gold"] == 90 and all(e.hp == 27 for e in b.enemies)
    b.end_turn()
    assert not b.tactic_ok(pal, bomb)      # тактика за золото — раз за бой
    assert hero.stat("attack") == 10       # бафф на 1 фазу кончился


def test_enemy_ai_goes_for_the_back_and_hits():
    hero = unit("hero", "party", (3, 3), facing=(1, 0), defense=0)
    foe = unit("e0", "enemy", (6, 3), facing=(-1, 0), move=6, attack=8)
    b, _ = battle([hero], [foe])
    b.end_turn()
    # перед героем (4,3) ближе, но ИИ обходит его и бьёт в спину (2,3)
    assert foe.pos == (2, 3) and foe.facing == (1, 0) and hero.hp < 30 and b.points == 0
    short = unit("e1", "enemy", (6, 3), facing=(-1, 0), move=4)
    hero2 = unit("hero", "party", (3, 3), facing=(1, 0))
    b2, _ = battle([hero2], [short])
    b2.end_turn()
    assert short.pos == (3, 2)   # до спины 6 шагов — фланг (меньший y)


def test_enemy_target_is_nearest_then_weakest():
    hero = unit("hero", "party", (0, 3), hp=30)
    pal = unit("pal", "party", (0, 2), hp=5)
    foe = unit("e0", "enemy", (3, 2), facing=(-1, 0))
    b, _ = battle([hero, pal], [foe])
    assert b.enemy_target(foe) is pal


def test_companion_joins_by_condition_and_scales_from_hero(demo):
    game = prepared(demo)
    world = World(game)
    hero = new_hero(game)
    arena = game.arenas["rats"]
    assert [u.kind for u in party_units(hero, world, arena)] == ["hero"]
    tim = next(c for c in game.characters if c.role == "companion")
    hero.flags[tim.joins.flag] = True
    units = party_units(hero, world, arena)
    assert [u.id for u in units] == ["hero", tim.id]
    assert units[1].max_hp == round(hero.max_hp * 0.7) and units[1].pos == tuple(arena.party[1])


def test_hero_down_loses_companion_down_does_not():
    hero = unit("hero", "party", (0, 3), hp=30)
    pal = unit("pal", "party", (5, 3), hp=1)
    foe = unit("e0", "enemy", (6, 3), facing=(-1, 0))
    b, _ = battle([hero, pal], [foe])
    b.hurt(foe, pal, 5, "Удар")
    assert not pal.alive and b.result is None
    b.hurt(foe, hero, 50, "Удар")
    assert b.result == "lose"


def test_start_battle_uses_stored_arena(demo):
    game = prepared(demo)
    world = World(game)
    foe = next(o for loc in game.locations for o in loc.objects if isinstance(o, s.Foe))
    b = start_battle(foe, new_hero(game), world, random.Random(0))
    assert [e.pos for e in b.enemies] == [tuple(p) for p in game.arenas[foe.id].enemies[:len(foe.enemies)]]
    assert {t.id for t in b.tactics} >= {"base_focus", "base_dash", "base_guard", "base_second_wind"}
