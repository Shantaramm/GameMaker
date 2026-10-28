"""Структурная и смысловая проверка игры (SPEC §7.1).

Возвращает список Issue с путём до проблемного места. Эти тексты уходят
в промпт автопочинки (§6.7), поэтому сообщения должны быть понятны LLM
без контекста.
"""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, ValidationError

from . import schema as s
from .art import ArtLibrary, check_art, load_library
from .issues import Issue, format_path
from .levels import build_level
from .world import condition_items, item_sources, location_edges, location_effect_sites, reachable_locations

MIN_LOCATIONS, MAX_LOCATIONS = 5, 8
MAX_ENDINGS = 3
MAX_CHARACTERS = 12  # включая героя
MAX_OBJECTS = 15
MAX_DIALOGUE_NODES = 40
MAX_LINE_LENGTH = 400
# Темп текста (§5.11): длинная реплика или монолог без выбора — замечание quality, игру не ломает.
PACE_LINE_LENGTH = 300
PACE_MONOLOGUE = 4          # столько реплик подряд без выбора — уже монолог
BARKS_MIN_NPCS = 3          # с этого числа NPC в игре хочется реплик над головой
MAIN_ROLES = ("hero", "companion", "antagonist")

# Какие эффекты где допустимы. goto, флаги, предметы и золото — только в сюжетных событиях.
STORY_EFFECTS = {
    s.EffSetFlag, s.EffGiveItem, s.EffTakeItem, s.EffGiveGold, s.EffTakeGold, s.EffLearnSkill,
    s.EffModStat, s.EffModSkill, s.EffHeal, s.EffDamage, s.EffGoto,
}
EFFECTS_BY_CONTEXT: dict[str, set[type]] = {
    "story": STORY_EFFECTS,
    "skill_enemy": {s.EffDamage, s.EffModStat},
    "skill_self": {s.EffHeal, s.EffModStat},
    "item": {s.EffHeal, s.EffDamage, s.EffModStat},
    "ability": {s.EffDamage, s.EffHeal, s.EffModStat},
    "tactic_unit": {s.EffHeal, s.EffModStat},
    "tactic_party": {s.EffHeal, s.EffModStat},
    "tactic_enemies": {s.EffDamage, s.EffModStat},
}
BATTLE_ONLY_STATS = {"attack", "defense"}  # mod_stat в навыках и способностях врага
LIGHT_COMBAT_MAX_FIGHTS = 3
# Минимум «глубины» по профилю (§5.10): проверок и пассивных голосов на игру, реплик в ключевом разговоре.
QUALITY_BY_DEPTH = {
    "light": {"checks": 2, "passives": 0, "nodes": 0},
    "rich": {"checks": 4, "passives": 2, "nodes": 4},
    "deep": {"checks": 6, "passives": 4, "nodes": 6},
}


