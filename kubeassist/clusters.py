"""Discover the kubeconfig contexts the assistant is allowed to target."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


class ClusterRegistry:
    def __init__(self, kubeconfig: Path):
        self.kubeconfig = Path(kubeconfig)
        self._contexts: list[str] = []
        self._current: str | None = None
        self.reload()

    def reload(self) -> None:
        self._contexts, self._current = [], None
        if not self.kubeconfig.is_file():
            log.warning("Kubeconfig not found at %s", self.kubeconfig)
            return
        try:
            data = yaml.safe_load(self.kubeconfig.read_text()) or {}
        except (OSError, yaml.YAMLError) as exc:
            log.error("Could not read kubeconfig %s: %s", self.kubeconfig, exc)
            return
        self._contexts = [c["name"] for c in data.get("contexts") or [] if "name" in c]
        self._current = data.get("current-context")
        log.info("Loaded %d context(s) from %s", len(self._contexts), self.kubeconfig)

    @property
    def names(self) -> list[str]:
        return list(self._contexts)

    @property
    def default(self) -> str | None:
        if self._current in self._contexts:
            return self._current
        return self._contexts[0] if self._contexts else None

    def __contains__(self, name: object) -> bool:
        return name in self._contexts
