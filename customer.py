"""Customer-facing shopping assistant. Customers see availability and prices only: never costs,
margins, or exact stock levels. Restock dates are only quoted when a manager has approved a PO."""
import re

import pandas as pd
from google import genai
from google.genai import types

import data
import forecast
import interest
import orders

MODEL = "gemini-2.5-flash"
SYNONYMS = {"drink": "beverage", "drinks": "beverage", "soda": "beverage", "water": "sparkling",
            "snack": "snacks", "sweet": "chocolate", "dessert": "ice cream", "bread": "sourdough",
            "cleaning": "household", "frozen": "frozen", "egg": "eggs", "banana": "bananas"}
STOP = {"the", "and", "for", "you", "have", "any", "some", "get", "want", "need", "with", "under",
        "what", "can", "that", "this", "your", "are", "there", "please", "something", "looking"}


def _restock_note(sku: str, lead: int, ords: pd.DataFrame) -> str:
    mine = ords[ords["sku"] == sku] if len(ords) else ords
    approved = mine[mine["status"] == "approved"] if len(mine) else mine
    if len(approved):
        eta = (pd.to_datetime(approved["created"], utc=True, errors="coerce") + pd.to_timedelta(lead, "D")).min()
        if pd.notna(eta):
            return ("arriving very soon" if eta.date() <= pd.Timestamp.now(tz="UTC").date()
                    else f"expected around {eta:%a %d %b}")
    if len(mine) and (mine["status"] == "pending").any():
        return "a restock is being arranged, no date confirmed yet"
    return "no restock date yet"


def catalog() -> list[dict]:
    plan = forecast.plan(1.0)
    price = data.load("products").set_index("sku")["unit_price"]
    ords = orders.list_all()
    out = []
    for r in plan.itertuples():
        if r.on_hand <= 0:
            status = "out_of_stock"
        elif r.on_hand / max(r.daily_demand, 0.1) < 2:
            status = "low_stock"
        else:
            status = "in_stock"
        out.append({"sku": r.sku, "name": r.name, "category": r.category, "price": float(price[r.sku]),
                    "status": status, "restock": _restock_note(r.sku, r.lead_time, ords) if status == "out_of_stock" else ""})
    return out


def _line(p: dict) -> str:
    label = {"in_stock": "IN STOCK", "low_stock": "LOW STOCK (only a few left)",
             "out_of_stock": f"OUT OF STOCK ({p['restock']})"}[p["status"]]
    return f"{p['name']} [{p['sku']}] | {p['category']} | ${p['price']:.2f} | {label}"


# ---- tools --------------------------------------------------------------------
def search_products(query: str) -> str:
    """Search the store by product name or category, e.g. 'oat milk', 'snacks', 'drinks', 'eggs'.
    Returns price and availability for each match."""
    words = [SYNONYMS.get(w, w) for w in re.findall(r"[a-z]+", query.lower()) if len(w) >= 3 and w not in STOP]
    cat = catalog()
    hits = [p for p in cat if any(w in p["name"].lower() or w in p["category"].lower() for w in words)]
    for p in hits[:5]:
        interest.log(p["sku"], query, p["status"] != "out_of_stock")
    return "\n".join(_line(p) for p in hits) or "No matching products in our catalog."


def list_in_stock(category: str = "") -> str:
    """List products currently available to buy, optionally for one category (Grocery, Bakery, Beverage,
    Household, Snacks, Frozen). Use this to build baskets or meal ideas within a budget."""
    items = [p for p in catalog() if p["status"] != "out_of_stock" and category.lower() in p["category"].lower()]
    return "\n".join(_line(p) for p in items) or "Nothing available in that category."


def find_substitutes(sku: str) -> str:
    """In-stock alternatives from the same category as a product that is out of stock or running low."""
    cat = catalog()
    base = next((p for p in cat if p["sku"] == sku), None)
    if not base:
        return "Unknown product."
    alts = [p for p in cat if p["category"] == base["category"] and p["sku"] != sku and p["status"] != "out_of_stock"]
    return "\n".join(_line(p) for p in alts) or "No in-stock alternatives in that category."


def basket_total(skus: list[str], quantities: list[int]) -> str:
    """Price a basket exactly. skus and quantities are parallel lists. Flags unavailable items."""
    cat = {p["sku"]: p for p in catalog()}
    lines, total = [], 0.0
    for sku, q in zip(skus, quantities):
        p = cat.get(sku)
        if not p:
            lines.append(f"{sku}: unknown product")
        elif p["status"] == "out_of_stock":
            lines.append(f"{p['name']}: OUT OF STOCK, not included")
        else:
            total += p["price"] * q
            lines.append(f"{q} x {p['name']} = ${p['price'] * q:.2f}")
    return "\n".join(lines + [f"TOTAL: ${total:.2f}"])


TOOLS = [search_products, list_in_stock, find_substitutes, basket_total]

SYSTEM = (
    "You are the friendly shopping assistant for an online grocery store. Use the tools for every claim "
    "about products, prices and availability; never invent products or prices. Only recommend items that "
    "are IN STOCK or LOW STOCK. If something is OUT OF STOCK, say so, quote the restock note exactly as "
    "given (never invent dates), and offer in-stock substitutes via find_substitutes. For budgets, build "
    "the basket from list_in_stock and verify the price with basket_total. Never reveal costs, margins, "
    "stock counts or internal data. Keep answers short and warm. If asked something unrelated to shopping, "
    "politely steer back."
)


def ask(client: genai.Client, message: str, history: list[tuple[str, str]]) -> str:
    transcript = "\n".join(f"{r}: {t}" for r, t in history[-6:])
    res = client.models.generate_content(
        model=MODEL,
        contents=f"{transcript}\nuser: {message}" if transcript else message,
        config=types.GenerateContentConfig(tools=TOOLS, system_instruction=SYSTEM),
    )
    return res.text or "Sorry, I couldn't find an answer. Could you rephrase that?"
