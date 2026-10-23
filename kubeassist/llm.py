"""Thin client for a local Ollama server plus prompt/response handling."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """Raised when the model server cannot be reached or returns garbage."""


@dataclass(frozen=True)
class LLMReply:
    kind: str                 # "command" | "answer"
    text: str = ""            # answer text, or explanation for a command
    command: str = ""


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: int = 60):
        self.base_url, self.model, self.timeout = base_url, model, timeout

    def generate(self, prompt: str) -> str:
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "format": "json", "options": {"temperature": 0.1}},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except (requests.RequestException, ValueError) as exc:
            raise LLMUnavailable(str(exc)) from exc

    def is_up(self) -> bool:
        try:
            return requests.get(f"{self.base_url}/api/tags", timeout=2).ok
        except requests.RequestException:
            return False


PROMPT = """You are KubeAssist, a careful Kubernetes operations assistant. You understand English and French.
Decide whether the user wants (a) an explanation or (b) a kubectl command, and reply with ONE JSON object.

Explanation:  {{"type": "answer", "text": "<clear, concise answer>"}}
Command:      {{"type": "command", "command": "<single kubectl command>", "explanation": "<one sentence>"}}

Rules:
- Prefer the simplest standard kubectl command. Never use pipes, shell operators or other binaries.
- Never include --context, --kubeconfig or --server; the target cluster is selected by the application.
- Use the reference notes when they are relevant; otherwise rely on general Kubernetes knowledge.
{avoid}
### Reference notes
{context}

### Conversation so far
{history}

### Target cluster
{cluster}

### User request
{query}

JSON:"""


def build_prompt(query: str, history: str, context: str, cluster: str, avoid: list[str] | None = None) -> str:
    avoid_line = ""
    if avoid:
        avoid_line = "- The user rejected these commands, so propose a different approach: " + "; ".join(avoid) + "\n"
    return PROMPT.format(query=query, history=history or "(none)", context=context or "(none)",
                         cluster=cluster or "(unspecified)", avoid=avoid_line)


def parse_reply(raw: str) -> LLMReply:
    """Extract the first JSON object from ``raw`` and validate its shape."""
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    start = cleaned.find("{")
    if start == -1:
        raise LLMUnavailable("The model did not return JSON.")
    try:
        data, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    except json.JSONDecodeError as exc:
        raise LLMUnavailable(f"Malformed JSON from the model: {exc}") from exc

    kind = str(data.get("type", "")).lower()
    if kind == "command" and str(data.get("command", "")).strip():
        return LLMReply("command", str(data.get("explanation", "")).strip(), str(data["command"]).strip())
    if kind in {"answer", "question"}:
        text = str(data.get("text") or data.get("answer") or "").strip()
        if text:
            return LLMReply("answer", text)
    raise LLMUnavailable("The model reply was missing required fields.")
