"""Offline rule-based translation of plain English into a kubectl command.

This is the safety net used when the language model is unreachable, and the fast
path for commands the user typed verbatim. It deliberately understands only a small,
predictable set of phrasings and returns ``None`` for anything else.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

RESOURCES = {
    "pod": "pods", "pods": "pods", "po": "pods",
    "deployment": "deployments", "deployments": "deployments", "deploy": "deployments",
    "statefulset": "statefulsets", "statefulsets": "statefulsets", "sts": "statefulsets",
    "daemonset": "daemonsets", "daemonsets": "daemonsets", "ds": "daemonsets",
    "job": "jobs", "jobs": "jobs", "cronjob": "cronjobs", "cronjobs": "cronjobs",
    "service": "services", "services": "services", "svc": "services",
    "ingress": "ingresses", "ingresses": "ingresses",
    "configmap": "configmaps", "configmaps": "configmaps", "cm": "configmaps",
    "secret": "secrets", "secrets": "secrets",
    "pv": "pv", "pvc": "pvc",
    "node": "nodes", "nodes": "nodes",
    "namespace": "namespaces", "namespaces": "namespaces", "ns": "namespaces",
    "event": "events", "events": "events",
}
FILLER = {"the", "a", "an", "named", "called", "name", "pod", "pods", "of", "for", "in", "on",
          "from", "to", "me", "all", "my", "please", "namespace", "ns", "with", "-n"}
NS_PATTERNS = (
    re.compile(r"(?:^|\s)(?:-n|--namespace)[\s=]+([a-z0-9][a-z0-9.-]*)"),
    re.compile(r"\bin\s+(?:the\s+)?namespace\s+([a-z0-9][a-z0-9.-]*)"),
    re.compile(r"\b(?:in|from|on)\s+(?:the\s+)?([a-z0-9][a-z0-9.-]*)\s+(?:namespace|ns)\b"),
    re.compile(r"\bnamespace\s+([a-z0-9][a-z0-9.-]*)\b(?=.*\b(?:pods?|deployments?|services?|svc|jobs?)\b)"),
)
NOT_A_NAMESPACE = {"all", "every", "cluster", "the", "this", "that", "my", "a"}


@dataclass(frozen=True)
class RuleResult:
    command: str
    explanation: str


def _namespace(text: str) -> tuple[str | None, bool]:
    if re.search(r"\ball\s+namespaces\b|\bevery\s+namespace\b|\bacross\s+namespaces\b", text):
        return None, True
    for pattern in NS_PATTERNS:
        m = pattern.search(text)
        if m and m.group(1) not in NOT_A_NAMESPACE:
            return m.group(1), False
    m = re.search(r"\bin\s+(?:the\s+)?([a-z0-9][a-z0-9.-]*)\s*$", text)
    if m and m.group(1) not in NOT_A_NAMESPACE and m.group(1) not in RESOURCES:
        return m.group(1), False
    return None, False


def _resource(tokens: list[str]) -> tuple[str | None, int]:
    for i, tok in enumerate(tokens):
        if tok in RESOURCES:
            return RESOURCES[tok], i
    return None, -1


def _name_after(tokens: list[str], start: int) -> str | None:
    """First plausible object name after ``start``, e.g. ``pod web-7d9f``."""
    for tok in tokens[start + 1:]:
        if tok in FILLER:
            continue
        if tok in RESOURCES:
            continue
        if re.fullmatch(r"[a-z0-9][a-z0-9.-]*", tok):
            return tok
    return None


def _scope(ns: str | None, all_ns: bool) -> str:
    if all_ns:
        return " -A"
    return f" -n {ns}" if ns else ""


def parse(message: str) -> RuleResult | None:
    text = message.strip().lower().rstrip("?.! ")
    if not text:
        return None

    if text.startswith("kubectl "):
        return RuleResult(" ".join(shlex.split(message.strip())) if _safe_split(message) else message.strip(),
                          "Command typed by the user.")

    text = re.sub(r"\s*\(on cluster:[^)]*\)", "", text)
    tokens = re.findall(r"[a-z0-9][a-z0-9.\-=]*|-n", text)
    ns, all_ns = _namespace(text)
    resource, ridx = _resource(tokens)
    scope = _scope(ns, all_ns)

    # --- logs -------------------------------------------------------
    if re.search(r"\blogs?\b", text):
        lidx = next(i for i, t in enumerate(tokens) if t in {"log", "logs"})
        pod_idx = next((i for i, t in enumerate(tokens) if t in {"pod", "pods"}), lidx)
        name = _name_after(tokens, pod_idx)
        if name and name not in {"log", "logs", "show", "get", "view", "see"}:
            return RuleResult(f"kubectl logs {name}{' -n ' + ns if ns else ''}",
                              f"Print the logs of pod {name}.")
        return None

    # --- scale ------------------------------------------------------
    m = re.search(r"\bscale\b.*?\b(?:to|=)\s*(\d+)", text) or re.search(r"\bscale\b.*?--replicas=(\d+)", text)
    if m and re.search(r"\bscale\b", text):
        kind = resource if resource in {"deployments", "statefulsets"} else "deployments"
        kidx = ridx if ridx >= 0 else next(i for i, t in enumerate(tokens) if t == "scale")
        name = _name_after(tokens, kidx)
        if name and not name.isdigit():
            return RuleResult(f"kubectl scale {kind[:-1]} {name} --replicas={m.group(1)}{' -n ' + ns if ns else ''}",
                              f"Set {name} to {m.group(1)} replicas.")
        return None

    # --- restart ----------------------------------------------------
    if re.search(r"\brestart\b", text) and resource in {"deployments", "statefulsets", "daemonsets"}:
        name = _name_after(tokens, ridx)
        if name:
            return RuleResult(f"kubectl rollout restart {resource[:-1]} {name}{' -n ' + ns if ns else ''}",
                              f"Roll out fresh pods for {name}.")
        return None

    # --- create namespace ----------------------------------------------
    if re.search(r"\b(create|make|add)\b", text) and resource == "namespaces":
        name = _name_after(tokens, ridx)
        if name:
            return RuleResult(f"kubectl create namespace {name}", f"Create the namespace {name}.")
        return None

    # --- delete -------------------------------------------------------
    if re.search(r"\b(delete|remove)\b", text) and resource:
        name = _name_after(tokens, ridx)
        if name and name not in {"delete", "remove"}:
            return RuleResult(f"kubectl delete {resource[:-1] if resource.endswith('s') else resource} {name}"
                              f"{' -n ' + ns if ns else ''}", f"Delete {resource[:-1]} {name}.")
        return None

    # --- describe -----------------------------------------------------
    if re.search(r"\b(describe|inspect|details?)\b", text) and resource:
        name = _name_after(tokens, ridx)
        if name and name not in {"describe", "inspect", "detail", "details"}:
            return RuleResult(f"kubectl describe {resource[:-1]} {name}{' -n ' + ns if ns else ''}",
                              f"Show detailed state of {resource[:-1]} {name}.")
        return None

    # --- get / list ---------------------------------------------------
    if re.search(r"\b(get|show|list|display|see|view|what\s+are)\b", text) and resource:
        if resource == "events":
            return RuleResult(f"kubectl get events{scope}", "List recent events.")
        if resource in {"nodes", "namespaces", "pv"}:
            return RuleResult(f"kubectl get {resource}", f"List {resource}.")
        return RuleResult(f"kubectl get {resource}{scope}", f"List {resource}"
                          f"{' in namespace ' + ns if ns else ' across all namespaces' if all_ns else ''}.")
    return None


def _safe_split(message: str) -> bool:
    try:
        shlex.split(message)
        return True
    except ValueError:
        return False
