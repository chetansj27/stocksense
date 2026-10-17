"""Data layer. SQLite locally; swap these functions for BigQuery clients in production."""
import os
import sqlite3

import numpy as np
import pandas as pd

DB = os.path.join(os.path.dirname(__file__), "stocksense.db")

# sku, name, category, unit_cost, lead_time_days, avg_daily_units
PRODUCTS = [
    ("SKU-001", "Oat Milk 1L", "Grocery", 1.2, 4, 40),
    ("SKU-002", "Organic Bananas 1kg", "Grocery", 0.9, 2, 55),
    ("SKU-003", "Sourdough Loaf", "Bakery", 1.5, 1, 30),
    ("SKU-004", "Cold Brew Coffee", "Beverage", 1.8, 6, 25),
    ("SKU-005", "Sparkling Water 6pk", "Beverage", 2.0, 5, 35),
    ("SKU-006", "Dish Soap 500ml", "Household", 1.1, 9, 18),
    ("SKU-007", "Paper Towels 4pk", "Household", 3.0, 10, 14),
    ("SKU-008", "Protein Bar Box", "Snacks", 7.5, 8, 9),
    ("SKU-009", "Dark Chocolate 100g", "Snacks", 1.4, 7, 28),
    ("SKU-010", "Frozen Pizza", "Frozen", 2.8, 5, 22),
    ("SKU-011", "Ice Cream 500ml", "Frozen", 3.2, 6, 16),
    ("SKU-012", "Free-range Eggs 12", "Grocery", 2.2, 3, 45),
]

# Starting days of cover per product, chosen for a mix of stockout / reorder / ok / overstock.
START_COVER_DAYS = [4, 7, 14, 9, 0, 14, 85, 18, 30, 5, 75, 22]

# Simulated heatwave: demand surge over the last 6 days (drives the demand-alert feature).
SURGES = {"SKU-005": 1.9, "SKU-011": 2.0}


def conn(readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    return sqlite3.connect(DB)


def generate(seed: int = 7, days: int = 180) -> None:
    rng = np.random.default_rng(seed)
    end = pd.Timestamp.today().normalize()
    dates = pd.date_range(end - pd.Timedelta(days=days - 1), end)
    dow = np.array([0.8, 0.8, 0.9, 1.0, 1.2, 1.5, 1.3])  # Mon..Sun
    sales, inv, prods = [], [], []
    for (sku, name, cat, cost, lead, base), cover in zip(PRODUCTS, START_COVER_DAYS):
        trend = np.linspace(1.0, rng.uniform(0.7, 1.6), days)
        promo = rng.random(days) < 0.05
        surge = np.ones(days)
        if sku in SURGES:
            surge[-6:] = SURGES[sku]
        lam = base * dow[dates.dayofweek] * trend * np.where(promo, 1.8, 1.0) * surge
        units = rng.poisson(lam)
        price = round(cost * 1.6, 2)
        sales.append(pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "sku": sku, "units": units,
                                   "revenue": np.round(units * price, 2), "promo": promo.astype(int)}))
        inv.append({"sku": sku, "on_hand": int(base * cover)})
        prods.append({"sku": sku, "name": name, "category": cat, "unit_cost": cost,
                      "unit_price": price, "lead_time_days": lead})
    with conn() as c:
        pd.concat(sales).to_sql("sales", c, if_exists="replace", index=False)
        pd.DataFrame(inv).to_sql("inventory", c, if_exists="replace", index=False)
        pd.DataFrame(prods).to_sql("products", c, if_exists="replace", index=False)


def ensure() -> None:
    if not os.path.exists(DB):
        generate()


def load(table: str) -> pd.DataFrame:
    with conn(readonly=True) as c:
        return pd.read_sql(f"SELECT * FROM {table}", c)


if __name__ == "__main__":
    generate()
    print("generated", DB)
