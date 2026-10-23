import tempfile
import unittest
from pathlib import Path

from kubeassist.knowledge import KnowledgeBase, split_text, tidy
from kubeassist.llm import LLMUnavailable, parse_reply


class ParseReplyTests(unittest.TestCase):
    def test_command(self):
        r = parse_reply('```json\n{"type":"command","command":"kubectl get pods","explanation":"List pods."}\n```')
        self.assertEqual((r.kind, r.command), ("command", "kubectl get pods"))

    def test_answer_variants(self):
        self.assertEqual(parse_reply('{"type":"answer","text":"hi"}').text, "hi")
        self.assertEqual(parse_reply('noise {"type":"question","answer":"yo"} trailing').text, "yo")

    def test_bad_replies(self):
        for raw in ("", "no json", '{"type":"command"}', '{"type":"answer"}', "{broken"):
            with self.assertRaises(LLMUnavailable):
                parse_reply(raw)


class KnowledgeTests(unittest.TestCase):
    def test_split_respects_size(self):
        text = "\n\n".join(f"paragraph {i} " + "x" * 200 for i in range(10))
        chunks = split_text(text, size=500, overlap=50)
        self.assertGreater(len(chunks), 3)

    def test_chunks_never_start_mid_sentence(self):
        text = "\n\n".join(f"Paragraph number {i} ends here." + " word" * 40 for i in range(8))
        for chunk in split_text(text, size=400, overlap=60):
            self.assertTrue(chunk.startswith("Paragraph"), chunk[:30])

    def test_tidy_strips_headings_and_unwraps(self):
        out = tidy("# Pods\n\nA Pod is the\nsmallest unit.\n\n# Next\n\nMore.")
        self.assertEqual(out, "A Pod is the smallest unit.\n\nMore.")

    def test_keyword_search_ranks_relevant_doc(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.md").write_text("A Pod is the smallest deployable unit.\n\nPods share network.")
            (Path(d) / "b.md").write_text("Ingress routes external HTTP traffic to services.")
            kb = KnowledgeBase(Path(d))
            self.assertEqual(kb.backend, "keyword")
            self.assertEqual(kb.search("what is an ingress?")[0].source, "b.md")
            self.assertEqual(kb.search("smallest unit pod")[0].source, "a.md")
            self.assertEqual(kb.search("zzzz"), [])


if __name__ == "__main__":
    unittest.main()
