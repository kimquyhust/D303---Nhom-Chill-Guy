#!/usr/bin/env python3
"""Entry point: run the multi-agent dispute-resolution pipeline over input/.

Usage:
  python run.py                                  # deterministic-grounded run
  LLM_PROVIDER=ollama LLM_MODEL=qwen2.5:7b-instruct python run.py   # neural run
  python run.py --only EC_001 EC_002             # subset (debugging)

Writes:
  output/EC_XXX.json     one graded output per input
  logging/trace.jsonl    real trace of this run (latest run only)
  logging/metadata.json  model / params / framework / runtime
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agents.coordinator import Coordinator          # noqa: E402
from src.config import (DEFAULT_MODEL, FRAMEWORK, POLICY_GUARDRAIL,  # noqa: E402
                        LLMConfig, PATHS, resolve_param_size)
from src.data_store import get_store                     # noqa: E402
from src.llm import LLMClient                            # noqa: E402
from src.trace import Tracer                             # noqa: E402


def load_cases(only=None):
    cases = []
    for f in sorted(glob.glob(os.path.join(PATHS.input, "EC_*.json"))):
        cid = os.path.splitext(os.path.basename(f))[0]
        if only and cid not in only:
            continue
        cases.append((f, json.load(open(f, encoding="utf-8"))))
    return cases


def _policy_stats():
    """Read the freshly-written trace and summarise policy decision sources."""
    counts = {"llm": 0, "rule_fallback": 0, "guardrail": 0}
    disagreements = 0
    path = os.path.join(PATHS.logging, "trace.jsonl")
    if not os.path.exists(path):
        return counts, disagreements
    for line in open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("event") == "decision" and r.get("agent") == "policy_agent":
            counts[r.get("source", "rule_fallback")] = counts.get(r.get("source"), 0) + 1
            if r.get("rule_agreement") is False:
                disagreements += 1
    return counts, disagreements


def write_metadata(llm: LLMClient, n_cases: int, elapsed: float):
    active_model = llm.active_model if llm.active_mode == "neural" else DEFAULT_MODEL
    counts, disagreements = _policy_stats()
    meta = {
        "system": "multi-agent-ecommerce-dispute-resolution",
        "task": "K4 Day 09 - EC_POLICY_V2",
        "model": active_model,
        "declared_model": DEFAULT_MODEL,
        "parameter_size": resolve_param_size(active_model),
        "parameter_constraint": "<=10B per agent (lab rule #1)",
        "framework": FRAMEWORK,
        "provider": llm.cfg.provider,
        "reasoning_mode": llm.active_mode,
        "decision_ownership": (
            "LLM decides primary_issue via EC_POLICY_V2 reasoning over a tool-built "
            "fact sheet; tools supply all exact numbers/ids; consequences derived "
            "mechanically; deterministic rule engine used as fallback + guardrail."
        ),
        "policy_decision_sources": counts,
        "llm_vs_rule_disagreements": disagreements,
        "policy_guardrail_enforced": POLICY_GUARDRAIL,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cases": n_cases,
            "elapsed_seconds": round(elapsed, 3),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "agents": [
            "coordinator", "customer_agent", "order_product_agent",
            "payment_agent", "delivery_agent", "policy_agent", "verifier_agent",
        ],
    }
    os.makedirs(PATHS.logging, exist_ok=True)
    with open(os.path.join(PATHS.logging, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="restrict to given case ids")
    args = ap.parse_args()

    os.makedirs(PATHS.output, exist_ok=True)
    store = get_store()
    llm = LLMClient(LLMConfig())
    tracer = Tracer(os.path.join(PATHS.logging, "trace.jsonl"))
    coord = Coordinator(store, llm, tracer)

    cases = load_cases(set(args.only) if args.only else None)
    print(f"[run] provider={llm.cfg.provider} mode={llm.active_mode} "
          f"model={llm.active_model} cases={len(cases)}")

    t0 = time.time()
    for path, case in cases:
        out = coord.process(case)
        dest = os.path.join(PATHS.output, os.path.basename(path))
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
    elapsed = time.time() - t0

    tracer.close()
    write_metadata(llm, len(cases), elapsed)
    print(f"[run] wrote {len(cases)} outputs in {elapsed:.2f}s -> {PATHS.output}")
    print(f"[run] trace -> {os.path.join(PATHS.logging, 'trace.jsonl')}")


if __name__ == "__main__":
    main()
