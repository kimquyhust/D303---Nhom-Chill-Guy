#!/usr/bin/env python3
"""Independent validator for the 50-ticket run.

Re-derives the expected answer straight from the raw CSVs (NOT by calling the
pipeline) and checks the 5 cohort criteria:
  1 Count      exactly 50 JSON in output/
  2 Schema     parse + required fields + types + enums + caps + timestamp format
  3 Grounding  every evidence id resolvable from source data
  4 Policy     decision/refund/actions/secondary match EC_POLICY_V2
  5 Handoff    trace.jsonl shows the agent flow for every ticket

Exit code 0 iff all tickets pass every check.
"""
import glob
import json
import os
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(ROOT, "data")
TS = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

orders = pd.read_csv(os.path.join(D, "olist_orders_dataset.csv"), dtype=str).set_index("order_id", drop=False)
items = pd.read_csv(os.path.join(D, "olist_order_items_dataset.csv"), dtype=str)
pays = pd.read_csv(os.path.join(D, "olist_order_payments_dataset.csv"), dtype=str)
custs = pd.read_csv(os.path.join(D, "olist_customers_dataset.csv"), dtype=str)
prods = pd.read_csv(os.path.join(D, "olist_products_dataset.csv"), dtype=str)
prod_cat = prods.set_index("product_id")["product_category_name"].to_dict()
cust_unique = custs.set_index("customer_id")["customer_unique_id"].to_dict()
orders_by_unique = {}
_m = orders.merge(custs[["customer_id", "customer_unique_id"]], on="customer_id", how="left")
for cu, g in _m.groupby("customer_unique_id", sort=False):
    orders_by_unique[cu] = g["order_id"].tolist()


def r2(v):
    if v is None:
        return None
    q = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    f = float(q)
    return 0.0 if f == 0.0 else f


def ts(x):
    if x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip() in ("", "nan"):
        return None
    return datetime.strptime(str(x), "%Y-%m-%d %H:%M:%S")


def hours(a, b):
    A, B = ts(a), ts(b)
    return None if (A is None or B is None) else r2((A - B).total_seconds() / 3600)


def expected(oid):
    """Re-derive the correct decision straight from source data."""
    o = orders.loc[oid] if oid in orders.index else None
    if o is None:
        return None
    it = items[items.order_id == oid].copy()
    it["oi"] = pd.to_numeric(it["order_item_id"], errors="coerce")
    it = it.sort_values("oi")
    py = pays[pays.order_id == oid].copy()
    py["ps"] = pd.to_numeric(py["payment_sequential"], errors="coerce")
    py = py.sort_values("ps")

    status = o["order_status"]
    ptot = r2(pd.to_numeric(py["payment_value"], errors="coerce").sum()) if len(py) else 0.0
    paid = ptot is not None and ptot > 0
    n_items = len(it)
    sellers = list(dict.fromkeys(it["seller_id"].tolist()))
    delivered = o["order_delivered_customer_date"]
    est = o["order_estimated_delivery_date"]
    carrier = o["order_delivered_carrier_date"]
    dv = hours(delivered, est)
    late = dv is not None and dv > 0
    # per-seller earliest limit -> late handoff
    limits = {}
    for _, x in it.iterrows():
        s = x["seller_id"]; l = ts(x["shipping_limit_date"])
        if l and (s not in limits or l < limits[s]):
            limits[s] = l
    tcarrier = ts(carrier)
    late_sellers = [s for s in sellers if tcarrier and limits.get(s) and tcarrier > limits[s]]

    itot = r2(pd.to_numeric(it["price"], errors="coerce").sum()) if n_items else None
    ftot = r2(pd.to_numeric(it["freight_value"], errors="coerce").sum()) if n_items else None
    reconciled = None if itot is None else abs(r2(ptot - r2(itot + ftot))) <= 0.10

    if status == "canceled" and paid:
        prim = "canceled_order_paid"
    elif status == "unavailable" and paid:
        prim = "unavailable_order_paid"
    elif late and late_sellers:
        prim = "late_delivery_seller"
    elif late:
        prim = "late_delivery_logistics"
    elif len(py) >= 2 and reconciled is True:
        prim = "valid_split_payment"
    else:
        prim = "unsupported_late_claim"

    refund = {"canceled_order_paid": ptot, "unavailable_order_paid": ptot,
              "late_delivery_seller": ftot, "late_delivery_logistics": ftot}.get(prim, 0.0)

    secondary = []
    if n_items >= 2: secondary.append("multi_item_order")
    if len(sellers) >= 2: secondary.append("multi_seller_order")
    if len(py) >= 2: secondary.append("split_payment")
    cu = cust_unique.get(o["customer_id"])
    related = [x for x in orders_by_unique.get(cu, []) if x != oid]
    if related: secondary.append("repeat_customer")
    cats = list(dict.fromkeys(c for c in (prod_cat.get(p) for p in it["product_id"]) if isinstance(c, str)))
    if len(cats) >= 2: secondary.append("multiple_categories")

    actions = [{"canceled_order_paid": "issue_full_refund", "unavailable_order_paid": "issue_full_refund",
                "late_delivery_seller": "refund_freight", "late_delivery_logistics": "refund_freight",
                "valid_split_payment": "explain_valid_split_payment",
                "unsupported_late_claim": "reject_late_refund"}[prim]]
    if prim == "late_delivery_seller": actions.append("review_seller_handoff")
    elif prim == "late_delivery_logistics": actions.append("review_carrier_delay")
    if prim in ("canceled_order_paid", "unavailable_order_paid"): actions.append("verify_refund_completion")
    if len(sellers) >= 2: actions.append("coordinate_multi_seller_case")
    if len(py) >= 2 and prim != "valid_split_payment": actions.append("verify_payment_allocation")

    # evidence universe (what ids are constructible)
    universe = {f"order:{oid}"}
    universe |= {f"item:{oid}:{x}" for x in it["order_item_id"]}
    universe |= {f"payment:{oid}:{x}" for x in py["payment_sequential"]}
    universe |= {f"seller:{s}" for s in sellers}
    universe |= {f"policy:{c}" for c in [
        "SELLER_HANDOFF_AFTER_LIMIT", "CARRIER_DELIVERED_AFTER_ESTIMATE",
        "ORDER_CANCELED_AFTER_PAYMENT", "ORDER_UNAVAILABLE_AFTER_PAYMENT",
        "MULTIPLE_PAYMENTS_RECONCILED", "DELIVERY_WITHIN_ESTIMATE"]}

    return dict(primary=prim, refund=refund, secondary=secondary, actions=actions,
                status=("action_required" if refund and refund > 0 else "no_action"),
                universe=universe, itot=itot, ftot=ftot, ptot=ptot, reconciled=reconciled,
                dv=dv, late_sellers=late_sellers)


