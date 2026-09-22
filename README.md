# ResearchRig

A deliberately crude document-triage agent that leaves an ordinary audit trail.
The agent is not the object of study. The trace is.

Fictional firm, synthetic data. No cloud, no API keys.

## Prerequisites

| | |
|---|---|
| `git` | to clone |
| Python | 3.9+ (developed on 3.14) — `make` uses whichever `python3` is first on `PATH` |
| [Ollama](https://ollama.com) | runs the local model |
| `make` | Xcode Command Line Tools on macOS, `build-essential` on Debian/Ubuntu |
| Docker Desktop | **optional** — only needed for Jaeger |
| RAM | **8 GB minimum** |

**On an 8 GB machine, do not run Jaeger and the model at the same time.**
The default model is ~1.9 GB resident and the Docker Desktop VM takes a further
~3.8 GB by default; on macOS the model's weights are wired and cannot be paged
out, so the two together will drive the machine into swap and may hang it. Run
the model *or* Jaeger. A larger model such as `llama3.1:8b` (~4.9 GB) does not
leave room for Jaeger on 8 GB at all. Traces are written to a file either way —
Jaeger is a convenience, not a requirement.

## Setup

```bash
git clone <repo-url> researchrig && cd researchrig
ollama serve                   # separate terminal, leave running
ollama pull qwen2.5:3b         # or: export RIG_MODEL=<model>
make run                       # first run builds .venv
```

By default the run writes its trace to a file only. Nothing is sent over the
network and no exporter errors are printed.

### Jaeger (optional)

```bash
make jaeger                            # docker compose up -d  -> UI on :16686
export RIG_OTLP=http://localhost:4318
make run
```

Spans are sent to Jaeger only when `RIG_OTLP` is set. If it is set and Jaeger is
not reachable, the exporter retries and prints connection errors to the console;
the run still completes and the JSON trace is still written.

### Environment variables

| variable | default | effect |
|---|---|---|
| `RIG_MODEL` | `qwen2.5:3b` | Ollama model tag used for both `classify` and `draft` |
| `RIG_OLLAMA` | `http://localhost:11434` | Ollama base URL |
| `RIG_OTLP` | *(unset)* | OTLP HTTP base URL. Unset means file-only; no spans are exported over the network |

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

`make clean` removes `out/drafts/` only. Traces are left in place so runs stay
comparable after a clean.

| flag | effect |
|---|---|
| `--leak-scope` | `data/restricted/` is added to the search roots; retrieved restricted context goes into the **prompt** |
| `--skip-approval` | the gate returns without prompting, and still records approval |
| `--nondeterministic` | temperature 0.9, each document run twice, both drafts written |

### About `--leak-scope`

The restricted material reaches the **prompt**, not necessarily the draft. The
retrieved file is concatenated into the `PRIOR:` block sent to the model; whether
any of it is reproduced in the generated reply is up to the model, and usually it
is not. What the trace shows is the retrieval, not the disclosure.

In the shipped corpus only **`01-alderton-supply-variation.md`** triggers the
leak. Its subject line shares enough terms with
`data/restricted/r-kv2291-settlement-position.md` for that file to score into the
top three hits. The other four documents retrieve archive files only, so a run
with `--leak-scope` looks identical to a baseline run for documents 02–05.

## Approval

**The approval gate is interactive.** Without `--skip-approval` the run prints
each draft and blocks on `approve? [y/n]` — once per document per pass. That is
5 prompts for a baseline or `--leak-scope` run, and 10 for `--nondeterministic`.
The run cannot complete unattended.

> **Do not pipe `yes` into the prompt.** `yes y | make run` makes the run
> unattended, but it also collapses the approval span's duration to the same
> microsecond scale as `--skip-approval`. The one signal in the trace that might
> have distinguished a human reading a draft from a gate that never prompted —
> how long `approval` took — is destroyed, and the resulting trace is
> indistinguishable from a `--skip-approval` trace by any attribute it records.
> If a run needs to be unattended, use `--skip-approval` and be honest about it.

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

### Sample traces

`examples/traces/` holds one committed trace per scenario — `baseline.json`,
`leak-scope.json`, `skip-approval.json`, `nondeterministic.json` — so the
reading protocol below can be worked through without running anything. All four
were produced with `qwen2.5:3b`.

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
   nothing in the trace distinguishes it from one that did. Span duration is the
   only remaining tell, and piping `yes` into a genuine run removes even that.

3. **Why did the two runs differ?**
   Prompt and completion content are not captured — the semantic conventions
   make that opt-in, and an ordinary application leaves it off. Two passes over
   the same document produce two different drafts and identical spans apart
   from token counts and duration.

## License

Apache 2.0. See [LICENSE](LICENSE).
