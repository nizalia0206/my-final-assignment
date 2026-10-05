"""Your capstone agent: the one your README demos and your CI grades.

Hardened past the starter: a provider that raises or hangs is caught and
turned into a flagged refusal within `timeout_s`, never an escaped exception
or an unbounded wait. And a retrieved passage shaped like an instruction is
flagged for review regardless of whether the model obeyed it.

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
)


def _looks_injected(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in INJECTION_MARKERS)


def _flagged_refusal(reason: str) -> ResearchAnswer:
    return ResearchAnswer(
        answer=f"I don't know based on the provided corpus. ({reason})",
        citations=(),
        confidence=0.0,
        needs_human_review=True,
    )


class _TimeoutGuard:
    def __init__(self, inner: LLMClient, timeout_s: float) -> None:
        self._inner = inner
        self._timeout_s = timeout_s

    def complete(self, system: str, user: str) -> str:
        outcome: queue.Queue = queue.Queue(maxsize=1)

        def worker() -> None:
            try:
                outcome.put(("ok", self._inner.complete(system=system, user=user)))
            except Exception as error:  # noqa: BLE001
                outcome.put(("error", error))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            status, payload = outcome.get(timeout=self._timeout_s)
        except queue.Empty:
            raise TimeoutError(f"provider did not respond within {self._timeout_s}s") from None
        if status == "error":
            raise payload
        return payload


class YourAgent:
    """The agent the tests and the grader run. Make it yours."""

    timeout_s: float = 30.0

    def __init__(self, client: LLMClient | None = None) -> None:
        self.documents: list[Document] = load_corpus(CORPUS_DIR)
        self.client: LLMClient = client if client is not None else get_client(load_settings())
        self.tools: dict[str, Tool] = build_tools(self.documents, self.client)

    def run(self, question: str) -> AgentResult:
        """One question, answered or refused, with the trace of how."""
        guarded_client = _TimeoutGuard(self.client, self.timeout_s)
        try:
            result = answer_question(
                question,
                self.documents,
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

        return self._flag_if_retrieved_text_was_injected(question, result)

    def _flag_if_retrieved_text_was_injected(self, question: str, result: AgentResult) -> AgentResult:
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