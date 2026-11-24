"""Central configuration loader for AgriResolve AI.

All non-secret configuration lives in YAML files next to this module; secrets live
only in ``.env`` (git-ignored). Importing this module never prints or logs a secret.

Typical use::

    from src.config.settings import get_config, monitoring_config, project_path

    cfg = get_config()
    print(cfg.reference_date, cfg.season_label)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import yaml
from dotenv import load_dotenv

# Project root = two levels above this file (src/config/settings.py -> project root).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# Load .env once, without overriding variables already set in the environment.
load_dotenv(PROJECT_ROOT / ".env", override=False)

CONFIG_DIR: Path = PROJECT_ROOT / "src" / "config"


@dataclass(frozen=True)
class AppConfig:
    """Non-secret application configuration."""

    reference_date: date
    season_label: str
    season_start: str
    season_end: str
    baseline_start_year: int
    synthetic_banner: str
    data_dirs: dict[str, Path]


@lru_cache(maxsize=None)
def _load_yaml(name: str) -> dict[str, Any]:
    """Load and cache a YAML file from ``src/config``.

    Args:
        name: File name inside ``src/config``, e.g. ``"monitoring.yaml"``.

    Returns:
        Parsed YAML content as a dictionary.
    """
    path = CONFIG_DIR / name
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Return the cached application configuration."""
    raw = _load_yaml("app_config.yaml")
    season = raw.get("season", {})
    paths = raw.get("paths", {})
    return AppConfig(
        reference_date=date.fromisoformat(str(raw["reference_date"])),
        season_label=str(season.get("label", "Kharif 2026")),
        season_start=str(season.get("start_month", "2026-06")),
        season_end=str(season.get("end_month", "2026-10")),
        baseline_start_year=int(raw.get("baseline_start_year", 2019)),
        synthetic_banner=str(
            raw.get("ui", {}).get(
                "synthetic_banner",
                "Synthetic data + simulated RSK-village mapping. Not government data.",
            )
        ),
        data_dirs={key: PROJECT_ROOT / value for key, value in paths.items()},
    )


def monitoring_config() -> dict[str, Any]:
    """Return the routine/reported monitoring configuration."""
    return _load_yaml("monitoring.yaml")


def priority_config() -> dict[str, Any]:
    """Return the combined priority-engine configuration."""
    return _load_yaml("priority_weights.yaml")


def project_path(*parts: str) -> Path:
    """Build a path relative to the project root."""
    return PROJECT_ROOT.joinpath(*parts)


def ensure_data_dirs() -> None:
    """Create the data folders (and .gitkeep placeholders) if they are missing."""
    for folder in get_config().data_dirs.values():
        folder.mkdir(parents=True, exist_ok=True)
        keep = folder / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def db_configured() -> bool:
    """True when a usable PostgreSQL configuration is present in the environment.

    A password of ``change-me`` or an empty value means "not configured" so that the
    application degrades to its clearly-labelled CSV demo mode instead of crashing.
    """
    password = _env("DB_PASSWORD")
    return bool(_env("DB_NAME")) and bool(_env("DB_USER")) and password not in {"", "change-me"}


def database_url() -> str | None:
    """Build a SQLAlchemy URL from ``DB_*`` environment variables.

    Returns:
        The connection URL, or ``None`` when PostgreSQL is not configured.
    """
    if not db_configured():
        return None
    user = quote_plus(_env("DB_USER"))
    password = quote_plus(_env("DB_PASSWORD"))
    host = _env("DB_HOST", "localhost") or "localhost"
    port = _env("DB_PORT", "5432") or "5432"
    name = _env("DB_NAME")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def ollama_settings() -> tuple[str, str]:
    """Return ``(base_url, model)`` for the local Ollama server."""
    return (
        _env("OLLAMA_BASE_URL", "http://localhost:11434") or "http://localhost:11434",
        _env("OLLAMA_MODEL", "llama3") or "llama3",
    )


def google_key(name: str) -> str | None:
    """Return a Google API key from the environment, or ``None`` if unset.

    Args:
        name: One of ``GOOGLE_MAPS_API_KEY``, ``GOOGLE_ROUTES_API_KEY``,
            ``GOOGLE_WEATHER_API_KEY``.
    """
    value = _env(name)
    return value or None


def gee_settings() -> dict[str, str]:
    """Return Google Earth Engine settings (never the key itself, only its path)."""
    return {
        "project_id": _env("GEE_PROJECT_ID"),
        "service_account": _env("GEE_SERVICE_ACCOUNT"),
        "private_key_path": _env("GEE_PRIVATE_KEY_PATH"),
    }