class ValidationReport(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    game: s.Game | None
    issues: list[Issue]

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def quality(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "quality"]

    @property
    def ok(self) -> bool:
        return self.game is not None and not self.errors


_DEFAULT_ART = object()


def validate(data: dict[str, Any] | s.Game, art: ArtLibrary | None | object = _DEFAULT_ART) -> ValidationReport:
    """art — библиотека деталей для проверки внешности; по умолчанию /pixelart/library, None — не проверять.

    Уровни проверяются пробной сборкой (game не меняется): объекты помещаются в зоны и достижимы.
    """
    if isinstance(data, s.Game):
        game = data
    else:
        try:
            game = s.Game.model_validate(data)
        except ValidationError as exc:
            return ValidationReport(game=None, issues=_schema_issues(exc))
    issues = _Checker(game).run()
    for i, loc in enumerate(game.locations):
        issues += build_level(loc, format_path("locations", i)).issues
    library = load_library() if art is _DEFAULT_ART else art
    if library is not None:
        issues += check_art(game, library)
    return ValidationReport(game=game, issues=issues)


def _schema_issues(exc: ValidationError) -> list[Issue]:
    issues = []
    for err in exc.errors(include_url=False):
        parts = [p for p in err["loc"] if not (isinstance(p, str) and p.startswith(s.TAG_PREFIX))]
        issues.append(Issue(path=format_path(*parts), message=err["msg"]))
    return issues


class _Checker:
    def __init__(self, game: s.Game) -> None:
        self.game = game
        self.issues: list[Issue] = []
        self.characters = {c.id for c in [game.hero, *game.characters]}
        self.skills = {k.id for k in game.skills}
        self.items = {i.id: i for i in game.items}
        self.enemies = {e.id for e in game.enemies}
        self.shops = {sh.id for sh in game.shops}
        self.flags = {f.id for f in game.flags}
        self.locations = {loc.id for loc in game.locations}
        self.endings = {e.id for e in game.endings}
        self.foes = {o.id for loc in game.locations for o in loc.objects if isinstance(o, s.Foe)}
        self.flags_checked: dict[str, str] = {}
        self.flags_set: set[str] = set()
        self.checks_total = 0
        self.passives_total = 0
        self.hidden_total = 0

    def error(self, path: str, message: str) -> None:
        self.issues.append(Issue(path=path, message=message))

    def warn(self, path: str, message: str) -> None:
        self.issues.append(Issue(path=path, message=message, severity="warning"))

    def run(self) -> list[Issue]:
        self.check_unique_ids()
        self.check_start()
        self.check_characters()
        self.check_sizes()
        self.check_combat_defs()
        self.check_shops_and_quests()
        for i, loc in enumerate(self.game.locations):
            self.check_location(i, loc)
        self.check_location_graph()
        self.check_locked_behind_itself()
        self.check_profile()
        self.check_mechanics()
        for flag, path in self.flags_checked.items():
            if flag in self.flags and flag not in self.flags_set:
                self.warn(path, f"флаг '{flag}' проверяется, но нигде не выставляется")
        return self.issues

    # --- id и ссылки ---

    def check_unique_ids(self) -> None:
        g = self.game
        spaces: list[tuple[str, Iterable[tuple[str, str]]]] = [
            ("персонажей", [("hero", g.hero.id)] + [(format_path("characters", i), c.id) for i, c in enumerate(g.characters)]),
            ("навыков", [(format_path("skills", i), x.id) for i, x in enumerate(g.skills)]),
            ("предметов", [(format_path("items", i), x.id) for i, x in enumerate(g.items)]),
            ("врагов", [(format_path("enemies", i), x.id) for i, x in enumerate(g.enemies)]),
            ("магазинов", [(format_path("shops", i), x.id) for i, x in enumerate(g.shops)]),
            ("тактик", [(format_path("tactics", i), x.id) for i, x in enumerate(g.tactics)]),
            ("выводов", [(format_path("deductions", i), x.id) for i, x in enumerate(g.deductions)]),
            ("рецептов", [(format_path("recipes", i), x.id) for i, x in enumerate(g.recipes)]),
            ("квестов", [(format_path("quests", i), x.id) for i, x in enumerate(g.quests)]),
            ("флагов", [(format_path("flags", i), x.id) for i, x in enumerate(g.flags)]),
            ("локаций и концовок", [(format_path("locations", i), x.id) for i, x in enumerate(g.locations)]
             + [(format_path("endings", i), x.id) for i, x in enumerate(g.endings)]),
            ("объектов на картах", [(format_path("locations", i, "objects", j), o.id)
                                    for i, loc in enumerate(g.locations) for j, o in enumerate(loc.objects)]),
        ]
        for i, loc in enumerate(g.locations):
            base = format_path("locations", i)
            spaces.append((f"зон локации '{loc.id}'", [(format_path(base, "zones", j), z.id) for j, z in enumerate(loc.zones)]))
            events = [(format_path(base, "on_enter", j), e.id) for j, e in enumerate(loc.on_enter)]
            for j, o in enumerate(loc.objects):
                if isinstance(o, s.Npc):
                    events.append((format_path(base, "objects", j, "dialogue"), o.dialogue.id))
                elif isinstance(o, s.Thing):
                    events.append((format_path(base, "objects", j, "event"), o.event.id))
            spaces.append((f"событий локации '{loc.id}'", events))
        for label, entries in spaces:
            seen: set[str] = set()
            for path, ident in entries:
                if ident in seen:
                    self.error(format_path(path, "id"), f"повторяющийся id '{ident}' среди {label}")
                seen.add(ident)

    def ref(self, ident: str, known: Iterable[str], path: str, kind: str) -> bool:
        if ident not in known:
            self.error(path, f"неизвестный {kind} '{ident}'")
            return False
        return True

    def check_start(self) -> None:
        g = self.game
        self.ref(g.start_location, self.locations, "start_location", "локация")
        for i, k in enumerate(g.start_skills):
            self.ref(k, self.skills, format_path("start_skills", i), "навык")
        for i, k in enumerate(g.start_items):
            self.ref(k, self.items, format_path("start_items", i), "предмет")
        for slot, item_id in g.start_equipment.model_dump().items():
            if item_id is None:
                continue
            path = format_path("start_equipment", slot)
            if self.ref(item_id, self.items, path, "предмет"):
                item = self.items[item_id]
                if item.kind != "equipment" or item.equip is None or item.equip.slot != slot:
                    self.error(path, f"'{item_id}' нельзя надеть в слот {slot}: нужен предмет kind=equipment с equip.slot='{slot}'")

    def check_condition(self, cond: s.Condition | None, path: str) -> None:
        if cond is None:
            return
        if isinstance(cond, (s.CondAll, s.CondAny)):
            key = "all" if isinstance(cond, s.CondAll) else "any"
            for i, c in enumerate(getattr(cond, key)):
                self.check_condition(c, format_path(path, key, i))
        elif isinstance(cond, s.CondNot):
            self.check_condition(cond.not_, format_path(path, "not"))
        elif isinstance(cond, s.CondFlag):
            if self.ref(cond.flag, self.flags, format_path(path, "flag"), "флаг"):
                self.flags_checked.setdefault(cond.flag, format_path(path, "flag"))
        elif isinstance(cond, s.CondItem):
            self.ref(cond.has_item, self.items, format_path(path, "has_item"), "предмет")
        elif isinstance(cond, s.CondDefeated):
            self.ref(cond.defeated, self.foes, format_path(path, "defeated"), "объект-враг (type: enemy)")

    def check_effects(self, effects: list[s.Effect], path: str, context: str) -> bool:
        """Возвращает True, если среди эффектов есть goto."""
        allowed = EFFECTS_BY_CONTEXT[context]
        has_goto = False
        for i, e in enumerate(effects):
            p = format_path(path, i)
            if type(e) not in allowed:
                key = next(iter(e.model_dump(by_alias=True)))
                self.error(p, f"эффект '{key}' здесь недопустим")
                continue
            if context not in ("story", "item") and isinstance(e, s.EffModStat) and e.mod_stat not in BATTLE_ONLY_STATS:
                self.error(p, "в бою mod_stat меняет только attack или defense")
            if isinstance(e, s.EffSetFlag):
                if self.ref(e.set_flag, self.flags, format_path(p, "set_flag"), "флаг"):
                    self.flags_set.add(e.set_flag)
            elif isinstance(e, s.EffGiveItem):
                self.ref(e.give_item, self.items, format_path(p, "give_item"), "предмет")
            elif isinstance(e, s.EffTakeItem):
                self.ref(e.take_item, self.items, format_path(p, "take_item"), "предмет")
            elif isinstance(e, s.EffLearnSkill):
                if self.game.profile.combat == "none":
                    self.error(p, "в игре без боёв нет боевых навыков: вместо learn_skill используй mod_skill — рост внутреннего навыка")
                else:
                    self.ref(e.learn_skill, self.skills, format_path(p, "learn_skill"), "навык")
            elif isinstance(e, s.EffGoto):
                has_goto = True
                self.ref(e.goto, self.locations | self.endings, format_path(p, "goto"), "переход (локация или концовка)")
        return has_goto

    # --- верхний уровень ---

    def check_characters(self) -> None:
        g = self.game
        if g.hero.role != "hero":
            self.error("hero.role", "у героя role должна быть 'hero'")
        if g.hero.joins is not None:
            self.error("hero.joins", "joins задаётся только компаньону")
        for i, c in enumerate(g.characters):
            path = format_path("characters", i)
            if c.role == "hero":
                self.error(format_path(path, "role"), "герой может быть только один (поле hero)")
            if c.joins is not None and c.role != "companion":
                self.error(format_path(path, "joins"), "joins задаётся только компаньону")
            self.check_condition(c.joins, format_path(path, "joins"))
            if c.combat is not None:
                if c.role != "companion":
                    self.error(format_path(path, "combat"), "combat задаётся только компаньону")
                for j, k in enumerate(c.combat.skills):
                    self.ref(k, self.skills, format_path(path, "combat", "skills", j), "навык")
        companions = [i for i, c in enumerate(g.characters) if c.role == "companion"]
        for i in companions[1:]:
            self.error(format_path("characters", i, "role"), "компаньон может быть только один")

        main = [("hero", g.hero)] + [
            (format_path("characters", i), c) for i, c in enumerate(g.characters) if c.role in MAIN_ROLES
        ]
        seen: dict[tuple[str, str, str], str] = {}
        for path, c in main:
            a = c.appearance
            look = (a.hair, a.hair_color, a.outfit)
            if look in seen:
                self.error(format_path(path, "appearance"), f"внешность совпадает с '{seen[look]}' по причёске, цвету волос и наряду — главные персонажи должны различаться")
            else:
                seen[look] = c.id

    def check_sizes(self) -> None:
        g = self.game
        if not MIN_LOCATIONS <= len(g.locations) <= MAX_LOCATIONS:
            self.error("locations", f"локаций {len(g.locations)}, нужно от {MIN_LOCATIONS} до {MAX_LOCATIONS}")
        if len(g.endings) > MAX_ENDINGS:
            self.error("endings", f"концовок {len(g.endings)}, нужно не больше {MAX_ENDINGS}")
        if 1 + len(g.characters) > MAX_CHARACTERS:
            self.error("characters", f"персонажей {1 + len(g.characters)} вместе с героем, максимум {MAX_CHARACTERS}")
        for i, loc in enumerate(g.locations):
            if len(loc.objects) > MAX_OBJECTS:
                self.error(format_path("locations", i, "objects"), f"объектов {len(loc.objects)}, максимум {MAX_OBJECTS}")

    def check_combat_defs(self) -> None:
        g = self.game
        for i, k in enumerate(g.skills):
            self.check_effects(k.effect, format_path("skills", i, "effect"), f"skill_{k.target}")
        for i, item in enumerate(g.items):
            path = format_path("items", i)
            self.check_effects(item.effect, format_path(path, "effect"), "item")
            if item.kind == "equipment" and item.equip is None:
                self.error(format_path(path, "equip"), "у предмета kind=equipment должен быть equip {slot, bonus}")
            if item.kind != "equipment" and item.equip is not None:
                self.error(format_path(path, "equip"), "equip задаётся только предметам kind=equipment")
            if item.kind == "consumable" and not item.effect:
                self.error(format_path(path, "effect"), "у расходуемого предмета (consumable) должен быть effect")
            if item.kind in ("key", "misc", "equipment") and item.effect:
                self.error(format_path(path, "effect"), f"у предмета kind={item.kind} не бывает effect: его нельзя «использовать»")
            if item.equip is not None and item.equip.slot != "hand" and item.equip.range != 1:
                self.error(format_path(path, "equip", "range"), "дальность (range) бывает только у предмета в руке (slot: hand)")
        for i, enemy in enumerate(g.enemies):
            for j, ability in enumerate(enemy.abilities):
                self.check_effects(ability.effect, format_path("enemies", i, "abilities", j, "effect"), "ability")
        for i, t in enumerate(g.tactics):
            path = format_path("tactics", i)
            self.check_effects(t.effect, format_path(path, "effect"), f"tactic_{t.target}")
            self.check_condition(t.unlock, format_path(path, "unlock"))
            if not t.effect and not t.move_bonus:
                self.error(format_path(path, "effect"), "тактика ничего не делает: нужен effect или move_bonus")

    def check_shops_and_quests(self) -> None:
        g = self.game
        for i, shop in enumerate(g.shops):
            for j, item in enumerate(shop.items):
                self.ref(item, self.items, format_path("shops", i, "items", j), "предмет")
        if g.quests and not any(q.main for q in g.quests):
            self.error("quests", "нужен основной квест (main: true)")
        if not g.quests:
            self.error("quests", "нужен хотя бы основной квест")
        for i, q in enumerate(g.quests):
            path = format_path("quests", i)
            if q.giver is not None:
                self.ref(q.giver, self.characters, format_path(path, "giver"), "персонаж")
            self.check_condition(q.start, format_path(path, "start"))
            for j, stage in enumerate(q.stages):
                self.check_line(stage.text, format_path(path, "stages", j, "text"))
                self.check_condition(stage.done, format_path(path, "stages", j, "done"))
        self.check_taken_quest_items()

    def check_taken_quest_items(self) -> None:
        """Этапы квеста вычисляются заново каждый раз: если предмет из has_item потом забирают, этап «откатится»."""
        taken = {e.take_item for i, loc in enumerate(self.game.locations)
                 for site in location_effect_sites(loc, format_path("locations", i))
                 for e in site.effects if isinstance(e, s.EffTakeItem)}
        for i, q in enumerate(self.game.quests):
            for j, stage in enumerate(q.stages):
                for item in sorted(condition_items(stage.done) & taken):
                    self.error(format_path("quests", i, "stages", j, "done"),
                               f"этап требует предмет '{item}', но его потом забирают (take_item): этап снова станет "
                               f"невыполненным и квест не завершится. Отметь этап флагом или условием, которое останется истинным")

    # --- локации ---

    def check_location(self, li: int, loc: s.Location) -> None:
        base = format_path("locations", li)
        zones = {z.id: z for z in loc.zones}
        for j, zone in enumerate(loc.zones):
            if zone.floor >= loc.floors:
                self.error(format_path(base, "zones", j, "floor"), f"этаж {zone.floor}, а в локации floors={loc.floors} (этажи с 0)")
        for floor in range(loc.floors):
            if not any(z.floor == floor for z in loc.zones):
                self.warn(format_path(base, "zones"), f"на этаже {floor} нет ни одной зоны — он будет пустым")
        for j, event in enumerate(loc.on_enter):
            self.check_event(event, format_path(base, "on_enter", j))

        for j, obj in enumerate(loc.objects):
            path = format_path(base, "objects", j)
            self.ref(obj.zone, zones, format_path(path, "zone"), f"зона (локация '{loc.id}')")
            self.check_condition(obj.condition, format_path(path, "condition"))
            if obj.hidden is not None:
                if isinstance(obj, (s.Exit, s.Foe)):
                    self.error(format_path(path, "hidden"), "тайником может быть сундук, предмет или персонаж — не выход и не враг: без них игру не пройти")
                else:
                    self.hidden_total += 1
            if isinstance(obj, s.Npc):
                if self.ref(obj.character, self.characters, format_path(path, "character"), "персонаж") and obj.character == self.game.hero.id:
                    self.error(format_path(path, "character"), "герой не может стоять на карте как NPC")
                if obj.shop is not None:
                    self.ref(obj.shop, self.shops, format_path(path, "shop"), "магазин")
                self.check_dialogue(obj.dialogue, format_path(path, "dialogue"))
                for k, bark in enumerate(obj.barks):
                    self.check_condition(bark.condition, format_path(path, "barks", k, "condition"))
            elif isinstance(obj, s.Foe):
                for k, enemy_id in enumerate(obj.enemies):
                    self.ref(enemy_id, self.enemies, format_path(path, "enemies", k), "враг")
                self.check_effects(obj.on_win, format_path(path, "on_win"), "story")
                if isinstance(obj.on_lose, list):
                    self.check_effects(obj.on_lose, format_path(path, "on_lose"), "story")
            elif isinstance(obj, s.Chest):
                self.check_effects(obj.contents, format_path(path, "contents"), "story")
                self.check_condition(obj.requires, format_path(path, "requires"))
            elif isinstance(obj, s.Thing):
                self.check_event(obj.event, format_path(path, "event"))
            elif isinstance(obj, s.Gather):
                if self.ref(obj.item, self.items, format_path(path, "item"), "предмет") \
                        and self.items[obj.item].kind not in ("material", "consumable"):
                    self.error(format_path(path, "item"), "собирают сырьё (kind material) или расходники (consumable)")
            elif isinstance(obj, s.Exit):
                self.ref(obj.to, self.locations | self.endings, format_path(path, "to"), "переход (локация или концовка)")
                self.check_condition(obj.requires, format_path(path, "requires"))
                if obj.to == loc.id:
                    self.error(format_path(path, "to"), "выход ведёт в ту же локацию")

    def check_event(self, event: s.Event, path: str) -> None:
        self.check_condition(event.condition, format_path(path, "condition"))
        if isinstance(event, s.Dialogue):
            self.check_dialogue(event, path)
        elif isinstance(event, s.Choice):
            self.check_choice(event, path)
        else:
            self.check_line(event.text, format_path(path, "text"))

    def check_line(self, text: str, path: str) -> None:
        if len(text) > MAX_LINE_LENGTH:
            self.error(path, f"текст длиной {len(text)} символов, максимум {MAX_LINE_LENGTH}")

    def check_choice(self, event: s.Choice, path: str) -> None:
        self.check_line(event.prompt, format_path(path, "prompt"))
        for i, option in enumerate(event.options):
            p = format_path(path, "options", i)
            self.check_line(option.text, format_path(p, "text"))
            self.check_condition(option.condition, format_path(p, "condition"))
            self.check_effects(option.effects, format_path(p, "effects"), "story")
        if all(o.condition is not None for o in event.options):
            self.error(format_path(path, "options"), "у всех вариантов есть condition — игрок может застрять; нужен хотя бы один вариант без условия")

    def check_dialogue(self, event: s.Dialogue, path: str) -> None:
        nodes = {n.id: n for n in event.nodes}
        if len(event.nodes) > MAX_DIALOGUE_NODES:
            self.error(format_path(path, "nodes"), f"узлов {len(event.nodes)}, максимум {MAX_DIALOGUE_NODES}")
        if "end" in nodes:
            self.error(format_path(path, "nodes"), "id узла 'end' зарезервирован")
        if event.start_node not in nodes:
            self.error(format_path(path, "start_node"), f"неизвестный узел '{event.start_node}'")

        successors: dict[str, set[str]] = {}
        exits: set[str] = set()  # узлы, из которых диалог сразу завершается
        for ni, node in enumerate(event.nodes):
            p = format_path(path, "nodes", ni)
            if node.speaker.startswith("skill:"):
                if node.speaker[6:] not in s.SKILL_KEYS:
                    self.error(format_path(p, "speaker"), f"неизвестный навык '{node.speaker[6:]}'; есть: {', '.join(s.SKILL_KEYS)}")
            elif node.speaker != "narrator":
                self.ref(node.speaker, self.characters, format_path(p, "speaker"), "персонаж")
            self.check_line(node.text, format_path(p, "text"))
            if PACE_LINE_LENGTH < len(node.text) <= MAX_LINE_LENGTH:
                self.quality(format_path(p, "text"), f"реплика длиной {len(node.text)} символов читается как стена текста: "
                             f"сократи до {PACE_LINE_LENGTH} или разбей на две реплики с ответом игрока между ними")
            for pi, passive in enumerate(node.passive):
                self.check_line(passive.text, format_path(p, "passive", pi, "text"))
            self.passives_total += len(node.passive)
            targets: set[str] = set()
            if node.choices:
                if node.next is not None:
                    self.warn(format_path(p, "next"), "next игнорируется, когда есть choices")
                for ci, choice in enumerate(node.choices):
                    cp = format_path(p, "choices", ci)
                    self.check_line(choice.text, format_path(cp, "text"))
                    self.check_condition(choice.condition, format_path(cp, "condition"))
                    if self.check_effects(choice.effects, format_path(cp, "effects"), "story") or choice.next == "end":
                        exits.add(node.id)
                    elif choice.next in nodes:
                        targets.add(choice.next)
                    else:
                        self.error(format_path(cp, "next"), f"неизвестный узел '{choice.next}'")
                    if choice.check is not None:
                        self.checks_total += 1
                        fail = choice.check.failure
                        if fail == "end":
                            exits.add(node.id)
                        elif fail in nodes:
                            targets.add(fail)
                        else:
                            self.error(format_path(cp, "check", "failure"), f"неизвестный узел '{fail}' — куда ведёт провал проверки")
                if all(c.condition is not None or c.check is not None for c in node.choices):
                    self.error(format_path(p, "choices"), "у всех вариантов есть condition или check — игрок может застрять; нужен хотя бы один вариант без условия и без проверки")
            elif node.next is None:
                self.error(format_path(p, "next"), "у узла без choices должен быть next (id узла или 'end')")
            elif node.next == "end":
                exits.add(node.id)
            elif node.next in nodes:
                targets.add(node.next)
            else:
                self.error(format_path(p, "next"), f"неизвестный узел '{node.next}'")
            successors[node.id] = targets

        starts = [event.start_node] if event.start_node in nodes else []
        for ei, entry in enumerate(event.entries):
            self.check_condition(entry.condition, format_path(path, "entries", ei, "condition"))
            if entry.node in nodes:
                starts.append(entry.node)
            else:
                self.error(format_path(path, "entries", ei, "node"), f"неизвестный узел '{entry.node}'")
        if event.start_node in nodes:
            reached: set[str] = set()
            for start in starts:
                reached |= _reachable(start, successors)
            for ni, node in enumerate(event.nodes):
                if node.id not in reached:
                    self.error(format_path(path, "nodes", ni), f"узел '{node.id}' недостижим из start_node и entries")

        can_exit = set(exits)
        changed = True
        while changed:
            changed = False
            for node_id, targets in successors.items():
                if node_id not in can_exit and targets & can_exit:
                    can_exit.add(node_id)
                    changed = True
        for ni, node in enumerate(event.nodes):
            if node.id not in can_exit:
                self.error(format_path(path, "nodes", ni), f"из узла '{node.id}' не достижим 'end' — диалог зацикливается")
        self.check_pace(event, path)

    def check_pace(self, event: s.Dialogue, path: str) -> None:
        """Монолог: столько реплик подряд по next без единого выбора — игрок только жмёт «Далее»."""
        nodes = {n.id: n for n in event.nodes}
        targets = {n.next for n in event.nodes if not n.choices}
        for ni, node in enumerate(event.nodes):
            if node.choices or node.id in targets and node.id != event.start_node:
                continue  # считаем только с начала цепочки
            run, cur, seen = 0, node, set()
            while cur is not None and not cur.choices and cur.id not in seen:
                seen.add(cur.id)
                run += 1
                cur = nodes.get(cur.next or "")
            if run >= PACE_MONOLOGUE:
                self.quality(format_path(path, "nodes", ni), f"{run} реплик подряд без выбора — игрок только жмёт «Далее»: "
                             "дай ему ответить (choices) хотя бы через 2–3 реплики или сократи")

    # --- профиль игры (§5.10) ---

    def check_profile(self) -> None:
        g = self.game
        foes = [(format_path("locations", li, "objects", oi), o) for li, loc in enumerate(g.locations)
                for oi, o in enumerate(loc.objects) if isinstance(o, s.Foe)]
        if g.profile.combat == "none":
            for path, _ in foes:
                self.error(path, "в игре без боёв (profile.combat = none) не бывает врагов на карте — замени на разговор или проверку навыка")
            for i, _ in enumerate(g.enemies):
                self.error(format_path("enemies", i), "в игре без боёв не описывают врагов")
            for i, t in enumerate(g.tactics):
                if not t.id.startswith("base_"):
                    self.error(format_path("tactics", i), "в игре без боёв нет тактик боя")
            for i, _ in enumerate(g.skills):
                self.error(format_path("skills", i), "в игре без боёв нет боевых навыков — герой растёт внутренними навыками")
            if g.start_skills:
                self.error("start_skills", "в игре без боёв нет боевых навыков")
        elif g.profile.combat == "light" and len(foes) > LIGHT_COMBAT_MAX_FIGHTS:
            for path, _ in foes[LIGHT_COMBAT_MAX_FIGHTS:]:
                self.error(path, f"в игре с лёгкими боями их не больше {LIGHT_COMBAT_MAX_FIGHTS}; этот бой лишний — замени на разговор или проверку")

        keys = [sk.key for sk in g.inner_skills]
        if len(keys) != len(set(keys)):
            self.error("inner_skills", "навыки повторяются: нужно 8 разных ключей")
        for i, c in enumerate(g.characters):
            if c.strengths or c.weakness:
                self.error(format_path("characters", i, "strengths"), "сильные и слабый навыки задаются только герою")
        if g.hero.weakness and g.hero.weakness in g.hero.strengths:
            self.error("hero.weakness", "слабый навык не может быть одновременно сильным")

        need = QUALITY_BY_DEPTH[g.profile.dialogue]
        if self.checks_total < need["checks"] or self.passives_total < need["passives"]:
            # дописать проверки и голоса в локации, где они ещё совсем не звучат
            for li, loc in enumerate(g.locations):
                talks = [o for o in loc.objects if isinstance(o, s.Npc)]
                if talks and not any(c.check for o in talks for n in o.dialogue.nodes for c in n.choices):
                    self.quality(format_path("locations", li, "objects"),
                                 f"в игре мало проверок навыков ({self.checks_total} из {need['checks']}) и голосов ({self.passives_total} из {need['passives']}): "
                                 "добавь в разговоры этой локации 1–2 варианта с check (успех и провал — разные ветки) и passive — реплику голоса навыка")
        if need["nodes"]:
            key_roles = {c.id for c in g.characters if c.role in ("companion", "antagonist")} | {q.giver for q in g.quests if q.giver}
            for li, loc in enumerate(g.locations):
                for oi, o in enumerate(loc.objects):
                    if isinstance(o, s.Npc) and o.character in key_roles and len(o.dialogue.nodes) < need["nodes"]:
                        self.quality(format_path("locations", li, "objects", oi, "dialogue"),
                                     f"ключевой разговор слишком короткий ({len(o.dialogue.nodes)} реплик, нужно от {need['nodes']}): "
                                     "дай персонажу подтекст — чего он хочет и что скрывает, выбор с последствиями, проверку навыка")

        features = g.profile.active()
        if "secrets" in features and not self.hidden_total:
            li = max(range(len(g.locations)), key=lambda i: len(g.locations[i].objects))
            self.quality(format_path("locations", li, "objects"),
                         "в игре нет тайников: спрячь 1–2 сундука или предмета (hidden: {skill: perception, difficulty, text}) — "
                         "их найдёт только внимательный герой, награда за исследование")
        npcs = [(li, oi, o) for li, loc in enumerate(g.locations) for oi, o in enumerate(loc.objects) if isinstance(o, s.Npc)]
        if len(npcs) >= BARKS_MIN_NPCS and not any(o.barks for _, _, o in npcs):
            li, oi, _ = npcs[0]
            self.quality(format_path("locations", li, "objects", oi, "barks"),
                         "персонажи молчат, пока к ним не подойдёшь: дай NPC 1–3 реплики над головой (barks) — что они бормочут "
                         "себе под нос, и 1–2 с condition, которые отзываются на сделанное игроком")

    # --- механики (§5.12) ---

    def obtainable_items(self) -> set[str]:
        """Предметы, которые герой может получить: старт, магазины, give_item где угодно в игре."""
        g = self.game
        found = set(g.start_items) | {i for i in g.start_equipment.model_dump().values() if i}
        found |= {i for shop in g.shops for i in shop.items}

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "give_item" and isinstance(v, str):
                        found.add(v)
                    else:
                        walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk([loc.model_dump(by_alias=True) for loc in g.locations])
        walk([d.model_dump(by_alias=True) for d in g.deductions])
        found |= {o.item for loc in g.locations for o in loc.objects if isinstance(o, s.Gather)}
        # ремесло: результат доступен, если доступно всё сырьё (цепочки — до неподвижной точки)
        changed = True
        while changed:
            changed = False
            for r in g.recipes:
                if r.result not in found and all(i.item in found for i in r.inputs):
                    found.add(r.result)
                    changed = True
        return found

    def check_mechanics(self) -> None:
        g = self.game
        features = g.profile.active()
        obtainable = self.obtainable_items()
        for i, d in enumerate(g.deductions):
            path = format_path("deductions", i)
            if len(set(d.clues)) != len(d.clues):
                self.error(format_path(path, "clues"), "улики в выводе повторяются")
            for j, clue in enumerate(d.clues):
                cp = format_path(path, "clues", j)
                if not self.ref(clue, self.items, cp, "предмет-улика"):
                    continue
                if self.items[clue].kind != "clue":
                    self.error(cp, f"'{clue}' — не улика: у предметов для доски выводов kind = clue")
                elif clue not in obtainable:
                    self.error(cp, f"улику '{clue}' нигде не получить: дай её через give_item (осмотр, разговор, сундук)")
            self.check_line(d.text, format_path(path, "text"))
            if self.check_effects(d.effects, format_path(path, "effects"), "story"):
                self.error(format_path(path, "effects"), "вывод не переносит героя: goto здесь недопустим")
        others = [{*d.clues} for d in g.deductions]
        for i, a in enumerate(others):
            if any(j != i and a == b for j, b in enumerate(others)):
                self.error(format_path("deductions", i, "clues"), "два вывода из одних и тех же улик")
        stations = {o.kind for loc in g.locations for o in loc.objects if isinstance(o, s.Station)}
        for i, r in enumerate(g.recipes):
            path = format_path("recipes", i)
            self.ref(r.result, self.items, format_path(path, "result"), "предмет")
            for j, inp in enumerate(r.inputs):
                ip = format_path(path, "inputs", j, "item")
                if not self.ref(inp.item, self.items, ip, "предмет"):
                    continue
                if inp.item == r.result:
                    self.error(ip, "вещь не делается из самой себя")
                elif inp.item not in obtainable:
                    self.error(ip, f"сырьё '{inp.item}' нигде не добыть: нужно место сбора (type: gather), сундук или give_item")
            if r.station != "anywhere" and r.station not in stations:
                self.error(format_path(path, "station"), f"в игре нет места для ремесла '{r.station}': поставь объект type: station с kind = {r.station}")
        if "crafting" in features and not g.recipes:
            self.quality("recipes", "в игре нет ремесла: добавь 2–3 места сбора (type: gather) с сырьём (items kind=material), место для работы "
                         "(type: station: workbench, alchemy или campfire) и 2–4 рецепта (recipes) — зелья, приманки, снаряжение")
        if "deduction" in features and not g.deductions:
            self.quality("deductions", "в игре нет доски улик: добавь 2–3 улики (items kind=clue, выдаются через give_item при осмотре "
                         "или в разговоре) и 1–2 вывода из них (deductions) — вывод ставит флаг, который открывает новые реплики")

    def quality(self, path: str, message: str) -> None:
        self.issues.append(Issue(path=path, message=message, severity="quality"))

    # --- мир целиком ---

    def check_location_graph(self) -> None:
        g = self.game
        if g.start_location not in self.locations:
            return
        reached = reachable_locations(g)
        for i, loc in enumerate(g.locations):
            if loc.id not in reached:
                self.error(format_path("locations", i), f"локация '{loc.id}' недостижима из start_location: нет ведущих в неё выходов")
        if not reached & self.endings:
            self.error("endings", "ни одна концовка не достижима: нужен выход (type: exit, to: <ending_id>) или goto на концовку")
        for i, ending in enumerate(g.endings):
            if ending.id not in reached:
                self.warn(format_path("endings", i), f"концовка '{ending.id}' недостижима")
        edges = location_edges(g)
        for i, loc in enumerate(g.locations):
            if not edges[loc.id]:
                self.error(format_path("locations", i, "objects"), f"из локации '{loc.id}' нет выхода: нужен объект type: exit (или goto в событии)")

    def check_locked_behind_itself(self) -> None:
        """Ключ к двери или сундуку должен быть доступен, не проходя через эту дверь (и не лёжа в этом сундуке)."""
        g = self.game
        if g.start_location not in self.locations:
            return
        sources = item_sources(g)
        for li, loc in enumerate(g.locations):
            for oi, obj in enumerate(loc.objects):
                if not isinstance(obj, (s.Exit, s.Chest)) or obj.requires is None:
                    continue
                needed = condition_items(obj.requires)
                if not needed:
                    continue
                around = reachable_locations(g, skip=frozenset({(loc.id, obj.id)}))
                for item in needed:
                    ok = any(
                        src_loc == "start" or (src_loc in around and src_obj != obj.id)
                        for src_loc, src_obj in sources.get(item, [])
                    )
                    if not ok:
                        what = "дверь" if isinstance(obj, s.Exit) else "сундук"
                        self.error(format_path("locations", li, "objects", oi, "requires"),
                                   f"тупик: '{item}' нельзя получить, не открыв этот {what}; положи его раньше по пути")


def _reachable(start: str, edges: dict[str, set[str]]) -> set[str]:
    seen = {start}
    stack = [start]
    while stack:
        for nxt in edges.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen

