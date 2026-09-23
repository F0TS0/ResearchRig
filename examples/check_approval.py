#!/usr/bin/env python3
# Example audit check. This is the SHAPE of a check, not a solution --
# students build the real harness. Deterministic: no LLM, no network.
# Question: "Was this draft approved by a human?" Against the traces this
# rig produces the answer is cannot_determine for every document, and that
# is the correct answer, not a missing feature.
# The trace records no approver identity, and span duration is not evidence
# of a human -- see README, "Approval".
import json, sys
from pathlib import Path


def check(spans):
    kids = {}
    for s in spans:
        kids.setdefault(s["parent_id"], []).append(s)
    for root in (s for s in spans if s["name"].startswith("document ")):
        a = root["attributes"]
        gate = next((c for c in kids.get(root["context"]["span_id"], [])
                     if c["name"] == "approval"), None)
        if gate is None:
            yield a["document.name"], a["document.pass"], "no", \
                root["context"]["span_id"], "no approval span under this document"
            continue
        sid = gate["context"]["span_id"]
        ev = next((e for e in gate.get("events") or []
                   if e["name"] == "approval"), None)
        if ev is None or not ev["attributes"].get("approved"):
            yield a["document.name"], a["document.pass"], "no", sid, \
                "approval event absent, or approved=false"
        else:
            yield a["document.name"], a["document.pass"], "cannot_determine", sid, \
                "approved=true, but no approver identity is recorded " \
                "and duration is not evidence of a human"


if __name__ == "__main__":
    for doc, p, verdict, span, why in check(json.loads(Path(sys.argv[1]).read_text())):
        print(f"{doc} pass {p}: {verdict}\n    span {span}: {why}")
