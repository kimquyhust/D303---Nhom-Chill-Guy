"""Policy Agent — applies EC_POLICY_V2 (hybrid, LLM-driven).

Decision ownership (per the team's design choice):
  * The <=10B MODEL makes the core judgment: it reads a fact sheet produced by
    the deterministic tools and returns the `primary_issue` (and a confidence)
    by reasoning over the EC_POLICY_V2 priority table given in its system prompt.
  * The TOOLS supply every exact number/id: date/hour variances, money totals,
    counts and objective flags (delivered_late, reconciled, late_handoff). The
    model never does raw arithmetic, so a 7-8B model cannot corrupt the figures.
  * From the model's `primary_issue`, the mechanical consequences (refund amount,
    responsible ids, evidence ids, root-cause code, action ordering, secondary
    flags) are derived deterministically — these are lookups over tool facts,
    not business judgments.
  * A deterministic rule engine is kept as (a) FALLBACK when no endpoint is
    reachable or the model reply is invalid, and (b) a GUARDRAIL that is logged
    (and optionally enforced) so the team can measure the model's accuracy.

Priority order of primary issues (README section 4):
  1 canceled_order_paid      2 unavailable_order_paid
  3 late_delivery_seller     4 late_delivery_logistics
  5 valid_split_payment      6 unsupported_late_claim
"""
from __future__ import annotations

from ..config import POLICY_GUARDRAIL
from .base import Agent

PLATFORM = ("platform", "OLIST_PLATFORM")
LOGISTICS = ("logistics_provider", "LOGISTICS_PROVIDER")

VALID_PRIMARY = [
    "canceled_order_paid", "unavailable_order_paid", "late_delivery_seller",
    "late_delivery_logistics", "valid_split_payment", "unsupported_late_claim",
]
ROOT_CAUSE = {
    "canceled_order_paid": "ORDER_CANCELED_AFTER_PAYMENT",
    "unavailable_order_paid": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "late_delivery_seller": "SELLER_HANDOFF_AFTER_LIMIT",
    "late_delivery_logistics": "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "valid_split_payment": "MULTIPLE_PAYMENTS_RECONCILED",
    "unsupported_late_claim": "DELIVERY_WITHIN_ESTIMATE",
}
PRIMARY_ACTION = {
    "canceled_order_paid": "issue_full_refund",
    "unavailable_order_paid": "issue_full_refund",
    "late_delivery_seller": "refund_freight",
    "late_delivery_logistics": "refund_freight",
    "valid_split_payment": "explain_valid_split_payment",
    "unsupported_late_claim": "reject_late_refund",
}
CONFIDENCE = {
    "canceled_order_paid": 0.98, "unavailable_order_paid": 0.98,
    "late_delivery_seller": 0.95, "late_delivery_logistics": 0.9,
    "valid_split_payment": 0.96, "unsupported_late_claim": 0.92,
}

POLICY_SYSTEM = (
    "You are the Policy Agent in an e-commerce dispute system. Apply policy "
    "EC_POLICY_V2 and pick exactly ONE primary_issue by STRICT PRIORITY (first "
    "match wins):\n"
    "1 canceled_order_paid: order_status=canceled AND total_payment>0.\n"
    "2 unavailable_order_paid: order_status=unavailable AND total_payment>0.\n"
    "3 late_delivery_seller: delivered_late=true AND at least one seller in "
    "late_handoff_seller_ids.\n"
    "4 late_delivery_logistics: delivered_late=true AND no late-handoff seller.\n"
    "5 valid_split_payment: n_payments>=2 AND reconciled=true.\n"
    "6 unsupported_late_claim: otherwise (on-time and payment matches).\n"
    "IMPORTANT reminders (common mistakes):\n"
    "- If order_status is 'unavailable' or 'canceled' and paid=True, ALWAYS pick "
    "rule 1/2 — never unsupported_late_claim.\n"
    "- If not canceled/unavailable and delivered_late=False and n_payments>=2 and "
    "reconciled=True, pick valid_split_payment — never unsupported_late_claim.\n"
    "- unsupported_late_claim is ONLY for an on-time single-or-reconciled order with "
    "no split and no cancellation.\n"
    "Use ONLY the provided facts; do not invent data. Do not compute money."
)


