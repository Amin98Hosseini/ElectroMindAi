"""Tests for Laya Context Intelligence (core/laya.py + ui/workers.ContextWorker).

The Laya model is NEVER downloaded here: scoring is stubbed. The selection
logic is pure, so filter_ranked() is tested directly; the ContextWorker is
exercised with a fake scorer and a patched rag.retrieve. PyQt6 must be
available (the project depends on it anyway) for the QThread test.

Run:  python -m unittest tests.test_laya -v
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import laya
from core.laya import LayaUnavailable, ContextScorer, filter_ranked


CANDS = [
    {"text": "buck converter loop compensation", "path": "a.py"},
    {"text": "stm32 gpio init", "path": "b.c"},
    {"text": "rotary encoder wiring", "path": "c.md"},
    {"text": "bom csv", "path": "d.csv"},
]


class FakeScorer:
    """Stands in for ContextScorer with canned probabilities."""

    def __init__(self, scores):
        self.scores = list(scores)
        self.calls = []

    def score_many(self, question, contexts, model="auto"):
        self.calls.append((question, model))
        return self.scores[:len(contexts)]


class BrokenScorer:
    def score_many(self, question, contexts, model="auto"):
        raise LayaUnavailable("Laya is not installed — run \"pip install laya\".")


class TestFilterRanked(unittest.TestCase):
    def test_threshold_sorts_and_caps(self):
        # doc example: threshold 0.70, final_k 4 -> A,B,C,D kept, E dropped
        cands = [{"text": "t", "path": p} for p in "ABCDE"]
        scores = [0.94, 0.89, 0.83, 0.71, 0.42]
        out = filter_ranked("q", cands, scores, threshold=0.70, final_top_k=4)
        self.assertEqual([c["path"] for c in out], ["A", "B", "C", "D"])
        self.assertEqual(out[0]["laya_score"], 0.94)

    def test_threshold_drops_below(self):
        out = filter_ranked("q", CANDS, [0.9, 0.8, 0.5, 0.1],
                            threshold=0.7, final_top_k=4)
        self.assertEqual([c["path"] for c in out], ["a.py", "b.c"])

    def test_fallback_never_empty_when_all_below_threshold(self):
        out = filter_ranked("q", CANDS, [0.4, 0.3, 0.2, 0.1],
                            threshold=0.7, final_top_k=2)
        self.assertEqual([c["path"] for c in out], ["a.py", "b.c"])

    def test_caps_at_final_top_k(self):
        out = filter_ranked("q", CANDS, [0.9, 0.8, 0.7, 0.6],
                            threshold=0.5, final_top_k=2)
        self.assertEqual(len(out), 2)

    def test_keeps_original_fields_and_adds_score(self):
        out = filter_ranked("q", CANDS[:1], [0.9], threshold=0.5, final_top_k=1)
        self.assertEqual(out[0]["text"], CANDS[0]["text"])
        self.assertIn("laya_score", out[0])


class TestContextScorer(unittest.TestCase):
    def test_missing_package_is_reported_not_crash(self):
        scorer = ContextScorer()
        with mock.patch.object(laya, "_import_router", return_value=None):
            with self.assertRaises(LayaUnavailable):
                scorer.score("q", "context")
            self.assertFalse(scorer.available)
            self.assertIn("pip install laya", scorer.error)

    def test_inference_failure_raises_unavailable(self):
        scorer = ContextScorer()

        class FakeRouter:
            def predict(self, *a, **k):
                raise RuntimeError("boom")

        with mock.patch.object(laya, "_import_router", return_value=FakeRouter):
            with self.assertRaises(LayaUnavailable):
                scorer.score("q", "context")
            # failure is remembered: no second import/construct attempt
            with self.assertRaises(LayaUnavailable):
                scorer.score("q", "context")

    def test_reset_allows_retry(self):
        scorer = ContextScorer()

        class Flaky:
            def __init__(self):
                self.n = 0

            def predict(self, state, questions, **k):
                self.n += 1
                if self.n == 1:
                    raise RuntimeError("transient")
                return {"answers": {"relevant": {"noul": 0.83}}}

        with mock.patch.object(laya, "_import_router", return_value=Flaky):
            with self.assertRaises(LayaUnavailable):
                scorer.score("q", "context")
            scorer.reset()
            self.assertEqual(scorer.score("q", "context"), 0.83)

    def test_score_clamps_and_uses_relevance_question(self):
        scorer = ContextScorer()
        captured = {}

        class FakeRouter:
            def predict(self, state, questions, model=None, max_len=None):
                captured.update(state=state, questions=questions,
                                model=model, max_len=max_len)
                return {"answers": {"relevant": {"noul": 1.7}}}  # out of range

        with mock.patch.object(laya, "_import_router", return_value=FakeRouter):
            self.assertEqual(scorer.score("q?", "c"), 1.0)
        self.assertIn("relevant", captured["questions"])
        self.assertEqual(captured["questions"]["relevant"]["type"], "noul")
        self.assertEqual(captured["state"]["question"], "q?")

    def test_empty_input_scores_zero_without_model(self):
        scorer = ContextScorer()
        self.assertEqual(scorer.score("  ", "context"), 0.0)
        self.assertEqual(scorer.score("q", ""), 0.0)


class TestContextWorker(unittest.TestCase):
    def _run(self, worker):
        result = {}
        worker.done.connect(lambda info: result.update(info))
        worker.run()  # synchronous: QThread.run called directly
        return result

    def test_laya_disabled_plain_ranking(self):
        from ui.workers import ContextWorker
        w = ContextWorker("q", top_k=2, laya_enabled=False)
        with mock.patch("rag.retrieve", return_value=CANDS) as retr:
            info = self._run(w)
        retr.assert_called_once_with("q", 2)
        self.assertFalse(info["laya_used"])
        self.assertEqual(info["selected"], 2)
        self.assertEqual([s["path"] for s in info["snippets"]], ["a.py", "b.c"])

    def test_laya_enabled_pipeline(self):
        from ui.workers import ContextWorker
        w = ContextWorker("q", top_k=4, laya_enabled=True, laya_initial_k=10,
                          laya_final_k=2, laya_threshold=0.7,
                          scorer=FakeScorer([0.94, 0.61, 0.83, 0.4]))
        with mock.patch("rag.retrieve", return_value=CANDS) as retr:
            info = self._run(w)
        retr.assert_called_once_with("q", 10)  # high-recall candidate set
        self.assertTrue(info["laya_used"])
        self.assertEqual(info["retrieved"], 4)
        self.assertEqual(info["selected"], 2)
        self.assertEqual([s["path"] for s in info["snippets"]], ["a.py", "c.md"])
        self.assertEqual(info["scores"][0], (0.94, "a.py"))

    def test_laya_failure_falls_back(self):
        from ui.workers import ContextWorker
        w = ContextWorker("q", top_k=3, laya_enabled=True, laya_initial_k=10,
                          laya_final_k=3, laya_threshold=0.7,
                          scorer=BrokenScorer())
        with mock.patch("rag.retrieve", return_value=CANDS):
            info = self._run(w)
        self.assertFalse(info["laya_used"])
        self.assertIn("pip install laya", info["laya_error"])
        self.assertEqual(info["selected"], 3)  # original ChromaDB ranking
        self.assertEqual(info["snippets"][0]["path"], "a.py")

    def test_empty_retrieval(self):
        from ui.workers import ContextWorker
        w = ContextWorker("q", top_k=4, laya_enabled=True, scorer=FakeScorer([]))
        with mock.patch("rag.retrieve", return_value=[]):
            info = self._run(w)
        self.assertEqual(info["retrieved"], 0)
        self.assertEqual(info["snippets"], [])
        self.assertFalse(info["laya_used"])

    def test_retrieval_failure_reported(self):
        from ui.workers import ContextWorker
        w = ContextWorker("q", top_k=4, laya_enabled=False)
        with mock.patch("rag.retrieve", side_effect=RuntimeError("db closed")):
            info = self._run(w)
        self.assertIn("db closed", info["retrieve_error"])
        self.assertEqual(info["snippets"], [])


if __name__ == "__main__":
    unittest.main()
