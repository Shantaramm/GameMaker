"""Надёжное получение JSON из ответа LLM (SPEC §8.1).

1. Вырезать первый сбалансированный JSON-объект (модель любит ```json и пояснения вокруг).
2. json.loads; при ошибке — один запрос на починку.
3. Pydantic-валидация делается вызывающим кодом; её ошибки идут в автопочинку.
"""

from __future__ import annotations

import json
from typing import Any

from ..llm import LLM
from .prompts import render


class JsonError(ValueError):
    pass


def extract_json(text: str) -> str:
    """Первый сбалансированный {...} с учётом строк и экранирования."""
    start = text.find("{")
    if start < 0:
        raise JsonError("в ответе нет JSON-объекта")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise JsonError("JSON-объект не закрыт (ответ оборван?)")


def try_parse(text: str) -> dict[str, Any]:
    try:
        value = json.loads(extract_json(text))
    except json.JSONDecodeError as exc:
        raise JsonError(f"невалидный JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise JsonError("ожидался JSON-объект")
    return value


async def parse_json(text: str, llm: LLM, *, step: str, game_id: str | None = None) -> dict[str, Any]:
    try:
        return try_parse(text)
    except JsonError as first:
        repaired = await llm.complete(
            [{"role": "system", "content": render("repair_json")},
             {"role": "user", "content": f"Ошибка: {first}\n\n{text}"}],
            step=f"repair_json:{step}", quality="fast", game_id=game_id, temperature=0,
        )
        try:
            return try_parse(repaired)
        except JsonError as second:
            raise JsonError(f"{step}: ответ не удалось разобрать как JSON даже после починки ({second})") from second
