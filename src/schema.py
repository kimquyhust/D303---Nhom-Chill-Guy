"""Output assembly + array-limit enforcement (README section 6)."""
from __future__ import annotations

from typing import Any

from .config import CURRENCY, LIMITS


def cap(seq, key: str):
    """Trim a list to its documented maximum, preserving order."""
    return list(seq)[: LIMITS[key]]


def assemble_output(case_id: str, customer: dict, op: dict, pay: dict,
                    delivery: dict, policy: dict) -> dict:
    """Combine every agent finding into the final graded JSON."""
    seller_ids = cap(op["seller_ids"], "seller_ids")
    return {
        "case_id": case_id,
        "case_assessment": {
            "primary_issue": policy["primary_issue"],
            "secondary_issues": policy["secondary_issues"],
            "case_status": policy["case_status"],
            "confidence": policy["confidence"],
        },
        "affected_entities": {
            "order_ids": cap([case_id_order(policy)], "order_ids"),
            "item_ids": cap(op["item_ids"], "item_ids"),
            "seller_ids": seller_ids,
            "payment_ids": cap(pay["payment_ids"], "payment_ids"),
        },
        "customer_context": {
            "customer_unique_id": customer["customer_unique_id"],
            "related_order_ids": cap(customer["related_order_ids"], "related_order_ids"),
        },
        "product_context": {
            "product_ids": cap(op["product_ids"], "product_ids"),
            "category_names": cap(op["category_names"], "category_names"),
        },
        "delivery_analysis": {
            "delivered_at": delivery["delivered_at"],
            "estimated_delivery_at": delivery["estimated_delivery_at"],
            "carrier_handoff_at": delivery["carrier_handoff_at"],
            "delivery_variance_hours": delivery["delivery_variance_hours"],
            "seller_handoff_analysis": delivery["seller_handoff_analysis"],
            "late_handoff_seller_ids": delivery["late_handoff_seller_ids"],
        },
        "payment_reconciliation": {
            "currency": CURRENCY,
            "item_total_brl": pay["item_total_brl"],
            "freight_total_brl": pay["freight_total_brl"],
            "expected_total_brl": pay["expected_total_brl"],
            "payment_total_brl": pay["payment_total_brl"],
            "difference_brl": pay["difference_brl"],
            "reconciled": pay["reconciled"],
            "payment_types": pay["payment_types"],
        },
        "root_cause_analysis": {
            "ranked_causes": cap(policy["ranked_causes"], "ranked_causes"),
            "responsible_parties": cap(policy["responsible_parties"], "responsible_parties"),
        },
        "evidence_ids": cap(policy["evidence_ids"], "evidence_ids"),
        "financial_resolution": {
            "currency": CURRENCY,
            "recommended_refund_brl": policy["recommended_refund_brl"],
        },
        "resolution_actions": cap(policy["resolution_actions"], "resolution_actions"),
    }


def case_id_order(policy: dict) -> str:
    return policy["order_id"]
