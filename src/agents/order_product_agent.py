"""Order & Product Agent — items, sellers, products, categories."""
from __future__ import annotations

from .base import Agent


class OrderProductAgent(Agent):
    name = "order_product_agent"

    def run(self, case_id: str, order_id: str) -> dict:
        self.tracer.log(case_id, self.name, "dispatch", order_id=order_id)
        finding = self.call_tool(
            case_id, "order_product_tool",
            lambda: self.store.order_product_tool(order_id), order_id=order_id,
        )
        self.annotate(
            case_id,
            system="You audit order composition (items, sellers, products, categories).",
            user=f"Order {order_id}: {finding['n_items']} item(s), "
                 f"{len(finding['seller_ids'])} seller(s), "
                 f"{len(finding['category_names'])} distinct category value(s).",
            fallback_text=(
                f"Joined order_items -> products/sellers: {finding['n_items']} items, "
                f"{len(finding['seller_ids'])} sellers. Empty arrays when no item row."
            ),
            fallback_conf=0.98 if finding["n_items"] else 0.9,
        )
        # order/product finding feeds both payment (totals) and delivery (handoff)
        self.handoff(case_id, "payment_agent", finding)
        return finding
