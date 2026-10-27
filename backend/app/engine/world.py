"""Обход мира игры: граф локаций, эффекты и источники предметов.

Общие функции для баланса, валидатора и симулятора.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterator

from . import schema as s
from .issues import format_path


@dataclass
class EffectSite:
    path: str             # путь до списка эффектов
    effects: list[s.Effect]
    object_id: str | None  # объект-источник (None — on_enter)


def event_effect_sites(event: s.Event, path: str) -> Iterator[tuple[str, list[s.Effect]]]:
    if isinstance(event, s.Dialogue):
        for ni, node in enumerate(event.nodes):
            for ci, choice in enumerate(node.choices):
                yield format_path(path, "nodes", ni, "choices", ci, "effects"), choice.effects
    elif isinstance(event, s.Choice):
        for oi, option in enumerate(event.options):
            yield format_path(path, "options", oi, "effects"), option.effects


def location_effect_sites(location: s.Location, path: str) -> Iterator[EffectSite]:
    for ei, event in enumerate(location.on_enter):
        for p, effects in event_effect_sites(event, format_path(path, "on_enter", ei)):
            yield EffectSite(p, effects, None)
    for oi, obj in enumerate(location.objects):
        op = format_path(path, "objects", oi)
        if isinstance(obj, s.Npc):
            for p, effects in event_effect_sites(obj.dialogue, format_path(op, "dialogue")):
                yield EffectSite(p, effects, obj.id)
        elif isinstance(obj, s.Thing):
            for p, effects in event_effect_sites(obj.event, format_path(op, "event")):
                yield EffectSite(p, effects, obj.id)
        elif isinstance(obj, s.Foe):
            yield EffectSite(format_path(op, "on_win"), obj.on_win, obj.id)
            if isinstance(obj.on_lose, list):
                yield EffectSite(format_path(op, "on_lose"), obj.on_lose, obj.id)
        elif isinstance(obj, s.Chest):
            yield EffectSite(format_path(op, "contents"), obj.contents, obj.id)


def location_edges(game: s.Game, skip: frozenset[tuple[str, str]] = frozenset()) -> dict[str, set[str]]:
    """location_id → куда можно попасть (локации и концовки) через выходы и goto.

    skip — пары (location_id, object_id), которые не учитывать (для анализа «что, если эта дверь закрыта»).
    """
    edges: dict[str, set[str]] = {loc.id: set() for loc in game.locations}
    for i, loc in enumerate(game.locations):
        for obj in loc.objects:
            if isinstance(obj, s.Exit) and (loc.id, obj.id) not in skip:
                edges[loc.id].add(obj.to)
        for site in location_effect_sites(loc, format_path("locations", i)):
            if site.object_id is not None and (loc.id, site.object_id) in skip:
                continue
            for e in site.effects:
                if isinstance(e, s.EffGoto):
                    edges[loc.id].add(e.goto)
    return edges


def reachable_locations(game: s.Game, skip: frozenset[tuple[str, str]] = frozenset()) -> set[str]:
    edges = location_edges(game, skip)
    seen = {game.start_location}
    queue = deque([game.start_location])
    while queue:
        for nxt in edges.get(queue.popleft(), ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def location_depth(game: s.Game) -> dict[str, int]:
    """Расстояние (число переходов) от стартовой локации; недостижимые — максимум + 1."""
    edges = location_edges(game)
    depth = {game.start_location: 0}
    queue = deque([game.start_location])
    while queue:
        cur = queue.popleft()
        for nxt in edges.get(cur, ()):
            if nxt in edges and nxt not in depth:
                depth[nxt] = depth[cur] + 1
                queue.append(nxt)
    worst = max(depth.values(), default=0) + 1
    return {loc.id: depth.get(loc.id, worst) for loc in game.locations}


def item_sources(game: s.Game) -> dict[str, list[tuple[str, str | None]]]:
    """item_id → где его можно получить: (location_id, object_id); ("start", None) — стартовый инвентарь."""
    sources: dict[str, list[tuple[str, str | None]]] = {}
    for item in game.start_items:
        sources.setdefault(item, []).append(("start", None))
    for slot_item in game.start_equipment.model_dump().values():
        if slot_item:
            sources.setdefault(slot_item, []).append(("start", None))
    shops = {sh.id: sh for sh in game.shops}
    for i, loc in enumerate(game.locations):
        for site in location_effect_sites(loc, format_path("locations", i)):
            for e in site.effects:
                if isinstance(e, s.EffGiveItem):
                    sources.setdefault(e.give_item, []).append((loc.id, site.object_id))
        for obj in loc.objects:
            if isinstance(obj, s.Npc) and obj.shop in shops:
                for item in shops[obj.shop].items:
                    sources.setdefault(item, []).append((loc.id, obj.id))
    return sources


def condition_items(cond: s.Condition | None) -> set[str]:
    """Предметы, которые условие требует иметь (has_item вне отрицаний и альтернатив)."""
    if cond is None:
        return set()
    if isinstance(cond, s.CondItem):
        return {cond.has_item}
    if isinstance(cond, s.CondAll):
        return set().union(*(condition_items(c) for c in cond.all))
    return set()
