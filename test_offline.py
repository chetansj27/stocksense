"""Offline tests (no API key or GCP needed). Run: python test_offline.py"""
import os
import tempfile

import data

data.DB = os.path.join(tempfile.mkdtemp(), "test.db")  # isolate from the real DB

import agents  # noqa: E402
import anomaly  # noqa: E402
import forecast  # noqa: E402
import interest  # noqa: E402
import customer  # noqa: E402
import orders  # noqa: E402
import simulate  # noqa: E402
from google.genai import types  # noqa: E402

data.generate()

# forecast / plan
base, up = forecast.plan(1.0), forecast.plan(1.3)
assert set(base.risk) <= {"STOCKOUT", "REORDER", "OVERSTOCK", "OK"}
assert len(base) == len(data.PRODUCTS)
assert up.daily_demand.sum() > base.daily_demand.sum() * 1.25, "multiplier must raise demand"
assert (up.reorder_qty.sum() >= base.reorder_qty.sum()), "more demand should not reduce orders"

# SQL guard
assert agents.query_data("SELECT COUNT(*) FROM sales").splitlines()[1].strip() != ""
for bad in ("DROP TABLE sales", "SELECT 1; DROP TABLE sales", "DELETE FROM sales", "UPDATE sales SET units=0"):
    assert agents.query_data(bad).startswith("Error") or "error" in agents.query_data(bad).lower(), bad
agents.query_data("WITH x AS (SELECT 1) SELECT * FROM x")
assert data.load("sales").shape[0] > 0, "sales table must survive attack attempts"

# orders: create, dedupe via incoming, approve, reject
oid = orders.create("SKU-001", 100, "test")
assert orders.incoming()["SKU-001"] == 100
assert forecast.plan(1.0).set_index("sku").loc["SKU-001", "on_order"] == 100
orders.set_status(oid, "approved")
assert orders.list_all().iloc[0].status == "approved"
orders.set_status(oid, "rejected")
assert "SKU-001" not in orders.incoming()
assert "pending PO" in agents.create_purchase_order("SKU-002", 5, "t")
assert "SKU-002" in agents.list_purchase_orders()

# names in orders, bulk ops, alerts, delete
det = orders.list_detailed()
assert {"product", "unit_cost", "total"} <= set(det.columns) and det["product"].notna().all()
assert det.loc[det.sku == "SKU-002", "product"].iloc[0] == "Organic Bananas 1kg"
ids = [orders.create("SKU-003", 10, "bulk"), orders.create("SKU-004", 20, "bulk")]
orders.set_status_many(ids, "approved")
assert set(orders.list_all().set_index("id").loc[ids, "status"]) == {"approved"}
assert orders.delete_all() >= 2 and orders.list_all().empty and orders.list_detailed().empty
al = anomaly.alerts()
assert set(al.sku) >= {"SKU-005", "SKU-011"} and (al.kind == "surge").all(), al
assert "SKU-011" in agents.demand_alerts()
assert "Organic" in agents.list_purchase_orders() or agents.list_purchase_orders() == "No purchase orders."

# customer assistant: availability, substitutes, honest restock notes, interest log, no cost leakage
cat = {p["sku"]: p for p in customer.catalog()}
assert cat["SKU-005"]["status"] == "out_of_stock" and cat["SKU-005"]["restock"] == "no restock date yet"
assert cat["SKU-001"]["status"] in ("in_stock", "low_stock")
out = customer.search_products("do you have sparkling water?")
assert "OUT OF STOCK" in out and "Sparkling Water" in out
assert "Oat Milk" in customer.search_products("oat milk") and "Frozen" in customer.search_products("ice cream")
assert "No matching" in customer.search_products("zzzz")
subs = customer.find_substitutes("SKU-005")
assert "Cold Brew" in subs and "Sparkling" not in subs
pid = orders.create("SKU-005", 100, "restock")
assert "being arranged" in customer.search_products("sparkling water")
orders.set_status(pid, "approved")
assert "expected around" in customer.search_products("sparkling water") or "arriving very soon" in customer.search_products("sparkling water")
bt = customer.basket_total(["SKU-001", "SKU-005"], [2, 1])
assert "OUT OF STOCK" in bt and "TOTAL: $3.84" in bt, bt  # 2 x $1.92; the sold-out item is excluded
joined = " ".join([out, subs, customer.list_in_stock(), bt]).lower()
assert "cost" not in joined and "on_hand" not in joined
sm = interest.summary()
assert sm.set_index("sku").loc["SKU-005", "unavailable_asks"] >= 1, sm
assert "SKU-005" in agents.customer_interest()
assert interest.clear() > 0 and interest.summary().empty
orders.delete_all()
for fn in customer.TOOLS:
    d = types.FunctionDeclaration.from_callable_with_api_option(callable=fn, api_option="GEMINI_API")
    assert d.name == fn.__name__

# tool schemas must be valid for Gemini function calling
for fn in agents.TOOLS:
    decl = types.FunctionDeclaration.from_callable_with_api_option(callable=fn, api_option="GEMINI_API")
    assert decl.name == fn.__name__ and decl.description, fn.__name__

# backtest
summary, detail = simulate.run(60)
assert list(summary.index) == list(simulate.POLICIES)
assert (summary.fill_rate_pct.between(0, 100)).all()
print(summary)
print("ALL OFFLINE TESTS PASSED")
