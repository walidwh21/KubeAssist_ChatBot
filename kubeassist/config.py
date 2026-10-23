"""Runtime configuration, read once from environment variables.

Every setting uses the ``KUBEASSIST_`` prefix so the app never collides with
other tooling that happens to live in the same environment.
"""
from __future__ import annotations

import logging
import os
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"KUBEASSIST_{name}", default)


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        log.warning("Ignoring non-numeric KUBEASSIST_%s=%r", name, raw)
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    secret_key: str
    token_ttl_hours: int = 12
    access_code: str | None = None

    kubeconfig: Path = Path("~/.kube/config").expanduser()
    kubectl_bin: str = "kubectl"
    command_timeout: int = 20
    max_output_chars: int = 20_000

    llm_url: str = "http://localhost:11434"
    llm_model: str = "mistral:instruct"
    llm_timeout: int = 60

    knowledge_dir: Path = PROJECT_ROOT / "knowledge"
    data_dir: Path = PROJECT_ROOT / "data"
    use_vector_search: bool = False
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    rate_limit_per_minute: int = 30
    history_turns: int = 8
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        secret = _env("SECRET_KEY")
        if not secret:
            secret = secrets.token_hex(32)
            log.warning(
                "KUBEASSIST_SECRET_KEY is not set: using a random key. "
                "Sessions will be invalidated on every restart."
            )
        return cls(
            secret_key=secret,
            token_ttl_hours=_env_int("TOKEN_TTL_HOURS", 12),
            access_code=_env("ACCESS_CODE") or None,
            kubeconfig=Path(_env("KUBECONFIG", "~/.kube/config")).expanduser(),
            kubectl_bin=_env("KUBECTL_BIN") or shutil.which("kubectl") or "kubectl",
            command_timeout=_env_int("COMMAND_TIMEOUT", 20),
            llm_url=_env("LLM_URL", "http://localhost:11434").rstrip("/"),
            llm_model=_env("LLM_MODEL", "mistral:instruct"),
            llm_timeout=_env_int("LLM_TIMEOUT", 60),
            knowledge_dir=Path(_env("KNOWLEDGE_DIR", str(PROJECT_ROOT / "knowledge"))),
            data_dir=Path(_env("DATA_DIR", str(PROJECT_ROOT / "data"))),
            use_vector_search=_env_bool("VECTOR_SEARCH", False),
            embedding_model=_env("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            rate_limit_per_minute=_env_int("RATE_LIMIT_PER_MINUTE", 30),
        )
