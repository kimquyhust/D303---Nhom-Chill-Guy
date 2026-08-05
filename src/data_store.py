"""Deterministic tool layer over the 9 Olist CSVs.

This module is the ONLY place that reads raw data. Every graded number is
produced here so the output never depends on a language model's arithmetic.
Each public function is a "tool" that an agent calls; calls are recorded in the
trace by the agents themselves.
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Optional

import pandas as pd

from .config import (
    PATHS,
    RECONCILE_TOLERANCE_BRL,
    ROUND_DP,
    USE_ENGLISH_CATEGORY,
)

TS_FMT = "%Y-%m-%d %H:%M:%S"


def round2(value: Optional[float]) -> Optional[float]:
    """Round-half-up to 2 dp, normalising -0.0 -> 0.0. None passes through."""
    if value is None:
        return None
    quantum = Decimal(1).scaleb(-ROUND_DP)
    q = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    f = float(q)
    return 0.0 if f == 0.0 else f


def _parse_ts(value) -> Optional[datetime]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return datetime.strptime(s, TS_FMT)
    except ValueError:
        # some columns include fractional seconds; fall back to pandas
        ts = pd.to_datetime(s, errors="coerce")
        return None if pd.isna(ts) else ts.to_pydatetime()


def _fmt_ts(value) -> Optional[str]:
    """Return the timestamp exactly in CSV format, or None."""
    dt = _parse_ts(value)
    return dt.strftime(TS_FMT) if dt else None


def _hours_between(later, earlier) -> Optional[float]:
    a, b = _parse_ts(later), _parse_ts(earlier)
    if a is None or b is None:
        return None
    return round2((a - b).total_seconds() / 3600.0)


class DataStore:
    """Loads and indexes the Olist dataset once; exposes tool functions."""

    def __init__(self, data_dir: Optional[str] = None):
        d = data_dir or PATHS.data
        self.orders = pd.read_csv(os.path.join(d, "olist_orders_dataset.csv"), dtype=str)
        self.items = pd.read_csv(os.path.join(d, "olist_order_items_dataset.csv"), dtype=str)
        self.payments = pd.read_csv(os.path.join(d, "olist_order_payments_dataset.csv"), dtype=str)
        self.customers = pd.read_csv(os.path.join(d, "olist_customers_dataset.csv"), dtype=str)
        self.products = pd.read_csv(os.path.join(d, "olist_products_dataset.csv"), dtype=str)
        self.sellers = pd.read_csv(os.path.join(d, "olist_sellers_dataset.csv"), dtype=str)
        trans = pd.read_csv(os.path.join(d, "product_category_name_translation.csv"))
        trans.columns = [c.strip().lstrip("﻿") for c in trans.columns]

        # numeric columns we compute on
        for col in ("price", "freight_value"):
            self.items[col + "_f"] = pd.to_numeric(self.items[col], errors="coerce")
        self.payments["payment_value_f"] = pd.to_numeric(self.payments["payment_value"], errors="coerce")
        self.payments["payment_sequential_i"] = pd.to_numeric(
            self.payments["payment_sequential"], errors="coerce"
        )
        self.items["order_item_id_i"] = pd.to_numeric(self.items["order_item_id"], errors="coerce")

        # indexes for O(1)/grouped lookups
        self._orders_by_id = self.orders.set_index("order_id", drop=False)
        self._items_by_order = {k: v for k, v in self.items.groupby("order_id", sort=False)}
        self._pays_by_order = {k: v for k, v in self.payments.groupby("order_id", sort=False)}
        self._cust_by_id = self.customers.set_index("customer_id", drop=False)
        self._orders_by_unique = {
            k: v for k, v in self.orders.merge(
                self.customers[["customer_id", "customer_unique_id"]], on="customer_id", how="left"
            ).groupby("customer_unique_id", sort=False)
        }
        self._prod_cat = self.products.set_index("product_id")["product_category_name"].to_dict()
        self._cat_en = dict(
            zip(trans["product_category_name"], trans["product_category_name_english"])
        )

    # ---------------------------------------------------------------- orders #
    def get_order(self, order_id: str) -> Optional[dict]:
        if order_id not in self._orders_by_id.index:
            return None
        r = self._orders_by_id.loc[order_id]
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        return r.to_dict()

    # ------------------------------------------------------------- customer #
    def customer_tool(self, order_id: str) -> dict:
        """Customer identity + history (other orders of the same unique id)."""
        order = self.get_order(order_id)
        if order is None:
            return {"customer_unique_id": None, "related_order_ids": []}
        cust_id = order["customer_id"]
        cu = None
        if cust_id in self._cust_by_id.index:
            row = self._cust_by_id.loc[cust_id]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            cu = row["customer_unique_id"]
        related = []
        if cu is not None and cu in self._orders_by_unique:
            for oid in self._orders_by_unique[cu]["order_id"].tolist():
                if oid != order_id and oid not in related:
                    related.append(oid)
        return {"customer_unique_id": cu, "related_order_ids": related}

    # -------------------------------------------------------- order/product #
    def order_product_tool(self, order_id: str) -> dict:
        it = self._items_by_order.get(order_id)
        item_ids, seller_ids, product_ids, categories = [], [], [], []
        item_rows = []
        if it is not None:
            it = it.sort_values("order_item_id_i")
            for _, row in it.iterrows():
                item_ids.append(f"{order_id}:{row['order_item_id']}")
                if row["seller_id"] not in seller_ids:
                    seller_ids.append(row["seller_id"])
                if row["product_id"] not in product_ids:
                    product_ids.append(row["product_id"])
                cat = self._category_name(row["product_id"])
                if cat is not None and cat not in categories:
                    categories.append(cat)
                item_rows.append({
                    "order_item_id": row["order_item_id"],
                    "product_id": row["product_id"],
                    "seller_id": row["seller_id"],
                    "shipping_limit_date": _fmt_ts(row["shipping_limit_date"]),
                    "price": row["price_f"],
                    "freight_value": row["freight_value_f"],
                })
        return {
            "n_items": len(item_rows),
            "item_ids": item_ids,
            "seller_ids": seller_ids,
            "product_ids": product_ids,
            "category_names": categories,
            "item_rows": item_rows,
        }

    def _category_name(self, product_id: str) -> Optional[str]:
        cat = self._prod_cat.get(product_id)
        if cat is None or (isinstance(cat, float) and pd.isna(cat)):
            return None
        if USE_ENGLISH_CATEGORY:
            return self._cat_en.get(cat, cat)
        return cat

    # ------------------------------------------------------------- payment #
    def payment_tool(self, order_id: str, item_total: Optional[float],
                     freight_total: Optional[float]) -> dict:
        py = self._pays_by_order.get(order_id)
        payment_ids, types = [], []
        total = 0.0
        n = 0
        if py is not None:
            py = py.sort_values("payment_sequential_i")
            for _, row in py.iterrows():
                payment_ids.append(f"{order_id}:{row['payment_sequential']}")
                if row["payment_type"] not in types:
                    types.append(row["payment_type"])
                total += float(row["payment_value_f"] or 0.0)
                n += 1
        payment_total = round2(total)
        # expected/difference/reconciled are null when the order has no item row
        if item_total is None:
            expected = difference = reconciled = None
        else:
            expected = round2((item_total or 0.0) + (freight_total or 0.0))
            difference = round2(payment_total - expected)
            reconciled = abs(difference) <= RECONCILE_TOLERANCE_BRL
        return {
            "n_payments": n,
            "payment_ids": payment_ids,
            "payment_types": types,
            "payment_total_brl": payment_total,
            "item_total_brl": round2(item_total) if item_total is not None else 0.0,
            "freight_total_brl": round2(freight_total) if freight_total is not None else 0.0,
            "expected_total_brl": expected,
            "difference_brl": difference,
            "reconciled": reconciled,
        }

    # ------------------------------------------------------------ delivery #
    def delivery_tool(self, order_id: str, item_rows: list) -> dict:
        order = self.get_order(order_id) or {}
        delivered = order.get("order_delivered_customer_date")
        estimated = order.get("order_estimated_delivery_date")
        carrier = order.get("order_delivered_carrier_date")

        delivery_variance = _hours_between(delivered, estimated)

        # earliest shipping_limit per seller
        per_seller: dict = {}
        for r in item_rows:
            sid = r["seller_id"]
            lim = r["shipping_limit_date"]
            if lim is None:
                continue
            if sid not in per_seller or _parse_ts(lim) < _parse_ts(per_seller[sid]):
                per_seller[sid] = lim

        seller_handoff, late_sellers = [], []
        # keep stable seller order as they first appear in item_rows
        seen = []
        for r in item_rows:
            if r["seller_id"] not in seen:
                seen.append(r["seller_id"])
        for sid in seen:
            lim = per_seller.get(sid)
            hv = _hours_between(carrier, lim) if lim else None
            late = bool(hv is not None and hv > 0)
            seller_handoff.append({
                "seller_id": sid,
                "shipping_limit_at": _fmt_ts(lim) if lim else None,
                "handoff_variance_hours": hv,
                "late_handoff": late,
            })
            if late:
                late_sellers.append(sid)

        delivered_late = bool(delivery_variance is not None and delivery_variance > 0)
        return {
            "delivered_at": _fmt_ts(delivered),
            "estimated_delivery_at": _fmt_ts(estimated),
            "carrier_handoff_at": _fmt_ts(carrier),
            "delivery_variance_hours": delivery_variance,
            "seller_handoff_analysis": seller_handoff,
            "late_handoff_seller_ids": late_sellers,
            "delivered_late": delivered_late,
        }


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    return DataStore()
