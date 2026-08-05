"""Coordinator Agent — receives a case, dispatches to domain agents in a fixed
handoff order, assembles the output and runs the verifier before returning it.

Handoff graph:
  coordinator
    -> customer_agent        (identity + history)
    -> order_product_agent   (items/sellers/products/categories)
    -> payment_agent         (reconciliation; consumes order/product totals)
    -> delivery_agent        (variance + handoff; consumes item rows)
    -> policy_agent          (EC_POLICY_V2; consumes all findings)
    -> verifier_agent        (schema/limits/evidence)
"""
from __future__ import annotations

from ..schema import assemble_output
from .customer_agent import CustomerAgent
from .delivery_agent import DeliveryAgent
from .order_product_agent import OrderProductAgent
from .payment_agent import PaymentAgent
from .policy_agent import ROOT_CAUSE, PolicyAgent
from .verifier_agent import VerifierAgent


class Coordinator:
    name = "coordinator"

    def __init__(self, store, llm, tracer):
        self.store, self.llm, self.tracer = store, llm, tracer
        self.customer = CustomerAgent(store, llm, tracer)
        self.order_product = OrderProductAgent(store, llm, tracer)
        self.payment = PaymentAgent(store, llm, tracer)
        self.delivery = DeliveryAgent(store, llm, tracer)
        self.policy = PolicyAgent(store, llm, tracer)
        self.verifier = VerifierAgent(store, llm, tracer)

    def process(self, case: dict) -> dict:
        case_id = case["case_id"]
        order_id = case["customer_request"]["claimed_order_id"]
        self.tracer.log(case_id, self.name, "case_start", order_id=order_id)

        order = self.store.get_order(order_id)
        if order is None:
            self.tracer.log(case_id, self.name, "warning", msg="order_id not in data")

        customer = self.customer.run(case_id, order_id)
        op = self.order_product.run(case_id, order_id)
        pay = self.payment.run(case_id, order_id, op)
        delivery = self.delivery.run(case_id, order_id, op)
        policy = self.policy.run(case_id, order_id, order, customer, op, pay, delivery)

        output = assemble_output(case_id, customer, op, pay, delivery, policy)

        universe = self._evidence_universe(order_id, op, pay)
        ok, issues = self.verifier.run(case_id, output, universe)
        self.tracer.log(case_id, self.name, "case_end", ok=ok,
                        primary=policy["primary_issue"], issues=issues)
        return output

    @staticmethod
    def _evidence_universe(order_id, op, pay) -> set:
        u = {f"order:{order_id}"}
        u |= set(f"item:{i}" for i in op["item_ids"])
        u |= set(f"payment:{p}" for p in pay["payment_ids"])
        u |= set(f"seller:{s}" for s in op["seller_ids"])
        u |= set(f"policy:{c}" for c in ROOT_CAUSE.values())
        return u
