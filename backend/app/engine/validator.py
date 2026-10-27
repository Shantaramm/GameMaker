"""Структурная и смысловая проверка игры (SPEC §7.1).

Возвращает список Issue с путём до проблемного места. Эти тексты уходят
в промпт автопочинки (§6.5), поэтому сообщения должны быть понятны LLM
без контекста.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from pydantic import BaseModel, ValidationError

from . import schema as s
from .issues import Issue, format_path

MIN_SCENES, MAX_SCENES = 5, 8
MAX_ENDINGS = 3
MAX_CHARACTERS = 12  # включая героя
MAX_DIALOGUE_NODES = 40
MAX_LINE_LENGTH = 400
MAIN_ROLES = ("hero", "companion", "antagonist")

# Какие эффекты где допустимы. goto, флаги и предметы — только в сюжетных событиях.
STORY_EFFECTS = {
    s.EffSetFlag, s.EffGiveItem, s.EffTakeItem, s.EffLearnSkill,
    s.EffModStat, s.EffHeal, s.EffDamage, s.EffGoto,
}
EFFECTS_BY_CONTEXT: dict[str, set[type]] = {
    "story": STORY_EFFECTS,
    "skill_enemy": {s.EffDamage, s.EffModStat},
    "skill_self": {s.EffHeal, s.EffModStat},
    "item": {s.EffHeal, s.EffDamage, s.EffModStat},
    "ability": {s.EffDamage, s.EffHeal, s.EffModStat},
}
BATTLE_ONLY_STATS = {"attack", "defense"}  # mod_stat в навыках и способностях врага


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
    def ok(self) -> bool:
        return self.game is not None and not self.errors


def validate(data: dict[str, Any] | s.Game) -> ValidationReport:
    if isinstance(data, s.Game):
        game = data
    else:
        try:
            game = s.Game.model_validate(data)
        except ValidationError as exc:
            return ValidationReport(game=None, issues=_schema_issues(exc))
    return ValidationReport(game=game, issues=_Checker(game).run())


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
        self.items = {i.id for i in game.items}
        self.enemies = {e.id for e in game.enemies}
        self.flags = {f.id for f in game.flags}
        self.scenes = {sc.id for sc in game.scenes}
        self.endings = {e.id for e in game.endings}
        self.flags_checked: dict[str, str] = {}
        self.flags_set: set[str] = set()
        # scene_id → цели goto из этой сцены
        self.edges: dict[str, set[str]] = defaultdict(set)

    def error(self, path: str, message: str) -> None:
        self.issues.append(Issue(path=path, message=message))

    def warn(self, path: str, message: str) -> None:
        self.issues.append(Issue(path=path, message=message, severity="warning"))

    def run(self) -> list[Issue]:
        self.check_unique_ids()
        self.check_characters()
        self.check_sizes()
        self.check_combat_defs()
        for si, scene in enumerate(self.game.scenes):
            self.check_scene(si, scene)
        self.check_scene_graph()
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
            ("флагов", [(format_path("flags", i), x.id) for i, x in enumerate(g.flags)]),
            ("сцен и концовок", [(format_path("scenes", i), x.id) for i, x in enumerate(g.scenes)]
             + [(format_path("endings", i), x.id) for i, x in enumerate(g.endings)]),
        ]
        for si, scene in enumerate(g.scenes):
            spaces.append((f"событий сцены '{scene.id}'", [
                (format_path("scenes", si, "events", ei), e.id)
                for ei, e in enumerate(scene.events) if not isinstance(e, s.Transition)
            ]))
        for label, entries in spaces:
            seen: set[str] = set()
            for path, ident in entries:
                if ident in seen:
                    self.error(format_path(path, "id"), f"повторяющийся id '{ident}' среди {label}")
                seen.add(ident)

        if g.start_scene not in self.scenes:
            self.error("start_scene", f"неизвестная сцена '{g.start_scene}'")
        for i, k in enumerate(g.start_skills):
            self.ref(k, self.skills, format_path("start_skills", i), "навык")
        for i, k in enumerate(g.start_items):
            self.ref(k, self.items, format_path("start_items", i), "предмет")

    def ref(self, ident: str, known: set[str], path: str, kind: str) -> bool:
        if ident not in known:
            self.error(path, f"неизвестный {kind} '{ident}'")
            return False
        return True

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

    def check_effects(self, effects: list[s.Effect], path: str, context: str, scene_id: str | None = None) -> bool:
        """Возвращает True, если среди эффектов есть goto."""
        allowed = EFFECTS_BY_CONTEXT[context]
        has_goto = False
        for i, e in enumerate(effects):
            p = format_path(path, i)
            if type(e) not in allowed:
                key = next(iter(e.model_dump(by_alias=True)))
                self.error(p, f"эффект '{key}' здесь недопустим")
                continue
            if context != "story" and context != "item" and isinstance(e, s.EffModStat) and e.mod_stat not in BATTLE_ONLY_STATS:
                self.error(p, "в бою mod_stat меняет только attack или defense")
            if isinstance(e, s.EffSetFlag):
                if self.ref(e.set_flag, self.flags, format_path(p, "set_flag"), "флаг"):
                    self.flags_set.add(e.set_flag)
            elif isinstance(e, s.EffGiveItem):
                self.ref(e.give_item, self.items, format_path(p, "give_item"), "предмет")
            elif isinstance(e, s.EffTakeItem):
                self.ref(e.take_item, self.items, format_path(p, "take_item"), "предмет")
            elif isinstance(e, s.EffLearnSkill):
                self.ref(e.learn_skill, self.skills, format_path(p, "learn_skill"), "навык")
            elif isinstance(e, s.EffGoto):
                has_goto = True
                if self.ref(e.goto, self.scenes | self.endings, format_path(p, "goto"), "переход (сцена или концовка)") and scene_id:
                    self.edges[scene_id].add(e.goto)
        return has_goto

    # --- верхний уровень ---

    def check_characters(self) -> None:
        g = self.game
        if g.hero.role != "hero":
            self.error("hero.role", "у героя role должна быть 'hero'")
        for i, c in enumerate(g.characters):
            if c.role == "hero":
                self.error(format_path("characters", i, "role"), "герой может быть только один (поле hero)")
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
        if not MIN_SCENES <= len(g.scenes) <= MAX_SCENES:
            self.error("scenes", f"сцен {len(g.scenes)}, нужно от {MIN_SCENES} до {MAX_SCENES}")
        if len(g.endings) > MAX_ENDINGS:
            self.error("endings", f"концовок {len(g.endings)}, нужно не больше {MAX_ENDINGS}")
        if 1 + len(g.characters) > MAX_CHARACTERS:
            self.error("characters", f"персонажей {1 + len(g.characters)} вместе с героем, максимум {MAX_CHARACTERS}")

    def check_combat_defs(self) -> None:
        g = self.game
        for i, k in enumerate(g.skills):
            self.check_effects(k.effect, format_path("skills", i, "effect"), f"skill_{k.target}")
        for i, item in enumerate(g.items):
            self.check_effects(item.effect, format_path("items", i, "effect"), "item")
        for i, enemy in enumerate(g.enemies):
            for j, ability in enumerate(enemy.abilities):
                self.check_effects(ability.effect, format_path("enemies", i, "abilities", j, "effect"), "ability")

    # --- сцены ---

    def check_scene(self, si: int, scene: s.Scene) -> None:
        base = format_path("scenes", si)
        terminal_at: int | None = None
        for ei, event in enumerate(scene.events):
            path = format_path(base, "events", ei)
            if terminal_at is not None:
                self.error(path, f"событие недостижимо: перед ним безусловный goto (events[{terminal_at}])")
                break
            if isinstance(event, s.Transition):
                self.check_condition(event.condition, format_path(path, "condition"))
                if self.ref(event.to, self.scenes | self.endings, format_path(path, "to"), "переход (сцена или концовка)"):
                    self.edges[scene.id].add(event.to)
                if event.condition is None:
                    terminal_at = ei
            elif isinstance(event, s.Dialogue):
                self.check_dialogue(event, path, scene.id)
            elif isinstance(event, s.Choice):
                self.check_choice(event, path, scene.id)
            elif isinstance(event, s.Battle):
                for j, enemy_id in enumerate(event.enemies):
                    self.ref(enemy_id, self.enemies, format_path(path, "enemies", j), "враг")
                self.check_effects(event.on_win, format_path(path, "on_win"), "story", scene.id)
                if isinstance(event.on_lose, list):
                    self.check_effects(event.on_lose, format_path(path, "on_lose"), "story", scene.id)

        last = scene.events[-1]
        if not (isinstance(last, s.Transition) and last.condition is None) and terminal_at is None:
            self.error(format_path(base, "events"), "сцена должна заканчиваться безусловным goto (последнее событие: {\"type\": \"goto\", \"to\": ...} без condition)")

    def check_line(self, text: str, path: str) -> None:
        if len(text) > MAX_LINE_LENGTH:
            self.error(path, f"текст длиной {len(text)} символов, максимум {MAX_LINE_LENGTH}")

    def check_choice(self, event: s.Choice, path: str, scene_id: str) -> None:
        self.check_line(event.prompt, format_path(path, "prompt"))
        for i, option in enumerate(event.options):
            p = format_path(path, "options", i)
            self.check_line(option.text, format_path(p, "text"))
            self.check_condition(option.condition, format_path(p, "condition"))
            self.check_effects(option.effects, format_path(p, "effects"), "story", scene_id)
        if all(o.condition is not None for o in event.options):
            self.error(format_path(path, "options"), "у всех вариантов есть condition — игрок может застрять; нужен хотя бы один вариант без условия")

    def check_dialogue(self, event: s.Dialogue, path: str, scene_id: str) -> None:
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
            if node.speaker != "narrator":
                self.ref(node.speaker, self.characters, format_path(p, "speaker"), "персонаж")
            self.check_line(node.text, format_path(p, "text"))
            targets: set[str] = set()
            if node.choices:
                if node.next is not None:
                    self.warn(format_path(p, "next"), "next игнорируется, когда есть choices")
                for ci, choice in enumerate(node.choices):
                    cp = format_path(p, "choices", ci)
                    self.check_line(choice.text, format_path(cp, "text"))
                    self.check_condition(choice.condition, format_path(cp, "condition"))
                    if self.check_effects(choice.effects, format_path(cp, "effects"), "story", scene_id) or choice.next == "end":
                        exits.add(node.id)
                    elif choice.next in nodes:
                        targets.add(choice.next)
                    else:
                        self.error(format_path(cp, "next"), f"неизвестный узел '{choice.next}'")
                if all(c.condition is not None for c in node.choices):
                    self.error(format_path(p, "choices"), "у всех вариантов есть condition — игрок может застрять; нужен хотя бы один вариант без условия")
            elif node.next is None:
                self.error(format_path(p, "next"), "у узла без choices должен быть next (id узла или 'end')")
            elif node.next == "end":
                exits.add(node.id)
            elif node.next in nodes:
                targets.add(node.next)
            else:
                self.error(format_path(p, "next"), f"неизвестный узел '{node.next}'")
            successors[node.id] = targets

        if event.start_node in nodes:
            reached = _reachable(event.start_node, successors)
            for ni, node in enumerate(event.nodes):
                if node.id not in reached:
                    self.error(format_path(path, "nodes", ni), f"узел '{node.id}' недостижим из start_node")

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

    def check_scene_graph(self) -> None:
        g = self.game
        if g.start_scene not in self.scenes:
            return
        reached = _reachable(g.start_scene, self.edges)
        for si, scene in enumerate(g.scenes):
            if scene.id not in reached:
                self.error(format_path("scenes", si), f"сцена '{scene.id}' недостижима из start_scene")
        if not reached & self.endings:
            self.error("endings", "ни одна концовка не достижима из start_scene")
        for i, ending in enumerate(g.endings):
            if ending.id not in reached:
                self.warn(format_path("endings", i), f"концовка '{ending.id}' недостижима")


def _reachable(start: str, edges: dict[str, set[str]]) -> set[str]:
    seen = {start}
    stack = [start]
    while stack:
        for nxt in edges.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen
