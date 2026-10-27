"""Пайплайн генерации (SPEC §6): бриф → каркас → локации → предметы → сборка →
проверка и автопочинка → баланс и уровни → плейтест.

Каждый фрагмент проверяется Pydantic сразу после своего шага (до 3 попыток
починки). Игра целиком проверяется валидатором; ошибка уходит в починку
только того фрагмента, к которому относится её путь (не больше 3 раундов).
"""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import ValidationError

from ..config import ROOT
from ..engine import schema as s
from ..engine.art import ArtLibrary, load_library, repair_art
from ..engine.balance import tune_until_winnable
from ..engine.issues import Issue
from ..engine.prepare import prepare
from ..engine.simulator import PlaytestReport
from ..engine.validator import _schema_issues, validate
from ..llm import LLM
from .fragments import PLAN_FIELDS, ItemsContent, LocationContent, Outline, assemble, dump, fragment_schema, referenced_ids
from .json_utils import JsonError, parse_json
from .prompts import render

MAX_FRAGMENT_ATTEMPTS = 3
MAX_FIX_ROUNDS = 3
CATALOG_PATH = ROOT / "pixelart" / "catalog.md"

StatusFn = Callable[[str, float, dict[str, Any]], Awaitable[None] | None]


class GenerationFailed(Exception):
    def __init__(self, message: str, issues: list[Issue] | None = None) -> None:
        super().__init__(message)
        self.issues = issues or []


@dataclass
class GenerationResult:
    game: s.Game
    report: PlaytestReport
    warnings: list[Issue] = field(default_factory=list)


# --- бриф ---------------------------------------------------------------------

QUESTIONS_HEADING = re.compile(r"^#+\s*Уточняющие вопросы\s*$", re.MULTILINE | re.IGNORECASE)


def split_brief(markdown: str) -> tuple[str, list[str]]:
    """Отделяет раздел «Уточняющие вопросы» от брифа."""
    m = QUESTIONS_HEADING.search(markdown)
    if not m:
        return markdown.strip(), []
    body, tail = markdown[:m.start()], markdown[m.end():]
    questions = []
    for line in tail.splitlines():
        line = line.strip()
        if re.match(r"^(#+\s)", line):
            break
        q = re.sub(r"^([-*•]|\d+[.)])\s*", "", line)
        is_item = q != line or line.endswith("?")  # пункт списка или просто вопрос
        if q and is_item:
            questions.append(q)
    return body.strip(), questions[:5]


async def generate_brief(idea: str, llm: LLM, game_id: str | None = None) -> dict[str, Any]:
    text = await llm.complete(
        [{"role": "system", "content": render("brief")}, {"role": "user", "content": idea}],
        step="brief", quality="text", game_id=game_id, temperature=0.9,
    )
    body, questions = split_brief(text)
    return {"brief_markdown": body, "questions": questions}


# --- игра ---------------------------------------------------------------------

class Pipeline:
    def __init__(self, llm: LLM, brief: str, game_id: str, on_status: StatusFn | None = None,
                 library: ArtLibrary | None = None) -> None:
        self.llm = llm
        self.brief = brief
        self.game_id = game_id
        self.on_status = on_status
        self.library = library or load_library()
        self.catalog = CATALOG_PATH.read_text(encoding="utf-8")
        self.outline: Outline | None = None
        self.contents: dict[str, LocationContent] = {}
        self.items: ItemsContent | None = None

    async def status(self, step: str, progress: float, **info: Any) -> None:
        if self.on_status:
            result = self.on_status(step, progress, info)
            if inspect.isawaitable(result):
                await result

    # --- шаги ---

    async def run(self) -> GenerationResult:
        await self.status("outline", 0.05)
        self.outline = await self.fragment("outline", Outline, render(
            "outline", brief=self.brief, catalog=self.catalog, schema=_json(fragment_schema(Outline))), "Составь каркас игры.")
        await self.status("outline", 0.1, outline=self.preview())

        plans = self.outline.locations
        outline_json = _json(dump(self.outline))
        for k, plan in enumerate(plans):
            await self.status("locations", 0.1 + 0.6 * k / len(plans), done=k, total=len(plans))
            system = render("location", brief=self.brief, outline=outline_json, location=_json(dump(plan)),
                            catalog=self.catalog, schema=_json(fragment_schema(LocationContent)))
            self.contents[plan.id] = await self.fragment(f"location:{plan.id}", LocationContent, system, f"Наполни локацию «{plan.title}» ({plan.id}).")
        await self.status("locations", 0.7, done=len(plans), total=len(plans))

        await self.status("items", 0.75)
        refs = referenced_ids(self.contents)
        system = render("items", brief=self.brief, referenced=_json(refs), catalog=self.catalog, schema=_json(fragment_schema(ItemsContent)))
        self.items = await self.fragment("items", ItemsContent, system, "Опиши предметы, навыки и магазины.", quality="fast")

        return await self.check_and_playtest()

    async def check_and_playtest(self) -> GenerationResult:
        warnings: list[Issue] = []
        for round_ in range(MAX_FIX_ROUNDS + 1):
            await self.status("validate", 0.85, round=round_)
            report = validate(assemble(self.outline, self.contents, self.items), art=self.library)
            if not report.ok:
                if round_ == MAX_FIX_ROUNDS:
                    game = self.last_resort(report, warnings)
                else:
                    await self.fix_all(report.errors)
                    continue
            else:
                game = report.game

            await self.status("balance", 0.88)
            level_issues = prepare(game)
            await self.status("levels", 0.9)
            if level_issues:
                if round_ == MAX_FIX_ROUNDS:
                    raise GenerationFailed("не удалось разложить объекты по уровням", level_issues)
                await self.fix_all(level_issues)
                continue

            await self.status("playtest", 0.95)
            playtest = tune_until_winnable(game)
            blocking = [i for i in playtest.issues if i.severity == "error"]
            if not blocking:
                warnings += [i for i in playtest.issues if i.severity == "warning"]
                await self.status("ready", 1.0)
                return GenerationResult(game=game, report=playtest, warnings=warnings)
            if round_ == MAX_FIX_ROUNDS:
                raise GenerationFailed("игру не удаётся пройти: " + "; ".join(i.message for i in blocking[:3]), blocking)
            await self.fix_all(blocking)
        raise GenerationFailed("не удалось починить игру")

    def last_resort(self, report, warnings: list[Issue]) -> s.Game:
        """После 3 раундов: неизвестные детали графики заменяются деталями по умолчанию (§6.7), остальное — провал."""
        if report.game is None:
            raise GenerationFailed("игра не соответствует схеме даже после починки", report.errors)
        warnings += repair_art(report.game, self.library)
        again = validate(report.game, art=self.library)
        if not again.ok:
            raise GenerationFailed("в игре остались ошибки, которые не удалось починить", again.errors)
        warnings += again.warnings
        return again.game

    # --- фрагменты и починка ---

    async def fragment(self, step: str, model: type[s.Strict], system: str, user: str, quality: str = "text"):
        text = await self.llm.complete([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                       step=step, quality=quality, game_id=self.game_id)
        issues: list[Issue] = []
        for _ in range(MAX_FRAGMENT_ATTEMPTS):
            try:
                data = await parse_json(text, self.llm, step=step, game_id=self.game_id)
            except JsonError as exc:
                raise GenerationFailed(str(exc)) from exc
            try:
                return model.model_validate(data)
            except ValidationError as exc:
                issues = _schema_issues(exc)
                text = await self.request_fix(step, model, data, issues)
        raise GenerationFailed(f"шаг {step}: ответ не соответствует схеме после {MAX_FRAGMENT_ATTEMPTS} попыток", issues)

    async def request_fix(self, step: str, model: type[s.Strict], fragment: dict[str, Any], issues: list[Issue]) -> str:
        errors = "\n".join(f"- {i}" for i in issues[:40])
        return await self.llm.complete(
            [{"role": "system", "content": render("fix", schema=_json(fragment_schema(model)))},
             {"role": "user", "content": f"Фрагмент:\n{_json(fragment)}\n\nОшибки:\n{errors}"}],
            step=f"fix:{step}", quality="fast", game_id=self.game_id, temperature=0.2,
        )

    def route(self, issue: Issue) -> list[str]:
        """К каким фрагментам относится ошибка: outline, location:<id> или items."""
        path = issue.path
        m = re.match(r"locations\[(\d+)\](?:\.(\w+))?", path)
        if m:
            plan = self.outline.locations[int(m.group(1))]
            if m.group(2) is None:
                # «локация недостижима»: чинить надо локации, из которых по плану в неё ведёт выход
                sources = [f"location:{p.id}" for p in self.outline.locations if plan.id in p.links]
                return sources or ["outline"]
            return ["outline"] if m.group(2) in PLAN_FIELDS else [f"location:{plan.id}"]
        if path == "endings":
            endings = {e.id for e in self.outline.endings}
            sources = [f"location:{p.id}" for p in self.outline.locations if endings & set(p.links)]
            sources += [f"location:{lid}" for lid, c in self.contents.items()
                        if endings & set(re.findall(r'"(?:to|goto)":"([a-z0-9_]+)"', _json(dump(c))))]
            return list(dict.fromkeys(sources)) or ["outline"]
        m = re.match(r"enemies\[(\d+)\]", path)
        if m:
            data = assemble(self.outline, self.contents, self.items)
            enemy_id = data["enemies"][int(m.group(1))]["id"]
            for loc_id, content in self.contents.items():
                if any(e.id == enemy_id for e in content.enemies):
                    return [f"location:{loc_id}"]
        if re.match(r"(items|skills|shops|start_)", path):
            return ["items"]
        return ["outline"]

    async def fix_all(self, issues: list[Issue]) -> None:
        await self.status("fix", 0.86, errors=len(issues))
        groups: dict[str, list[Issue]] = {}
        for issue in issues:
            for target in self.route(issue):
                groups.setdefault(target, []).append(issue)
        for target, group in groups.items():
            if target == "outline":
                model, current = Outline, self.outline
            elif target == "items":
                model, current = ItemsContent, self.items
            else:
                model, current = LocationContent, self.contents[target.split(":", 1)[1]]
            text = await self.request_fix(target, model, dump(current), group)
            try:
                fixed = model.model_validate(await parse_json(text, self.llm, step=f"fix:{target}", game_id=self.game_id))
            except (JsonError, ValidationError):
                continue  # плохая починка — остаёмся на прежнем фрагменте, следующий раунд попробует снова
            if target == "outline":
                self.outline = fixed
            elif target == "items":
                self.items = fixed
            else:
                self.contents[target.split(":", 1)[1]] = fixed

    def preview(self) -> dict[str, Any]:
        """Что показать на экране ожидания после каркаса: название и герои с внешностью."""
        o = self.outline
        return {
            "title": o.meta.title, "logline": o.meta.logline,
            "characters": [{"id": c.id, "name": c.name, "role": c.role, "appearance": dump(c.appearance)} for c in [o.hero, *o.characters]],
            "locations": len(o.locations),
        }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
