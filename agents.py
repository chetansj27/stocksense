import re

from google import genai
from google.genai import types

import anomaly
import data
import forecast
import interest
import orders

MODEL = "gemini-2.5-flash"


# ---- tools --------------------------------------------------------------------
def query_data(sql: str) -> str:
    """Run a read-only SQL SELECT on the retail database. Tables: sales(date,sku,units,revenue,promo),
    inventory(sku,on_hand), products(sku,name,category,unit_cost,unit_price,lead_time_days).
    Returns up to 50 rows. (Use list_purchase_orders for orders.)"""
    if not re.match(r"^\s*(select|with)\b", sql, re.I) or ";" in sql.strip().rstrip(";"):
        return "Error: only a single SELECT statement is allowed."
    try:
        with data.conn(readonly=True) as c:
            cur = c.execute(sql)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(50)
        return "\n".join([" | ".join(cols)] + [" | ".join(map(str, r)) for r in rows]) or "No rows."
    except Exception as e:
        return f"SQL error: {e}"


def inventory_plan(demand_multiplier: float = 1.0) -> str:
    """Get stock risk and reorder recommendations for all products. demand_multiplier is a what-if
    factor (1.2 means demand rises 20%)."""
    return forecast.plan(demand_multiplier).to_string(index=False)


def create_purchase_order(sku: str, qty: int, reason: str) -> str:
    """Create a PENDING purchase order. A human must approve it before it is placed."""
    return f"Created pending PO {orders.create(sku, qty, reason)}: {qty} x {sku}"


def list_purchase_orders() -> str:
    """List existing purchase orders and their status."""
    df = orders.list_detailed()
    return df.to_string(index=False) if len(df) else "No purchase orders."


def demand_alerts() -> str:
    """Products whose demand over the last 7 days is unusually high (surge) or low (drop) versus the
    prior 8 weeks. Use this to explain why a product's risk changed."""
    df = anomaly.alerts()
    return df.to_string(index=False) if len(df) else "No unusual demand changes."


def customer_interest() -> str:
    """What customers asked the storefront assistant about in the last 24 hours, including how often the
    product was unavailable when asked (unmet demand)."""
    df = interest.summary()
    return df.to_string(index=False) if len(df) else "No customer activity yet."


TOOLS = [query_data, inventory_plan, create_purchase_order, list_purchase_orders, demand_alerts, customer_interest]

SYSTEM = (
    "You are StockSense, an inventory and demand-planning copilot for a retailer. Use the tools to get "
    "real numbers; never invent data. For what-if questions call inventory_plan with a demand_multiplier "
    "and compare against the baseline (1.0). Explain recommendations briefly with the key figures "
    "(days of cover, lead time, quantity, cost). When a product's demand looks unusual, call demand_alerts. For unmet customer demand call customer_interest. Purchase orders you create are pending human approval "
    "and you should say so."
)


def ask(client: genai.Client, message: str, history: list[tuple[str, str]]) -> str:
    transcript = "\n".join(f"{r}: {t}" for r, t in history[-6:])
    res = client.models.generate_content(
        model=MODEL,
        contents=f"{transcript}\nuser: {message}" if transcript else message,
        config=types.GenerateContentConfig(tools=TOOLS, system_instruction=SYSTEM),
    )
    return res.text or "(no response)"


def explain(client: genai.Client, row: dict, multiplier: float) -> str:
    res = client.models.generate_content(
        model=MODEL,
        contents=f"In 2 sentences, explain this inventory recommendation to a store manager "
                 f"(demand multiplier {multiplier}): {row}",
    )
    return res.text
