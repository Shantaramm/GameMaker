"""Сборщик уровней: размещение, связность, детерминизм, поиск пути."""

from app.engine import schema as s
from app.engine.levels import FLOOR_HEIGHT, WIDTH, build_level, check_reachability, find_path, spawn_for
from app.engine.validator import validate


def game(demo) -> s.Game:
    return validate(demo).game


def test_every_object_is_placed_on_its_zone_floor(demo):
    g = game(demo)
    for loc in g.locations:
        level = build_level(loc).level
        placed = {o.id: o for o in level.objects}
        zones = {z.id: z for z in loc.zones}
        assert set(placed) == {o.id for o in loc.objects}, loc.id
        for o in loc.objects:
            assert placed[o.id].floor == zones[o.zone].floor, (loc.id, o.id)


def test_zones_keep_declared_order(demo):
    loc = game(demo).location("alley")
    xs = {o.id: o.x for o in build_level(loc).level.objects}
    assert xs["torn_letter"] < xs["rats"] < xs["net_crates"]


def test_edge_exits_sit_on_edges_and_door_exits_inside(demo):
    loc = game(demo).location("alley")
    level = build_level(loc).level
    xs = {o.id: o.x for o in level.objects}
    assert xs["alley_to_pier"] == level.floors[0].x0
    assert xs["alley_to_cliffs"] == level.floors[0].x1
    assert level.floors[0].x0 < xs["alley_to_archive"] < level.floors[0].x1


def test_objects_do_not_overlap(demo):
    for loc in game(demo).locations:
        objs = build_level(loc).level.objects
        for floor in {o.floor for o in objs}:
            xs = sorted(o.x for o in objs if o.floor == floor)
            assert all(b - a >= 1 for a, b in zip(xs, xs[1:])), loc.id


def test_multi_floor_level_is_connected_by_ladders(demo):
    loc = game(demo).location("tower")
    level = build_level(loc).level
    assert level.height == 3 * FLOOR_HEIGHT + 2 and level.width == WIDTH["small"]
    assert len(level.links) == 2
    for link in level.links:
        (fa, xa), (fb, xb) = link.a, link.b
        assert xa == xb and fb == fa + 1
        top, bottom = level.floors[fb].y, level.floors[fa].y
        assert all(level.tiles[y][xa] == "H" for y in range(top + 1, bottom + 1))
    assert check_reachability(level) == []


def test_path_climbs_to_top_floor(demo):
    level = build_level(game(demo).location("tower")).level
    lens = next(o for o in level.objects if o.id == "great_lens")
    start = spawn_for(level, "lighthouse_foot")
    path = find_path(level, (start.floor, start.x), (lens.floor, lens.x))
    assert path is not None
    assert [f for f, _ in path][-1] == 2
    assert {f for f, _ in path} == {0, 1, 2}
    assert all(abs(a[1] - b[1]) + abs(a[0] - b[0]) == 1 for a, b in zip(path, path[1:]))


def test_spawns_match_incoming_exits(demo):
    g = game(demo)
    level = build_level(g.location("alley")).level
    froms = {sp.from_ for sp in level.spawns}
    assert {"default", "pier", "archive", "lighthouse_foot"} <= froms
    door = next(o for o in level.objects if o.id == "alley_to_archive")
    sp = spawn_for(level, "archive")
    assert (sp.floor, sp.x) == (door.floor, door.x)
    assert spawn_for(level, "unknown").from_ == "default"


def test_build_is_deterministic(demo):
    for loc in game(demo).locations:
        assert build_level(loc).level == build_level(loc).level


def test_walls_close_levels_except_edge_exits(demo):
    g = game(demo)
    alley = build_level(g.location("alley")).level
    archive = build_level(g.location("archive")).level
    feet = alley.floors[0].y - 1
    assert alley.tiles[feet][0] == "." and alley.tiles[feet][-1] == "."  # выходы за оба края
    assert all(archive.tiles[y][0] == "|" and archive.tiles[y][-1] == "|" for y in range(1, archive.floors[0].y + 1))
