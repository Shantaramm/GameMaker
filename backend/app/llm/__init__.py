"""Провайдеры LLM: GigaChat, демо (без ключа) и сценарный (для тестов).

Пайплайн знает только интерфейс LLM.complete(); какой провайдер отвечает, задаёт LLM_PROVIDER.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Callable, Literal, Protocol

from ..config import Settings

Quality = Literal["text", "fast"]  # text — GIGACHAT_MODEL_TEXT, fast — GIGACHAT_MODEL_FAST
Messages = list[dict[str, str]]


class LLM(Protocol):
    name: str

    async def complete(self, messages: Messages, *, step: str, quality: Quality = "text",
                       game_id: str | None = None, temperature: float = 0.7) -> str: ...


class GigaChatLLM:
    name = "gigachat"

    def __init__(self, settings: Settings, client=None) -> None:
        from ..gigachat.client import GigaChatClient

        self.settings = settings
        self.client = client or GigaChatClient(settings)

    async def complete(self, messages: Messages, *, step: str, quality: Quality = "text",
                       game_id: str | None = None, temperature: float = 0.7) -> str:
        model = self.settings.gigachat_model_text if quality == "text" else self.settings.gigachat_model_fast
        result = await self.client.chat(messages, model, step=step, game_id=game_id, temperature=temperature)
        return result.text


class ScriptedLLM:
    """Отвечает функцией responder(step, messages); записывает все вызовы. Для тестов."""

    name = "scripted"

    def __init__(self, responder: Callable[[str, Messages], str]) -> None:
        self.responder = responder
        self.calls: list[tuple[str, Messages]] = []

    async def complete(self, messages: Messages, *, step: str, quality: Quality = "text",
                       game_id: str | None = None, temperature: float = 0.7) -> str:
        self.calls.append((step, messages))
        return self.responder(step, messages)


DEMO_BRIEF = """# Погасший маяк

**Жанр и тон:** мрачная сказка с надеждой, детектив с щепоткой мистики.

**Герой:** Арина Стрельцова — следовательница из столицы, выросла в портовом городе. Упрямая, наблюдательная, привыкла полагаться только на себя.

**Мир:** туманный северный порт. Три ночи назад погас маяк, и начали пропадать люди.

**Антагонист:** магистр Олеандр — учёный-отшельник, поселившийся в маяке. Платит морю «подношениями».

**Локации:**
1. Пристань — встреча с другом детства Тимофеем и торговкой Марфой.
2. Рыбный переулок — гигантские крысы и ключ от архива.
3. Архив управы — архивариус и журнал Олеандра.
4. Подножие маяка — встреча с магистром и его служителями.
5. Башня маяка — треснувшая линза.

**Основной квест:** зажечь маяк. **Побочный:** прогнать крыс для Марфы.

**Финалы:** зажечь маяк вместе с Тимофеем — рассвет; в одиночку — туман остаётся.

## Уточняющие вопросы
- Насколько мрачной должна быть история?
- Нужен ли компаньон в бою или только в разговорах?
"""


class DemoLLM:
    """Без ключа GigaChat: на любой запрос отвечает фрагментами демо-игры «Погасший маяк».

    Позволяет прогнать весь путь пользователя (бриф → генерация → игра) до появления ключа.
    Содержимое идеи не учитывается — интерфейс честно сообщает о демо-режиме.
    """

    name = "demo"

    async def complete(self, messages: Messages, *, step: str, quality: Quality = "text",
                       game_id: str | None = None, temperature: float = 0.7) -> str:
        from ..generation.fragments import dump

        outline, contents, items = _demo_fragments()
        if step == "brief":
            return DEMO_BRIEF
        if step == "outline":
            return json.dumps(dump(outline), ensure_ascii=False)
        if step.startswith("location:"):
            return json.dumps(dump(contents[step.split(":", 1)[1]]), ensure_ascii=False)
        if step == "items":
            return json.dumps(dump(items), ensure_ascii=False)
        # починка: демо-фрагменты корректны, возвращаем присланный фрагмент без изменений
        return messages[-1]["content"]


@lru_cache(maxsize=1)
def _demo_fragments():
    from ..engine.validator import validate
    from ..generation.fragments import split_game
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "demo_game.json"
    return split_game(validate(json.loads(fixture.read_text(encoding="utf-8"))).game)


def make_llm(settings: Settings) -> LLM:
    if settings.llm_provider == "gigachat":
        return GigaChatLLM(settings)
    if settings.llm_provider == "demo":
        return DemoLLM()
    raise ValueError(f"неизвестный LLM_PROVIDER: {settings.llm_provider}")
