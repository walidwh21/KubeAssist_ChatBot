import unittest

from kubeassist.guard import evaluate


class GuardTests(unittest.TestCase):
    def allowed(self, cmd, risk):
        v = evaluate(cmd)
        self.assertTrue(v.allowed, v.reason)
        self.assertEqual(v.risk, risk)

    def denied(self, cmd):
        self.assertFalse(evaluate(cmd).allowed, cmd)

    def test_risk_levels(self):
        self.allowed("kubectl get pods -n dev", "read")
        self.allowed("kubectl logs web-1 -n dev", "read")
        self.allowed("kubectl rollout status deployment/api", "read")
        self.allowed("kubectl scale deployment api --replicas=3", "write")
        self.allowed("kubectl rollout restart deployment api", "write")
        self.allowed("kubectl delete pod web-1", "destructive")

    def test_blocked_verbs(self):
        for cmd in ("kubectl exec -it web -- sh", "kubectl port-forward svc/x 80", "kubectl config view",
                    "kubectl edit deploy api", "kubectl proxy"):
            self.denied(cmd)

    def test_cluster_escape_flags(self):
        for cmd in ("kubectl get pods --context prod", "kubectl get pods --server=https://x",
                    "kubectl get pods --kubeconfig /tmp/k", "kubectl get pods --token abc", "kubectl get pods -s https://x"):
            self.denied(cmd)

    def test_blocking_flags(self):
        self.denied("kubectl get pods -w")
        self.denied("kubectl logs web-1 -f")
        self.denied("kubectl logs web-1 --follow")

    def test_secret_dump_blocked_but_listing_allowed(self):
        self.denied("kubectl get secret db -o yaml")
        self.denied("kubectl get secrets -ojson")
        self.allowed("kubectl get secrets -n dev", "read")
        self.allowed("kubectl get secrets -o name", "read")

    def test_remote_manifest_and_non_kubectl(self):
        self.denied("kubectl apply -f https://example.com/x.yaml")
        self.denied("rm -rf /")
        self.denied("ls kubectl")
        self.denied("kubectl")
        self.denied("kubectl 'unterminated")

    def test_shell_metacharacters_are_inert_arguments(self):
        v = evaluate("kubectl get pods ; echo hi")
        self.assertTrue(v.allowed)  # passed as literal args, never to a shell
        self.assertIn(";", v.argv)


if __name__ == "__main__":
    unittest.main()
