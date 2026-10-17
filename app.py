import pandas as pd
import streamlit as st
from google import genai

import agents
import anomaly
import bq
import data
import forecast
import interest
import orders
import customer_ui
import simulate

st.set_page_config(page_title="StockSense", page_icon="📦", layout="wide")
data.ensure()

RISK_ICON = {"STOCKOUT": "🔴 STOCKOUT", "REORDER": "🟠 REORDER", "OVERSTOCK": "🟡 OVERSTOCK", "OK": "🟢 OK"}
STATUS_ICON = {"pending": "🕓 pending", "approved": "✅ approved", "rejected": "❌ rejected"}
SUGGESTIONS = ["Which products will stock out first?", "What happens if demand rises 20%?",
               "Why is demand unusual this week?", "What are customers asking for that we don't have?",
               "Order what we need for the riskiest items."]


@st.cache_resource
def client():
    return genai.Client()  # GEMINI_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI=true


@st.cache_data(show_spinner="Replaying the last 60 days under both policies...")
def backtest():
    return simulate.run(60)


# Customer link: <app-url>/?view=customer shows only the storefront (no manager data in the UI).
shop_only = st.query_params.get("view") in ("customer", "shop")  # "shop" kept for old links
view = "Customer" if shop_only else st.sidebar.radio("View", ["Manager", "Customer"], horizontal=True)
if view == "Customer":
    customer_ui.render(client)
    st.stop()

st.title("📦 StockSense")
st.caption("Demand forecasting and inventory copilot: forecast, decide, order, with a human approving every purchase.")

# ---- sidebar ---------------------------------------------------------------------
mult = st.sidebar.slider("What-if demand multiplier", 0.5, 2.0, 1.0, 0.05,
                         help="1.2 means demand rises 20% (e.g. a heatwave or promotion).")
if mult != 1.0:
    st.sidebar.info(f"Scenario active: demand x{mult:.2f}")
if bq.enabled() and st.sidebar.button("Train BigQuery ML model"):
    with st.spinner("Loading data and training ARIMA_PLUS in BigQuery..."):
        bq.load_and_train()
    st.sidebar.success("Model trained.")
if st.sidebar.button("Regenerate sample data"):
    data.generate(seed=int(pd.Timestamp.now().timestamp()) % 1000)
    backtest.clear()
    st.rerun()

plan = forecast.plan(mult)
st.sidebar.divider()
st.sidebar.caption(f"Forecast engine: {forecast.engine['name']}")
st.sidebar.caption(f"Orders store: {'Firestore' if orders.use_firestore() else 'SQLite (local)'}")
if forecast.engine["error"]:
    st.sidebar.warning(f"BigQuery error: {forecast.engine['error'][:200]}")

# ---- KPI row ---------------------------------------------------------------------
pos_all = orders.list_detailed()
pending_value = pos_all.loc[pos_all.status == "pending", "total"].sum()
k = st.columns(5)
k[0].metric("🔴 Stockout risk", int((plan.risk == "STOCKOUT").sum()))
k[1].metric("🟠 Need reorder", int((plan.risk == "REORDER").sum()))
k[2].metric("🟡 Overstocked", int((plan.risk == "OVERSTOCK").sum()))
k[3].metric("Recommended spend", f"${plan.order_cost.sum():,.0f}")
k[4].metric("Pending PO value", f"${pending_value:,.0f}")

tab_over, tab_po, tab_chat, tab_impact = st.tabs(["Overview", "Purchase orders", "Copilot", "Impact"])