REQUIRED_TOP = {"case_id", "case_assessment", "affected_entities", "customer_context",
                "product_context", "delivery_analysis", "payment_reconciliation",
                "root_cause_analysis", "evidence_ids", "financial_resolution", "resolution_actions"}
CAPS = {"order_ids": 5, "item_ids": 5, "seller_ids": 3, "payment_ids": 5,
        "related_order_ids": 5, "product_ids": 5, "category_names": 5,
        "ranked_causes": 3, "responsible_parties": 3, "evidence_ids": 20, "resolution_actions": 5}


def check_schema(o):
    errs = []
    miss = REQUIRED_TOP - set(o)
    if miss: errs.append(f"missing fields {miss}")
    ca = o.get("case_assessment", {})
    if ca.get("case_status") not in ("action_required", "no_action"): errs.append("bad case_status")
    if not (isinstance(ca.get("confidence"), (int, float)) and 0 <= ca["confidence"] <= 1): errs.append("confidence not in [0,1]")
    for k, cap in CAPS.items():
        for sect in ("affected_entities", "customer_context", "product_context", "root_cause_analysis", o):
            pass
    # cap checks (locate each list)
    lists = {
        "order_ids": o["affected_entities"]["order_ids"], "item_ids": o["affected_entities"]["item_ids"],
        "seller_ids": o["affected_entities"]["seller_ids"], "payment_ids": o["affected_entities"]["payment_ids"],
        "related_order_ids": o["customer_context"]["related_order_ids"],
        "product_ids": o["product_context"]["product_ids"], "category_names": o["product_context"]["category_names"],
        "ranked_causes": o["root_cause_analysis"]["ranked_causes"],
        "responsible_parties": o["root_cause_analysis"]["responsible_parties"],
        "evidence_ids": o["evidence_ids"], "resolution_actions": o["resolution_actions"],
    }
    for k, v in lists.items():
        if len(v) > CAPS[k]: errs.append(f"{k} exceeds cap {CAPS[k]}")
    for f in ("delivered_at", "estimated_delivery_at", "carrier_handoff_at"):
        v = o["delivery_analysis"][f]
        if v is not None and not TS.match(v): errs.append(f"bad ts {f}")
    return errs


