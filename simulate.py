"""Backtest: replay the last N days under two replenishment policies with the same lead times,
weekly reviews and starting stock, and compare service level and inventory.

- Rolling average: order up to the trailing 28-day average demand over (lead + review) days. No
  seasonality, no growth, no safety stock. A common spreadsheet-style rule.
- StockSense: day-of-week + growth forecast, plus safety stock for demand variability.
"""
import math

import pandas as pd

import data
import forecast

POLICIES = ("Rolling average", "StockSense")


def _targets(hist: pd.DataFrame, lead: int) -> tuple[float, float]:
    horizon = lead + forecast.REVIEW_DAYS
    rolling = hist["units"].tail(28).mean() * horizon
    fc = forecast.forecast_sku(hist, horizon)["forecast"].sum()
    safety = forecast.Z * (hist["units"].tail(56).std() or 0) * math.sqrt(horizon)
    return rolling, fc + safety


def run(days: int = 60) -> tuple[pd.DataFrame, pd.DataFrame]:
    sales, prods = data.load("sales"), data.load("products")
    rows = []
    for p in prods.itertuples():
        h = sales[sales["sku"] == p.sku].reset_index(drop=True)
        n, start, lead = len(h), len(h) - days, p.lead_time_days
        targets = {d: _targets(h.iloc[:d], lead) for d in range(start, n, forecast.REVIEW_DAYS)}
        init = h.iloc[start - 28 : start]["units"].mean() * (lead + forecast.REVIEW_DAYS)
        for k, policy in enumerate(POLICIES):
            stock, pipeline, sold, lost, inv_sum = init, [], 0, 0, 0.0
            for d in range(start, n):
                stock += sum(q for a, q in pipeline if a <= d)
                pipeline = [(a, q) for a, q in pipeline if a > d]
                if (d - start) % forecast.REVIEW_DAYS == 0:
                    position = stock + sum(q for _, q in pipeline)
                    q = max(0, math.ceil(targets[d][k] - position))
                    if q:
                        pipeline.append((d + lead, q))
                demand = int(h.loc[d, "units"])
                s = min(stock, demand)
                stock -= s
                sold += s
                lost += demand - s
                inv_sum += stock
            rows.append({"policy": policy, "sku": p.sku, "demand": sold + lost, "sold": sold,
                         "lost_units": lost, "lost_revenue": lost * p.unit_price,
                         "avg_inventory_value": inv_sum / days * p.unit_cost})
    detail = pd.DataFrame(rows)
    g = detail.groupby("policy").agg(demand=("demand", "sum"), sold=("sold", "sum"),
                                     lost_units=("lost_units", "sum"), lost_revenue=("lost_revenue", "sum"),
                                     avg_inventory_value=("avg_inventory_value", "sum"))
    g["fill_rate_pct"] = (100 * g["sold"] / g["demand"]).round(2)
    summary = g.loc[list(POLICIES), ["fill_rate_pct", "lost_units", "lost_revenue", "avg_inventory_value"]].round(0)
    summary["fill_rate_pct"] = g.loc[list(POLICIES), "fill_rate_pct"]
    return summary, detail
