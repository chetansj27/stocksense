"""Demand surge / drop detection: last 7 days versus the prior 8 weeks."""
import pandas as pd

import data

SURGE, DROP = 1.3, 0.7
COLS = ["sku", "product", "kind", "change_pct", "recent_daily", "baseline_daily"]


def alerts(window: int = 7) -> pd.DataFrame:
    sales, prods = data.load("sales"), data.load("products").set_index("sku")
    out = []
    for sku, g in sales.groupby("sku"):
        u = g.sort_values("date")["units"].reset_index(drop=True)
        recent, base = u.tail(window).mean(), u.iloc[-(window + 56) : -window].mean()
        if base <= 0:
            continue
        ratio = recent / base
        if ratio >= SURGE or ratio <= DROP:
            out.append({"sku": sku, "product": prods.loc[sku, "name"], "kind": "surge" if ratio >= SURGE else "drop",
                        "change_pct": round((ratio - 1) * 100), "recent_daily": round(recent, 1),
                        "baseline_daily": round(base, 1)})
    df = pd.DataFrame(out, columns=COLS)
    return df.reindex(df["change_pct"].abs().sort_values(ascending=False).index).reset_index(drop=True)
