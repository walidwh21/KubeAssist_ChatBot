"""KubeAssist — a conversational front-end for kubectl."""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask

from .api import bp
from .clusters import ClusterRegistry
from .config import Settings
from .knowledge import KnowledgeBase
from .llm import OllamaClient
from .planner import Planner
from .security import RateLimiter
from .store import SessionStore

__version__ = "1.0.0"


def create_app(settings: Settings | None = None, *, llm=None) -> Flask:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = Flask(__name__)
    app.config["SETTINGS"] = settings

    llm = llm or OllamaClient(settings.llm_url, settings.llm_model, settings.llm_timeout)
    kb = KnowledgeBase(settings.knowledge_dir, Path(settings.data_dir) / "vector_index",
                       settings.use_vector_search, settings.embedding_model)
    app.config["SERVICES"] = {
        "clusters": ClusterRegistry(settings.kubeconfig),
        "store": SessionStore(Path(settings.data_dir) / "sessions.sqlite3"),
        "kb": kb,
        "llm": llm,
        "planner": Planner(llm, kb),
        "limiter": RateLimiter(settings.rate_limit_per_minute),
    }
    app.register_blueprint(bp)
    return app
