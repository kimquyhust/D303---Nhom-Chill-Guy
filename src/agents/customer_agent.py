"""Customer Agent — resolves customer identity and order history."""
from __future__ import annotations

from .base import Agent


class CustomerAgent(Agent):
    name = "customer_agent"

    def run(self, case_id: str, order_id: str) -> dict:
        self.tracer.log(case_id, self.name, "dispatch", order_id=order_id)
        finding = self.call_tool(
            case_id, "customer_tool",
            lambda: self.store.customer_tool(order_id), order_id=order_id,
        )
        n = len(finding["related_order_ids"])
        self.annotate(
            case_id,
            system="You verify e-commerce customer identity from order records.",
            user=f"Order {order_id} maps to customer_unique_id "
                 f"{finding['customer_unique_id']} with {n} other order(s).",
            fallback_text=(
                f"Resolved customer_unique_id via customers table; found {n} "
                f"related order(s) (history only, excluded from affected_entities)."
            ),
            fallback_conf=0.99 if finding["customer_unique_id"] else 0.4,
        )
        self.handoff(case_id, "order_product_agent", finding)
        return finding