def main():
    out = sorted(glob.glob(os.path.join(ROOT, "output", "EC_*.json")))
    report = {"count": len(out), "schema": [], "grounding": [], "policy": [], "handoff": []}

    # 5 handoff: load trace, index events per case
    trace_path = os.path.join(ROOT, "logging", "trace.jsonl")
    trace_ok = os.path.exists(trace_path)
    case_events = {}
    if trace_ok:
        for line in open(trace_path, encoding="utf-8"):
            try: r = json.loads(line)
            except ValueError: continue
            case_events.setdefault(r.get("case_id"), set()).add((r.get("agent"), r.get("event")))

    for f in out:
        cid = os.path.splitext(os.path.basename(f))[0]
        try:
            o = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            report["schema"].append((cid, [f"parse error {e}"])); continue

        se = check_schema(o)
        if se: report["schema"].append((cid, se))

        oid = o["affected_entities"]["order_ids"][0]
        exp = expected(oid)
        if exp is None:
            report["policy"].append((cid, ["order not in data"])); continue

        # 3 grounding
        bad_ev = [e for e in o["evidence_ids"] if e not in exp["universe"]]
        if bad_ev: report["grounding"].append((cid, bad_ev))

        # 4 policy
        pe = []
        got = o["case_assessment"]
        if got["primary_issue"] != exp["primary"]:
            pe.append(f"primary {got['primary_issue']} != {exp['primary']}")
        if got["case_status"] != exp["status"]:
            pe.append(f"status {got['case_status']} != {exp['status']}")
        if o["resolution_actions"] != exp["actions"]:
            pe.append(f"actions {o['resolution_actions']} != {exp['actions']}")
        if o["case_assessment"]["secondary_issues"] != exp["secondary"]:
            pe.append(f"secondary {o['case_assessment']['secondary_issues']} != {exp['secondary']}")
        gr = o["financial_resolution"]["recommended_refund_brl"]
        if r2(gr) != r2(exp["refund"]):
            pe.append(f"refund {gr} != {exp['refund']}")
        # reasoning consistency: root cause + evidence policy code must match primary
        rc = o["root_cause_analysis"]["ranked_causes"][0]["cause_code"]
        expect_rc = {"canceled_order_paid": "ORDER_CANCELED_AFTER_PAYMENT",
                     "unavailable_order_paid": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
                     "late_delivery_seller": "SELLER_HANDOFF_AFTER_LIMIT",
                     "late_delivery_logistics": "CARRIER_DELIVERED_AFTER_ESTIMATE",
                     "valid_split_payment": "MULTIPLE_PAYMENTS_RECONCILED",
                     "unsupported_late_claim": "DELIVERY_WITHIN_ESTIMATE"}[exp["primary"]]
        if rc != expect_rc: pe.append(f"root_cause {rc} != {expect_rc}")
        if f"policy:{expect_rc}" not in o["evidence_ids"]: pe.append("policy evidence missing")
        if pe: report["policy"].append((cid, pe))

        # 5 handoff per case
        ev = case_events.get(cid, set())
        need = [("coordinator", "case_start"), ("customer_agent", "handoff"),
                ("order_product_agent", "handoff"), ("payment_agent", "handoff"),
                ("delivery_agent", "handoff"), ("policy_agent", "decision"),
                ("verifier_agent", "verify"), ("coordinator", "case_end")]
        missing = [x for x in need if x not in ev]
        if missing: report["handoff"].append((cid, missing))

    # ---- print report ----
    print("=" * 60)
    print(f"1. COUNT      : {report['count']} JSON files  ->  {'PASS' if report['count']==50 else 'FAIL'}")
    print(f"2. SCHEMA     : {50-len(report['schema'])}/50 pass  ->  {'PASS' if not report['schema'] else 'FAIL'}")
    for c, e in report["schema"]: print(f"     {c}: {e}")
    print(f"3. GROUNDING  : {50-len(report['grounding'])}/50 pass  ->  {'PASS' if not report['grounding'] else 'FAIL'}")
    for c, e in report["grounding"]: print(f"     {c}: {e}")
    print(f"4. POLICY     : {50-len(report['policy'])}/50 pass  ->  {'PASS' if not report['policy'] else 'FAIL'}")
    for c, e in report["policy"]: print(f"     {c}: {e}")
    print(f"5. HANDOFF    : trace={'present' if trace_ok else 'MISSING'}; "
          f"{50-len(report['handoff'])}/50 flows complete  ->  {'PASS' if trace_ok and not report['handoff'] else 'FAIL'}")
    for c, e in report["handoff"]: print(f"     {c}: missing {e}")
    print("=" * 60)
    allpass = (report["count"] == 50 and not report["schema"] and not report["grounding"]
               and not report["policy"] and trace_ok and not report["handoff"])
    print("RESULT:", "ALL CHECKS PASS" if allpass else "FAILURES PRESENT")
    return 0 if allpass else 1


if __name__ == "__main__":
    raise SystemExit(main())
