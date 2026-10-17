"""Live Gemini smoke test. Needs GEMINI_API_KEY (or Vertex env vars). Run: python smoke_test.py"""
import data
import orders
from google import genai

import agents

data.ensure()
client = genai.Client()
before = len(orders.list_all())

CASES = [
    ("Which products are at the highest risk of stocking out?", ("SKU-",)),
    ("What happens if demand rises 20%? Compare with the baseline.", ("20%", "SKU-")),
    ("Why is demand unusual this week?", ("ice cream", "sparkling", "surge")),
    ("Create a purchase order for the single riskiest item.", ("pending",)),
    ("Which category had the highest revenue in the last 30 days?", ("Grocery", "Beverage", "Snacks",
                                                                    "Bakery", "Household", "Frozen")),
]
import customer
for q, expect in [("Do you have sparkling water?", ("out of stock", "restock")),
                  ("What can I get for a barbecue under $20?", ("$",))]:
    a = customer.ask(client, q, [])
    ok = any(e in a.lower() for e in expect)
    print(f"[{'PASS' if ok else 'FAIL'}] customer: {q}\n    {a[:200]!r}\n")
failed = 0
for q, expect in CASES:
    try:
        a = agents.ask(client, q, [])
        ok = any(e.lower() in a.lower() for e in expect)
    except Exception as e:
        a, ok = f"EXCEPTION {type(e).__name__}: {e}", False
    failed += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {q}\n    {a[:300]!r}\n")

assert len(orders.list_all()) > before, "agent should have created a pending PO"
print("explain():", agents.explain(client, {"sku": "SKU-001", "risk": "REORDER"}, 1.0)[:200])
print(f"{len(CASES) - failed}/{len(CASES)} passed")
