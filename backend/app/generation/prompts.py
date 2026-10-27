"""Промпты лежат в prompts/*.md; плейсхолдеры {{name}} подставляются простой заменой (SPEC §9)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS = Path(__file__).parent / "prompts"


@lru_cache(maxsize=None)
def template(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def render(name: str, **values: str) -> str:
    text = template(name)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    missing = [part.split("}}")[0] for part in text.split("{{")[1:] if "}}" in part]
    if missing:
        raise KeyError(f"промпт {name}: не подставлены {missing}")
    return text
