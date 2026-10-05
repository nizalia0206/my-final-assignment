# my-final-assignment

A research assistant that answers developer questions from six source documents on RAG, agents, and MCP, citing the exact document it drew from — and refuses, in the same recognizable words every time, when those documents do not support an answer.

## The problem

A developer learning agent architecture has to piece together scattered advice on retrieval, tool design, structured outputs, and prompt injection from many sources, with no way to check whether an answer is actually grounded in something real or just sounds plausible. This agent answers only from a fixed, inspectable set of documents, and says so plainly when a question falls outside them — rather than confidently guessing.

## Demo

Two runs, pasted exactly as the commands printed them. Never an edited one.
`trace` prints every step the agent took, then the answer.

### One supported answer

```bash
uv run bootcamp capstone trace "How does chunking work in RAG?"
```

```text
[retrieve] top_k=3 -> [('rag-basics', 1), ('rag-basics', 2), ('evaluation-basics', 0)]
[llm_call] attempt 1: 260 chars
[decision] answered with citations ['rag-basics']

answer: Chunking splits documents into passages small enough to be individually relevant — respecting paragraph boundaries beats cutting at a fixed character count mid-sentence.
citations: ['rag-basics']
confidence: 1.0
needs_human_review: False
```

### One refusal

```bash
uv run bootcamp capstone trace "What is the capital city of Mongolia?"
```

```text
[retrieve] top_k=3 -> []
[decision] no relevant chunks; refusing without an LLM call

answer: I don't know based on the provided corpus.
citations: []
confidence: 0.0
needs_human_review: True
```

## Architecture

One question costs at most one model call (plus one corrective retry if the
model's JSON doesn't parse): retrieve top-3 chunks by keyword overlap, refuse
immediately with zero model calls if nothing is retrieved, otherwise call the
model once with the retrieved context, verify every citation against what was
actually retrieved (stripping and flagging anything fabricated), and return.
Past the course's own pipeline, `YourAgent` adds: a timeout/error guard so a
hung or broken provider becomes a flagged refusal instead of a crash or an
unbounded wait; a retrieval dominance filter that narrows to one document when
its best-matching chunk clearly outscores every other document's best chunk,
so a tangentially related document can't dilute an answer; and a refusal
normalizer that rewrites any free-form "I don't know" into the same canonical
phrase, so a refusal always reads identically regardless of how the model
happened to phrase it that run.

See [docs/adr/0001-run-shape.md](docs/adr/0001-run-shape.md).

## Measured results

Every number here comes from a command in this table, run on this commit. Say
which model produced it: CI has no keys, so a CI number is always the offline
fake model's.

| What | Command | Model | Result |
|---|---|---|---|
| Contract tests | `uv run pytest` | fake | `7 passed, 2 skipped` |
| Practice grader | `uv run bootcamp final grade` | fake | `score: 3/10 (30%) — critical safety gate failed` |
| Practice grader | `uv run bootcamp final grade` | ollama, qwen2.5:7b-instruct | `score: 5/10 (50%) — critical safety gate failed` (best observed; 40-60% across repeated runs, see docs/ISSUES.md rank 1) |
| Evaluation, before and after | see [docs/EVAL_REPORT.md](docs/EVAL_REPORT.md) | fake vs. ollama | 30% → 40-60% |

## The honest limitation

The local model gives different citation and grounding behavior across
identical runs of the same question, confirmed directly by running the same
practice question twice and getting a pass, then a fail, with no code change
between runs. The next step is a regression test that runs a question
multiple times against a real client and asserts the refusal shape stays
consistent, which needs a real model in CI rather than the fake lane CI
currently uses. The full ranked list is in [docs/ISSUES.md](docs/ISSUES.md).

## How to run it

```bash
git clone https://github.com/nizalia0206/my-final-assignment && cd my-final-assignment && uv sync && uv run pytest
```

No key needed: without a `.env` it runs on the offline fake model. For a real
model, copy `.env.example` to `.env` and set `BOOTCAMP_PROVIDER=ollama` (no
key needed, needs a local Ollama server with `qwen2.5:7b-instruct` pulled), or
set `anthropic`/`openai` with the matching API key.

To hand in the final assignment, commit and push, then run
`uv run bootcamp final submit --github nizalia0206`. It runs the practice set
first, then answers the final questions and opens the pull request.
`--dry-run` shows the bundle without handing anything in.

---

| Path | What it is |
|---|---|
| `agent.py` | The agent: `YourAgent`, the class the tests, `trace` and the grader run |
| `tests/test_contract.py` | The capstone contract, as tests (`uv run pytest -k refusal`, `-k injection`, ...) |
| `data/corpus/` | The six source documents, versioned; nothing here writes to them |
| `docs/EVAL_REPORT.md` | Numbers produced, before and after, with the command behind each |
| `docs/ISSUES.md` | The ranked issue list (session 9, kept until 14) |

Built during the Dev3Pack AI Engineering bootcamp, on the course package at
commit `c6e260c93b7679448d82e1036b40c5c8952619bf` of https://github.com/Gecko-Academy/dev3pack-cohort-2026-09.