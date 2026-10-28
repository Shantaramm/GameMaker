"""Фрагменты, которые LLM возвращает на шагах пайплайна (SPEC §6.2–6.4), и сборка игры из них.

Каждый фрагмент проверяется Pydantic сразу после своего шага; игра целиком —
валидатором после сборки.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ..engine import schema as s


class LocationPlan(s.Strict):
    """Локация в каркасе: где она, как выглядит и куда из неё можно уйти — без объектов и диалогов."""

    id: s.Id
    title: str = Field(min_length=1, max_length=120)
    theme: s.Id
    background: s.BackgroundSpec
    size: s.Literal["small", "medium", "large"]
    floors: int = Field(ge=1, le=3)
    zones: list[s.Zone] = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=800)  # что здесь происходит по сюжету
    links: list[s.Id] = Field(default_factory=list)  # куда ведут выходы: локации и концовки


class Outline(s.Strict):
    meta: s.Meta
    profile: s.GameProfile = Field(default_factory=s.GameProfile)  # выбирает пользователь; пайплайн его закрепляет
    inner_skills: list[s.InnerSkill] = Field(default_factory=list, max_length=8)
    hero: s.Character
    characters: list[s.Character] = Field(default_factory=list)
    flags: list[s.FlagDef] = Field(default_factory=list)
    quests: list[s.Quest] = Field(min_length=1)
    locations: list[LocationPlan] = Field(min_length=1)
    start_location: s.Id
    endings: list[s.Ending] = Field(min_length=1)


class LocationContent(s.Strict):
    """Наполнение одной локации."""

    intro: str = Field(min_length=1)
    on_enter: list[s.Event] = Field(default_factory=list)
    objects: list[s.MapObject] = Field(default_factory=list)
    enemies: list[s.Enemy] = Field(default_factory=list)  # враги, которые впервые появляются здесь (без чисел)


class ItemsContent(s.Strict):
    items: list[s.Item] = Field(default_factory=list)
    skills: list[s.Skill] = Field(default_factory=list)
    shops: list[s.Shop] = Field(default_factory=list)
    tactics: list[s.Tactic] = Field(default_factory=list, max_length=6)
    deductions: list[s.Deduction] = Field(default_factory=list, max_length=8)
    start_skills: list[s.Id] = Field(default_factory=list)
    start_items: list[s.Id] = Field(default_factory=list)
    start_equipment: s.StartEquipment = Field(default_factory=s.StartEquipment)


def dump(model: s.Strict) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def fragment_schema(model: type[s.Strict]) -> dict[str, Any]:
    schema = model.model_json_schema(by_alias=True)
    s._drop_field_titles(schema)
    return schema


PLAN_FIELDS = ("title", "theme", "background", "size", "floors", "zones")


def assemble(outline: Outline, contents: dict[str, LocationContent], items: ItemsContent) -> dict[str, Any]:
    """Собирает сырой JSON игры. Враги с одинаковым id берутся из первой локации, где описаны."""
    o = dump(outline)
    enemies: dict[str, Any] = {}
    locations = []
    for plan in o["locations"]:
        content = contents.get(plan["id"])
        c = dump(content) if content else {"intro": plan["summary"], "objects": [], "on_enter": [], "enemies": []}
        for enemy in c.pop("enemies", []):
            enemies.setdefault(enemy["id"], enemy)
        locations.append({"id": plan["id"], **{k: plan[k] for k in PLAN_FIELDS}, **c})
    i = dump(items)
    return {
        "schema_version": "2",
        "meta": o["meta"], "profile": o.get("profile", {}), "inner_skills": o.get("inner_skills", []),
        "hero": o["hero"], "characters": o.get("characters", []),
        "start_skills": i.get("start_skills", []), "start_items": i.get("start_items", []),
        "start_equipment": i.get("start_equipment", {}),
        "skills": i.get("skills", []), "items": i.get("items", []), "enemies": list(enemies.values()),
        "shops": i.get("shops", []), "tactics": i.get("tactics", []), "deductions": i.get("deductions", []), "quests": o["quests"], "flags": o.get("flags", []),
        "locations": locations, "start_location": o["start_location"], "endings": o["endings"],
    }


def split_game(game: s.Game) -> tuple[Outline, dict[str, LocationContent], ItemsContent]:
    """Обратная операция: готовая игра → фрагменты. Нужна демо-провайдеру и тестам."""
    first_seen: dict[str, str] = {}
    for loc in game.locations:
        for obj in loc.objects:
            if isinstance(obj, s.Foe):
                for e in obj.enemies:
                    first_seen.setdefault(e, loc.id)
    enemies_by_loc: dict[str, list[s.Enemy]] = {}
    for enemy in game.enemies:
        clean = enemy.model_copy(update={"hp": None, "attack": None, "defense": None, "xp": None, "gold": None})
        enemies_by_loc.setdefault(first_seen.get(enemy.id, game.start_location), []).append(clean)

    plans = []
    contents = {}
    for loc in game.locations:
        links = [o.to for o in loc.objects if isinstance(o, s.Exit)]
        plans.append(LocationPlan(
            id=loc.id, title=loc.title, theme=loc.theme, background=loc.background, size=loc.size, floors=loc.floors,
            zones=loc.zones, summary=loc.intro, links=list(dict.fromkeys(links)),
        ))
        contents[loc.id] = LocationContent(intro=loc.intro, on_enter=loc.on_enter, objects=loc.objects,
                                           enemies=enemies_by_loc.get(loc.id, []))
    outline = Outline(meta=game.meta, profile=game.profile, inner_skills=game.inner_skills, hero=game.hero, characters=game.characters, flags=game.flags, quests=game.quests,
                      locations=plans, start_location=game.start_location, endings=game.endings)
    tactics = [t.model_copy(update={"cost": None}) for t in game.tactics if not t.id.startswith("base_")]
    items = ItemsContent(items=[i.model_copy(update={"price": None}) for i in game.items], skills=game.skills, shops=game.shops, tactics=tactics, deductions=game.deductions,
                         start_skills=game.start_skills, start_items=game.start_items, start_equipment=game.start_equipment)
    return outline, contents, items


def referenced_ids(contents: dict[str, LocationContent], outline: Outline | None = None) -> dict[str, list[str]]:
    """Какие предметы, навыки и магазины упомянуты в локациях (и навыки компаньона в каркасе) — их опишет шаг «предметы»."""
    items: set[str] = set()
    skills: set[str] = set()
    shops: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("give_item", "take_item", "has_item") and isinstance(value, str):
                    items.add(value)
                elif key == "learn_skill" and isinstance(value, str):
                    skills.add(value)
                elif key == "shop" and isinstance(value, str):
                    shops.add(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for content in contents.values():
        walk(dump(content))
    for c in outline.characters if outline else []:
        if c.combat:
            skills.update(c.combat.skills)
    return {"items": sorted(items), "skills": sorted(skills), "shops": sorted(shops)}
