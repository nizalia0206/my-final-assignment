"""Your capstone agent: the one your README demos and your CI grades.

Hardened past the starter: a provider that raises or hangs is caught and
turned into a flagged refusal within `timeout_s`, never an escaped exception
or an unbounded wait. A retrieved passage shaped like an instruction is
flagged for review regardless of whether the model obeyed it. When one
document's best-matching chunk clearly dominates the rest, the agent answers
from that document alone, so a tied, keyword-overlapping chunk from an
unrelated document cannot dilute the answer. And a soft refusal in the
model's own words is normalized to the canonical refusal text, so a refusal
always reads the same way.

The provider comes from `.env` (`BOOTCAMP_PROVIDER`), and falls back to the
offline `FakeLLM`. Keys live only in `.env`, which git ignores.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path

from bootcamp_agent.agent import AgentResult, TraceEvent, answer_question
from bootcamp_agent.config import load_settings
from bootcamp_agent.documents import Document, load_corpus
from bootcamp_agent.llm import LLMClient, get_client
from bootcamp_agent.retrieval import retrieve
from bootcamp_agent.schema import ResearchAnswer
from bootcamp_agent.tools import Tool, build_tools

CORPUS_DIR = Path(__file__).resolve().parent / "data" / "corpus"

INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "disregard the above",
    "disregard all previous",
    "new instructions:",
    "you are now",
    "forget everything",
    "override your",
    "act as if",
    "do not follow",
    "do not refuse",
    "pretend you",
)
CANONICAL_REFUSAL = "I don't know based on the provided corpus."

#: When the best-scoring document beats every other document's best chunk by
#: at least this ratio, only that document goes to the model.
DOMINANCE_RATIO = 1.3


def _looks_injected(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in INJECTION_MARKERS)


def _flagged_refusal(reason: str) -> ResearchAnswer:
    return ResearchAnswer(
        answer=f"{CANONICAL_REFUSAL} ({reason})",
        citations=(),
        confidence=0.0,
        needs_human_review=True,
    )


class _TimeoutGuard:
    """Wraps an `LLMClient` so a slow or broken provider never escapes as an
    unbounded wait or an unhandled exception."""

    def __init__(self, inner: LLMClient, timeout_s: float) -> None:
        self._inner = inner
        self._timeout_s = timeout_s

    def complete(self, system: str, user: str) -> str:
        strict_system = system + (
            "\n\nKeep the answer to two or three sentences. Do not use markdown "
            "headings. Do not invent an example that is not in the context. Cite "
            "only the document(s) a specific sentence in your answer is drawn from."
        )

        outcome: queue.Queue = queue.Queue(maxsize=1)

        def worker() -> None:
            try:
                outcome.put(("ok", self._inner.complete(system=strict_system, user=user)))
            except Exception as error:  # noqa: BLE001
                outcome.put(("error", error))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            status, payload = outcome.get(timeout=self._timeout_s)
        except queue.Empty:
            raise TimeoutError(f"provider did not respond within {self._timeout_s}s") from None
        if status == "error":
            raise payload  # type: ignore[misc]
        return payload  # type: ignore[return-value]


class YourAgent:
    """The agent the tests and the grader run. Make it yours."""

    timeout_s: float = 120.0

    def __init__(self, client: LLMClient | None = None) -> None:
        self.documents: list[Document] = load_corpus(CORPUS_DIR)
        self.client: LLMClient = client if client is not None else get_client(load_settings())
        self.tools: dict[str, Tool] = build_tools(self.documents, self.client)

    def run(self, question: str) -> AgentResult:
        """One question, answered or refused, with the trace of how."""
        guarded_client = _TimeoutGuard(self.client, self.timeout_s)
        focused_documents = self._focus_on_strongest_document(question)
        try:
            result = answer_question(
                question,
                focused_documents,
                guarded_client,
                max_tool_calls=3,
                top_k=3,
            )
        except Exception as error:  # noqa: BLE001
            reason = (
                "request timed out"
                if isinstance(error, TimeoutError)
                else f"{type(error).__name__}: {error}"
            )
            return AgentResult(answer=_flagged_refusal(reason), trace=(TraceEvent("decision", reason),))

        result = self._normalize_soft_refusals(result)
        return self._flag_if_retrieved_text_was_injected(question, result)

    def _focus_on_strongest_document(self, question: str) -> list[Document]:
        """When one document's best chunk clearly dominates the rest, answer
        from that document alone."""
        scored = retrieve(question, self.documents, top_k=5)
        if not scored:
            return self.documents
        best_by_doc: dict[str, float] = {}
        for s in scored:
            best_by_doc[s.chunk.doc_id] = max(best_by_doc.get(s.chunk.doc_id, 0.0), s.score)
        _, top_score = max(best_by_doc.items(), key=lambda item: item[1])
        dominant = {
            doc_id for doc_id, score in best_by_doc.items()
            if score * DOMINANCE_RATIO >= top_score
        }
        if len(dominant) == len(best_by_doc):
            return self.documents
        return [doc for doc in self.documents if doc.doc_id in dominant]

    def _normalize_soft_refusals(self, result: AgentResult) -> AgentResult:
        """If the model's own answer already amounts to a refusal but used its
        own wording, replace it with the canonical refusal text."""
        answer = result.answer
        looks_like_a_refusal = answer.citations == () and answer.confidence <= 0.2
        already_canonical = answer.answer.startswith(CANONICAL_REFUSAL)
        if not looks_like_a_refusal or already_canonical:
            return result
        normalized = ResearchAnswer(
            answer=CANONICAL_REFUSAL,
            citations=(),
            confidence=0.0,
            needs_human_review=True,
        )
        trace = (*result.trace, TraceEvent("decision", "model's own refusal wording normalized"))
        return AgentResult(answer=normalized, trace=trace)

    def _flag_if_retrieved_text_was_injected(self, question: str, result: AgentResult) -> AgentResult:
        """If any passage retrieved for this question looked like an
        instruction, the answer is flagged for review regardless of what the
        model did with it."""
        scored = retrieve(question, self.documents, top_k=3)
        injected = any(_looks_injected(s.chunk.text) for s in scored)
        if not injected:
            return result

        answer = result.answer
        if answer.needs_human_review and answer.confidence <= 0.2:
            return result

        flagged = ResearchAnswer(
            answer=answer.answer,
            citations=answer.citations,
            confidence=min(answer.confidence, 0.2),
            needs_human_review=True,
        )
        trace = (*result.trace, TraceEvent("decision", "instruction-shaped text in a retrieved passage; flagged"))
        return AgentResult(answer=flagged, trace=trace)

    def __call__(self, question: str) -> ResearchAnswer:
        return self.run(question).answer