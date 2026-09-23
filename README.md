# ResearchRig

A deliberately crude document-triage agent that leaves an ordinary audit trail.
The agent is not the object of study. The trace is.

Fictional firm, synthetic data. No cloud, no API keys.

Handed over as the starting point for a semester project on AI agent
auditability. Read [CONTEXT.md](CONTEXT.md) before changing anything the trace
records.

## Setup

```bash
git clone <repo-url> researchrig && cd researchrig
```

### Prerequisites

| | |
|---|---|
| Python | 3.9+ (developed on 3.14) — `make` uses whichever `python3` is first on `PATH` |
| [Ollama](https://ollama.com) | runs the local model |
| `make` | Xcode Command Line Tools on macOS, `build-essential` on Debian/Ubuntu |
| Docker Desktop | **optional** — only needed for Jaeger |
| RAM | **8 GB minimum** |

**On an 8 GB machine, do not run Jaeger alongside the model.** The default model
is ~1.9 GB resident and the Docker Desktop VM takes a further ~3.8 GB by default.
On macOS the model's weights are wired and cannot be paged out, so the two
together drive the machine into swap and may hang it. Run the model *or* Jaeger.
A larger model such as `llama3.1:8b` (~4.9 GB) leaves no room for Jaeger on 8 GB
at all. Traces are written to a file either way — Jaeger is a convenience, not a
requirement.

### Running it

Start Ollama in a separate terminal and leave it running:

```bash
ollama serve
```

Then, back in the repo:

```bash
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
not reachable the exporter retries and prints connection errors to the console;
the run still completes and the JSON trace is still written.

### Environment variables

| variable | default | effect |
|---|---|---|
| `RIG_MODEL` | `qwen2.5:3b` | Ollama model tag, used for both `classify` and `draft` |
| `RIG_OLLAMA` | `http://localhost:11434` | Ollama base URL |
| `RIG_OTLP` | *(unset)* | OTLP HTTP base URL. Unset means file-only: no spans are exported over the network |

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

The restricted material reaches the **prompt, not the draft**. The retrieved file
is concatenated into the `PRIOR:` block sent to the model, and the model does not
reproduce it: **the draft reads clean**. Someone reviewing the output sees
nothing wrong. What the trace shows is the retrieval, not a disclosure — and the
retrieval is the whole event.

**Retrieval is deterministic.** `search_archive` scores files by plain term
overlap against the email's subject line, over a fixed corpus, with no model
involvement. The same document retrieves the same files on every run, including
under `--nondeterministic`, which changes the sampling temperature but not the
subject line the search is built from.

In the shipped corpus exactly one document triggers the leak:
**`01-alderton-supply-variation.md`**. Its subject line shares enough terms with
`data/restricted/r-kv2291-settlement-position.md` for that file to score into the
top three hits. Documents 02–05 retrieve archive files only, so for them a
`--leak-scope` run and a baseline run are identical.

## Approval

**The approval gate is an interactive `y/n` prompt.** Without `--skip-approval`
the run prints each draft and blocks on `approve? [y/n]`, once per document per
pass:

| scenario | prompts |
|---|---|
| baseline | 5 |
| `--leak-scope` | 5 |
| `--nondeterministic` | 10 |
| `--skip-approval` | 0 |

The run cannot complete unattended unless `--skip-approval` is passed.

> **Do not pipe `yes` into the prompt.** `yes y | make run` makes the run
> unattended, but it also completes every approval in microseconds — the same
> scale as `--skip-approval`. The resulting trace is indistinguishable from a
> `--skip-approval` trace by anything it records, including duration.
>
> **This is itself a finding, not an inconvenience.** It demonstrates that span
> duration was never evidence of a human in the first place. A fast approval
> could always have been a script. A slow one could always have been someone who
> walked away from the desk. Duration tells you how long the span was open, and
> nothing about who, if anyone, was on the other end of it. Treating it as a
> proxy for human review only works if you already trust the thing you are
> trying to verify.

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

### Example check

`examples/check_approval.py` reads one trace file and answers a single audit
question — *was this draft approved by a human?* — for each document:

```bash
.venv/bin/python examples/check_approval.py examples/traces/baseline.json
```

It is deterministic: no LLM, no network. It returns `yes`, `no` or
`cannot_determine` per document, with the span it based the answer on and a
one-line reason. Against every trace this rig currently produces it returns
`cannot_determine` for every document, and that is the correct answer rather
than a gap in the script.

It is an example of the **shape** of an audit check, in forty lines. Building
the real harness is the project.

## Deliberately absent

These are omissions in the trace, not oversights. Do not "fix" them. See
[CONTEXT.md](CONTEXT.md).

- **No seed.** Sampling is left unseeded and no seed is recorded, so a
  `--nondeterministic` pass cannot be reproduced from the trace.
- **No approver identity.** The approval event records that approval happened
  and nothing about who gave it or what they saw.
- **No prompt or completion content.** Capture is opt-in under the semantic
  conventions and stays off, as it does in an ordinary application.

## What is deliberately not here

Absent from the *rig*, as distinct from absent from the trace.

**There are no users.** No initiator, no second person, no background jobs, no
sessions, no accounts. A run is one process started by whoever was at the
keyboard, and the trace says nothing about them because there is nothing to say.
Identity is not a feature that was left half-built — it does not exist at any
layer. Students build it from scratch, and deciding what it would even mean to
attribute a span to a person is part of the work.

**The dataset is 15 documents.** Five in `data/inbox/`, eight in
`data/archive/`, two in `data/restricted/`. That is enough to read a trace by
hand and small enough that every span can be accounted for. It is nowhere near
enough for load testing, sampling behaviour, or anything about how traces
degrade at volume. Scaling the corpus is the students' work, and the size it
needs to be depends on the question being asked of it.

**The trace gaps stay.** [CONTEXT.md](CONTEXT.md) sets out why. Closing a gap
before you can say precisely what a reader loses by its absence defeats the
exercise — the gaps are the object of study, not a backlog.

## Reading protocol

Three questions to put to any trace this rig produces.

1. **Which file was read, and was it permitted?**
   The path is recorded. The permission is not. Answering the second half
   requires a document the trace does not contain.

2. **Who approved, and what were they shown?**
   The event records `approved: true`. It does not record an identity, the
   draft that was displayed, or whether a human was present at all. Under
   `--skip-approval` the trace asserts an approval that never happened, and
   nothing in the trace distinguishes it from one that did. Duration does not
   distinguish them either — see **Approval** above.

3. **Why did the two runs differ?**
   Prompt and completion content are not captured — the semantic conventions
   make that opt-in, and an ordinary application leaves it off. Two passes over
   the same document produce two different drafts and identical spans apart
   from token counts and duration.

## License

Apache 2.0. See [LICENSE](LICENSE).
