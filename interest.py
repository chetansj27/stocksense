"""Customer interest log: what customers ask about, and whether it was available.
SQLite locally; Firestore when USE_FIRESTORE=true."""
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

import data
import orders

COLS = ["ts", "sku", "query", "available"]
SUMMARY_COLS = ["sku", "product", "asks", "unavailable_asks"]


def _col():
    from google.cloud import firestore

    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT")).collection("shopper_events")


def _local():
    c = data.conn()
    c.execute("CREATE TABLE IF NOT EXISTS shopper_events (ts TEXT, sku TEXT, query TEXT, available INTEGER)")
    return c


def log(sku: str, query: str, available: bool) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    if orders.use_firestore():
        _col().add({"ts": ts, "sku": sku, "query": query[:200], "available": bool(available)})
        return
    with _local() as c:
        c.execute("INSERT INTO shopper_events VALUES (?,?,?,?)", (ts, sku, query[:200], int(available)))


def events() -> pd.DataFrame:
    if orders.use_firestore():
        return pd.DataFrame([d.to_dict() for d in _col().stream()], columns=COLS)
    with _local() as c:
        return pd.read_sql("SELECT ts, sku, query, available FROM shopper_events", c)


def summary(hours: int = 24) -> pd.DataFrame:
    df = events()
    if df.empty:
        return pd.DataFrame(columns=SUMMARY_COLS)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df[df["ts"] >= datetime.now(timezone.utc) - timedelta(hours=hours)]
    if df.empty:
        return pd.DataFrame(columns=SUMMARY_COLS)
    df["unavailable"] = ~df["available"].astype(bool)
    g = df.groupby("sku").agg(asks=("sku", "size"), unavailable_asks=("unavailable", "sum")).reset_index()
    names = data.load("products").set_index("sku")["name"]
    g["product"] = g["sku"].map(names)
    g["unavailable_asks"] = g["unavailable_asks"].astype(int)
    return g.sort_values(["unavailable_asks", "asks"], ascending=False)[SUMMARY_COLS].reset_index(drop=True)


def clear() -> int:
    if orders.use_firestore():
        n = 0
        for d in _col().stream():
            d.reference.delete()
            n += 1
        return n
    with _local() as c:
        return c.execute("DELETE FROM shopper_events").rowcount
