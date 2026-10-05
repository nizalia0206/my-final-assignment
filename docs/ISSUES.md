# Ranked issues

**Filled by:** session 9 (the first list, `cap01-e5`), kept current until
session 14, which fixes rank 1 and adds its regression test.

| rank | issue | impact |
|---:|---|---|
| 1 | The local model (qwen2.5:7b-instruct via Ollama) gives different citation and grounding behavior across identical runs of the same question, with no code change between runs. Confirmed directly: running the practice grader twice in a row, the refusal question "Qual time venceu o campeonato brasileiro em 2024?" passed on one run and failed on the next, with the exact same four-gate failure signature it had before a fix that had already been verified working. | A user re-asking the identical question could get a correctly-grounded, correctly-refused answer one time and a malformed one the next, which undermines trust in the agent's consistency for identical inputs — especially damaging for a refusal, where consistency is the whole point. |
| 2 | The lexical retriever sometimes ranks a document that only shares generic security/validation vocabulary (e.g. "structured-outputs", about JSON schema validation) close to the document that actually answers a security question (e.g. "prompt-injection"), because both discuss "treating model output as untrusted input." A dominance filter was added to prefer the document whose best chunk dominates, but it only fully resolves cases where the score gap is large; near-tied cases still sometimes pull in the wrong second document. | A grounded answer can cite a tangentially related document instead of (or alongside) the one that actually supports the claim, which is caught by the grader's citation_precision gate but would otherwise look plausible to a human reader who didn't check the source. |
| 3 | The agent has no retry or self-correction step when a claim_support style failure happens — it only retries on a JSON parse failure, never on an answer that parsed fine but drifted from the source's exact wording into plausible-but-unstated elaboration. | Answers can be fluent, confidently delivered, and still contain claims the corpus does not literally support, with no automated check inside the agent itself to catch that before it reaches the person asking. |

## Rank 1, in progress

- The fix: Hardened `agent.py`'s `_TimeoutGuard` to instruct the model to stay
  concise and cite only what it draws from directly, and added
  `_normalize_soft_refusals` so a refusal is always rendered in the same
  canonical wording regardless of how the model phrased it that run. This
  reduces, but does not eliminate, the inconsistency: a temperature=0 /
  seed=0 experiment was tried and reverted, since it made overall practice
  scores worse rather than better.
- The regression test: not yet written; the right test is one that runs the
  same question through `YourAgent` multiple times with a real (non-fake)
  client and asserts the `stopped_because`/refusal shape agrees across runs —
  deferred because it needs a real model in CI, which the grader's own `fake`
  lane in CI cannot exercise.
- Before and after: see [EVAL_REPORT.md](EVAL_REPORT.md).