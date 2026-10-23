"""Command policy: decide whether a proposed ``kubectl`` command may run, and how risky it is.

The assistant never goes through a shell. Even so, a model (or a user) can propose
commands that hang, leak credentials or redirect kubectl to another cluster, so every
command is parsed and checked here before anything is executed.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass

READ_VERBS = {
    "get", "describe", "logs", "top", "explain", "events",
    "api-resources", "api-versions", "version", "cluster-info",
}
WRITE_VERBS = {
    "apply", "create", "scale", "annotate", "label", "patch", "set", "expose",
    "run", "cordon", "uncordon", "autoscale", "taint",
}
DESTRUCTIVE_VERBS = {"delete", "drain", "replace"}
ROLLOUT_READ = {"status", "history"}

# Verbs that are interactive, long-lived, or that reach outside the cluster API.
BLOCKED_VERBS = {
    "exec", "attach", "port-forward", "proxy", "cp", "edit", "debug",
    "config", "auth", "certificate", "plugin", "completion", "wait",
}

# Flags that would let a command escape the cluster chosen in the UI.
BLOCKED_FLAGS = {
    "--kubeconfig", "--context", "--cluster", "--user", "--server", "-s",
    "--token", "--as", "--as-group", "--certificate-authority",
    "--client-certificate", "--client-key", "--insecure-skip-tls-verify",
    "--username", "--password", "--raw",
}
SECRET_RESOURCES = {"secret", "secrets"}
SAFE_OUTPUTS = {"name", "wide"}


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    risk: str = "read"          # read | write | destructive
    reason: str = ""
    argv: tuple[str, ...] = ()


def _deny(reason: str) -> Verdict:
    return Verdict(False, reason=reason)


def _flag_name(token: str) -> str:
    return token.split("=", 1)[0]


def _output_format(args: list[str]) -> str | None:
    for i, tok in enumerate(args):
        if tok in {"-o", "--output"} and i + 1 < len(args):
            return args[i + 1]
        if tok.startswith("--output="):
            return tok.split("=", 1)[1]
        if tok.startswith("-o") and len(tok) > 2 and not tok.startswith("--"):
            return tok[2:]
    return None


def evaluate(command: str) -> Verdict:
    """Parse ``command`` and return a :class:`Verdict`."""
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return _deny(f"Could not parse the command ({exc}).")

    if not argv or argv[0] != "kubectl":
        return _deny("Only kubectl commands are supported.")
    args = argv[1:]
    if not args:
        return _deny("The command is empty.")

    verb = next((a for a in args if not a.startswith("-")), None)
    if verb is None:
        return _deny("No kubectl sub-command found.")
    if verb in BLOCKED_VERBS:
        return _deny(f"`kubectl {verb}` is not allowed from the chat interface.")
    if verb not in READ_VERBS | WRITE_VERBS | DESTRUCTIVE_VERBS | {"rollout"}:
        return _deny(f"Unsupported kubectl sub-command: {verb}.")

    for tok in args:
        if _flag_name(tok) in BLOCKED_FLAGS:
            return _deny(f"The flag `{_flag_name(tok)}` is not allowed.")
        if tok.lower().startswith(("http://", "https://")):
            return _deny("Remote manifests are not allowed.")

    flags = {_flag_name(t) for t in args}
    if verb == "get" and flags & {"-w", "--watch", "--watch-only"}:
        return _deny("Watching resources would block the request; run it without --watch.")
    if verb == "logs" and flags & {"-f", "--follow"}:
        return _deny("Following logs would block the request; run it without --follow.")

    if verb in {"get", "describe"} and SECRET_RESOURCES & {a.lower() for a in args}:
        fmt = _output_format(args)
        if verb == "get" and fmt not in SAFE_OUTPUTS and fmt is not None:
            return _deny("Dumping secret contents is not allowed.")

    if verb == "rollout":
        sub = next((a for a in args[args.index("rollout") + 1:] if not a.startswith("-")), None)
        if sub is None:
            return _deny("`kubectl rollout` needs a sub-command (status, history, restart, undo).")
        risk = "read" if sub in ROLLOUT_READ else "write"
    elif verb in DESTRUCTIVE_VERBS:
        risk = "destructive"
    elif verb in WRITE_VERBS:
        risk = "write"
    else:
        risk = "read"

    return Verdict(True, risk=risk, argv=tuple(argv))
