"""Delivery Agent — delivery variance and per-seller handoff variance."""
from __future__ import annotations

from .base import Agent


class DeliveryAgent(Agent):
    name = "delivery_agent"

    def run(self, case_id: str, order_id: str, op: dict) -> dict:
        self.tracer.log(case_id, self.name, "dispatch", order_id=order_id)

        item_rows = op["item_rows"]

        finding = self.call_tool(
            case_id,
            "delivery_tool",
            lambda: self.store.delivery_tool(order_id, item_rows),
            order_id=order_id,
        )

        delivery_variance = finding["delivery_variance_hours"]
        late_handoff_sellers = finding["late_handoff_seller_ids"]
        late_seller_count = len(late_handoff_sellers)

        self.annotate(
            case_id,
            system=(
                "You measure delivery timeliness and seller handoff punctuality."
            ),
            user=(
                f"Order {order_id}: "
                f"delivery_variance={delivery_variance}h, "
                f"late_handoff_sellers={late_seller_count}."
            ),
            fallback_text=(
                f"delivery_variance={delivery_variance}h (>0 means late). "
                f"{late_seller_count} seller(s) handed off after "
                f"shipping_limit_date."
            ),
            fallback_conf=0.95 if delivery_variance is not None else 0.8,
        )

        self.handoff(case_id, "policy_agent", finding)
        return finding