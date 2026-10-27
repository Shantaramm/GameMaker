"""Настройки из окружения и файла .env в корне репозитория (SPEC §13)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#"):
            continue
        line = line.split(" #", 1)[0].strip()  # комментарий в конце строки — только после пробела
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    gigachat_auth_key: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_oauth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    gigachat_base_url: str = "https://api.giga.chat"
    gigachat_model_text: str = "GigaChat-2-Max"
    gigachat_model_fast: str = "GigaChat-2"
    gigachat_ca_bundle: str = "./certs/russian_trusted_root_ca.cer"
    llm_provider: str = "demo"  # gigachat | demo | relay
    max_concurrent_generations: int = 3
    games_per_hour_per_ip: int = 5
    data_dir: Path = field(default_factory=lambda: ROOT / "data")

    @property
    def ca_bundle_path(self) -> Path:
        p = Path(self.gigachat_ca_bundle)
        return p if p.is_absolute() else ROOT / p


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Порядок: явный env (для тестов) → переменные окружения → .env. Без ключа GigaChat — демо-провайдер."""
    source = {**_load_dotenv(ROOT / ".env"), **os.environ} if env is None else env
    get = lambda key, default: source.get(key) or default  # noqa: E731
    key = get("GIGACHAT_AUTH_KEY", "")
    data_dir = Path(get("DATA_DIR", str(ROOT / "data")))
    return Settings(
        gigachat_auth_key=key,
        gigachat_scope=get("GIGACHAT_SCOPE", Settings.gigachat_scope),
        gigachat_oauth_url=get("GIGACHAT_OAUTH_URL", Settings.gigachat_oauth_url),
        gigachat_base_url=get("GIGACHAT_BASE_URL", Settings.gigachat_base_url).rstrip("/"),
        gigachat_model_text=get("GIGACHAT_MODEL_TEXT", Settings.gigachat_model_text),
        gigachat_model_fast=get("GIGACHAT_MODEL_FAST", Settings.gigachat_model_fast),
        gigachat_ca_bundle=get("GIGACHAT_CA_BUNDLE", Settings.gigachat_ca_bundle),
        llm_provider=get("LLM_PROVIDER", "gigachat" if key else "demo"),
        max_concurrent_generations=int(get("MAX_CONCURRENT_GENERATIONS", "3")),
        games_per_hour_per_ip=int(get("GAMES_PER_HOUR_PER_IP", "5")),
        data_dir=data_dir if data_dir.is_absolute() else ROOT / data_dir,
    )
