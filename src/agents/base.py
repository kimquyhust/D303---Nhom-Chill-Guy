"""Shared agent scaffolding: tool-call tracing + grounded LLM annotation."""
from __future__ import annotations

from typing import Any, Callable

from ..config import LLM_ANNOTATE
from ..llm import LLMClient, LLMResult
from ..trace import Tracer


class Agent:
    name = "agent"

    def __init__(self, store, llm: LLMClient, tracer: Tracer):
        self.store = store
        self.llm = llm
        self.tracer = tracer

    def call_tool(self, case_id: str, tool: str, fn: Callable[[], Any], **args) -> Any:
        """Run a deterministic tool and record it in the trace."""
        self.tracer.log(case_id, self.name, "tool_call", tool=tool, args=args)
        result = fn()
        self.tracer.log(case_id, self.name, "tool_result", tool=tool,
                        summary=_summarise(result))
        return result

    def annotate(self, case_id: str, system: str, user: str,
                 fallback_text: str, fallback_conf: float):
        """Attach a grounded rationale/confidence suggestion to the trace.
        Skips the neural call when LLM_ANNOTATE is disabled (quota saving)."""
        if LLM_ANNOTATE:
            res = self.llm.assess(system, user, fallback_text, fallback_conf)
        else:
            res = LLMResult(fallback_text, round(float(fallback_conf), 2),
                            "rule_based", "rule-based-reasoner")
        self.tracer.log(case_id, self.name, "llm_call", mode=res.mode,
                        model=res.model, rationale=res.text, confidence=res.confidence)
        return res

    def handoff(self, case_id: str, to: str, finding: dict) -> None:
        self.tracer.log(case_id, self.name, "handoff", to=to,
                        keys=sorted(finding.keys()))


def _summarise(result: Any) -> Any:
    """Compact a tool result for the trace (avoid dumping big row lists)."""
    if isinstance(result, dict):
        out = {}
        for k, v in result.items():
            if isinstance(v, list):
                out[k] = f"[{len(v)} items]" if v and isinstance(v[0], dict) else v
            else:
                out[k] = v
        return out
    return result
