import math

import numpy as np
import pandas as pd

import bq
import data
import orders

REVIEW_DAYS = 7
Z = 1.65  # ~95% service level
engine = {"name": "local statistical", "error": None}


def forecast_sku(sales: pd.DataFrame, horizon: int = 14, multiplier: float = 1.0) -> pd.DataFrame:
    """Day-of-week profile from the last 8 weeks, scaled by recent growth and a what-if multiplier."""
    s = sales.assign(date=pd.to_datetime(sales["date"])).set_index("date")["units"].asfreq("D", fill_value=0)
    recent = s[-56:]
    dow = recent.groupby(recent.index.dayofweek).mean()
    prev, last = s[-56:-28].mean(), s[-28:].mean()
    growth = float(np.clip(last / prev, 0.7, 1.4)) if prev > 0 else 1.0
    days = pd.date_range(s.index[-1] + pd.Timedelta(days=1), periods=horizon)
    vals = [dow[d.dayofweek] * growth ** ((i + 1) / 28) * multiplier for i, d in enumerate(days)]
    return pd.DataFrame({"date": days, "forecast": vals})


def sku_forecast(sku: str, hist: pd.DataFrame, horizon: int, multiplier: float) -> pd.DataFrame:
    """BigQuery ARIMA_PLUS when configured, otherwise (or on failure) the local model."""
    if bq.enabled():
        try:
            fc = bq.forecasts()[sku].copy()
            fc["date"] = pd.to_datetime(fc["date"])
            fc["forecast"] = fc["forecast"] * multiplier
            engine.update(name="BigQuery ML ARIMA_PLUS", error=None)
            return fc.head(horizon)
        except Exception as e:  # keep the demo alive; surface the reason in the UI
            engine.update(name="local statistical (BigQuery failed)", error=str(e))
    return forecast_sku(hist, horizon, multiplier)


def plan(multiplier: float = 1.0) -> pd.DataFrame:
    """Per-product risk and reorder recommendation."""
    sales, inv, prods = data.load("sales"), data.load("inventory"), data.load("products")
    on_order = orders.incoming()
    out = []
    for p in prods.itertuples():
        hist = sales[sales["sku"] == p.sku]
        fc = sku_forecast(p.sku, hist, 14, multiplier)
        daily = float(fc["forecast"].mean())
        std = float(hist["units"].tail(56).std() or 0) * multiplier
        on_hand = int(inv.loc[inv["sku"] == p.sku, "on_hand"].iloc[0])
        incoming = int(on_order.get(p.sku, 0))
        cover = on_hand / daily if daily else 999.0
        horizon = p.lead_time_days + REVIEW_DAYS
        target = daily * horizon + Z * std * math.sqrt(horizon)
        qty = max(0, math.ceil(target - on_hand - incoming))
        if cover < p.lead_time_days and incoming == 0:
            risk = "STOCKOUT"
        elif qty > 0:
            risk = "REORDER"
        elif cover > 60:
            risk = "OVERSTOCK"
        else:
            risk = "OK"
        out.append({"sku": p.sku, "name": p.name, "category": p.category, "on_hand": on_hand, "on_order": incoming,
                    "daily_demand": round(daily, 1), "days_cover": round(cover, 1),
                    "lead_time": p.lead_time_days, "risk": risk, "reorder_qty": qty,
                    "order_cost": round(qty * p.unit_cost, 2)})
    order = {"STOCKOUT": 0, "REORDER": 1, "OVERSTOCK": 2, "OK": 3}
    return pd.DataFrame(out).sort_values("risk", key=lambda c: c.map(order)).reset_index(drop=True)
