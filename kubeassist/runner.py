"""Execute an already-approved kubectl command against a chosen context."""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass

from .config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    ok: bool
    output: str
    returncode: int | None = None


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… output truncated ({len(text) - limit} more characters)"


def run_kubectl(argv: tuple[str, ...], context: str, settings: Settings) -> RunResult:
    """Run ``argv`` (which starts with ``kubectl``) pinned to ``context``.

    The context is passed with ``--context`` for this single process, so concurrent
    requests for different clusters never share global state.
    """
    cmd = [settings.kubectl_bin, "--context", context, *argv[1:]]
    env = {**os.environ, "KUBECONFIG": str(settings.kubeconfig)}
    log.info("Running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True,
            timeout=settings.command_timeout, check=False, shell=False,
        )
    except FileNotFoundError:
        return RunResult(False, f"kubectl executable not found ({settings.kubectl_bin}).")
    except subprocess.TimeoutExpired:
        return RunResult(False, f"Timed out after {settings.command_timeout}s.")
    except OSError as exc:
        return RunResult(False, f"Could not start kubectl: {exc}")

    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip() or f"kubectl exited with {proc.returncode}."
        return RunResult(False, _clip(message, settings.max_output_chars), proc.returncode)
    text = proc.stdout.strip() or "Done — kubectl returned no output."
    return RunResult(True, _clip(text, settings.max_output_chars), 0)
