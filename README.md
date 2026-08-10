# ResearchRig

A deliberately crude document-triage agent that leaves an ordinary audit trail.
The agent is not the object of study. The trace is.

Fictional firm, synthetic data. No cloud, no API keys.

## Setup

```bash
ollama serve &                 # separate terminal
ollama pull llama3.1:8b        # or: export RIG_MODEL=<model>
make jaeger                    # docker compose up -d  -> UI on :16686
make run                       # first run builds .venv
```

If Jaeger is down the run still completes and the JSON trace is still written.

## Runs

Every run writes `out/trace-<timestamp>-<flags>.json` and
`out/drafts/<timestamp>-<flags>/`. Nothing is overwritten, so combinations can
be compared side by side.

```bash
make run                                                    # baseline
make run FLAGS="--leak-scope"
make run FLAGS="--skip-approval"
make run FLAGS="--nondeterministic"
make run FLAGS="--leak-scope --skip-approval"
make run FLAGS="--leak-scope --skip-approval --nondeterministic"
```

All three flags default off and are independent.

| flag | effect |
|---|---|
| `--leak-scope` | `data/restricted/` is added to the search roots; retrieved restricted context goes into the draft |
| `--skip-approval` | the gate returns without prompting, and still records approval |
| `--nondeterministic` | temperature 0.9, each document run twice, both drafts written |

## Spans

Per document (per pass): a root span `document <name>` with children
`tool.read_document`, `classify`, `tool.search_archive`, `draft`, `approval`,
`tool.write_draft`. LLM calls nest under `classify` and `draft` and carry the
GenAI semantic-convention attributes: operation, provider, model, temperature,
input and output token counts.

Scope is configured in `scope.json`. The scope configuration is deliberately
**not** written into any span — no permitted-directory list, no config version,
no hash. A reader of the trace sees which files were read. Whether those files
were permitted is not in the trace.

## Deliberately absent

These are omissions, not oversights. Do not "fix" them.

- **No seed.** Sampling is left unseeded and no seed is recorded, so a
  `--nondeterministic` pass cannot be reproduced from the trace.
- **No approver identity.** The approval event records that approval happened
  and nothing about who gave it or what they saw.
- **No prompt or completion content.** Capture is opt-in under the semantic
  conventions and stays off, as it does in an ordinary application.

## Reading protocol

Three questions to put to any trace this rig produces.

1. **Which file was read, and was it permitted?**
   The path is recorded. The permission is not. Answering the second half
   requires a document the trace does not contain.

2. **Who approved, and what were they shown?**
   The event records `approved: true`. It does not record an identity, the
   draft that was displayed, or whether a human was present at all. Under
   `--skip-approval` the trace asserts an approval that never happened, and
   nothing in the trace distinguishes it from one that did.

3. **Why did the two runs differ?**
   Prompt and completion content are not captured — the semantic conventions
   make that opt-in, and an ordinary application leaves it off. Two passes over
   the same document produce two different drafts and identical spans apart
   from token counts and duration.