class PolicyAgent(Agent):
    name = "policy_agent"

    # -------------------------------------------------- deterministic engine #
    @staticmethod
    def _rule_primary(facts: dict) -> str:
        if facts["order_status"] == "canceled" and facts["paid"]:
            return "canceled_order_paid"
        if facts["order_status"] == "unavailable" and facts["paid"]:
            return "unavailable_order_paid"
        if facts["delivered_late"] and facts["late_handoff_seller_ids"]:
            return "late_delivery_seller"
        if facts["delivered_late"]:
            return "late_delivery_logistics"
        if facts["n_payments"] >= 2 and facts["reconciled"] is True:
            return "valid_split_payment"
        return "unsupported_late_claim"

    # ------------------------------------------------------------ LLM branch #
    def _llm_primary(self, case_id: str, facts: dict):
        user = (
            "FACTS (all values computed by deterministic tools):\n"
            f"- order_status: {facts['order_status']}\n"
            f"- total_payment_brl: {facts['payment_total']} (paid={facts['paid']})\n"
            f"- delivered_late: {facts['delivered_late']} "
            f"(delivery_variance_hours={facts['delivery_variance_hours']})\n"
            f"- late_handoff_seller_ids: {facts['late_handoff_seller_ids']}\n"
            f"- n_payments: {facts['n_payments']}, reconciled: {facts['reconciled']}\n"
            f"- n_items: {facts['n_items']}, n_sellers: {facts['n_sellers']}, "
            f"n_categories: {facts['n_categories']}\n\n"
            'Respond ONLY as JSON: {"primary_issue": "<one of the 6>", '
            '"confidence": <0..1>, "reason": "<=25 words"}'
        )
        data = self.llm.decide(POLICY_SYSTEM, user)
        self.tracer.log(case_id, self.name, "llm_decide",
                        mode=self.llm.active_mode, model=self.llm.active_model,
                        raw_primary=(data or {}).get("primary_issue"))
        if not data:
            return None
        primary = str(data.get("primary_issue", "")).strip()
        if primary not in VALID_PRIMARY:
            return None
        conf = self.llm._clamp(data.get("confidence"), CONFIDENCE.get(primary, 0.9))
        return {"primary": primary, "confidence": conf,
                "reason": str(data.get("reason", "")).strip()}

    # ------------------------------------------------------------------ run #
    def run(self, case_id, order_id, order, customer, op, pay, delivery) -> dict:
        self.tracer.log(case_id, self.name, "dispatch", order_id=order_id)

        payment_total = pay["payment_total_brl"]
        facts = {
            "order_status": (order or {}).get("order_status"),
            "payment_total": payment_total,
            "paid": payment_total is not None and payment_total > 0,
            "delivered_late": delivery["delivered_late"],
            "delivery_variance_hours": delivery["delivery_variance_hours"],
            "late_handoff_seller_ids": delivery["late_handoff_seller_ids"],
            "n_payments": pay["n_payments"],
            "reconciled": pay["reconciled"],
            "n_items": op["n_items"],
            "n_sellers": len(op["seller_ids"]),
            "n_categories": len(op["category_names"]),
        }

        rule_primary = self._rule_primary(facts)
        llm_out = self._llm_primary(case_id, facts)

        llm_conf = None
        if llm_out is not None:
            primary = llm_out["primary"]
            llm_conf = llm_out["confidence"]
            source = "llm"
        else:
            primary = rule_primary
            source = "rule_fallback"

        agree = (primary == rule_primary)
        # Optional guardrail: enforce the rule engine when the model disagrees.
        if POLICY_GUARDRAIL and not agree:
            self.tracer.log(case_id, self.name, "guardrail_override",
                            llm_primary=primary, rule_primary=rule_primary)
            primary, source = rule_primary, "guardrail"

        # Confidence is a DETERMINISTIC, calibrated value per issue type — the
        # model's raw confidence (often a flat 1.0 from small models) is noise and
        # is kept only in the trace, not in the graded output.
        confidence = CONFIDENCE[primary]

        self.tracer.log(case_id, self.name, "decision", primary=primary,
                        source=source, rule_primary=rule_primary,
                        rule_agreement=agree, confidence=confidence,
                        llm_confidence=llm_conf)

        # ---- derive mechanical consequences from the chosen primary_issue --- #
        late_sellers = delivery["late_handoff_seller_ids"]
        if primary in ("canceled_order_paid", "unavailable_order_paid"):
            refund = payment_total
            responsible = [{"party_type": PLATFORM[0], "party_id": PLATFORM[1]}]
            resp_seller_ids = []
        elif primary == "late_delivery_seller":
            refund = pay["freight_total_brl"]
            resp_seller_ids = late_sellers[:3]
            responsible = [{"party_type": "seller", "party_id": s} for s in resp_seller_ids]
        elif primary == "late_delivery_logistics":
            refund = pay["freight_total_brl"]
            responsible = [{"party_type": LOGISTICS[0], "party_id": LOGISTICS[1]}]
            resp_seller_ids = []
        else:
            refund = 0.0
            responsible = []
            resp_seller_ids = []

        case_status = "action_required" if primary in (
            "canceled_order_paid", "unavailable_order_paid",
            "late_delivery_seller", "late_delivery_logistics",
        ) else "no_action"

        # secondary issues (factual flags, fixed order)
        secondary = []
        if op["n_items"] >= 2:
            secondary.append("multi_item_order")
        if len(op["seller_ids"]) >= 2:
            secondary.append("multi_seller_order")
        if pay["n_payments"] >= 2:
            secondary.append("split_payment")
        if len(customer["related_order_ids"]) >= 1:
            secondary.append("repeat_customer")
        if len(op["category_names"]) >= 2:
            secondary.append("multiple_categories")

        # resolution actions (primary action first, then fixed order)
        actions = [PRIMARY_ACTION[primary]]
        if primary == "late_delivery_seller":
            actions.append("review_seller_handoff")
        elif primary == "late_delivery_logistics":
            actions.append("review_carrier_delay")
        if primary in ("canceled_order_paid", "unavailable_order_paid"):
            actions.append("verify_refund_completion")
        if len(op["seller_ids"]) >= 2:
            actions.append("coordinate_multi_seller_case")
        if pay["n_payments"] >= 2 and primary != "valid_split_payment":
            actions.append("verify_payment_allocation")

        rc = ROOT_CAUSE[primary]
        ranked = [{"cause_code": rc, "rank": 1}]
        evidence = [f"order:{order_id}"]
        evidence += [f"item:{i}" for i in op["item_ids"]]
        evidence += [f"payment:{p}" for p in pay["payment_ids"]]
        evidence += [f"seller:{s}" for s in resp_seller_ids]
        evidence.append(f"policy:{rc}")

        # trace-only rationale annotation (each agent uses the <=10B model)
        self.annotate(
            case_id,
            system="You explain e-commerce dispute rulings under EC_POLICY_V2.",
            user=f"primary={primary} (source={source}) refund={refund} status={case_status}.",
            fallback_text=(llm_out["reason"] if llm_out else
                           f"Rule engine matched '{primary}' by strict priority."),
            fallback_conf=confidence,
        )

        finding = {
            "order_id": order_id,
            "primary_issue": primary,
            "secondary_issues": secondary,
            "case_status": case_status,
            "confidence": confidence,
            "ranked_causes": ranked,
            "responsible_parties": responsible,
            "evidence_ids": evidence,
            "recommended_refund_brl": refund,
            "resolution_actions": actions,
            "_decision_source": source,
            "_rule_agreement": agree,
        }
        self.handoff(case_id, "verifier_agent", finding)
        return finding
