"""Delivery Agent — delivery variance and per-seller handoff variance."""
from __future__ import annotations

from .base import Agent


class DeliveryAgent(Agent):
    name = "delivery_agent"

    def run(self, case_id: str, order_id: str, op: dict) -> dict:
        self.tracer.log(case_id, self.name, "dispatch", order_id=order_id)
        finding = self.call_tool(
            case_id, "delivery_tool",
            lambda: self.store.delivery_tool(order_id, op["item_rows"]),
            order_id=order_id,
        )
        dv = finding["delivery_variance_hours"]
        late_sellers = finding["late_handoff_seller_ids"]
        self.annotate(
            case_id,
            system="You measure delivery timeliness and seller handoff punctuality.",
            user=f"Order {order_id}: delivery_variance={dv}h, "
                 f"late_handoff_sellers={len(late_sellers)}.",
            fallback_text=(
                f"delivery_variance={dv}h (>0 means late). "
                f"{len(late_sellers)} seller(s) handed off after shipping_limit_date."
            ),
            fallback_conf=0.95 if dv is not None else 0.8,
        )
        self.handoff(case_id, "policy_agent", finding)
        return finding