# ---- overview --------------------------------------------------------------------
with tab_over:
    alerts = anomaly.alerts()
    if len(alerts):
        with st.container(border=True):
            st.markdown("**⚠️ Unusual demand (last 7 days vs prior 8 weeks)**")
            for r in alerts.itertuples():
                icon = "📈" if r.kind == "surge" else "📉"
                st.write(f"{icon} **{r.product}** ({r.sku}): {r.change_pct:+d}%, "
                         f"{r.recent_daily} units/day vs {r.baseline_daily} normally")

    demand = interest.summary()
    if len(demand):
        with st.container(border=True):
            st.markdown("**🛍️ Customer interest (last 24h, from the customer assistant)**")
            for r in demand.head(5).itertuples():
                miss = f", **{r.unavailable_asks} while out of stock**" if r.unavailable_asks else ""
                st.write(f"{r.product} ({r.sku}): {r.asks} asks{miss}")

    f1, f2 = st.columns([2, 1])
    risks = f1.multiselect("Filter by risk", list(RISK_ICON), default=list(RISK_ICON),
                           format_func=lambda r: RISK_ICON[r])
    cats = f2.multiselect("Category", sorted(plan.category.unique()), default=sorted(plan.category.unique()))
    view = plan[plan.risk.isin(risks) & plan.category.isin(cats)].copy()
    view["risk"] = view.risk.map(RISK_ICON)
    st.dataframe(
        view[["risk", "sku", "name", "category", "on_hand", "on_order", "daily_demand", "days_cover",
              "lead_time", "reorder_qty", "order_cost"]],
        hide_index=True, width="stretch",
        column_config={
            "risk": "Risk", "sku": "SKU", "name": "Product", "category": "Category",
            "on_hand": "On hand", "on_order": "On order", "daily_demand": "Demand/day",
            "days_cover": st.column_config.ProgressColumn("Days of cover", min_value=0, max_value=60, format="%.1f d"),
            "lead_time": st.column_config.NumberColumn("Lead time", format="%d d"),
            "reorder_qty": "Reorder qty",
            "order_cost": st.column_config.NumberColumn("Order cost", format="$%.2f"),
        },
    )

    left, right = st.columns([2, 1])
    with left:
        sku = st.selectbox("Product detail", plan.sku, format_func=lambda s: f"{plan.set_index('sku').loc[s, 'name']} ({s})")
        sales = data.load("sales")
        hist = sales[sales.sku == sku].assign(date=lambda d: pd.to_datetime(d.date)).set_index("date")["units"].tail(60)
        fc = forecast.sku_forecast(sku, sales[sales.sku == sku], 14, mult).set_index("date")["forecast"]
        st.line_chart(pd.concat([hist.rename("Actual units"), fc.rename("Forecast")], axis=1))
        if st.button("Explain this recommendation"):
            try:
                with st.spinner("Thinking..."):
                    st.write(agents.explain(client(), plan[plan.sku == sku].iloc[0].to_dict(), mult))
            except Exception as e:
                st.error(f"Gemini unavailable: {e}")
    with right:
        st.markdown("**Recommended spend by category**")
        spend = plan.groupby("category").order_cost.sum()
        if spend.sum() > 0:
            st.bar_chart(spend)
        else:
            st.caption("Nothing to order right now.")

# ---- purchase orders -------------------------------------------------------------
with tab_po:
    st.subheader("Recommended orders")
    todo = plan[plan.reorder_qty > 0]
    st.dataframe(todo[["risk", "sku", "name", "reorder_qty", "order_cost"]].assign(risk=lambda d: d.risk.map(RISK_ICON)),
                 hide_index=True, width="stretch",
                 column_config={"risk": "Risk", "sku": "SKU", "name": "Product", "reorder_qty": "Qty",
                                "order_cost": st.column_config.NumberColumn("Cost", format="$%.2f")})
    if st.button("Create pending POs for all recommendations", disabled=todo.empty, type="primary"):
        for r in todo.itertuples():
            orders.create(r.sku, r.reorder_qty, f"{r.risk}: {r.days_cover}d cover, lead {r.lead_time}d")
        st.rerun()

    st.subheader("Purchase orders")
    pos = orders.list_detailed()
    if pos.empty:
        st.info("No purchase orders yet.")
    else:
        shown = pos.assign(status=pos.status.map(STATUS_ICON))
        st.dataframe(shown, hide_index=True, width="stretch",
                     column_config={"id": "PO", "sku": "SKU", "product": "Product", "qty": "Qty",
                                    "unit_cost": st.column_config.NumberColumn("Unit cost", format="$%.2f"),
                                    "total": st.column_config.NumberColumn("Total", format="$%.2f"),
                                    "reason": "Reason", "status": "Status", "created": "Created"})
        st.download_button("Download CSV", pos.to_csv(index=False), "purchase_orders.csv", "text/csv")

        pending = pos[pos.status == "pending"]
        if not pending.empty:
            st.markdown("**Review**")
            label = {r.id: f"{r.product}: {r.qty} units (${r.total:,.2f})" for r in pending.itertuples()}
            pid = st.selectbox("Pending order", pending.id.tolist(), format_func=lambda i: label[i])
            a, b, c, d = st.columns(4)
            if a.button("✅ Approve"):
                orders.set_status(pid, "approved"); st.rerun()
            if b.button("❌ Reject"):
                orders.set_status(pid, "rejected"); st.rerun()
            if c.button(f"✅ Approve all ({len(pending)})"):
                orders.set_status_many(pending.id.tolist(), "approved"); st.rerun()
            if d.button("❌ Reject all"):
                orders.set_status_many(pending.id.tolist(), "rejected"); st.rerun()

        with st.expander("Danger zone"):
            confirm = st.checkbox("I understand this deletes every purchase order")
            if st.button("Delete all purchase orders", disabled=not confirm):
                st.success(f"Deleted {orders.delete_all()} orders.")
                st.rerun()
            if st.button("Clear customer interest log"):
                st.success(f"Cleared {interest.clear()} events.")
                st.rerun()

