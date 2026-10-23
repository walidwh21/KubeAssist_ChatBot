"""Turns a user message into a :class:`Plan` — the single decision the API acts on."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from . import intent
from .knowledge import KnowledgeBase, tidy
from .llm import LLMUnavailable, OllamaClient, build_prompt, parse_reply

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Plan:
    kind: str                 # "command" | "answer"
    text: str = ""
    command: str = ""
    source: str = "llm"       # llm | rules | direct | notes


class Planner:
    def __init__(self, llm: OllamaClient, kb: KnowledgeBase):
        self.llm, self.kb = llm, kb

    def plan(self, message: str, history: str, cluster: str, avoid: list[str] | None = None) -> Plan:
        # 1. A command typed verbatim needs no interpretation.
        if message.strip().startswith("kubectl "):
            return Plan("command", "Command typed by the user.", message.strip(), "direct")

        # 2. Ask the language model, grounded in the knowledge base.
        try:
            raw = self.llm.generate(build_prompt(message, history, self.kb.context_for(message), cluster, avoid))
            reply = parse_reply(raw)
            return Plan(reply.kind, reply.text, reply.command, "llm")
        except LLMUnavailable as exc:
            log.warning("LLM unavailable, falling back to rules: %s", exc)

        # 3. Offline fallback: deterministic phrase rules, then raw knowledge notes.
        rule = None if avoid else intent.parse(message)
        if rule:
            return Plan("command", rule.explanation, rule.command, "rules")
        if avoid:
            return Plan("answer", "I couldn't come up with a different command without the language model.", source="rules")
        notes = self.kb.search(message, k=1, kind="prose")
        if notes:
            return Plan("answer", tidy(notes[0].text), source="notes")
        return Plan("answer", "The language model is offline and I couldn't match that request to a known command. "
                              "Try something like “show pods in namespace dev”.", source="rules")
