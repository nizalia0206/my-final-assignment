# ADR 0001: the shape of one run

**Filled by:** session 10, for the choice you measured in session 8 (chain,
loop or graph, and the model calls each one cost). The four fields are the
ones `ch10-e2` reads.

- Status: accepted
- Date: 2026-10-05

## Context

The assignment budget is one model call per question, plus one corrective
retry if the JSON does not parse. The agent also has to refuse unsupported
questions, and do it the same way every time. I compared the same task as
three shapes:

- chain (retrieve, one model call, deterministic checks): 1 call per
  answered question, 0 calls per refused question (the relevance floor
  and the empty-retrieval refusal never reach the model);
- loop (the model may call read-only tools up to 3 times): up to 4 calls per
  question, since `max_tool_calls=3` allows three tool rounds before the
  final answer. This is the bound the setting allows, not a count I measured
  separately;
- graph (separate nodes for retrieve, draft, verify): 2 calls per answered
  question, the draft plus the verifier. This follows from the design, not
  from a separate measurement.

The failures I saw were not about how many steps the model took. They were
about what came back: citations or confidence on a refusal, and answers
missing concepts the cited document states. Deterministic code after the
model fixed those without extra model calls.

## Decision (`decision`)

We keep the chain in `agent.py`: one model call per question, followed by
deterministic checks, instead of adding a loop or a verifier node.

## Options considered (`options_considered`)

1. A chain: relevance floor, one model call, then code that enforces the
   refusal shape, makes the answer extractive from the cited sections, and
   flags injected text.
2. A graph with a second, model-based verifier node that checks each claim
   against the cited text.

## Why not the other option (`why_not`)

The verifier would cost a second model call on every answered question,
which is over the one-call budget, and it would add another run-to-run
variance source on a local 7B model that already scores differently on
identical runs. The measured failures (a refusal that kept its citations,
an answer that missed required concepts) were fixed by plain code at zero
extra calls, so the extra call buys nothing today.

## What would reverse it (`reverses_it`)

We would add the verifier node when the code checks leave 3 or more of the
7 grounded and adversarial practice cases failing `claim_support` on each of
3 consecutive `uv run bootcamp final grade` runs, and a prototype verifier
raises the practice score by at least 10 percentage points. We would also
revisit the chain if the course raises the budget above 1 call per question.