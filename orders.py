"""Purchase-order store. SQLite locally; Firestore when USE_FIRESTORE=true (survives Cloud Run restarts)."""
import os

import pandas as pd

import data

COLS = ["id", "sku", "qty", "reason", "status", "created"]


def use_firestore() -> bool:
    return os.getenv("USE_FIRESTORE", "").lower() == "true"


def _col():
    from google.cloud import firestore

    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT")).collection("purchase_orders")


def _local():
    c = data.conn()
    c.execute("""CREATE TABLE IF NOT EXISTS purchase_orders (
        id INTEGER PRIMARY KEY, sku TEXT, qty INTEGER, reason TEXT,
        status TEXT DEFAULT 'pending', created TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return c


def create(sku: str, qty: int, reason: str) -> str:
    if use_firestore():
        from google.cloud import firestore

        ref = _col().document()
        ref.set({"sku": sku, "qty": int(qty), "reason": reason, "status": "pending",
                 "created": firestore.SERVER_TIMESTAMP})
        return ref.id
    with _local() as c:
        return str(c.execute("INSERT INTO purchase_orders (sku, qty, reason) VALUES (?,?,?)",
                             (sku, int(qty), reason)).lastrowid)


def list_all() -> pd.DataFrame:
    if use_firestore():
        rows = [{"id": d.id, **{k: v for k, v in d.to_dict().items()}} for d in _col().stream()]
        df = pd.DataFrame(rows, columns=COLS)
        df["created"] = df["created"].astype(str)
        return df.sort_values("created", ascending=False).reset_index(drop=True)
    with _local() as c:
        df = pd.read_sql("SELECT id, sku, qty, reason, status, created FROM purchase_orders ORDER BY id DESC", c)
    df["id"] = df["id"].astype(str)
    return df


def set_status(order_id: str, status: str) -> None:
    if use_firestore():
        _col().document(order_id).update({"status": status})
        return
    with _local() as c:
        c.execute("UPDATE purchase_orders SET status=? WHERE id=?", (status, int(order_id)))


def incoming() -> dict[str, int]:
    """Units already on order (pending or approved), so we don't recommend duplicates."""
    df = list_all()
    df = df[df["status"].isin(["pending", "approved"])]
    return df.groupby("sku")["qty"].sum().astype(int).to_dict()


def list_detailed() -> pd.DataFrame:
    """Orders joined with product name and cost."""
    df = list_all()
    prods = data.load("products")[["sku", "name", "unit_cost"]].rename(columns={"name": "product"})
    df = df.merge(prods, on="sku", how="left")
    df["total"] = (df["qty"].astype(float) * df["unit_cost"]).round(2)
    return df[["id", "sku", "product", "qty", "unit_cost", "total", "reason", "status", "created"]]


def set_status_many(order_ids: list[str], status: str) -> None:
    for i in order_ids:
        set_status(i, status)


def delete_all() -> int:
    if use_firestore():
        n = 0
        for d in _col().stream():
            d.reference.delete()
            n += 1
        return n
    with _local() as c:
        return c.execute("DELETE FROM purchase_orders").rowcount
