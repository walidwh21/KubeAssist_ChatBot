import os
import stat
import tempfile
import unittest
from pathlib import Path

from kubeassist import create_app
from kubeassist.config import Settings
from kubeassist.llm import LLMUnavailable

ROOT = Path(__file__).resolve().parent.parent


class FakeLLM:
    def __init__(self, reply=None):
        self.reply, self.prompts = reply, []

    def generate(self, prompt):
        self.prompts.append(prompt)
        if self.reply is None:
            raise LLMUnavailable("offline")
        return self.reply

    def is_up(self):
        return self.reply is not None


class ApiTests(unittest.TestCase):
    def make(self, llm, code=None, **overrides):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        kubectl = Path(self.tmp.name) / "kubectl"
        kubectl.write_text('#!/bin/sh\necho "ran: $@"\n')
        kubectl.chmod(kubectl.stat().st_mode | stat.S_IEXEC)
        settings = Settings(
            secret_key="test-secret", kubeconfig=ROOT / "demo" / "kubeconfig.yaml",
            kubectl_bin=str(kubectl), data_dir=Path(self.tmp.name) / "data",
            knowledge_dir=ROOT / "knowledge", rate_limit_per_minute=1000, **overrides,
        )
        self.client = create_app(settings, llm=llm).test_client()
        tok = self.client.post("/api/token", json={"access_code": code}).get_json().get("token", "")
        self.auth = {"Authorization": f"Bearer {tok}"}

    def post(self, path, body=None):
        return self.client.post(path, json=body or {}, headers=self.auth)

    # ---- auth ---------------------------------------------------------
    def test_requires_token(self):
        self.make(FakeLLM())
        self.assertEqual(self.client.post("/api/ask", json={"message": "x"}).status_code, 401)
        bad = {"Authorization": "Bearer nope"}
        self.assertEqual(self.client.get("/api/history", headers=bad).status_code, 401)

    def test_access_code(self):
        self.make(FakeLLM(), code="letmein", access_code="letmein")
        self.assertEqual(self.client.post("/api/token", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/token", json={"access_code": "letmein"}).status_code, 200)

    # ---- offline fallback ---------------------------------------------
    def test_rules_fallback_proposal_then_approve(self):
        self.make(FakeLLM(None))
        r = self.post("/api/ask", {"message": "show pods in namespace shop", "cluster": "dev-cluster"}).get_json()
        self.assertEqual((r["kind"], r["command"], r["risk"], r["source"]),
                         ("proposal", "kubectl get pods -n shop", "read", "rules"))
        out = self.post("/api/approve", {"decision": "approve"}).get_json()
        self.assertTrue(out["ok"])
        self.assertEqual(out["output"], "ran: --context dev-cluster get pods -n shop")
        hist = self.client.get("/api/history", headers=self.auth).get_json()["items"]
        self.assertEqual(hist[0]["command"], "kubectl get pods -n shop")
        # approval is single-use
        self.assertEqual(self.post("/api/approve", {"decision": "approve"}).status_code, 409)

    def test_knowledge_answer_when_offline(self):
        self.make(FakeLLM(None))
        r = self.post("/api/ask", {"message": "what is a deployment?", "cluster": "dev-cluster"}).get_json()
        self.assertEqual((r["kind"], r["source"]), ("answer", "notes"))
        self.assertIn("Deployment", r["text"])

    # ---- llm path -----------------------------------------------------
    def test_llm_command_and_destructive_flag(self):
        llm = FakeLLM('{"type":"command","command":"kubectl delete pod web-1 -n shop","explanation":"Remove it."}')
        self.make(llm)
        r = self.post("/api/ask", {"message": "kill web-1", "cluster": "staging-cluster"}).get_json()
        self.assertEqual((r["kind"], r["risk"], r["source"]), ("proposal", "destructive", "llm"))
        self.assertIn("staging-cluster", llm.prompts[0])

    def test_reject_runs_nothing(self):
        self.make(FakeLLM(None))
        self.post("/api/ask", {"message": "get nodes", "cluster": "dev-cluster"})
        self.assertEqual(self.post("/api/approve", {"decision": "reject"}).get_json()["kind"], "cancelled")
        self.assertEqual(self.client.get("/api/history", headers=self.auth).get_json()["items"], [])

    def test_llm_proposing_forbidden_command_is_blocked(self):
        self.make(FakeLLM('{"type":"command","command":"kubectl exec -it web -- sh","explanation":"x"}'))
        r = self.post("/api/ask", {"message": "open a shell", "cluster": "dev-cluster"}).get_json()
        self.assertEqual(r["kind"], "blocked")
        self.assertEqual(self.post("/api/approve", {"decision": "approve"}).status_code, 409)

    def test_retry_passes_rejected_commands_to_model(self):
        llm = FakeLLM('{"type":"command","command":"kubectl get pods","explanation":"x"}')
        self.make(llm)
        self.post("/api/ask", {"message": "show pods", "cluster": "dev-cluster"})
        self.post("/api/retry")
        self.assertIn("rejected these commands", llm.prompts[-1])

    # ---- validation ---------------------------------------------------
    def test_invalid_cluster_and_input(self):
        self.make(FakeLLM(None))
        r = self.post("/api/ask", {"message": "get nodes", "cluster": "prod-nope"}).get_json()
        self.assertEqual(r["kind"], "blocked")
        self.assertEqual(self.post("/api/ask", {"message": ""}).status_code, 400)
        self.assertEqual(self.post("/api/ask", {"message": "x" * 2000}).status_code, 400)

    def test_sessions_are_isolated(self):
        self.make(FakeLLM(None))
        self.post("/api/ask", {"message": "get nodes", "cluster": "dev-cluster"})
        other = self.client.post("/api/token", json={}).get_json()["token"]
        res = self.client.post("/api/approve", json={"decision": "approve"},
                               headers={"Authorization": f"Bearer {other}"})
        self.assertEqual(res.status_code, 409)

    def test_rate_limit(self):
        self.make(FakeLLM(None))
        app = self.client.application
        from kubeassist.security import RateLimiter
        app.config["SERVICES"]["limiter"] = RateLimiter(2)
        codes = [self.client.get("/api/config").status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_ui_has_no_branding(self):
        self.make(FakeLLM())
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("KubeAssist", html)


if __name__ == "__main__":
    unittest.main()