# ---- copilot ---------------------------------------------------------------------
with tab_chat:
    st.write("Ask about stock, demand, or have the copilot raise orders (they stay pending until you approve them).")
    hist = st.session_state.setdefault("chat", [])
    picked = None
    for col, s in zip(st.columns(len(SUGGESTIONS)), SUGGESTIONS):
        if col.button(s, key=f"sug-{s}", width="stretch"):
            picked = s
    for role, text in hist:
        st.chat_message(role).write(text)
    msg = st.chat_input("Ask StockSense") or picked
    if msg:
        st.chat_message("user").write(msg)
        try:
            with st.spinner("Analyzing..."):
                reply = agents.ask(client(), msg, hist)
        except Exception as e:
            reply = (f"The AI copilot is unavailable right now ({type(e).__name__}). "
                     "The Overview and Purchase orders tabs still work.")
        st.chat_message("assistant").write(reply)
        hist += [("user", msg), ("assistant", reply)]
    if hist and st.button("Clear conversation"):
        st.session_state.chat = []
        st.rerun()

# ---- impact ----------------------------------------------------------------------
with tab_impact:
    st.write("Replays the last 60 days with the same lead times, weekly reviews and starting stock. "
             "**Rolling average** orders up to the trailing 28-day average demand; **StockSense** uses "
             "day-of-week and growth forecasts plus safety stock.")
    summary, detail = backtest()
    ra, ss = summary.loc["Rolling average"], summary.loc["StockSense"]
    m1, m2, m3 = st.columns(3)
    m1.metric("Fill rate", f"{ss.fill_rate_pct:.1f}%", f"{ss.fill_rate_pct - ra.fill_rate_pct:+.1f} pts vs rolling avg")
    m2.metric("Lost revenue", f"${ss.lost_revenue:,.0f}", f"{ss.lost_revenue - ra.lost_revenue:+,.0f}", delta_color="inverse")
    m3.metric("Avg inventory value", f"${ss.avg_inventory_value:,.0f}",
              f"{ss.avg_inventory_value - ra.avg_inventory_value:+,.0f}", delta_color="inverse")
    st.dataframe(summary.rename(columns={"fill_rate_pct": "Fill rate %", "lost_units": "Lost units",
                                         "lost_revenue": "Lost revenue $", "avg_inventory_value": "Avg inventory $"}))
    worst = detail[detail.policy == "Rolling average"].nlargest(5, "lost_revenue")[["sku", "lost_revenue"]]
    names = data.load("products").set_index("sku").name
    st.markdown("**Where the rolling-average rule loses the most sales**")
    st.bar_chart(worst.assign(product=worst.sku.map(names)).set_index("product").lost_revenue)
    st.caption("Safety stock raises inventory; the trade-off is shown honestly. Results use synthetic data.")
