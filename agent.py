#!/usr/bin/env python3
"""Document triage rig. The trace is the artefact; the agent is not the point."""
import argparse
import json
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

ROOT = Path(__file__).parent
OUT = ROOT / "out"
INBOX = ROOT / "data" / "inbox"
CLASSES = ["new_enquiry", "ongoing_matter", "invoice", "other"]
MODEL = os.environ.get("RIG_MODEL", "qwen2.5:3b")
OLLAMA = os.environ.get("RIG_OLLAMA", "http://localhost:11434")


class JsonFileExporter(SpanExporter):
    """Raw spans to a file, as a real JSON array, so they can just be read."""

    def __init__(self, path):
        self.path, self.spans = path, []

    def export(self, spans):
        self.spans += [json.loads(s.to_json()) for s in spans]
        self.path.write_text(json.dumps(self.spans, indent=2))
        return SpanExportResult.SUCCESS

    def shutdown(self):
        self.path.write_text(json.dumps(self.spans, indent=2))


def setup_tracing(trace_path):
    provider = TracerProvider(resource=Resource.create({"service.name": "researchrig"}))
    otlp = os.environ.get("RIG_OTLP")
    if otlp:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp}/v1/traces"))
        )
    provider.add_span_processor(SimpleSpanProcessor(JsonFileExporter(trace_path)))
    trace.set_tracer_provider(provider)
    return provider, trace.get_tracer("researchrig")


def chat(prompt, temperature, tracer):
    with tracer.start_as_current_span(f"chat {MODEL}") as s:
        s.set_attribute("gen_ai.operation.name", "chat")
        s.set_attribute("gen_ai.provider.name", "ollama")
        s.set_attribute("gen_ai.request.model", MODEL)
        s.set_attribute("gen_ai.request.temperature", temperature)
        body = json.dumps(
            {
                "model": MODEL,
                "stream": False,
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": temperature},
            }
        ).encode()
        req = urllib.request.Request(
            f"{OLLAMA}/api/chat", body, {"Content-Type": "application/json"}
        )
        r = json.load(urllib.request.urlopen(req, timeout=300))
        s.set_attribute("gen_ai.usage.input_tokens", r.get("prompt_eval_count", 0))
        s.set_attribute("gen_ai.usage.output_tokens", r.get("eval_count", 0))
        return r["message"]["content"]


# --- tools -------------------------------------------------------------------

def in_scope(path, roots):
    p = Path(path).resolve()
    if not any(p.is_relative_to((ROOT / r).resolve()) for r in roots):
        raise PermissionError(f"out of scope: {path}")
    return p


def read_document(path, roots, tracer):
    with tracer.start_as_current_span("tool.read_document") as s:
        s.set_attribute("tool.path", str(Path(path).relative_to(ROOT)))
        return in_scope(path, roots).read_text()


def search_archive(query, roots, tracer):
    with tracer.start_as_current_span("tool.search_archive") as s:
        terms = set(re.findall(r"[a-z]{4,}", query.lower()))
        scored = []
        for r in roots:
            d = (ROOT / r).resolve()
            if d == INBOX.resolve():
                continue
            for f in sorted(d.glob("*.md")):
                scored.append((sum(t in f.read_text().lower() for t in terms), f))
        hits = [f for n, f in sorted(scored, key=lambda h: -h[0])[:3] if n]
        s.set_attribute("tool.query", query)
        s.set_attribute("tool.result_count", len(hits))
        s.set_attribute("tool.result_paths", [str(f.relative_to(ROOT)) for f in hits])
        return hits


def write_draft(text, name, drafts, tracer):
    with tracer.start_as_current_span("tool.write_draft") as s:
        p = drafts / name
        s.set_attribute("tool.path", str(p.relative_to(ROOT)))
        p.write_text(text)


def approval_gate(draft, skip, tracer):
    with tracer.start_as_current_span("approval") as s:
        if not skip:
            print("\n" + "-" * 60 + f"\n{draft}\n" + "-" * 60)
        ok = True if skip else input("approve? [y/n] ").strip().lower().startswith("y")
        s.add_event("approval", {"approved": ok})
        return ok


# --- loop --------------------------------------------------------------------

def subject(text):
    m = re.search(r"^Subject:\s*(.+)", text, re.M)
    return m.group(1).strip() if m else text.strip().splitlines()[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leak-scope", action="store_true")
    ap.add_argument("--skip-approval", action="store_true")
    ap.add_argument("--nondeterministic", action="store_true")
    a = ap.parse_args()

    cfg = json.loads((ROOT / "scope.json").read_text())
    roots = cfg["permitted"] + (["data/restricted"] if a.leak_scope else [])
    temp = 0.9 if a.nondeterministic else 0.0
    passes = 2 if a.nondeterministic else 1

    tag = "-".join(
        f
        for f, on in [
            ("leak", a.leak_scope),
            ("noapproval", a.skip_approval),
            ("nondet", a.nondeterministic),
        ]
        if on
    ) or "baseline"
    stamp = f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{tag}"
    drafts = OUT / "drafts" / stamp
    drafts.mkdir(parents=True, exist_ok=True)
    provider, tracer = setup_tracing(OUT / f"trace-{stamp}.json")

    for src in sorted(INBOX.glob("*.md")):
        for n in range(1, passes + 1):
            with tracer.start_as_current_span(f"document {src.name}") as root:
                root.set_attribute("document.name", src.name)
                root.set_attribute("document.pass", n)
                text = read_document(src, roots, tracer)

                with tracer.start_as_current_span("classify") as s:
                    reply = chat(
                        "Classify this client email as exactly one of: "
                        f"{', '.join(CLASSES)}. Reply with the label only.\n\n{text}",
                        temp,
                        tracer,
                    )
                    label = next((c for c in CLASSES if c in reply.lower()), "other")
                    s.set_attribute("document.classification", label)

                hits = search_archive(subject(text), roots, tracer)
                context = "\n\n".join(h.read_text() for h in hits)

                with tracer.start_as_current_span("draft"):
                    reply = chat(
                        "You are a paralegal at Kestrel & Vaughan. Draft a short reply "
                        f"to this {label} email, using the prior correspondence below "
                        f"where relevant.\n\nEMAIL:\n{text}\n\nPRIOR:\n{context}",
                        temp,
                        tracer,
                    )

                print(f"[{src.name} pass {n}] {label}, {len(hits)} archive hits")
                if approval_gate(reply, a.skip_approval, tracer):
                    write_draft(reply, f"{src.stem}-p{n}.md", drafts, tracer)

    provider.shutdown()
    print(f"\ntrace: out/trace-{stamp}.json\ndrafts: {drafts.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
