"""HTTP routes: a small JSON API plus the single-page UI."""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, g, jsonify, render_template, request

from . import guard
from .runner import run_kubectl
from .security import access_code_matches, issue_token, login_required, new_subject

log = logging.getLogger(__name__)
bp = Blueprint("kubeassist", __name__)

MAX_MESSAGE_CHARS = 1000


def _svc():
    return current_app.config["SERVICES"]


@bp.before_request
def _throttle():
    if request.endpoint == "kubeassist.index":
        return None
    if not _svc()["limiter"].allow(request.remote_addr or "unknown"):
        return jsonify(error="Too many requests. Please slow down."), 429
    return None


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/healthz")
def healthz():
    s = _svc()
    return jsonify(status="ok", clusters=len(s["clusters"].names),
                   llm_online=s["llm"].is_up(), knowledge_backend=s["kb"].backend)


@bp.get("/api/config")
def config():
    s = _svc()
    return jsonify(
        clusters=s["clusters"].names,
        default_cluster=s["clusters"].default,
        access_code_required=bool(current_app.config["SETTINGS"].access_code),
        llm_online=s["llm"].is_up(),
    )


@bp.post("/api/token")
def token():
    settings = current_app.config["SETTINGS"]
    body = request.get_json(silent=True) or {}
    if not access_code_matches(settings.access_code, body.get("access_code")):
        return jsonify(error="Invalid access code."), 403
    subject = new_subject()
    return jsonify(token=issue_token(settings.secret_key, subject, settings.token_ttl_hours))


def _proposal(plan, cluster: str, query: str, rejected: list[str] | None = None):
    """Validate a command plan and either stage it for approval or explain why not."""
    s = _svc()
    verdict = guard.evaluate(plan.command)
    if not verdict.allowed:
        s["store"].set_pending(g.session_id, None)
        return {"kind": "blocked", "text": verdict.reason, "command": plan.command}
    s["store"].set_pending(g.session_id, {
        "command": plan.command, "cluster": cluster, "query": query,
        "risk": verdict.risk, "rejected": (rejected or []) + [plan.command],
    })
    return {"kind": "proposal", "command": plan.command, "explanation": plan.text,
            "risk": verdict.risk, "cluster": cluster, "source": plan.source}


@bp.post("/api/ask")
@login_required
def ask():
    s, settings = _svc(), current_app.config["SETTINGS"]
    body = request.get_json(silent=True) or {}
    message = str(body.get("message", "")).strip()
    cluster = str(body.get("cluster") or "")
    if not message:
        return jsonify(error="Please enter a message."), 400
    if len(message) > MAX_MESSAGE_CHARS:
        return jsonify(error=f"Messages are limited to {MAX_MESSAGE_CHARS} characters."), 400

    store = s["store"]
    history = "\n".join(f"{r}: {t}" for r, t in store.recent_turns(g.session_id, settings.history_turns))
    plan = s["planner"].plan(message, history, cluster)
    store.add_turn(g.session_id, "user", message)

    if plan.kind == "command":
        if cluster not in s["clusters"]:
            store.set_pending(g.session_id, None)
            return jsonify(kind="blocked", text="Select a valid cluster before running commands.",
                           command=plan.command)
        payload = _proposal(plan, cluster, message)
        store.add_turn(g.session_id, "assistant", f"Proposed: {plan.command}")
        return jsonify(payload)

    store.set_pending(g.session_id, None)
    store.add_turn(g.session_id, "assistant", plan.text)
    return jsonify(kind="answer", text=plan.text, source=plan.source)


@bp.post("/api/retry")
@login_required
def retry():
    s, settings = _svc(), current_app.config["SETTINGS"]
    pending = s["store"].get_pending(g.session_id)
    if not pending:
        return jsonify(error="There is no proposal to replace."), 409
    history = "\n".join(f"{r}: {t}" for r, t in s["store"].recent_turns(g.session_id, settings.history_turns))
    plan = s["planner"].plan(pending["query"], history, pending["cluster"], avoid=pending["rejected"])
    if plan.kind != "command":
        s["store"].set_pending(g.session_id, None)
        return jsonify(kind="answer", text=plan.text, source=plan.source)
    return jsonify(_proposal(plan, pending["cluster"], pending["query"], pending["rejected"]))


@bp.post("/api/approve")
@login_required
def approve():
    s, settings = _svc(), current_app.config["SETTINGS"]
    body = request.get_json(silent=True) or {}
    decision = str(body.get("decision", "")).lower()
    pending = s["store"].get_pending(g.session_id)
    if not pending:
        return jsonify(error="There is nothing waiting for approval."), 409

    if decision == "reject":
        s["store"].set_pending(g.session_id, None)
        s["store"].add_turn(g.session_id, "assistant", "Command cancelled.")
        return jsonify(kind="cancelled", text="Cancelled. Nothing was run.")
    if decision != "approve":
        return jsonify(error="decision must be 'approve' or 'reject'."), 400

    # Re-validate at execution time: never trust what was stored earlier.
    verdict = guard.evaluate(pending["command"])
    if not verdict.allowed or pending["cluster"] not in s["clusters"]:
        s["store"].set_pending(g.session_id, None)
        return jsonify(kind="blocked", text=verdict.reason or "Cluster is no longer available.")

    result = run_kubectl(verdict.argv, pending["cluster"], settings)
    s["store"].set_pending(g.session_id, None)
    s["store"].record_execution(g.session_id, pending["cluster"], pending["command"], verdict.risk, result.ok)
    s["store"].add_turn(g.session_id, "assistant",
                        f"Ran `{pending['command']}` on {pending['cluster']} -> {'ok' if result.ok else 'failed'}")
    return jsonify(kind="result", ok=result.ok, output=result.output,
                   command=pending["command"], cluster=pending["cluster"])


@bp.get("/api/history")
@login_required
def history():
    return jsonify(items=_svc()["store"].recent_executions(g.session_id))
