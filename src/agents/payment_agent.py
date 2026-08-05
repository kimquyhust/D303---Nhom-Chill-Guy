"""Payment Agent — aggregates payment rows and reconciles vs item+freight."""
from __future__ import annotations

from .base import Agent


class PaymentAgent(Agent):
    name = "payment_agent"

    def run(self, case_id: str, order_id: str, op: dict) -> dict:
        self.tracer.log(case_id, self.name, "dispatch", order_id=order_id)
        # item/freight totals are null when the order has no item row
        if op["n_items"] == 0:
            item_total = freight_total = None
        else:
            item_total = sum(r["price"] or 0.0 for r in op["item_rows"])
            freight_total = sum(r["freight_value"] or 0.0 for r in op["item_rows"])
        finding = self.call_tool(
            case_id, "payment_tool",
            lambda: self.store.payment_tool(order_id, item_total, freight_total),
            order_id=order_id,
        )
        rec = finding["reconciled"]
        self.annotate(
            case_id,
            system="You reconcile customer payments against expected item+freight totals.",
            user=f"Order {order_id}: payments={finding['payment_total_brl']} "
                 f"expected={finding['expected_total_brl']} reconciled={rec}.",
            fallback_text=(
                f"Summed {finding['n_payments']} payment row(s) = "
                f"{finding['payment_total_brl']} BRL; reconciled={rec} "
                f"(|diff| <= 0.10 BRL). Null expected when no item row."
            ),
            fallback_conf=0.97 if rec in (True, None) else 0.85,
        )
        self.handoff(case_id, "delivery_agent", finding)
        return finding
