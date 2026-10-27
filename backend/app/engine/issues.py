from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Issue(BaseModel):
    path: str  # "scenes[3].events[1].nodes[4].next"; "" — вся игра
    message: str
    # quality — замечание о качестве (например, мелкие диалоги в глубокой игре): один раз уходит
    # в автопочинку, но игру не ломает и в итоге становится предупреждением.
    severity: Literal["error", "warning", "quality"] = "error"

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


def format_path(*parts: str | int) -> str:
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else part
    return out
