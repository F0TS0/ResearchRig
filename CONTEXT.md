# CONTEXT.md

Read this before changing anything in this repo.

## What this is

A research rig, not a product. It exists to study the gap between what an
AI agent's audit trail records and what can actually be proven from it
afterwards. The agent is a prop. The trail is the object of study.

A document triage agent runs over synthetic client emails in a fictional
professional services firm: reads a file, classifies it, searches an
archive for context, drafts a response, passes an approval gate, writes
the draft. Local model via Ollama. OpenTelemetry spans, written to a JSON
file per run.

Three deviations are runtime flags, default off:

    --leak-scope        archive search reaches into data/restricted/
    --skip-approval     approval gate short-circuits, draft written anyway
    --nondeterministic  raised temperature, each document run twice

## What it is deliberately bad at

The instrumentation is exactly as thorough as a normal application's and
no more. That is the point. The following are NOT bugs and must NOT be
"improved" without an explicit instruction from the supervisor:

- No session ID, run ID, or initiator identity. Each document gets its own
  trace_id with no linking span. The only accidental correlator is
  service.instance.id, which is a process attribute and would not survive
  a long-lived or multi-tenant process.
- The approval span records only `approved: true`. No approver identity, no
  record of what was shown, no reference to which draft version was
  approved. Under --skip-approval the trail asserts an approval that never
  happened.
- No prompt or completion content on the LLM spans. GenAI semconv makes
  content capture opt-in and off by default; a normal application leaves it
  off. No seed is recorded either.
- The scope config is never written into a span: no permitted list, no
  path, no version, no hash. A reader sees which file was touched but
  cannot tell whether it was in scope. This omission is deliberate and
  load-bearing.
- Which flags were active is nowhere in the trail. It survives only in the
  output directory name.
- `document.classification` looks like a decision but is not causal: the
  subsequent search query is byte-identical across two runs that classified
  the same document differently.

Every one of these is a finding. Fixing them silently destroys the research
value of the rig.

## A note on span duration

Under --skip-approval the approval span completes in microseconds, and it
is tempting to treat that as the tell that no human was involved. Do not
build on it. A fast approval could always have been a script, and a slow
one could be a person who walked away from the desk. Duration was never
evidence of human oversight; it is a coincidence of how a particular run
was driven. Piping `yes` into the interactive prompt removes even that
coincidence, which is why the README tells you not to.

## Findings already established

Run and read from the committed traces regenerated on 23 September 2026 with
qwen2.5:3b and OpenTelemetry 1.44.0. The exact Ollama version and model digest
were not recorded:

1. Initiator is unrecoverable. No correlating structure exists.
2. The trail asserts a human approval that did not occur, and nothing in
   the recorded schema contradicts it.
3. The scope leak does not move any metric. result_count is 3 either way,
   because the restricted document displaces a permitted one rather than
   adding to the set. Visible only as one string in tool.result_paths, and
   indirectly as roughly 20 extra input tokens on the draft call.
4. Two passes over the same document produced contradictory classifications
   with no recorded basis, and the recorded decision did not change what the
   agent did next.

## What this rig is for

It is the starting point for a student project. The work to be built, which
is NOT to be pre-built here, is:

- delegated identity carried through the whole chain, including
  asynchronous execution hours later
- three independent audit-trail approaches running over the same executions
- a deterministic harness that reads a trail and answers each audit question
  yes or no with a pointer to the supporting record
- running it at scale: hundreds of documents, concurrent agents, one
  approver approving several things at once

The harness must be deterministic code. A language model must never be used
to judge a trail. A nondeterministic judge produces an opinion, not
evidence.

`examples/check_approval.py` shows the shape of a single check and nothing
more. It answers one question against one trace file and currently returns
`cannot_determine` for every document, including clean runs. That verdict is
reached, not hardcoded: flip `approved` to false in a trace and it returns
`no`. There is no reachable path to `yes` with the current span schema. That
is the finding, not an unfinished branch.

## Working rules

- Keep agent.py small, roughly 200 lines. Crude keyword search, one-word
  classification with a fallback, no retries, no cleverness.
- Never overwrite trace or draft output; both are timestamped and
  flag-tagged per run. Existing output is evidence.
- Do not add trace analysis, scoring, diffing or detectability checks to
  this repo beyond the single example. Reading the trail is the project's
  work, not the rig's.
- No cloud APIs, no keys, no web UI, no second backend.
- All data is synthetic. No real organisation's processes, documents or
  configuration appear anywhere.
