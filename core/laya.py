"""Laya Context Intelligence: relevance filtering for retrieved RAG contexts.

Laya (https://huggingface.co/convaiinnovations/laya) is a local, non-
autoregressive *decision* model — it does not generate answers. Here it is
used purely as a context-selection layer: for each chunk retrieved from
ChromaDB it answers one typed question ("is this context relevant to the
user's question?") of type "noul" and returns a calibrated probability.

Responsibilities stay separated:
    ChromaDB  = retrieve candidate knowledge (high recall)
    Laya      = decide/rank which retrieved knowledge is relevant
    llama.cpp = reason, synthesize and generate the final answer

A Laya relevance score is NOT a statement about factual correctness — only
about topical relevance to the question.

The ``laya`` package is optional: everything degrades gracefully when it is
not installed, fails to load, or errors during inference ( callers fall back
to the raw ChromaDB ranking ). The Router is created lazily on first use,
kept for the session (loading costs seconds; inference ~30-400 ms per call),
and never imported at module import time.
"""
import os
import threading

# transformers probes for TensorFlow at import; when TF is installed its
# abseil runtime can deadlock model construction (documented Laya issue).
# Must be set before the laya package is imported.
os.environ.setdefault("USE_TF", "0")

# Verified against the official model card (laya 0.3.20):
#   pip install laya                     (Python 3.10+)
#   from laya import Router
#   Router().predict(state, questions, model="multilingual", max_len=8192)
#   result["answers"]["relevant"]["noul"]  ->  probability the answer is yes
RELEVANCE_QUESTION = {
    "relevant": {
        "type": "noul",
        "instructions": ("Determine whether this context is relevant to "
                         "answering the user's question."),
    }
}

# Router model choices: "auto" lets the built-in router detect language and
# dispatch (English -> laya, everything else -> laya-multilingual, which also
# covers Persian and mixed-language questions). "english"/"multilingual"
# force one checkpoint.
MODEL_CHOICES = ("auto", "english", "multilingual")

# Layas state budget per question: english 512 tokens, multilingual 1024
# (up to 8192 with max_len). Chunks are ~1500 chars (~375 tokens), question
# plus wrapper adds a little more, so 8192 covers any single chunk.
STATE_MAX_LEN = 8192

# Chunk text longer than this is truncated before scoring: enough signal to
# judge relevance, keeps state small (see doc note about Laya context limits).
MAX_CONTEXT_CHARS = 3000
MAX_QUESTION_CHARS = 2000


class LayaUnavailable(Exception):
    """Laya cannot be used (not installed, failed to load, inference error)."""


class ContextScorer:
    """Lazy, session-wide Laya relevance scorer.

    Usage:
        scorer = ContextScorer()
        p = scorer.score("how do I flash it?", chunk_text)   # 0.0 .. 1.0
    The model loads on the first successful call, once per instance; the
    instance should live for the whole session (the GUI creates one).
    """

    def __init__(self):
        self._router = None
        self._failed = False
        self._error = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ state
    @property
    def available(self):
        """True when the Laya package can be imported (model may still load lazily)."""
        if self._router is not None:
            return True
        if self._failed:
            return False
        return _import_router() is not None

    @property
    def loaded(self):
        """True once the model is resident in memory."""
        return self._router is not None

    @property
    def error(self):
        return self._error

    def reset(self):
        """Forget a previous failure so the next call retries loading."""
        self._failed = False
        self._error = None

    # ------------------------------------------------------------ scoring
    def score(self, question, context, model="auto"):
        """Probability (0.0-1.0) that ``context`` is relevant to ``question``.

        Raises LayaUnavailable when Laya is not installed / cannot load /
        inference fails — callers decide how to fall back.
        """
        if not str(question).strip() or not str(context).strip():
            return 0.0
        router = self._ensure_router(model)
        try:
            state = {"question": str(question)[:MAX_QUESTION_CHARS],
                     "context": str(context)[:MAX_CONTEXT_CHARS]}
            result = router.predict(state, RELEVANCE_QUESTION,
                                    model=None if model == "auto" else model,
                                    max_len=STATE_MAX_LEN)
            value = float(result["answers"]["relevant"]["noul"])
        except LayaUnavailable:
            raise
        except Exception as e:
            raise LayaUnavailable(f"Laya inference failed: {e}") from e
        return min(max(value, 0.0), 1.0)

    def score_many(self, question, contexts, model="auto"):
        """Score several contexts. Laya answers every question of one call in
        a single forward pass, but its Python API takes ONE state per call,
        so candidates are evaluated sequentially (correct, still ~fast).
        """
        return [self.score(question, c, model) for c in contexts]

    # ------------------------------------------------------------ loading
    def _ensure_router(self, model):
        if self._router is not None:
            return self._router
        if self._failed:
            raise LayaUnavailable(self._error)
        with self._lock:  # two workers may race on first use
            if self._router is None:
                router_cls = _import_router()
                if router_cls is None:
                    self._failed = True
                    self._error = ('Laya is not installed — run '
                                   '"pip install laya" (Python 3.10+).')
                    raise LayaUnavailable(self._error)
                try:
                    self._router = router_cls()  # lazy: downloads on first use
                except Exception as e:
                    self._failed = True
                    self._error = f"Laya failed to load: {e}"
                    raise LayaUnavailable(self._error) from e
        return self._router


_ROUTER = None
_ROUTER_CHECKED = False


def _import_router():
    """Import laya.Router once; None when the package is missing."""
    global _ROUTER, _ROUTER_CHECKED
    if not _ROUTER_CHECKED:
        try:
            from laya import Router  # noqa: deferred — optional dependency
            _ROUTER = Router
        except Exception:
            _ROUTER = None
        _ROUTER_CHECKED = True
    return _ROUTER


# ---------------------------------------------------------------- selection
def filter_ranked(question, candidates, scores, threshold=0.70, final_top_k=4):
    """Threshold -> sort by Laya score -> cap at ``final_top_k``.

    Fallback policies (documented behaviour):
      * at least one candidate passes the threshold -> only the passing ones
      * NONE pass                                    -> the highest-scoring
                                                        candidates up to
                                                        final_top_k — an empty
                                                        context is never
                                                        returned while RAG
                                                        found something
    Every returned candidate keeps its original fields and gains "laya_score".
    """
    scored = []
    for cand, sc in zip(candidates, scores):
        c = dict(cand)
        c["laya_score"] = float(sc)
        scored.append(c)
    passing = [c for c in scored if c["laya_score"] >= threshold]
    picked = passing if passing else scored  # never send an empty context
    picked.sort(key=lambda c: c["laya_score"], reverse=True)
    return picked[:final_top_k]
