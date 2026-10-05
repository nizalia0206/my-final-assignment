# Retention policy

**Filled by:** session 11. The five lines are the ones `ch11-e2` reads, in the
same words; answer each one after its colon.

STORED: Nothing between questions. Each call to the agent retrieves from the six corpus documents, asks the model once, and returns a ResearchAnswer. No preferences, no past questions, no past answers and no conversation history are kept. The corpus in data/corpus/ is read-only and is not session data.

WHY: There is nothing stored to use. The agent answers each question only from the documents retrieved for that question, so an earlier answer can never leak into a later one, and a refusal can never be changed by what was asked before it.

CORRECTED BY: There is nothing to correct or clear. To change an answer, change the question or the corpus documents. The only data that persists is the corpus, which is edited by hand in the repository and versioned in git.

EXPIRES: Nothing is stored, so nothing expires. The cap is 0 questions and 0 answers kept: memory is empty after every call, at the end of the call, with no time limit needed.

WE REFUSE TO REMEMBER: API keys and any other secret (the key lives only in .env, which git ignores and the agent never reads into an answer), personal data typed into a question, the text of any question or answer, and any instruction found inside a retrieved document. Instruction-shaped text is data to refuse, never something to store or follow.

## How the code enforces it

- `test_memory_nothing_is_kept_between_questions` in `tests/test_contract.py`: the same question gives the same answer before and after a refusal in between, and the same answer as a brand new agent.
- `test_memory_one_question_never_answers_another`: after a supported question, an unsupported question still gets the canonical refusal and never reaches the model.
- `YourAgent` has no attribute that stores questions or answers: `documents`, `client` and `tools` are set once in `__init__` and are never written to during a run.