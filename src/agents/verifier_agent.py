"""Verifier Agent — schema, limits, evidence existence, null handling.

Runs last, before the coordinator writes the file. It re-derives the valid
evidence-id universe from the raw data and rejects any id that cannot be built
from a CSV row (a false positive per README section 5). It also enforces every
array cap, the confidence range, the case_status enum and timestamp format.
"""
from __future__ import annotations

import re

from ..config import LIMITS
from .base import Agent

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
VALID_PRIMARY = {
    "canceled_order_paid", "unavailable_order_paid", "late_delivery_seller",
    "late_delivery_logistics", "valid_split_payment", "unsupported_late_claim",
}


class VerifierAgent(Agent):
    name = "verifier_agent"

    def run(self, case_id, output: dict, evidence_universe: set) -> tuple:
        self.tracer.log(case_id, self.name, "dispatch")
        issues = []

        ca = output["case_assessment"]
        if ca["primary_issue"] not in VALID_PRIMARY:
            issues.append(f"bad primary_issue {ca['primary_issue']}")
        if not (0.0 <= ca["confidence"] <= 1.0):
            issues.append("confidence out of [0,1]")
        if output["case_assessment"]["case_status"] not in ("action_required", "no_action"):
            issues.append("bad case_status")

        # array caps
        for path, key in [
            (output["affected_entities"]["order_ids"], "order_ids"),
            (output["affected_entities"]["item_ids"], "item_ids"),
            (output["affected_entities"]["seller_ids"], "seller_ids"),
            (output["affected_entities"]["payment_ids"], "payment_ids"),
            (output["customer_context"]["related_order_ids"], "related_order_ids"),
            (output["product_context"]["product_ids"], "product_ids"),
            (output["product_context"]["category_names"], "category_names"),
            (output["root_cause_analysis"]["ranked_causes"], "ranked_causes"),
            (output["root_cause_analysis"]["responsible_parties"], "responsible_parties"),
            (output["evidence_ids"], "evidence_ids"),
            (output["resolution_actions"], "resolution_actions"),
        ]:
            if len(path) > LIMITS[key]:
                issues.append(f"{key} exceeds cap {LIMITS[key]}")

        # evidence existence (no false positives)
        for ev in output["evidence_ids"]:
            if ev not in evidence_universe:
                issues.append(f"evidence not in data: {ev}")

        # null handling for no-item orders
        pr = output["payment_reconciliation"]
        if pr["expected_total_brl"] is None:
            if pr["difference_brl"] is not None or pr["reconciled"] is not None:
                issues.append("null-handling: expected null but diff/reconciled not null")
            if output["delivery_analysis"]["seller_handoff_analysis"] and \
                    not output["affected_entities"]["item_ids"]:
                issues.append("no-item order should have empty seller_handoff_analysis")

        # timestamp format
        for f in ("delivered_at", "estimated_delivery_at", "carrier_handoff_at"):
            v = output["delivery_analysis"][f]
            if v is not None and not TS_RE.match(v):
                issues.append(f"bad timestamp format {f}={v}")

        # financial consistency with status
        refund = output["financial_resolution"]["recommended_refund_brl"]
        if output["case_assessment"]["case_status"] == "action_required" and not (refund and refund > 0):
            issues.append("action_required but refund <= 0")
        if output["case_assessment"]["case_status"] == "no_action" and refund:
            issues.append("no_action but refund > 0")

        ok = not issues
        self.tracer.log(case_id, self.name, "verify",
                        ok=ok, issues=issues,
                        evidence_checked=len(output["evidence_ids"]))
        self.annotate(
            case_id,
            system="You validate dispute outputs against the submission schema.",
            user=f"case {case_id}: {'PASS' if ok else 'FAIL'} ({len(issues)} issue(s)).",
            fallback_text="Schema, caps, evidence existence and null-handling checked."
            if ok else f"Validation failed: {issues}",
            fallback_conf=0.99 if ok else 0.5,
        )
        return ok, issues
