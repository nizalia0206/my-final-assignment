# my-final-assignment

A research assistant that answers developer questions from six source documents on RAG, agents, and MCP, citing the exact document it drew from — and refuses, in the same recognizable words every time, when those documents do not support an answer.

## The problem

A developer learning agent architecture has to piece together scattered advice on retrieval, tool design, structured outputs, and prompt injection from many sources, with no way to check whether an answer is actually grounded in something real or just sounds plausible. This agent answers only from a fixed, inspectable set of documents, and says so plainly when a question falls outside them — rather than confidently guessing.

## Demo

Two runs, pasted as the commands printed them. `trace` prints every step the
agent took, then the answer. Both ran on the local model (ollama,
qwen2.5:7b-instruct).

### One supported answer

```bash
uv run bootcamp final trace "How does chunking work in RAG?"
```

```text
[retrieve] top_k=3 -> [('rag-basics', 1), ('rag-basics', 2), ('rag-basics', 0)]
[llm_call] attempt 1: 260 chars
[decision] answered with citations ['rag-basics']
[decision] answer made extractive from cited sentences

answer: A minimal RAG pipeline has four stages. Chunking splits documents into passages small enough to be individually relevant — respecting paragraph boundaries beats cutting at a fixed character count mid-sentence. Indexing prepares chunks for search; a lexical index (keyword overlap) is a perfectly respectable baseline and is deterministic, cheap, and debuggable. When a RAG system answers wrongly, the first diagnostic question is: did the right passage reach the prompt? If retrieval missed it, no amount of prompt engineering will fix the answer — fix chunking, the index, or the query instead.
citations: ['rag-basics']
confidence: 0.6
needs_human_review: False
```

### One refusal

```bash
uv run bootcamp final trace "What is the capital city of Mongolia?"
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
Past the course's own pipeline, `YourAgent` adds deterministic code around
that one call, at zero extra model calls:

- a relevance floor that refuses weak-retrieval questions before the model;
- a timeout/error guard, so a hung or broken provider becomes a flagged
  refusal instead of a crash or an unbounded wait;
- a retrieval dominance filter that narrows to one document when its best
  chunk clearly outscores every other document's best chunk;
- one canonical refusal shape, enforced in code on every path;
- an extractive grounding step: the answer is rebuilt from sentences of the
  cited text, plus the whole section whose heading matches the question, and
  the citations are narrowed to the documents those sentences came from;
- a flag when a retrieved passage looks like an instruction. Instruction-shaped
  sentences never count as support.

See [docs/adr/0001-run-shape.md](docs/adr/0001-run-shape.md).

## Measured results

Every number here comes from a command in this table, run on this code. Say
which model produced it: CI has no keys, so a CI number is always the offline
fake model's.

| What | Command | Model | Result |
|---|---|---|---|
| Contract tests | `uv run pytest` | fake | `10 passed` |
| Practice grader | `uv run bootcamp final grade` | fake | `score: 3/10 (30%) — critical safety gate failed` |
| Practice grader | `uv run bootcamp final grade` | ollama, qwen2.5:7b-instruct | `score: 6/10 (60%) — critical safety gate failed` (before the section-aware step) |
| Practice grader | `uv run bootcamp final grade` | ollama, qwen2.5:7b-instruct | `score: 9/10 (90%) — pass bar 30% — PASSED`, all 5 critical cases passing; fa-02 fails `claim_support`. Two runs on this code, both 9/10 with the same fa-02 failure |
| Evaluation, before and after | see [docs/EVAL_REPORT.md](docs/EVAL_REPORT.md) | fake vs. ollama | 30% → 60% → 90% |

The practice report is not credential evidence. The private set has different
questions, so a 90% practice score does not predict the private score.

## The honest limitation

Two limits, both in [docs/ISSUES.md](docs/ISSUES.md).

The practice grader's `claim_support` checks that required concept phrases
appear in the answer, not that the answer is a good summary. The agent covers
list questions by adding the whole section whose heading matches the question.
A question whose answer is spread over several sections, or whose heading
shares no words with it, does not get a section added, and the private set has
different required concepts. fa-02 is a practice case that still fails for
this kind of reason.

The local model also gives different answers across identical runs, so every
score here is reported with the model that produced it. The next step is a
regression test that runs a question several times against a real client,
which needs a real model in CI rather than the fake lane CI uses today.

**Rollback:** if a change lowers the practice score or fails a critical case,
`git revert` the commit and push. The corpus is read-only, so nothing needs
restoring.

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
| `docs/adr/0001-run-shape.md` | The decision record for the shape of one run |
| `docs/RETENTION.md` | What a session stores (nothing) and what it refuses to remember |
| `docs/SKILL.md` | The agent as a skill another assistant can load, with before and after runs |

Built during the Dev3Pack AI Engineering bootcamp, on the course package at
commit `c6e260c93b7679448d82e1036b40c5c8952619bf` of https://github.com/Gecko-Academy/dev3pack-cohort-2026-09.