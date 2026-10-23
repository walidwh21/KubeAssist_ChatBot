import unittest

from kubeassist.intent import parse


class IntentTests(unittest.TestCase):
    def cmd(self, text):
        r = parse(text)
        return r.command if r else None

    def test_listing(self):
        self.assertEqual(self.cmd("show me the pods in namespace shop"), "kubectl get pods -n shop")
        self.assertEqual(self.cmd("list all pods in all namespaces"), "kubectl get pods -A")
        self.assertEqual(self.cmd("get nodes"), "kubectl get nodes")
        self.assertEqual(self.cmd("what are the services in the default namespace"), "kubectl get services -n default")

    def test_named_objects(self):
        self.assertEqual(self.cmd("describe deployment api in dev"), "kubectl describe deployment api -n dev")
        self.assertEqual(self.cmd("logs for pod web-7d9f in namespace shop"), "kubectl logs web-7d9f -n shop")
        self.assertEqual(self.cmd("delete pod web-7d9f in shop"), "kubectl delete pod web-7d9f -n shop")

    def test_mutations(self):
        self.assertEqual(self.cmd("scale deployment api to 3 in shop"),
                         "kubectl scale deployment api --replicas=3 -n shop")
        self.assertEqual(self.cmd("restart deployment api in shop"),
                         "kubectl rollout restart deployment api -n shop")
        self.assertEqual(self.cmd("create a namespace called staging"), "kubectl create namespace staging")

    def test_passthrough_and_non_commands(self):
        self.assertEqual(self.cmd("kubectl get pods -n x"), "kubectl get pods -n x")
        self.assertIsNone(self.cmd("what is a pod"))
        self.assertIsNone(self.cmd("show me the logs"))
        self.assertIsNone(self.cmd(""))


if __name__ == "__main__":
    unittest.main()
